# -*- coding: utf-8 -*-
"""W45:`mutation_check` 的基线预检闸补上测试。

契约「变异检查的基线预检闸要有测试」。`precheck_no_baseline` 在未变异的隔离副本里先跑一遍全量:副本环境本身就红,就拒绝做变异检查 ——
否则回退路径只看退出码非 0,每条变异都会被判成"抓到",报出恒真的全部抓到。这道闸此前在 `test_mutation_tooling.py` 里零命中。

三层,都是毫秒级(不端到端跑预检 —— 那要多跑一遍全量):
① 放行判定抽成纯函数 `precheck_passes`,真值表四格都钉;`main` 里那一处调用它。
② 读源码:`precheck_no_baseline` 的函数体里调用 `isolated_copy(`、设置 `PAIR_MUTATION_RUN`;`isolated_copy` 的忽略模式里有 `.git`。
   (照 `test_v1_shipped` 读 `cmd_whose_turn` 源码的先例 —— `mutation_check` 不变异它自己,只能这样守。)
③ 直接调 `isolated_copy`,看副本里有什么、没什么。
"""

import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "mutation_check.py").read_text(encoding="utf-8")


def _load():
    spec = importlib.util.spec_from_file_location("mutation_precheck_under_test", HERE / "mutation_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MUT = _load()


def body(name):
    """顶层函数 `name` 的源码(到下一个顶层 def 为止)。"""
    m = re.search(r"(?m)^def %s\(.*?(?=^def |\Z)" % re.escape(name), SRC, re.S)
    assert m, "mutation_check.py 里没有函数 %s" % name
    return m.group(0)


class TestPrecheckTruthTable(unittest.TestCase):

    def test_退出码_0_且没有失败_放行(self):
        self.assertTrue(MUT.precheck_passes(0, []))

    def test_退出码_0_但抓到_FAIL_行_不放行(self):
        """并行运行器某一片失败、汇总行照打时就是这个形态 —— 只看退出码的判定在这里放行。"""
        self.assertFalse(MUT.precheck_passes(0, ["test_x.T.test_y"]))

    def test_退出码非_0_但一条失败都没抓到_不放行(self):
        """运行器自身崩溃(导入失败)时一条 FAIL 行都没有 —— 只看失败集的判定在这里放行。"""
        self.assertFalse(MUT.precheck_passes(1, []))

    def test_退出码非_0_且有失败_不放行(self):
        self.assertFalse(MUT.precheck_passes(1, ["test_x.T.test_y"]))

    def test_main_里用的是这个判定(self):
        self.assertIn("precheck_passes(", body("main"))


class TestPrecheckSource(unittest.TestCase):

    def test_预检在隔离副本里跑(self):
        self.assertIn("isolated_copy(", body("precheck_no_baseline"))

    def test_预检带着_PAIR_MUTATION_RUN(self):
        """与判定环境同构:变异判定带着它,预检也得带。"""
        self.assertRegex(body("precheck_no_baseline"), r"PAIR_MUTATION_RUN\s*=\s*\"1\"|PAIR_MUTATION_RUN=\"1\"")

    def test_隔离副本排除_git(self):
        self.assertRegex(body("isolated_copy"), r"ignore_patterns\([^)]*\"\.git\"")


class TestIsolatedCopyBehaviour(unittest.TestCase):

    def test_副本里没有_git_与字节码_有协议与运行器(self):
        tmp = tempfile.mkdtemp(prefix="isocopy-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = MUT.isolated_copy(tmp)
        self.assertFalse((dst / ".git").exists())
        self.assertEqual([p for p in dst.rglob("__pycache__")], [])
        self.assertTrue((dst / ".agents/skills/pair-protocol/scripts/pair.py").is_file())
        self.assertTrue((dst / "tests/conformance/run.py").is_file())
