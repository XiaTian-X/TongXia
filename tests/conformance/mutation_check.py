#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异检查:逐个拆掉 pair.py 里的防护,确认对应一致性测试会失败。

一个恒真的测试集比没有测试更危险 —— 它会让人以为强制力还在,
而实际上执行层可能已经什么都不拦了。

    python3 tests/conformance/mutation_check.py

每次改动 pair.py 的强制逻辑后都应该跑一遍。新增防护时,
在 MUTATIONS 里补上对应的变异点。
"""
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
     "    if phase in REVIEW_PHASES:\n        return shared",
     "    if False:\n        return shared"),

    ("拆掉写权限边界",
     "    if violations:\n        lines =",
     "    if False:\n        lines ="),

    ("拆掉测试删除防护",
     "    if deleted and not args.allow_deletion:",
     "    if False:"),

    ("拆掉 spec 阶段红绿检查",
     '    if phase == "spec" and green:',
     "    if False:"),

    ("拆掉 impl 阶段红绿检查",
     '    if phase == "impl" and not green:',
     "    if False:"),

    ("拆掉评审理由强制",
     '        if not message:\n            die("裁决必须附理由。禁止空手通过。")',
     "        if False:\n            pass"),

    ("拆掉死锁闸",
     "        if changes_n >= DEADLOCK_LIMIT:",
     "        if False:"),

    ("拆掉认领工作项强制",
     '    if phase == "spec" and not item:',
     "    if False:"),

    ("拆掉 PLAN 全完成的终止检查",
     "    if plan_all_done(root, cfg):\n        die(",
     "    if False:\n        die("),
]

FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (\S+)", re.M)


def run_suite(root):
    proc = subprocess.run(
        ["python3", "-m", "unittest", "discover",
         "-s", "tests/conformance", "-t", "tests/conformance"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
