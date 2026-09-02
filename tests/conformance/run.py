#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一致性测试的并行运行器 —— 以及"改了什么测什么"。

    python3 tests/conformance/run.py              # 全量,按核数并行
    python3 tests/conformance/run.py --changed    # 只跑与本次改动相关的
    python3 tests/conformance/run.py memory flows # 模糊匹配模块名
    python3 tests/conformance/run.py -j1          # 串行(调试用,输出不交错)
    python3 tests/conformance/run.py --list       # 只列出会跑哪些

为什么需要它:测试本身不慢,慢在**每个用例都要起真的 git 仓库、真的
pair.py 子进程**。这类负载是 I/O 密集的,不吃 GIL,分片并行近似线性加速。

`--changed` 的取舍:改了 pair.py 就跑全量。不是做不到更细,是**做细了不安全** ——
pair.py 里的守卫互相之间有顺序依赖,靠路径猜覆盖面会漏。真正需要细粒度选择的
是变异检查(它要把全套跑几十遍),那里用的是缓存机制,见 mutation_check.py。
"""

import argparse
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

ALL = "__all__"

# 改动路径 → 相关测试模块。第一个命中的规则生效;没命中的一律跑全量。
# 保守优先:漏跑一个测试的代价,远大于多跑几秒。
CHANGED_RULES = [
    (r"^tests/conformance/test_(\w+)\.py$",              lambda m: ["test_" + m.group(1)]),
    (r"^tests/conformance/(harness|run)\.py$",           lambda m: ALL),
    # test_mutation_tooling 直接测 mutation_check 的内部函数(run_suite/load_cache),
    # 改了那边最可能弄坏的就是它 —— 漏掉它,--changed 会全绿而防护已经坏了。
    (r"^tests/conformance/mutation_check\.py$",
     lambda m: ["test_docs_consistency", "test_mutation_tooling"]),
    (r"^tests/conformance/mutation-cache\.json$",        lambda m: ["test_mutation_tooling"]),
    (r"^cli/",                                           lambda m: ["test_v1_cli"]),
    (r"^examples/",                                      lambda m: []),
    (r"^(docs/.*\.md|README\.md|INSTALL\.md)$",          lambda m: ["test_docs_consistency"]),
    (r"pair-protocol/(SKILL\.md|references/)",           lambda m: ["test_docs_consistency"]),
    (r"pair-protocol/scripts/pair\.py$",                 lambda m: ALL),
]


def all_test_ids(patterns=None):
    """收集测试 id。patterns 为模块名的模糊匹配。"""
    loader = unittest.TestLoader()
    out = []

    def walk(suite):
        for t in suite:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            elif isinstance(t, unittest.loader._FailedTest):
                sys.stderr.write("!! 无法导入:%s\n" % t.id())
                raise SystemExit(2)
            else:
                out.append(t.id())

    walk(loader.discover(str(HERE), top_level_dir=str(HERE)))
    if patterns:
        out = [i for i in out
               if any(p.lower() in i.split(".")[0].lower() for p in patterns)]
    return sorted(out)


def changed_files():
    """工作区里改动过的文件(含未跟踪),仓库根的相对路径。"""
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO),
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    files = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:                      # 重命名
            path = path.split(" -> ")[-1]
        if path.endswith("/"):                  # 未跟踪目录:展开
            for p in (REPO / path).rglob("*"):
                if p.is_file():
                    files.append(str(p.relative_to(REPO)))
        else:
            files.append(path)
    return files


def modules_for(files):
    """返回 (模块名集合, 说明行)。ALL 表示跑全量。"""
    picked, why = set(), []
    for f in files:
        if f.endswith((".pyc", ".DS_Store")) or "__pycache__" in f:
            continue
        for pat, fn in CHANGED_RULES:
            m = re.search(pat, f)
            if m:
                got = fn(m)
                if got is ALL:
                    return ALL, ["%s → 全量" % f]
                if got:
                    picked.update(got)
                    why.append("%s → %s" % (f, ", ".join(got)))
                break
        else:
            return ALL, ["%s → 无匹配规则,保守跑全量" % f]
    return picked, why


def shard(ids, n):
    """轮转分片。按 id 轮转而不是按模块,因为模块之间用例数差 10 倍。"""
    return [ids[i::n] for i in range(n) if ids[i::n]]


def run(ids, jobs):
    if not ids:
        print("没有要跑的测试。")
        return 0
    jobs = max(1, min(jobs, len(ids)))
    shards = shard(ids, jobs)
    t0 = time.time()
    procs = [subprocess.Popen(
        [sys.executable, "-m", "unittest", "-q"] + s, cwd=str(HERE),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for s in shards]
    outs = [p.communicate()[0].decode("utf-8", "replace") for p in procs]
    codes = [p.returncode for p in procs]
    elapsed = time.time() - t0

    bad = [o for o, c in zip(outs, codes) if c != 0]
    for o in bad:
        sys.stdout.write(o.rstrip() + "\n")

    n_fail = sum(len(re.findall(r"^(?:FAIL|ERROR):", o, re.M)) for o in bad)
    print("\n%d 个测试 / %d 进程 / %.1fs — %s"
          % (len(ids), len(shards), elapsed,
             "全绿" if not bad else "失败 %d 项" % n_fail))
    return 0 if not bad else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="run.py", description="一致性测试的并行运行器")
    ap.add_argument("patterns", nargs="*", help="模块名的模糊匹配,如 memory flows")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4,
                    help="并行进程数(默认=核数)")
    ap.add_argument("--changed", action="store_true",
                    help="只跑与工作区改动相关的测试")
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些,不执行")
    args = ap.parse_args(argv)

    patterns = list(args.patterns)
    if args.changed:
        if patterns:
            ap.error("--changed 不能和模块名一起用")
        files = changed_files()
        if not files:
            print("工作区没有改动 —— 没有要跑的测试。")
            return 0
        mods, why = modules_for(files)
        for line in why[:12]:
            print("  %s" % line)
        if len(why) > 12:
            print("  …… 另有 %d 条" % (len(why) - 12))
        if mods is ALL:
            print("→ 跑全量\n")
        elif not mods:
            print("→ 没有相关测试。")
            return 0
        else:
            patterns = sorted(mods)
            print("→ 只跑:%s\n" % " ".join(patterns))

    ids = all_test_ids(patterns)
    if patterns and not ids:
        # --changed 选不出测试是正常的(改的是 examples/),那条路径在上面就返回了。
        # 走到这里说明是人手打的模式匹配不到东西 —— 多半是拼错了。
        # 这时候返回 0 等于告诉他"测试通过了",是最坏的一种假绿。
        sys.stderr.write("没有模块匹配 %s。可用模块:\n  %s\n"
                         % (" ".join(patterns),
                            "\n  ".join(sorted({i.split(".")[0]
                                                for i in all_test_ids()}))))
        return 2
    if args.list:
        for i in ids:
            print(i)
        print("\n共 %d 个" % len(ids))
        return 0
    return run(ids, args.jobs)


if __name__ == "__main__":
    sys.exit(main())
