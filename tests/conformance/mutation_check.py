#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异检查:逐个拆掉 pair.py 里的防护,确认对应一致性测试会失败。

一个恒真的测试集比没有测试更危险 —— 它会让人以为强制力还在,
而实际上执行层可能已经什么都不拦了。

    python3 tests/conformance/mutation_check.py            # 并行 + 走缓存
    python3 tests/conformance/mutation_check.py --full     # 每个变异都跑全量
    python3 tests/conformance/mutation_check.py --only 死锁 # 只跑名字含"死锁"的

每次改动 pair.py 的强制逻辑后都应该跑一遍。新增防护时,
在 MUTATIONS 里补上对应的变异点。

## 为什么不用每次都跑全套

一个变异只要**有任何一个测试**抓到它就算过关。所以第一次跑全量之后,
把"谁抓到了它"记进 mutation-cache.json,之后先只跑那几个 —— 抓到就直接过。

这不会放松判定:子集没抓到时会**回退跑全量**再下结论。缓存只影响快慢,
不影响结论,而且缓存失效(测试改名、防护挪位)会自动走回退路径重建。

快路径成立的前提是**基线全绿**,所以缓存里还存着一份基线指纹;`--no-baseline`
只在指纹对得上时才敢用快路径,否则自动退回全量。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAIR_REL = ".agents/skills/pair-protocol/scripts/pair.py"

MUTATIONS = [
    ("拆掉状态篡改检测",
     "    return any(p == STATE_REL for _, p in changed_entries(root))",
     "    return False"),

    ("拆掉回合归属检查",
     '    if me != owner:\n        die("现在是 %s 的 %s 回合',
     '    if False:\n        die("现在是 %s 的 %s 回合'),

    ("拆掉评审只读",
     '    if phase in REVIEW_PHASES or phase == "idle":\n        return shared',
     "    if False:\n        return shared"),

    ("拆掉写权限边界",
     "    if violations:\n        lines =",
     "    if False:\n        lines ="),

    ("拆掉测试删除防护",
     "    if deleted and not args.allow_deletion:",
     "    if False:"),

    ("拆掉 spec 阶段红绿检查",
     '    if expect == "RED" and green:',
     "    if False:"),

    ("拆掉 impl 阶段红绿检查",
     '    if expect == "GREEN" and not green:',
     "    if False:"),

    ("拆掉评审理由强制",
     '        if not message:\n            die("裁决必须附理由。禁止空手通过。")',
     "        if False:\n            pass"),

    ("拆掉死锁闸",
     "        if changes_n >= DEADLOCK_LIMIT:",
     "        if False:"),

    ("拆掉 PLAN 全完成的终止检查",
     "    if plan_all_done(root, cfg):\n        die(",
     "    if False:\n        die("),

    # --- v1 新增防护 ---------------------------------------------------
    ("拆掉 cover 新增测试检查",
     '    if phase in flow["require_new_tests"]:',
     "    if False:"),

    ("拆掉 verify-setup 门禁",
     '    if cfg["require_setup_verification"] and not state["setup_verified"]:\n        die("尚未通过开工前校验',
     '    if False:\n        die("尚未通过开工前校验'),

    ("拆掉角色重叠检测",
     '    if both:\n        bad("以下文件同时属于两个角色',
     '    if False:\n        bad("以下文件同时属于两个角色'),

    ("拆掉 init 基线检查",
     "    if not run_tests(root, probe_cfg):",
     "    if False:"),

    ("拆掉 verify-setup 基线检查",
     "    elif not run_tests(root, cfg):",
     "    elif False:"),

    ("拆掉 glob 负模式",
     '        if pat.startswith("!"):\n            if path_matches(path, pat[1:]):',
     '        if pat.startswith("!"):\n            if False:'),

    ("拆掉 idle 阶段交接拦截",
     '    if phase == "idle":\n        die("还没有认领工作项',
     '    if False:\n        die("还没有认领工作项'),

    ("拆掉 ignore_paths",
     '        if path in PROTOCOL_LOGS or matches_any(path, cfg["ignore_paths"]):',
     "        if path in PROTOCOL_LOGS:"),

    ("拆掉协议日志的边界豁免",
     "        if path in PROTOCOL_LOGS or matches_any",
     "        if False or matches_any"),

    ("拆掉异议后必须改测试",
     '    if state.get("after_rebound") and phase == "spec" and verdict is None:',
     "    if False:"),

    ("拆掉契约小节重名检测",
     "        if name in out:\n            dupes.add(name)",
     "        if False:\n            dupes.add(name)"),

    ("拆掉 frontmatter 保位",
     "    c_fm, c_body = _split_frontmatter(content)",
     "    c_fm, c_body = \"\", content"),

    ("拆掉契约覆盖度检查",
     '                bad("工作项 \'%s\' 没有指向契约。在它下面加一行:\\n"',
     '                pass  # bad("工作项 \'%s\' 没有指向契约。在它下面加一行:\\n"'),

    # --- 评审反馈轮新增的防护 -------------------------------------------
    ("拆掉异议必须写下来",
     "        if not written:",
     "        if False:"),

    ("拆掉异议的红绿豁免",
     "    if is_dispute or (after_rebound and expect == \"RED\"):",
     "    if False:"),

    ("拆掉打回后 spec 回合的 RED 豁免",
     '    after_rebound = state.get("after_rebound") and phase == "spec"',
     "    after_rebound = False"),

    ("把 RED 豁免放宽成整个红绿豁免",
     '    if is_dispute or (after_rebound and expect == "RED"):\n        expect = None',
     "    if is_dispute or after_rebound:\n        expect = None"),

    ("只认 impl 阶段的异议,漏掉评审打回",
     '    state["after_rebound"] = (verdict == "changes")',
     '    state["after_rebound"] = bool(is_dispute)'),

    ("拆掉契约审查门禁",
     "    if len(text) < MIN_SETUP_REPORT_CHARS:",
     "    if False:"),

    ("拆掉 sync push 失败上报",
     '    push_failed = cfg.get("sync") and git("push", cwd=root, check=False) is None',
     '    push_failed = bool(cfg.get("sync")) and False'),

    ("拆掉 sync pull 失败上报",
     '        if git("pull", "--rebase", cwd=root, check=False) is None:',
     "        if False:"),

    # --- 记忆层 ---------------------------------------------------------
    ("拆掉决策追加式校验",
     "    if old and not _read(root / dfile).startswith(old):",
     "    if False:"),

    ("拆掉决策字段校验",
     "    for name in DECISION_FIELDS:\n        if not fields.get(name):",
     "    for name in ():\n        if not fields.get(name):"),

    ("拆掉决策长度上限",
     "    if size > MAX_DECISION_CHARS:",
     "    if False:"),

    ("拆掉解析不出条目的检查",
     "    if added and not fresh:",
     "    if False:"),

    ("拆掉 refactor 考古强制",
     '    if state["item_type"] == "refactor" and phase == "impl" and verdict is None:',
     "    if False:"),

    ("拆掉 cover 特征测试记录强制",
     '    if state["item_type"] == "cover" and phase == "spec" and verdict is None:',
     "    if False:"),

    ("拆掉 claim 时的契约小节存在性检查",
     "            if anchor_name not in sections:",
     "            if False:"),

    ("拆掉契约依据的可断言检查",
     "            if not ok:\n                return (\"拒绝认领 —— 契约小节「%s」的依据",
     "            if False:\n                return (\"拒绝认领 —— 契约小节「%s」的依据"),

    ("拆掉契约依据必填",
     '                bad("契约小节 \'%s\' 没写 `依据`。在小节里加一行:\\n"',
     '                pass  # bad("契约小节 \'%s\' 没写 `依据`。在小节里加一行:\\n"'),

    ("拆掉 refactor 保护测试强制",
     "        refs = PROTECT_REF_RE.findall(block)\n        if not refs:\n            return (",
     "        refs = PROTECT_REF_RE.findall(block)\n        if False:\n            return ("),

    ("拆掉 scope 边界",
     '        if cfg["scope"] and not matches_any(path, exempt_from_scope) \\',
     '        if False and not matches_any(path, exempt_from_scope) \\'),

    ("拆掉入口文件合并",
     '        how = merge_entry(root, rel, content)',
     '        how = None if (root / rel).exists() else merge_entry(root, rel, content)'),

    ("拆掉全量套件上报",
     "    return 2 if full_failed else 0",
     "    return 0"),

    ("拆掉第二次打回强制",
     '    if verdict == "changes" and state["changes_count"] + 1 == 2 and not mine:',
     "    if False:"),

    ("拆掉契约变更强制",
     '        if (state.get("contract_sha") and cur_sha\n'
     '                and cur_sha != state["contract_sha"] and not mine):',
     "        if False:"),

    ("拆掉完成时的晋升 gate",
     "        if len(note) >= MIN_NOTE_PROMOTE_CHARS and not mine and not args.no_decision:",
     "        if False:"),

    ("拆掉 status 记忆召回",
     "    mem = memory_brief(root, cfg, state, phase)",
     '    mem = ""'),

    ("拆掉 inbox 散文内容",
     "    for rel in changed:\n        text = _read(root / rel).strip()",
     "    for rel in []:\n        text = _read(root / rel).strip()"),

    ("拆掉记忆层与共享路径的隔离",
     '                   if "D" not in xy and matches_any(p, cfg["shared_paths"])]',
     '                   if "D" not in xy and matches_any(p, writable_paths(cfg, phase))]'),

    ("拆掉记忆层落在角色路径下的检查",
     '            for r in ROLES:\n                if matches_any(target, cfg["roles"][r]):',
     '            for r in ():\n                if matches_any(target, cfg["roles"][r]):'),

    ("拆掉记忆层落在冻结路径下的检查",
     '            if hit:\n                bad("%s(%s)落在冻结路径 %s 之下',
     '            if False:\n                bad("%s(%s)落在冻结路径 %s 之下'),

    ("拆掉记忆层落在共享路径下的检查",
     '        if matches_any(cfg["notes_dir"], cfg["shared_paths"]) or \\',
     '        if False and matches_any(cfg["notes_dir"], cfg["shared_paths"]) or \\'),

    # --- 评审证据 -------------------------------------------------------
    ("拆掉 approve 检查清单强制",
     "        if missing:\n            return (\"拒绝交接 —— approve 必须交出检查清单",
     "        if False:\n            return (\"拒绝交接 —— approve 必须交出检查清单"),

    ("拆掉 changes 位置引用强制",
     "    if not refs:\n        return (\"拒绝交接 —— 打回必须具体到位置",
     "    if False:\n        return (\"拒绝交接 —— 打回必须具体到位置"),

    ("拆掉引用路径真实性检查",
     "    if not real:\n        return (\"拒绝交接 —— 你引用的位置指向不存在的文件",
     "    if False:\n        return (\"拒绝交接 —— 你引用的位置指向不存在的文件"),

    ("拆掉评审证据门禁本身",
     "    refusal = check_review_evidence(root, cfg, phase, verdict, entries, message, args)",
     "    refusal = None"),

    ("拆掉 verify-setup 的提交范围",
     '    to_add = [STATE_REL, SETUP_REPORT_REL] + [',
     '    to_add = ["-A"] + [] + ['),

    ("拆掉死锁留痕",
     '            hit = "%s x%d" % (item or "?", changes_n)',
     '            hit = None; state["deadlock_hits"] = []; hit = ""'),
]

# unittest 的失败行有两种形态:
#   3.10-  FAIL: test_x (module.Class)
#   3.11+  FAIL: test_x (module.Class.test_x)
# 只抓方法名是不够的 —— 缓存要能被 `python -m unittest <id>` 重新认出来,
# 必须存完整的 module.Class.method。
FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M)


def _ids(text):
    out = set()
    for method, path in FAIL_RE.findall(text):
        out.add(path if path.endswith("." + method) else path + "." + method)
    return sorted(out)

# 变异点 -> 抓到它的测试 id。由全量运行产出,之后当快路径用。
CACHE_REL = "tests/conformance/mutation-cache.json"

# 每个变异点缓存**一个**抓手就够了,原因有两条:
#   1. 回退跑的是 failfast,遇到第一个失败就停,本来也只拿得到一个;
#   2. 更关键的是,`loaded` 要求"请求了几个就跑了几个" —— 只要缓存里有一个 id
#      失效,整组就判失效并回退。多存几个不但没有冗余作用,还会让失效更频繁。
# 想让缓存同时充当"每条防护由哪些测试守着"的资产,得先去掉回退路径的 failfast
# 并放宽 loaded,那是另一笔账,现在不做。
MAX_CACHED = 1

# 快路径("只跑缓存里那几个测试,失败就算抓到")成立的前提是**基线是绿的** ——
# 只有基线全绿,才能把"这些测试失败了"归因到变异上。
#
# 所以基线跑绿时把当时的指纹记进缓存;`--no-baseline` 只有在指纹对得上时才敢
# 走快路径。否则(比如你正改到一半、某个测试本来就红着)快路径会在 0.8 秒内
# 报"全部被抓到" —— 一个看着是绿的、其实什么都没验的检查,正是这个项目最怕的东西。
BASELINE_KEY = "baseline"
CATCHERS_KEY = "catchers"


def fingerprint(files=None):
    """能让基线由绿转红的东西:执行层 + 全部测试代码。"""
    h = hashlib.sha256()
    if files is None:
        files = ([REPO / PAIR_REL]
                 + sorted((REPO / "tests" / "conformance").glob("*.py")))
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def run_suite(root, ids=None, failfast=False):
    """跑一遍测试。ids 为 None 时跑全量,否则只跑这些测试 id。

    failfast 只给全量回退用。**绝不能给缓存快路径用** —— 快路径靠
    "请求了几个就跑了几个"判断缓存有没有失效,提前中断会让它误判成失效,
    然后每次都白白回退跑全量。

    告诉一致性测试:现在跑的是被故意改坏的 pair.py。变异点匹配检查在这种
    情况下必然失败,会让每个变异都显得"被抓到",掩盖真正存活的变异。
    """
    env = dict(os.environ, PAIR_MUTATION_RUN="1")
    if ids:
        cmd = [sys.executable, "-m", "unittest", "-q"] + list(ids)
        cwd = Path(root) / "tests" / "conformance"
    else:
        # 注意:discover 是子命令,-q/-f 只能跟在 discover **后面**,
        # 放前面会被主解析器吞掉然后报 unrecognized arguments。
        cmd = [sys.executable, "-m", "unittest", "discover"]
        if failfast:
            # 一个变异只要有任何一个测试抓到就算过关,没必要跑完剩下的 200 个。
            cmd.append("-f")
        cmd += ["-s", "tests/conformance", "-t", "tests/conformance"]
        cwd = Path(root)
    proc = subprocess.run(cmd, cwd=str(cwd), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    fails = _ids(text)

    # 缓存里的测试可能已经改名或被删。unittest 对认不出的 id 会报
    # _FailedTest 并非零退出 —— 那看起来和"抓到了变异"一模一样。
    # 不识别这一点,一份过期的缓存就能让每个变异都假装通过,
    # 而整套变异检查会变成恒真的。
    ran = re.search(r"^Ran (\d+) test", text, re.M)
    loaded = ("_FailedTest" not in text
              and not (ids and (not ran or int(ran.group(1)) != len(ids))))
    return proc.returncode, fails, loaded


def baseline_verified(no_baseline, cached_fp, current_fp):
    """快路径能不能用 —— 也就是"基线是绿的"这个前提还成不成立。

    跑过基线就是直接证据;`--no-baseline` 只能靠指纹间接证明"树没变过,
    所以上次那次绿仍然作数"。抽成纯函数是为了能被测住:它是这套缓存机制里
    唯一一处"判断错了就会让整个检查变成恒真"的地方。
    """
    if not no_baseline:
        return True
    return bool(cached_fp) and cached_fp == current_fp


def load_cache(path=None):
    """返回 (基线指纹, {变异点: [测试 id]})。文件不存在或损坏时当空缓存。"""
    p = Path(path) if path else REPO / CACHE_REL
    if not p.exists():
        return "", {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return "", {}
    if not isinstance(data, dict):
        return "", {}
    if CATCHERS_KEY in data:
        return data.get(BASELINE_KEY, ""), data.get(CATCHERS_KEY, {})
    # 旧的扁平格式:没有基线指纹,所以快路径一律不放行,直到跑过一次基线。
    return "", data


def save_cache(baseline, catchers):
    (REPO / CACHE_REL).write_text(
        json.dumps({BASELINE_KEY: baseline, CATCHERS_KEY: catchers},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def check_one(job):
    """在隔离副本里应用一个变异并判定它有没有被抓到。

    返回 (name, status, fails, note)。status: caught / survived / unmatched
    """
    name, old, new, cached = job
    tmp = Path(tempfile.mkdtemp(prefix="mutate-"))
    try:
        dst = tmp / "repo"
        shutil.copytree(REPO, dst, symlinks=True,
                        ignore=shutil.ignore_patterns(
                            ".git", "__pycache__", "*.pyc", ".DS_Store"))
        p = dst / PAIR_REL
        src = p.read_text(encoding="utf-8")
        if old not in src:
            return (name, "unmatched", [], "变异点没匹配到,变异脚本需要更新")
        p.write_text(src.replace(old, new, 1), encoding="utf-8")

        # 快路径:只跑上次抓到它的那几个测试。
        # 只有"这些测试确实都跑起来了、并且失败了"才算数。
        if cached:
            rc, fails, loaded = run_suite(dst, cached)
            if rc != 0 and loaded:
                return (name, "caught", fails, "缓存命中")

        # 回退:跑全量再下结论。用 failfast —— 找到一个抓手就够了。
        rc, fails, _ = run_suite(dst, failfast=True)
        if rc != 0:
            return (name, "caught", fails,
                    "缓存已失效,重建" if cached else "首次全量")
        return (name, "survived", [], "全量也没抓到")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mutation_check.py",
                                 description="逐个拆掉防护,确认测试抓得到")
    ap.add_argument("--full", action="store_true",
                    help="忽略缓存,每个变异都跑全量")
    ap.add_argument("--only", metavar="子串",
                    help="只跑名字包含该子串的变异点")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4,
                    help="并行进程数(默认=核数)")
    ap.add_argument("--slice", metavar="k/n",
                    help="只跑第 k 片(共 n 片),用于 CI 分片或分次建缓存")
    ap.add_argument("--no-baseline", action="store_true",
                    help="跳过基线检查(只在你刚跑过基线时用)")
    args = ap.parse_args(argv)

    muts = [m for m in MUTATIONS if not args.only or args.only in m[0]]
    if args.slice:
        try:
            k, n = (int(x) for x in args.slice.split("/"))
            assert 1 <= k <= n
        except (ValueError, AssertionError):
            ap.error("--slice 格式是 k/n,且 1 <= k <= n,例如 2/4")
        muts = muts[k - 1::n]
        print("[分片 %d/%d] 本片 %d 个变异点\n" % (k, n, len(muts)))
    if not muts:
        print("没有匹配 '%s' 的变异点。" % args.only)
        return 1

    fp = fingerprint()
    if args.no_baseline:
        # 没跑基线,就只能靠"上次跑绿时的指纹还对得上"来确认前提仍然成立。
        verified = baseline_verified(True, load_cache()[0], fp)
        print("(已跳过基线检查%s)\n"
              % ("" if verified else ";指纹与上次跑绿时不一致,快路径已停用"))
    else:
        if run_baseline(args.jobs) != 0:
            return 1
        verified = True
    return run_mutations(muts, args, fp, verified)


def run_baseline(jobs):
    print("=== 基线(未变异)===")
    t0 = time.time()
    # 基线走并行运行器 —— 它是每次调用都要付的固定成本,没必要串行等 30 秒。
    # 这里**不设** PAIR_MUTATION_RUN:基线跑的是未变异的代码,
    # "变异点仍能匹配到源码"那条检查正该在这里一次性拦住陈旧的 MUTATIONS。
    # 设了它,一个挪了位的变异点会变成后面 57 次"没匹配到"的噪音。
    env = dict(os.environ)
    env.pop("PAIR_MUTATION_RUN", None)
    base = subprocess.run(
        [sys.executable, str(REPO / "tests/conformance/run.py"),
         "-j", str(jobs)], cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if base.returncode != 0:
        print("基线就没全绿,先修好再做变异测试:\n%s"
              % base.stdout.decode("utf-8", "replace"))
        return 1
    print("基线全绿 (%.1fs)\n" % (time.time() - t0))
    save_cache(fingerprint(), load_cache()[1])
    return 0


def run_mutations(muts, args, fp, verified):
    cached_fp, cache = load_cache()
    # 快路径只在两个条件都成立时才用:基线这次跑绿了(或指纹证明它还是绿的),
    # 而且没有 --full。前者是"失败可以归因到变异"这条推理的全部依据。
    fast = verified and not args.full
    if not fast and cache:
        print("(不走缓存快路径:%s)\n"
              % ("--full" if args.full else "基线未经验证"))
    jobs = [(n, o, w, cache.get(n, []) if fast else []) for n, o, w in muts]

    t0 = time.time()
    results = []
    workers = max(1, min(args.jobs, len(jobs)))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(check_one, jobs):
            name, status, f, note = r
            results.append(r)
            if status == "caught":
                print("OK %-26s %-16s %d 个测试: %s"
                      % (name, note, len(f),
                         ", ".join(x.split(".")[-1] for x in f[:3])
                         + (" …" if len(f) > 3 else "")))
            elif status == "survived":
                print("!! %-26s 存活 —— 没有任何测试发现防护消失了" % name)
            else:
                print("!! %-26s %s" % (name, note))
            sys.stdout.flush()
    elapsed = time.time() - t0

    # 只有全量得来的结论才配写进缓存 —— 快路径命中说明缓存已经是对的。
    # 同样,只有基线经过验证的这一轮,结论才配被记下来当以后的快路径依据。
    fresh = dict(cache)
    for name, status, f, note in results:
        if status == "caught" and note != "缓存命中":
            fresh[name] = f[:MAX_CACHED]
    if verified and (fresh != cache or cached_fp != fp):
        save_cache(fp, fresh)

    bad = [r for r in results if r[1] != "caught"]
    print()
    print("%d 个变异 / %d 进程 / %.1fs" % (len(results), workers, elapsed))
    if bad:
        print("\n有问题的变异点:")
        for name, status, _, note in bad:
            print("  - %s(%s)" % (name, note))
        print("\n存活 = 这条防护没有被任何测试覆盖,补一个用例;"
              "\n没匹配到 = 源码挪位了,更新 MUTATIONS 里的字符串。")
        return 1
    print("全部被测试抓到。测试集确实有拦截力。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
