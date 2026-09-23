# -*- coding: utf-8 -*-
"""W33:mutation_check 的基线与变异在同一个环境里跑。

契约「mutation_check 的基线与变异同一个环境」。第十四轮 W30:变异在排除 `.git` 的隔离副本里判定,基线却在本仓库里跑;
一个只在无 `.git` 时失败的用例让基线照绿、每个变异都被它"抓到",缓存从此恒判抓到。

**不在测试里跑全套**(基线一次要一分多钟):造一个迷你仓库 —— `mutation_check.py`、`run.py`、存根 `pair.py`、
一两个小测试 —— 用 `git init` 让它自己是 git 仓库(在原地跑时 `.git` 在),跑它的 `mutation_check.py`,只看基线那一段。

**同一个的是文件系统,不是环境变量**(W33 的 spec 回合带声明补):基线照旧不设 `PAIR_MUTATION_RUN`,
锚点检查("变异点仍能匹配到源码")仍在基线里一次性把守。
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT_ID = ("-c", "user.name=conformance", "-c", "user.email=conformance@test")

NEEDS_GIT = '''import unittest
from pathlib import Path


class T(unittest.TestCase):
    def test_要有_git(self):
        """只在本仓库(有 .git)里能过 —— W30 那一类用例的最小形状。"""
        self.assertTrue((Path(__file__).resolve().parents[2] / ".git").exists())
'''

PLAIN = '''import unittest


class T(unittest.TestCase):
    def test_总是过(self):
        self.assertTrue(True)
'''

NO_MUTATION_ENV = '''import os
import unittest


class T(unittest.TestCase):
    def test_基线不带_PAIR_MUTATION_RUN(self):
        self.assertIsNone(os.environ.get("PAIR_MUTATION_RUN"))
'''


class MiniRepo(unittest.TestCase):

    def mini(self, *tests):
        root = Path(tempfile.mkdtemp(prefix="mini-mutate-")) / "repo"
        self.addCleanup(shutil.rmtree, root.parent, True)
        conf = root / "tests" / "conformance"
        conf.mkdir(parents=True)
        for name in ("mutation_check.py", "run.py"):
            shutil.copy2(HERE / name, conf / name)
        stub = root / ".agents" / "skills" / "pair-protocol" / "scripts" / "pair.py"
        stub.parent.mkdir(parents=True)
        stub.write_text("# 存根:迷你仓库只看基线\n", encoding="utf-8")
        for i, body in enumerate(tests):
            (conf / ("test_mini_%d.py" % i)).write_text(body, encoding="utf-8")
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "迷你仓库")):
            subprocess.run(("git",) + GIT_ID + args, cwd=root, check=True, stdout=subprocess.DEVNULL)
        return root

    def baseline(self, root):
        """跑迷你仓库的 mutation_check,只取基线那一段的结论。`--only` 选一个真实的变异名:
        基线先跑;之后那个变异在存根上匹配不到,不影响基线那一段。"""
        proc = subprocess.run(
            [sys.executable, str(root / "tests/conformance/mutation_check.py"),
             "--only", "拆掉死锁闸", "-j", "1"],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        self.assertIn("基线", out, out)
        return proc.returncode, out


class TestBaselineRunsInIsolatedCopy(MiniRepo):

    def test_只在无_git_时失败的用例让基线变红(self):
        """前提先核实:它在原地(有 .git)是绿的。"""
        root = self.mini(NEEDS_GIT)
        here = subprocess.run([sys.executable, str(root / "tests/conformance/run.py"), "-j", "1"],
                              cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(here.returncode, 0, "前提:原地跑是绿的\n" + here.stdout.decode("utf-8", "replace"))
        rc, out = self.baseline(root)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("基线就没全绿", out, out)

    def test_对照组_不依赖_git_的用例基线照绿(self):
        rc, out = self.baseline(self.mini(PLAIN))
        self.assertIn("基线全绿", out, out)

    def test_基线不带_PAIR_MUTATION_RUN(self):
        """同一个的是文件系统:基线环境变量照旧,锚点检查才留在基线里。"""
        rc, out = self.baseline(self.mini(NO_MUTATION_ENV))
        self.assertIn("基线全绿", out, out)


if __name__ == "__main__":
    unittest.main()
