# -*- coding: utf-8 -*-
"""W62:`run.py --junit-xml <路径>` —— 本仓库的测试也写出用例级结果。

契约「run.py 写出 JUnit XML」(含 spec 回合带声明补的「补充」,开工前审查 ⑲)。`run.py` 在 tester 路径,实现与用例都由 tester 写(cover)。

- `FAIL:` / `ERROR:` 行的解析直接喂各种形态 —— 本机是 3.14,CI 的 3.9 那一支(括号里只有 `模块.类`)只能这样守住;
- 端到端:跑一个小模块,报告能被 `pair.py` 的 `junit_failures` 读出、ID 与 `run.py --list` 一致;
- 红的那一格:在临时目录里放一份 `run.py` 和一个有红有绿的用例模块(不往本仓库的测试目录里放红用例),跑那一份。
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import run as runner

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SMALL = "test_mutation_exit_codes"


def _load_pair():
    spec = importlib.util.spec_from_file_location(
        "pair_for_run_junit", REPO / ".agents" / "skills" / "pair-protocol" / "scripts" / "pair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAIR = _load_pair()

MIXED_MODULE = '''import unittest


class T(unittest.TestCase):

    def test_bad(self):
        self.assertEqual(1, 2)

    def test_boom(self):
        raise RuntimeError("出错而不是断言失败")

    def test_good(self):
        pass

    def test_sub(self):
        for i in range(2):
            with self.subTest(i=i):
                self.assertEqual(i, 0)
'''


def run_runner(cwd, *args):
    proc = subprocess.run([sys.executable, str(Path(cwd) / "run.py")] + list(args), cwd=str(cwd),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def report_ids(path):
    out = []
    for case in ET.parse(str(path)).getroot().iter("testcase"):
        out.append("%s.%s" % (case.get("classname"), case.get("name")))
    return sorted(out)


class TestFailLineParsing(unittest.TestCase):
    """⑲:两种形态都认,subTest 的参数不混进 ID。"""

    def test_311_起的形态(self):
        self.assertEqual(runner.failed_ids(["FAIL: test_x (mod.Cls.test_x)\n"]), {"mod.Cls.test_x"})

    def test_310_及以前的形态(self):
        self.assertEqual(runner.failed_ids(["FAIL: test_x (mod.Cls)\n"]), {"mod.Cls.test_x"})

    def test_ERROR_行同样算(self):
        self.assertEqual(runner.failed_ids(["ERROR: test_y (mod.Cls.test_y)\n", "ERROR: test_z (mod.Cls)\n"]),
                         {"mod.Cls.test_y", "mod.Cls.test_z"})

    def test_subTest_的参数不进_ID(self):
        self.assertEqual(runner.failed_ids(["FAIL: test_s (mod.Cls.test_s) (i=1)\n",
                                            "FAIL: test_t (mod.Cls) (i=2)\n"]),
                         {"mod.Cls.test_s", "mod.Cls.test_t"})

    def test_不是行首的不算(self):
        self.assertEqual(runner.failed_ids(["    AssertionError: FAIL: test_x (mod.Cls.test_x)\n", "OK\n"]), set())


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="run-junit-"))
        self.addCleanup(shutil.rmtree, self.out, True)

    def test_写出的报告能被_pair_py_读出_ID_与_list_一致(self):
        report = self.out / "junit.xml"
        rc, text = run_runner(HERE, "--junit-xml", str(report), SMALL)
        self.assertEqual(rc, 0, text)
        self.assertTrue(report.exists(), text)
        self.assertEqual(PAIR.junit_failures(report), [])
        rc, listed = run_runner(HERE, "--list", SMALL)
        ids = sorted(l for l in listed.splitlines() if l.startswith(SMALL + "."))
        self.assertTrue(ids, "前提:--list 列出了用例")
        self.assertEqual(report_ids(report), ids)

    def test_报告写进不存在的目录也行(self):
        report = self.out / "nested" / "dir" / "junit.xml"
        rc, text = run_runner(HERE, "--junit-xml", str(report), SMALL)
        self.assertEqual(rc, 0, text)
        self.assertTrue(report.exists())


class TestWithFailures(unittest.TestCase):
    """临时目录里的一份 `run.py` 加一个有红有绿的模块:红的带 failure、绿的不带,退出码非 0。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="run-junit-mixed-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        shutil.copy2(HERE / "run.py", self.dir / "run.py")
        (self.dir / "test_zz_mixed.py").write_text(MIXED_MODULE, encoding="utf-8")

    def test_红的带_failure_绿的不带_退出码非零(self):
        report = self.dir / "junit.xml"
        rc, text = run_runner(self.dir, "--junit-xml", str(report))
        self.assertNotEqual(rc, 0, text)
        self.assertEqual(sorted(PAIR.junit_failures(report)),
                         ["test_zz_mixed.T.test_bad", "test_zz_mixed.T.test_boom", "test_zz_mixed.T.test_sub"])
        self.assertIn("test_zz_mixed.T.test_good", report_ids(report))

    def test_报告与退出码一致_pair_py_不降级(self):
        """W58 ⑰:读得出、与退出码一致才用。"""
        report = self.dir / "junit.xml"
        rc, _ = run_runner(self.dir, "--junit-xml", str(report))
        rel = report.relative_to(self.dir)
        failed, warning = PAIR.read_report(self.dir, str(rel), rc)
        self.assertIsNone(warning)
        self.assertEqual(len(failed), 3)

    def test_不给参数时不写文件_输出照旧(self):
        rc, text = run_runner(self.dir)
        self.assertNotEqual(rc, 0)
        self.assertEqual(sorted(p.name for p in self.dir.glob("*.xml")), [])
        self.assertRegex(text, r"(?m)^\d+ 个测试 / \d+ 进程 / [\d.]+s — 失败 \d+ 项$")


if __name__ == "__main__":
    unittest.main()
