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

指纹闸只闸得住快路径。回退路径同样靠"未变异状态是绿的"才能把 rc≠0 归因到
变异上,所以 `--no-baseline` 会先在**未变异的隔离副本**里预检一遍全量套件:
副本环境本身就红的,拒绝做变异检查 —— 否则每一个变异都会被误判成"抓到"。
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

    # W13 起这两处不再看"本回合新追加的"(`mine`),改看"决策记录里存在 id 等于
    # 本工作项的条目"(`settled`)。锚点在 W13 的 spec 回合就改成了新字面 ——
    # dev 的 impl 回合改不了本文件,而 impl 结束必须 GREEN(契约「三节共同」)。
    ("拆掉契约变更强制",
     '        if (state.get("contract_sha") and cur_sha\n'
     '                and cur_sha != state["contract_sha"] and not settled):',
     "        if False:"),

    ("拆掉完成时的晋升 gate",
     "        if len(note) >= MIN_NOTE_PROMOTE_CHARS and not settled and not args.no_decision:",
     "        if False:"),

    # 锚在这一行而不是 `mem = ...` 整句:契约要求简报与终端**同一次取值**,
    # 所以这次取值被提到了 write_brief 之前、写成三元式。拆掉它,记忆召回
    # 对终端和简报**同时**失效 —— 抓手比原来还多。
    # 拿掉它,PLAN 全部完成那一次简报里有记忆段落、终端里没有 —— 同时违反
    # 契约的「逐字一致」与「同一次取值」。W2 的 review-test 打回换来的用例守它。
    ("拆掉简报的提前收尾守卫",
     '    mem = ("" if all_done or me != owner',
     '    mem = ("" if me != owner'),

    ("拆掉 status 记忆召回",
     "           else memory_brief(root, cfg, state, phase))",
     '           else "")'),

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

    # W12 要改写 `to_add = [STATE_REL, SETUP_REPORT_REL] + [` 那一行(报告路径
    # 按角色取),原锚点一改就失配 —— 而 dev 的 impl 回合改不了本文件,impl
    # 结束又必须 GREEN。改锚在下一行:它才是这条防护真正生效的地方(add 的
    # 范围),W12 不需要动它。名字不变,抓手仍是
    # test_不把工作区里的代码一并提交进基线。
    ("拆掉 verify-setup 的提交范围",
     '    git("add", "--", *sorted(set(to_add)), cwd=root)',
     '    git("add", "-A", cwd=root)'),

    # --- W12:开工前校验的产物与退出码(第五轮)----------------------------
    # 前七个是 dev 在 impl 回合点名、tester 在 review-impl 隔离副本里逐个复现
    # 过的(读并集那个是 tester 补的);第八个是 dev 在 review-test 用来打回的
    # 那个 —— 看整个索引,正是路线图开放条目 12 原文给的修法。
    ("结论不认角色文件",
     "    if (root / mine).exists():",
     "    if False:"),
    ("拆掉回落警告",
     "    if fallback_why and report.exists():",
     "    if False:"),
    ("回落改回解析不出就停",
     "    me, _ = try_resolve_role(root)",
     "    me, _ = resolve_role(root)"),
    ("索引判据换成工作区",
     "    if index_has_diff(root, sorted(set(to_add))):",
     "    if changed_entries(root):"),
    ("索引判据恒真",
     "    if index_has_diff(root, sorted(set(to_add))):",
     "    if True:"),
    ("索引判据看整个索引",
     '("git", "diff", "--cached", "--quiet", "--") + tuple(paths)',
     '("git", "diff", "--cached", "--quiet")'),
    ("拆掉两个新结论文件名的命名豁免",
     '"baseline.md",\n                      PurePosixPath(SETUP_REPORT_ROLE_FMT % "tester").name,\n                      PurePosixPath(SETUP_REPORT_ROLE_FMT % "dev").name)',
     '"baseline.md")'),
    ("结论读并集",
     '    text = report.read_text(encoding="utf-8").strip() if report.exists() else ""',
     '    text = "\\n".join(p.read_text(encoding="utf-8") for p in {report, root / SETUP_REPORT_REL} if p.exists()).strip()'),

    # --- 文档规范 -------------------------------------------------------
    ("拆掉评审文件命名检查",
     "    if not bad:\n        return None\n    return (\"拒绝交接 —— 评审目录里",
     "    if True:\n        return None\n    return (\"拒绝交接 —— 评审目录里"),

    ("拆掉固定名豁免",
     "        if name in REVIEW_FIXED_NAMES:",
     "        if False:"),

    ("拆掉子目录豁免",
     "    return any(parent == str(PurePosixPath(sp)) for sp in cfg[\"shared_paths\"])",
     "    return True"),

    ("拆掉点文件豁免",
     '    if not name.endswith(".md") or name.startswith("."):',
     '    if not name.endswith(".md"):'),

    ("拆掉异议文件必须存在",
     '        if name not in written:',
     "        if False:"),

    ("拆掉必含小节的正文长度下限",
     "        if len(body) < min_chars:",
     "        if False:"),

    ("拆掉考古 sha 校验",
     "    if not bad:\n        return None\n    return (\"拒绝交接 —— `考古观察",
     "    if True:\n        return None\n    return (\"拒绝交接 —— `考古观察"),

    ("拆掉契约审查结论的逐节点名",
     "    if unnamed:",
     "    if False:"),

    ("拆掉结论侧的围栏剥离",
     "    naked = _normalize(_blank_fenced_blocks(text))",
     "    naked = _normalize(text)"),

    ("拆掉起草人身份声明",
     "    if args.drafter is None:",
     "    if False:"),

    ("拆掉基线说明的提醒",
     '    if cfg.get("full_test_cmd") and not (root / BASELINE_REL).exists():',
     "    if False:"),

    ("拆掉死锁留痕",
     '            hit = "%s x%d" % (item or "?", changes_n)',
     '            hit = None; state["deadlock_hits"] = []; hit = ""'),

    # --- W7 补:W3 与 W4 的五条防护,落地一轮多都没有变异点 -----------------
    ("拆掉简报写失败的降级",
     "        except OSError as exc:",
     "        except UnicodeDecodeError as exc:"),

    ("拆掉简报进 gitignore",
     '                   ".pair/whoami", ".pair/turns/", BRIEF_REL,',
     '                   ".pair/whoami", ".pair/turns/",'),

    ("拆掉开工前的孤儿清单",
     "    orphans = [f for f in files if is_orphan(f, cfg)]",
     "    orphans = []"),

    ("拆掉 ignore_paths 的覆盖清单",
     '    ignored = [f for f in files if matches_any(f, cfg["ignore_paths"])]',
     "    ignored = []"),

    ("剩余数打成总数",
     '        lines.append("      … 还有 %d 个没列出" % (len(paths) - limit))',
     '        lines.append("      … 还有 %d 个没列出" % len(paths))'),

    ("拆掉越界文案里的孤儿分情况",
     "        orphaned = [p for p, _ in violations if is_orphan(p, cfg)]",
     "        orphaned = []"),

    # --- W7 补:W10 的四条。实现刚落地,锚点这时才有得可锚 -------------------
    ("拆掉裁判副本的逐字节比对",
     "    return copy is None or copy.read_bytes() == src.read_bytes()",
     "    return True"),

    ("裁判副本改成 strip 后比",
     "    return copy is None or copy.read_bytes() == src.read_bytes()",
     "    return copy is None or copy.read_bytes().strip() == src.read_bytes().strip()"),

    ("裁判正本改用 __file__",
     "    copy, src = root / JUDGE_REL, root / PROG_HINT",
     "    copy, src = root / JUDGE_REL, Path(__file__).resolve()"),

    ("拆掉重钉后 sha 的 strip",
     '    return (out or "").strip()',
     '    return (out or "")'),

    # --- W8:文档改动要带理由 / 路线图改写要有依据 -------------------------
    # 锚在 `touched_docs = …` 而不是它下面那个 `if`:那个 `if` 的条件正在被
    # 改(空白也要算不合格),而锚点一失配 `test_变异点仍能匹配到源码` 就红,
    # 那个文件 dev 改不了。这一行不会变。
    ("拆掉文档理由强制",
     "    touched_docs = normative_docs(cfg, entries)",
     "    touched_docs = []"),

    # 这一条**故意锚在还不存在的代码上**,它就是本回合的规格:
    # `--doc-reason` 要按仓库既有口径(pair.py 里 --checked/--uncovered 那一处)
    # 判空,即 `(args.doc_reason or "").strip()`。落地之前它是 unmatched,
    # 落地之后这条变异会被 test_理由只有空白不算数 打死。
    ("文档理由不 strip",
     '(args.doc_reason or "").strip()',
     "args.doc_reason"),

    ("规范性文档不算删除",
     '    for _, path in entries:\n        if not path.endswith(".md"):',
     '    for _xy, path in entries:\n        if "D" in _xy:\n            continue\n'
     '        if not path.endswith(".md"):'),

    ("拆掉路线图依据强制",
     "        if not basis_points_at_file(root, args.basis, entries):",
     "        if False:"),

    # --- W9:冻结文件改成带声明才放行 ---------------------------------------
    ("拆掉承重文件的冻结豁免",
     "        if path in named_frozen and args.contract_change:",
     "        if False:"),

    ("拆掉契约变更声明的真实性",
     "        if not basis_points_at_file(root, args.contract_change, entries):",
     "        if False:"),

    ("拆掉契约变更当场留决策",
     "        if not fresh:",
     "        if False:"),

    ("契约变更计数恒为 0",
     "            contract_changes += 1",
     "            pass"),

    # --- W13:「已沉淀」按工作项算 -------------------------------------------
    # 新代码的字面照抄紧挨着的 `mine = [e for e in fresh if e[0] == item]`,
    # 在 spec 回合定死(「三节共同」)。`settled` 必须紧接在 `mine` 那一行之后:
    # 下面「第二次打回改成按工作项算」要在打回检查里引用它。
    ("沉淀改回按回合算",
     "    settled = [e for e in parse_decisions(_read(root / dfile)) if e[0] == item]",
     "    settled = mine"),

    ("沉淀不认工作项 id",
     "    settled = [e for e in parse_decisions(_read(root / dfile)) if e[0] == item]",
     "    settled = parse_decisions(_read(root / dfile))"),

    # 契约:另外两处**一个字都不改**。这两个变异把它们也换成按工作项算。
    ("第二次打回改成按工作项算",
     '    if verdict == "changes" and state["changes_count"] + 1 == 2 and not mine:',
     '    if verdict == "changes" and state["changes_count"] + 1 == 2 and not settled:'),

    ("当场留决策改成按工作项算",
     "        fresh = [e for e in new_decision_entries(root, cfg) if e[0] == item]",
     '        fresh = [e for e in parse_decisions(_read(root / cfg["decisions_file"]))'
     " if e[0] == item]"),

    # --- W13:契约变了,之前的校验作废(claim 侧)------------------------------
    # 形状由 dev 定,dev 在 impl 笔记里点名、tester 在 review-impl 隔离复现过,
    # 在 W14 的 spec 回合登记(W13 本项里 tester 唯一能写 tests/ 的回合漏了,
    # 见 DECISIONS.md 的 `## W13 — claim 侧的 8 个变异点欠着`)。
    # W19 的 spec 回合重锚:claim 要看两个角色,那一段必然改写。新字面照原来那几行派生,
    # 在 spec 回合定死(「三节共同」),落地前这两个锚点不匹配。
    ("claim 不拦过期的校验",
     '            die("拒绝认领 —— " + "\\n\\n".join(stales))',
     "            pass"),

    ("校验比对端取 HEAD",
     "    now = worktree_sha(root, rel)",
     "    now = blob_sha(root, rel)"),

    ("校验记录端取 HEAD",
     '        rec[who] = worktree_sha(root, cfg["contract_file"])',
     '        rec[who] = blob_sha(root, cfg["contract_file"])'),

    ("校验记录变回全局单值",
     '    seen = (state.get("setup_verified_contract") or {}).get(role)',
     '    seen = next(iter((state.get("setup_verified_contract") or {}).values()), None)'),

    ("校验记录缺失时放行",
     "    if seen == now:",
     "    if seen is None or seen == now:"),

    ("契约读不到时放行",
     '    if now is None:\n        return ("读不到',
     '    if now is None:\n        return None\n        return ("读不到'),

    ("门禁没开也拦过期的校验",
     '    if cfg["require_setup_verification"]:\n'
     "        stales = [s for s in (stale_verification(root, cfg, state, r) for r in ROLES) if s]",
     "    if True:\n"
     "        stales = [s for s in (stale_verification(root, cfg, state, r) for r in ROLES) if s]"),

    ("claim 只看执行者自己那一份",
     "(stale_verification(root, cfg, state, r) for r in ROLES)",
     "(stale_verification(root, cfg, state, r) for r in (me,))"),

    ("校验通过后不记契约",
     '        state["setup_verified_contract"] = rec',
     "        pass"),

    # --- W14:声明只在生效时留痕,report 分开净回合 ---------------------------
    # 形状由 dev 定、dev 在 impl 笔记里点名、tester 在 review-impl 隔离复现。
    # 最后两个是 review-test 打回时两边都没想到的方向(只守了不生效那一侧),
    # 连同前 11 个一起在这个打回回合登记 —— 不必再欠到 W15。
    ("声明恒写-未留决策",
     "    if args.no_decision and no_decision_read:",
     "    if args.no_decision:"),

    ("晋升闸读旗标时不看已沉淀",
     "    return len(note) >= MIN_NOTE_PROMOTE_CHARS and not settled",
     "    return len(note) >= MIN_NOTE_PROMOTE_CHARS"),

    ("晋升闸读旗标时不看完成",
     '    if not memory_on(cfg) or target != "DONE":',
     "    if not memory_on(cfg):"),

    ("声明恒写-文档理由",
     "    if args.doc_reason and touched_docs:",
     "    if args.doc_reason:"),

    ("声明恒写-改写依据",
     "    if args.basis and ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):",
     "    if args.basis:"),

    ("依据从不写",
     "    if args.basis and ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):",
     "    if False:"),

    ("声明恒写-契约变更",
     "    if args.contract_change and changed_named_frozen:",
     "    if args.contract_change:"),

    ("声明恒写-删除测试",
     "    if args.allow_deletion and deleted:",
     "    if args.allow_deletion:"),

    ("判定行只在空转时写",
     '        body += "\\n%s: %s" % (IDLE_JUDGMENT, "是" if idle else "否")',
     '        body += ("\\n%s: 是" % IDLE_JUDGMENT) if idle else ""'),

    ("判定行不看阶段",
     '    if phase == "impl" and not is_dispute:',
     "    if not is_dispute:"),

    ("判定行不排除异议",
     '    if phase == "impl" and not is_dispute:',
     '    if phase == "impl":'),

    ("承重文件的交付算成空转",
     "                    or (args.contract_change and changed_named_frozen))",
     "                    or False)"),

    ("没有判定行的 impl 交接不单独计",
     "                unjudged += 1           # 没有判定行的 impl 交接不猜,单独计",
     "                pass"),

    # --- W15:verify-setup 的提交只带它自己 add 的那批路径 ----------------------
    # 契约允许 tester 在 spec 回合把 `git commit` 那一行"只带这批路径"写成锚点。
    # 只定**这一行**与变量名 `staged`;列路径的小函数由 dev 定(`index_has_diff`
    # 与它身上两个既有锚点不要动)。这两个锚点在 impl 落地前不匹配 —— 同第四轮
    # 「文档理由不 strip」的先例,`test_变异点仍能匹配到源码` 今天是红的。
    ("提交不限定路径",
     '            "-m", drafter_line, "--", *staged, cwd=root)',
     '            "-m", drafter_line, cwd=root)'),

    ("提交范围回到第一版的全部 to_add",
     '            "-m", drafter_line, "--", *staged, cwd=root)',
     '            "-m", drafter_line, "--", *sorted(set(to_add)), cwd=root)'),

    # 以下两个锚在 dev 写的 `staged_paths` 上,dev 在 impl 回合探出、tester 在
    # review-impl 复现,review-test 打回回 spec 时登记。`return [p for p in
    # out.split("\0") if p]` 在 pair.py 里单独出现两次,所以不带 -z 那个连同
    # 上一行 `git("diff", …)` 一起锚。"退回全部 to_add"与上面那条是同一个行为,不重复。
    ("提交路径不带 -z",
     '    out = git("diff", "--cached", "--name-only", "-z", "--", *paths, cwd=root)\n'
     '    return [p for p in out.split("\\0") if p]',
     '    out = git("diff", "--cached", "--name-only", "--", *paths, cwd=root)\n'
     '    return [p for p in out.split("\\n") if p]'),

    ("提交路径不看索引",
     '    out = git("diff", "--cached", "--name-only", "-z", "--", *paths, cwd=root)',
     '    out = git("diff", "--name-only", "-z", "--", *paths, cwd=root)'),

    # --- W16:评审回合可以只追加变异点登记 ------------------------------------
    # 前九个是 dev 在 impl 回合点名、tester 在 review-impl 隔离复现的;在打回回的 spec
    # 回合登记,没有欠到下一项。最后一个是并进本项的 `--no-renames`,字面在 spec 定死
    # (照抄那一行既有写法,只加一个旗标),落地前不匹配。
    ("只追加路径不在 HEAD 也放行",
     '    if not blob_sha(root, path):',
     '    if False:'),

    ("只追加路径有删除行也放行",
     '    if has_rewrite(root, path):',
     '    if False:'),

    ("不单独判只追加路径",
     '        if matches_any(path, appendable):',
     '        if False:'),

    ("只追加的拒绝理由不落地",
     '            if why:',
     '            if False:'),

    ("只追加路径不分阶段",
     '    if phase not in REVIEW_PHASES:',
     '    if False:'),

    ("只追加路径合并所有角色名下",
     '    return list((cfg.get("review_append_paths") or {}).get(PHASE_OWNER[phase], []))',
     '    return [p for v in (cfg.get("review_append_paths") or {}).values() for p in v]'),

    ("可写路径不标只追加",
     '    parts += ["%s(只追加)" % p for p in review_append_paths(cfg, phase)]',
     '    pass'),

    ("status 头部不标只追加",
     '    print(" 可写路径 : %s" % writable_display(cfg, phase, me))',
     '    print(" 可写路径 : %s" % " ".join(writable_paths(cfg, phase)))'),

    ("简报不标只追加",
     '        "paths": writable_display(cfg, phase),',
     '        "paths": " ".join(writable_paths(cfg, phase)),'),

    ("改名合成一条只给新路径",
     '    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", cwd=root)',
     '    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=root)'),

    # --- W17:只涉及测试的打回不再经过 impl ---------------------------------------
    # W16 落地后第一个在 review-impl 当场登记的工作项(只追加)。锚点 dev 点名、tester 在
    # review-impl 复现。dev 删掉了原型里两个死重的判定,另两个等价变异(外层 `target == "impl"`、
    # `rebound_from` 随非打回清空)照它的说明不登记。
    ("捷径不看 GREEN",
     '    if not green:\n        return False\n    if state.get("rebound_from") != "review-test":',
     '    if False:\n        return False\n    if state.get("rebound_from") != "review-test":'),

    ("捷径不看回弹来源",
     '    if state.get("rebound_from") != "review-test":',
     '    if False:'),

    ("捷径不看本回合承重文件改动",
     '    if changed_named_frozen:\n        return False',
     '    if False:\n        return False'),

    ("捷径不比 review-impl 时的契约",
     '    return state.get("reviewed_contract") == worktree_sha(root, cfg["contract_file"])',
     '    return True'),

    ("捷径的契约在打回时才记",
     '    if phase == "review-impl" and verdict == "approve":\n        state["reviewed_contract"] = worktree_sha(root, cfg["contract_file"])',
     '    if verdict == "changes":\n        state["reviewed_contract"] = worktree_sha(root, cfg["contract_file"])'),

    ("捷径从不生效",
     '        target = "review-test"',
     '        pass'),

    # --- W18:评审记录只能追加 ------------------------------------------------
    # dev 点名、tester 在 review-impl 当场登记(W16)。"已在 HEAD 里"那一项是等价变异
    # (未跟踪文件删除行恒为 0),PLAN ⑥′ 已带声明改成不要求变异点,故不在此列。
    # `if not _review_top_level(cfg, path):` 这一行 check_review_names 里也有一句一模一样的,
    # 锚要带上后两行才唯一。
    ("评审记录改写不看顶层范围",
     '    if not _review_top_level(cfg, path):\n        return None\n'
     '    if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:',
     '    if False:\n        return None\n'
     '    if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:'),

    ("评审记录改写不豁免 ignore",
     '    if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:\n'
     '        return None\n    if blob_sha(root, path) is None:',
     '    if False:\n        return None\n    if blob_sha(root, path) is None:'),

    ("评审记录改写不看删除行",
     '    if not has_rewrite(root, path):',
     '    if False:'),

    ("评审记录改写 handoff 不判",
     '        rewrite = review_rewrite_violation(root, cfg, path)',
     '        rewrite = None'),

    ("评审记录改写 verify-setup 不判",
     '    rewrite = review_rewrite_violation(root, cfg, report_rel)',
     '    rewrite = None'),

    # 顺序变异:在**检查之前**先落一次盘 —— 等价于"拒绝晚于写状态"。
    # 第一版写成在 `state["setup_verified"] = True` 之后插一次 save_state,那是在拒绝
    # **之后**,die 早就退出了,拆了等于没拆 —— mutation_check 如实报了"存活"。
    ("评审记录改写的拒绝晚于写状态",
     '    rewrite = review_rewrite_violation(root, cfg, report_rel)\n',
     '    state["setup_verified"] = True\n    save_state(root, state)\n'
     '    rewrite = review_rewrite_violation(root, cfg, report_rel)\n'),

    # W19 的 idle 归属(dev 在 impl 回合给的锚点,review-impl 登记)。
    ("idle 归 dev 不看 tester 作数",
     '        if (stale_verification(root, cfg, state, "tester") is None',
     '        if (True'),

    ("idle 归 dev 不看 dev 不作数",
     '                and stale_verification(root, cfg, state, "dev")):',
     '                and True):'),

    ("idle 例外从不生效",
     '            return "dev"\n    return PHASE_OWNER[phase]',
     '            pass\n    return PHASE_OWNER[phase]'),

    ("status 不用 idle 例外",
     '    owner = phase_owner(root, cfg, state)',
     '    owner = PHASE_OWNER[phase]'),

    ("whose-turn 不用 idle 例外",
     '    print("turn %s" % phase_owner(root, cfg, state))',
     '    print("turn %s" % PHASE_OWNER[state["phase"]])'),

    # W19 review-test 打回后补的三处(字面见 notes/W19.md)。
    ("idle 归属例外不限 idle",
     '    if phase == "idle" and cfg["require_setup_verification"]:',
     '    if cfg["require_setup_verification"]:'),

    ("门禁没开也改 idle 归属",
     '    if phase == "idle" and cfg["require_setup_verification"]:',
     '    if phase == "idle":'),

    ("dev 在 idle 看到认领说明",
     '    if phase == "idle" and owner == "dev":',
     '    if False:'),

    # W20 的 report --since(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('report 忽略起点',
     '    rows = _handoff_log(root, since)',
     '    rows = _handoff_log(root)'),

    ('report 区间不生效',
     '    span = ("%s..HEAD" % since,) if since else ()',
     '    span = ()'),

    # 「report 起点不限定为提交」W20 第二次 spec 回合撤掉:契约补了"起点必须是 HEAD 的祖先"之后,
    # 树对象过不了祖先判定(merge-base --is-ancestor 对非提交报错),拆掉 ^{commit} 照样被拒 ——
    # 参考实现里实测存活,是等价变异。"不是提交也拒绝"这个性质仍由 test_不是提交的对象也拒绝 守。

    ('report 非法起点不拒',
     '        if since is None:\n            die("report --since',
     '        if False:\n            die("report --since'),

    ('report 分母照读状态',
     '    per_done = finished if since else done',
     '    per_done = done'),

    # W21 的 spec 回合重锚(「三节共同」):完成数只认行首协议行的去向,字面按参考实现定死。
    ('report 完成数不看 idle',
     '            if m.group(2) == "idle":',
     '            if True:'),

    ('report 表头不写起点',
     '    if since:\n        print(" 起点',
     '    if False:\n        print(" 起点'),

    # W20 review-test 打回后补的两处。
    ('report 不带起点时分母也用区间',
     '    per_done = finished if since else done',
     '    per_done = finished'),

    ('report 偏高判定照读状态',
     '"!  偏高" if per_done and no_decision > per_done / 2.0 else "—")',
     '"!  偏高" if done and no_decision > done / 2.0 else "—")'),

    # W20 起点必须是 HEAD 的祖先(dev 第二次 impl 给的锚点,review-impl 登记)。
    ('report 不查起点是不是祖先',
     '        if git("merge-base", "--is-ancestor", since, "HEAD", cwd=root, check=False) is None:',
     '        if False:'),

    # W21 report 只认协议写进提交的那几行(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('report 死锁回到主题子串',
     '        if DEADLOCK_SUBJECT_RE.match(subject):',
     '        if "触发死锁闸" in subject:'),

    ('report 未留决策回到子串',
     '        if NO_DECISION_LINE_RE.search(body):',
     '        if "未留决策(已声明)" in body:'),

    ('report 契约变更回到子串',
     '        if CONTRACT_CHANGE_LINE_RE.search(body):',
     '        if "契约变更(已声明)" in body:'),

    ('report 协议行不锚行首',
     'PROTOCOL_LINE_RE = re.compile(r"^role=',
     'PROTOCOL_LINE_RE = re.compile(r"role='),

    ('report 未留决策不锚行首',
     'NO_DECISION_LINE_RE = re.compile(r"^未留决策',
     'NO_DECISION_LINE_RE = re.compile(r"未留决策'),

    ('report impl 回到子串',
     '            elif j is None and m.group(1) == "impl" and prefix != "dispute":',
     '            elif j is None and "phase=impl -> " in body and prefix != "dispute":'),

    # W21 review-test 打回后补的一处。
    ('report 契约变更不锚行首',
     'CONTRACT_CHANGE_LINE_RE = re.compile(r"^契约变更',
     'CONTRACT_CHANGE_LINE_RE = re.compile(r"契约变更'),

    # W22 共用目录时角色要来自 PAIR_ROLE(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('共用目录警告不看 sync',
     '    if not cfg.get("sync") and source != ROLE_FROM_ENV:',
     '    if source != ROLE_FROM_ENV:'),

    ('共用目录警告不看来源',
     '    if not cfg.get("sync") and source != ROLE_FROM_ENV:',
     '    if not cfg.get("sync"):'),

    ('共用目录警告写法角色写死',
     '        print("  PAIR_ROLE=%s python3 %s <命令>" % (me, PROG_HINT))',
     '        print("  PAIR_ROLE=%s python3 %s <命令>" % ("dev", PROG_HINT))'),

    # W23 验证副本放 .pair/scratch/(dev 在 impl 回合给的锚点,review-impl 登记)。
    # W31 的 spec 回合重锚(「三节共同」):GITIGNORE_LINES 那一行后面接着系统文件那一行,字面定死。
    ('gitignore 不含 scratch',
     '                   "__pycache__/", "*.pyc", ".pair/scratch/",\n',
     '                   "__pycache__/", "*.pyc",\n'),

    # W24 的 spec 回合(带声明补的正面):verify-setup 对没声明保护测试的 refactor 项要警告。
    # 样板项目那条是"不出现",单向的;这条变异由 test_v1_brownfield 的正面用例抓。
    ('verify-setup 不警告 refactor 缺保护测试',
     "        if not refs:\n            warn(\"工作项 '%s' [refactor] 没声明保护它的测试",
     "        if False:\n            warn(\"工作项 '%s' [refactor] 没声明保护它的测试"),

    # W25:status 头部按执行命令的角色显示。字面在 spec 回合定死(「三节共同」:它改写了上面那个锚点)。
    ('status 可写路径退回按阶段归属',
     '    print(" 可写路径 : %s" % writable_display(cfg, phase, me))',
     '    print(" 可写路径 : %s" % writable_display(cfg, phase, owner))'),

    # W26 的 spec 回合(带声明补的正面):入口文件缺激活段落时 verify-setup 要警告。
    # 样板那条是"不出现",单向的;这条变异由 test_v1_setup 的正面用例抓。
    ('verify-setup 不警告入口文件缺激活段落',
     '        elif ENTRY_MARK_BEGIN not in fp.read_text(encoding="utf-8"):',
     '        elif False:'),

    # W27 verify-setup 的结尾看另一方(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('verify-setup 结尾不看另一方',
     '        if stale_verification(root, cfg, state, other):',
     '        if False:'),

    # W28 改了 CLAUDE_MD 而样板没跟上(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('CLAUDE_MD 改了而样板没跟上',
     '  不要转手给别的 agent 或会话去跑 —— 回合状态在 `.pair/state.json`,',
     '  不要转手给别的 agent 或会话 —— 回合状态在 `.pair/state.json`,'),

    # W30 验证副本的去处写进简报(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('简报不提 scratch',
     '    if phase != "idle":\n        print(scratch_hint(phase))',
     '    if False:\n        print(scratch_hint(phase))'),

    ('idle 也提 scratch',
     '    if phase != "idle":\n        print(scratch_hint(phase))',
     '    if True:\n        print(scratch_hint(phase))'),

    # W31 操作系统写的文件(spec 回合定死字面并登记;认出系统文件那一句的锚点等 dev 定形状,review-impl 登记)。
    # W34 的 spec 回合重锚:三个系统文件名写在 OS_FILES 一处,GITIGNORE_LINES 用 *OS_FILES 引用。
    ('gitignore 不含 .DS_Store',
     '                   *OS_FILES]',
     '                   *(f for f in OS_FILES if f != ".DS_Store")]'),

    # W31 认出系统文件(dev 在 impl 回合给的锚点,review-impl 登记)。
    ('越界文案不认系统文件',
     '    if PurePosixPath(path).name in OS_FILES:',
     '    if False:'),

    # W34 名单显式写出(spec 回合定死字面并登记)。
    ('OS_FILES 退回按形状筛',
     '                   *OS_FILES]\n',
     '                   *OS_FILES]\nOS_FILES = tuple(l for l in GITIGNORE_LINES if "/" not in l and "*" not in l)\n'),
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

# 快路径("只跑缓存里那几个测试,失败就算抓到")和回退路径("全量 failfast,
# rc≠0 就算抓到")成立的前提是同一个:**在做归因判定的那个环境里,未变异状态
# 是绿的** —— 只有基线全绿,才能把"测试失败了"归因到变异上。
#
# 所以基线跑绿时把当时的指纹记进缓存;`--no-baseline` 只有在指纹对得上时才敢
# 走快路径。但指纹闸只闸得住快路径:指纹对不上时回退路径照跑,而它的判据
# 只有 rc≠0,**分不清失败来自变异还是来自环境**。基线本来就红的环境里,每个
# 变异都会被判成"抓到" —— 一个看着是绿的、其实什么都没验的检查,正是这个
# 项目最怕的东西。
#
# 所以 `--no-baseline` 还要过第二道闸:precheck_no_baseline 在未变异的隔离
# 副本(与 check_one 的判定环境同构)里跑一遍全量套件,失败集非空就拒绝
# 检查;为空则两条路径的 rc≠0 都必然由变异引起,判据恢复可靠。预检不写缓存、
# 不放宽 verified —— "指纹对不对得上"仍由 baseline_verified 独自裁定。
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


def isolated_copy(tmp):
    """判定环境的同构副本。排除 .git —— 变异不该碰真实的 git 历史,
    预检也不该碰(见 precheck_no_baseline)。"""
    dst = Path(tmp) / "repo"
    shutil.copytree(REPO, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(
                        ".git", "__pycache__", "*.pyc", ".DS_Store"))
    return dst


def check_one(job):
    """在隔离副本里应用一个变异并判定它有没有被抓到。

    返回 (name, status, fails, note)。status: caught / survived / unmatched
    """
    name, old, new, cached = job
    tmp = Path(tempfile.mkdtemp(prefix="mutate-"))
    try:
        dst = isolated_copy(tmp)
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
                    help="跳过基线检查(改用一次未变异副本预检;"
                         "指纹对不上时快路径仍停用)")
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
        # 指纹闸只管快路径。回退路径(以及被环境污染的快路径)同样要靠
        # "未变异状态是绿的"才能把 rc≠0 归因到变异,所以在判定环境同构的
        # 副本里预检一遍;副本环境红着就拒绝 —— 否则每一条变异都会被误判成
        # "抓到",报出一个恒真的 70/70。
        rc, fails, text = precheck_no_baseline(args.jobs)
        if rc != 0 or fails:
            print("拒绝做变异检查:在未变异的隔离副本里,测试就没有全绿。\n")
            if fails:
                print("副本环境里的失败项(%d 个):" % len(fails))
                for f in fails:
                    print("  - %s" % f)
            print("\n基线不是绿的,此时跑变异,rc≠0 分不清是变异引起的还是环境"
                  "本来就红 —— \"全部被抓到\"会是恒真结论,而恒真的检查比没有"
                  "检查更危险。\n下一步:\n"
                  "  1. 先修红:看上面的失败清单,逐条修到全绿;\n"
                  "  2. 环境性失败(比如 git 身份探测不到)就换一个能跑绿的"
                  "环境;\n"
                  "  3. 或者去掉 --no-baseline 走默认路径,让基线门禁把问题"
                  "拦在最前面。")
            if rc != 0 and not fails:
                # 运行器自身出问题时(导入失败、崩溃),一条 FAIL 行都抓不到。
                # 这时候只报"失败清单为空"反而像绿的,把原始输出兜底打出来。
                print("\n预检运行器输出:\n%s" % text.rstrip())
            return 2
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
    # W33:基线跑在**未变异的隔离副本**里,与变异同一个 `isolated_copy`(排除 `.git`)。
    # 曾经跑在本仓库里:一个只在无 `.git` 时失败的用例让基线照绿,而在副本里它对每个变异都失败 ——
    # failfast 回退把它记成任何新变异的抓手,缓存从此恒判抓到(第十四轮 W30 的 review-impl 真实发生过)。
    # **同一个的是文件系统,不是环境变量**:上面照旧去掉 PAIR_MUTATION_RUN,锚点检查仍在这里一次性把守。
    tmp = Path(tempfile.mkdtemp(prefix="mutate-baseline-"))
    try:
        dst = isolated_copy(tmp)
        base = subprocess.run(
            [sys.executable, str(dst / "tests/conformance/run.py"),
             "-j", str(jobs)], cwd=str(dst), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if base.returncode != 0:
        print("基线就没全绿,先修好再做变异测试:\n%s"
              % base.stdout.decode("utf-8", "replace"))
        return 1
    print("基线全绿 (%.1fs)\n" % (time.time() - t0))
    save_cache(fingerprint(), load_cache()[1])
    return 0


def precheck_no_baseline(jobs):
    """--no-baseline 的归因前提预检:在**未变异**的隔离副本里跑一遍全量套件。

    返回 (returncode, 失败 id 列表, 原始输出)。returncode 非零或失败列表
    非空,都意味着"rc≠0 由变异引起"这条归因不成立,调用方必须拒绝检查。

    为什么在副本里跑而不是在真实仓库里跑:check_one 的判定发生在 copytree
    出来的副本里(排除 .git)。需要恢复的不变量是"在**做归因判定的那个
    环境**里,未变异状态是绿的" —— 真实仓库绿而副本红,回退路径照样恒真。
    预检必须与判定环境同构,所以要落在副本里。

    为什么设 PAIR_MUTATION_RUN:判定环境(check_one → run_suite)带着它,
    预检必须同构 —— "变异点仍能匹配到源码"那条检查属于基线职责(由默认
    路径的 run_baseline 一次性把守),不该混进这里的归因前提。
    """
    print("=== --no-baseline 预检:未变异的隔离副本,全量套件 ===")
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="mutate-precheck-"))
    try:
        dst = isolated_copy(tmp)
        env = dict(os.environ, PAIR_MUTATION_RUN="1")
        proc = subprocess.run(
            [sys.executable, str(dst / "tests/conformance/run.py"),
             "-j", str(jobs)], cwd=str(dst), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = proc.stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    fails = _ids(text)
    if proc.returncode == 0 and not fails:
        print("预检全绿 (%.1fs) —— rc≠0 可以归因到变异,判据可靠\n"
              % (time.time() - t0))
    return proc.returncode, fails, text


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
