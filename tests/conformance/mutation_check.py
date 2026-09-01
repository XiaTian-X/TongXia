#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异检查:逐个拆掉 pair.py 里的防护,确认对应一致性测试会失败。

一个恒真的测试集比没有测试更危险 —— 它会让人以为强制力还在,
而实际上执行层可能已经什么都不拦了。

    python3 tests/conformance/mutation_check.py

每次改动 pair.py 的强制逻辑后都应该跑一遍。新增防护时,
在 MUTATIONS 里补上对应的变异点。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
     '    if state.get("after_dispute") and phase == "spec" and verdict is None:',
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
     "    expect = (None if (is_dispute or after_dispute_fix)",
     "    expect = (flow[\"expect\"].get(phase) if (is_dispute or after_dispute_fix)"),

    ("拆掉异议后 spec 回合的豁免",
     '    after_dispute_fix = state.get("after_dispute") and phase == "spec"',
     "    after_dispute_fix = False"),

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

FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (\S+)", re.M)


def run_suite(root):
    # 告诉一致性测试:现在跑的是被故意改坏的 pair.py。变异点匹配检查在这种
    # 情况下必然失败,会让每个变异都显得"被抓到",掩盖真正存活的变异。
    env = dict(os.environ, PAIR_MUTATION_RUN="1")
    proc = subprocess.run(
        ["python3", "-m", "unittest", "discover",
         "-s", "tests/conformance", "-t", "tests/conformance"],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    return proc.returncode, sorted(set(FAIL_RE.findall(text)))


def main():
    print("=== 基线(未变异)===")
    rc, fails = run_suite(REPO)
    if rc != 0:
        print("基线就没全绿,先修好再做变异测试:\n%s" % "\n".join(fails))
        return 1
    print("基线全绿\n")

    survivors = []
    for name, old, new in MUTATIONS:
        tmp = Path(tempfile.mkdtemp(prefix="mutate-"))
        dst = tmp / "repo"
        shutil.copytree(REPO, dst, symlinks=True,
                        ignore=shutil.ignore_patterns(".git"))
        p = dst / PAIR_REL
        src = p.read_text(encoding="utf-8")
        if old not in src:
            print("!! %-24s 变异点没匹配到,变异脚本需要更新" % name)
            survivors.append(name)
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        p.write_text(src.replace(old, new, 1), encoding="utf-8")

        rc, fails = run_suite(dst)
        if rc == 0:
            print("!! %-24s 存活 —— 没有任何测试发现防护消失了" % name)
            survivors.append(name)
        else:
            print("OK %-24s 被 %d 个测试抓到: %s"
                  % (name, len(fails), ", ".join(f.split(".")[-1] for f in fails[:3])
                     + (" …" if len(fails) > 3 else "")))
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if survivors:
        print("存活的变异(说明这些防护没有被测试覆盖):")
        for s in survivors:
            print("  - %s" % s)
        return 1
    print("全部 %d 个变异都被测试抓到。测试集确实有拦截力。" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
