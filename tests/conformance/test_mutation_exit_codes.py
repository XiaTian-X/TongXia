# -*- coding: utf-8 -*-
"""W52:变异检查的预检拒绝用退出码 3。

契约「变异检查的预检拒绝用退出码 3」。`--no-baseline` 被基线预检拒绝与 argparse 的用法错误原先都退 2,
只读退出码分不清"副本环境不绿、拒绝归因"与"命令行写错了"。

**分工**:`mutation_check.py` 在 tester 路径,改动与这里的代码用例由 tester 在 spec 回合写(同第二十三轮 W40),
spec 回合结束时就是绿的;红的只有 `docs/contributing.md` 那一条,由 dev 在 impl 回合写。

不端到端跑预检(那要多跑一遍全量):把模块里的 `precheck_no_baseline` 换成直接返回"不放行",再调 `main`。
"""

import contextlib
import importlib.util
import io
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRIBUTING = REPO / "docs" / "contributing.md"


def _load():
    spec = importlib.util.spec_from_file_location("mutation_exit_codes_under_test", HERE / "mutation_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPrecheckRefusalIsThree(unittest.TestCase):

    def run_main(self, argv, precheck):
        mod = _load()
        mod.precheck_no_baseline = precheck
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = mod.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue() + err.getvalue()

    def test_预检有失败项时退_3(self):
        rc, out = self.run_main(["--no-baseline"], lambda jobs: (1, ["test_x.T.test_y"], ""))
        self.assertEqual(rc, 3, out)
        self.assertIn("拒绝做变异检查", out)

    def test_预检运行器崩溃_没抓到失败项时也退_3(self):
        """rc≠0、失败集为空(导入失败之类):`precheck_passes` 的另一支,同一个拒绝出口。"""
        rc, out = self.run_main(["--no-baseline"], lambda jobs: (1, [], "Traceback: boom"))
        self.assertEqual(rc, 3, out)
        self.assertIn("boom", out)

    def test_用法错误仍是_2(self):
        def must_not_run(jobs):
            raise AssertionError("用法错误时不该走到预检")
        rc, out = self.run_main(["--no-baseline", "--slice", "abc"], must_not_run)
        self.assertEqual(rc, 2, out)
        self.assertIn("usage:", out)


class TestContributingSaysThree(unittest.TestCase):
    """`docs/contributing.md` 的退出码说明是 dev 的;spec 回合结束时这一条红。"""

    def setUp(self):
        self.text = CONTRIBUTING.read_text(encoding="utf-8")

    def exit_code_paragraph(self):
        """变异检查那一节"退出码:`0` = …"开头的那一段(到空行为止)。"""
        m = re.search(r"(?m)^退出码:`0`.*?(?=\n\s*\n|\Z)", self.text, re.S)
        self.assertIsNotNone(m, "contributing.md 里找不到以「退出码:`0`」开头的那一段")
        return m.group(0)

    def test_退出码那一段把预检拒绝对上_3(self):
        para = self.exit_code_paragraph()
        self.assertIn("`3`", para)
        self.assertRegex(para, r"`3`[^。]*预检|预检[^。]*`3`", "`3` 要和预检拒绝说在一起:\n" + para)

    def test_不再靠_usage_区分两种_2(self):
        self.assertNotRegex(self.text, r"看[^。\n]{0,20}usage:")

    def test_预检闸那段不再说以退出码_2_拒绝(self):
        """「第二道是基线预检闸」那段原先写"以**退出码 2** 拒绝执行"。"""
        self.assertNotRegex(self.text, r"退出码\W{0,4}2\W{0,4}拒绝")


if __name__ == "__main__":
    unittest.main()
