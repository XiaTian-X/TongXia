# -*- coding: utf-8 -*-
"""W58:可选的 JUnit XML 报告 —— 读出红的是哪几条。

契约「可选的 JUnit XML 报告」(含 spec 回合带声明补的「补充」,开工前审查 ⑰)。

**假测试命令**:仓库外一个小脚本,按 harness 的布局判红绿(`tests/X` 存在而 `src/X` 不在 = X 红),退出码照判定,
再按"模式"写报告:`normal` 照实写(`classname="tests"`、`name=X`,红的带 `<failure>`);`none` 不写;`garbage` 写一份坏 XML;
`lying-green` 照实退出、报告全绿;`lying-red` 报告全红、退出 0;`fixed` 把一份给定的 XML 原样写出、按给定退出码退出。
它还往仓库外的计数文件追加一行,用来判"这次执行了没有"(同 W57)。
"""

import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from harness import PairTestCase

FAKE_RUNNER = r'''
import os, sys
counter, report, mode = sys.argv[1], sys.argv[2], sys.argv[3]
open(counter, "a").write("x\n")
t = sorted(n for n in os.listdir("tests") if not n.startswith("."))
bad = [n for n in t if not os.path.exists(os.path.join("src", n))]
rc = 1 if bad else 0
def case(n, red):
    return '<testcase classname="tests" name="%s">%s</testcase>' % (n, '<failure message="no impl"/>' if red else "")
def write(text):
    d = os.path.dirname(report)
    if d:
        os.makedirs(d, exist_ok=True)
    open(report, "w").write(text)
if mode == "normal":
    write('<?xml version="1.0"?><testsuites><testsuite name="fake">%s</testsuite></testsuites>'
          % "".join(case(n, n in bad) for n in t))
elif mode == "garbage":
    write("<testsuites><testsuite><testcase name=")
elif mode == "lying-green":
    write('<testsuite name="fake">%s</testsuite>' % "".join(case(n, False) for n in t))
elif mode == "lying-red":
    write('<testsuite name="fake">%s</testsuite>' % "".join(case(n, True) for n in t))
    rc = 0
elif mode == "fixed":
    write(open(sys.argv[4]).read())
    rc = int(sys.argv[5])
sys.exit(rc)
'''

REPORT = ".pair/junit.xml"          # 故意放在冻结路径 `.pair` 下:报告路径要豁免边界
NO_FRESH = {"PAIR_FRESH_TESTS": ""}


class JunitBase(PairTestCase):

    report_rel = REPORT
    mode = "normal"

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-junit-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        self.runner = self.outside / "runner.py"
        self.runner.write_text(FAKE_RUNNER, encoding="utf-8")
        self.counter = self.outside / "runs"
        self.config = {"test_cmd": self.cmd(self.mode)}
        if self.report_rel:
            self.config["test_report"] = self.report_rel
        super().setUp()

    def cmd(self, mode, *extra):
        return " ".join(shlex.quote(str(a)) for a in
                        [sys.executable, self.runner, self.counter, self.report_rel or "unused.xml", mode] + list(extra))

    def runs(self):
        return sum(1 for _ in open(self.counter)) if self.counter.exists() else 0

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def status(self, env=None, role="tester"):
        r = self.pair("status", role=role, env=env)
        self.assertAccepted(r)
        return r

    def layout(self, green=(), red=()):
        for n in green:
            self.repo.write("tests/%s" % n)
            self.repo.write("src/%s" % n)
        for n in red:
            self.repo.write("tests/%s" % n)

    @staticmethod
    def state_line(out):
        return out.split("测试状态", 1)[1].split("\n", 1)[0]

    @staticmethod
    def new_lines_naming(problem_out, normal_out, needle):
        """`problem_out` 里提到 `needle`、而正常输出里没有的那些行 —— 判"有一条点名它的警告",
        不被"正常输出本来就印报告路径"满足。"""
        normal = set(normal_out.splitlines())
        return [l for l in problem_out.splitlines() if needle in l and l not in normal]


class TestListsRedCases(JunitBase):

    def test_列出红着的用例_不列绿的(self):
        self.layout(green=["A"], red=["B", "C"])
        r = self.status()
        self.assertIn("RED", self.state_line(r.out))
        self.assertIn("tests.B", r.out)
        self.assertIn("tests.C", r.out)
        self.assertNotIn("tests.A", r.out)

    def test_最多列_20_条_其余写另有几条(self):
        self.layout(red=["T%02d" % i for i in range(25)])
        r = self.status()
        listed = [i for i in range(25) if ("tests.T%02d" % i) in r.out]
        self.assertEqual(len(listed), 20, r.out)
        self.assertIn("另有 5 条", r.out)

    def test_全绿时不列(self):
        self.layout(green=["A"])
        r = self.status()
        self.assertIn("GREEN", self.state_line(r.out))
        self.assertNotIn("tests.A", r.out)


class TestNotConfigured(JunitBase):
    """不配 `test_report` 时一切照旧:命令照样写出了一份报告,协议也不读它。"""

    report_rel = None

    def test_不配时不列用例(self):
        self.layout(green=["A"], red=["B"])
        r = self.status()
        self.assertIn("RED", self.state_line(r.out))
        self.assertNotIn("tests.B", r.out)


class TestCaseIdsAndMerging(JunitBase):

    XML = ('<?xml version="1.0"?><testsuites>'
           '<testsuite name="outer"><testsuite name="inner">'
           '<testcase classname="pkg.TestX" name="t_failed"><failure/></testcase>'
           '</testsuite></testsuite>'
           '<testsuite name="second">'
           '<testcase name="solo_error"><error/></testcase>'
           '<testcase classname="pkg.TestX" name="t_skipped"><skipped/></testcase>'
           '<testcase classname="pkg.TestX" name="t_passed"/>'
           '</testsuite></testsuites>')

    def test_ID_与红的判定_嵌套与多个_testsuite_合并(self):
        fixed = self.outside / "fixed.xml"
        fixed.write_text(self.XML, encoding="utf-8")
        r = self.status(env={"PAIR_TEST_CMD": self.cmd("fixed", fixed, 1)})
        self.assertIn("RED", self.state_line(r.out))
        self.assertIn("pkg.TestX.t_failed", r.out, "嵌套 testsuite 里的 failure")
        self.assertIn("solo_error", r.out, "没有 classname 的只用 name;error 算红")
        self.assertNotIn("t_skipped", r.out, "skipped 不算红")
        self.assertNotIn("t_passed", r.out)


class TestDegrades(JunitBase):
    """报告缺失、坏了、或与退出码对不上:警告点名报告路径,GREEN/RED 照旧由退出码定,不列用例,绝不拒绝。"""

    def normal_out(self):
        return self.status(env={"PAIR_FRESH_TESTS": "1"}).out

    def assertDegraded(self, mode, expect):
        self.layout(green=["A"], red=["B"] if expect == "RED" else [])
        normal = self.normal_out()
        r = self.status(env={"PAIR_TEST_CMD": self.cmd(mode)})
        self.assertIn(expect, self.state_line(r.out))
        self.assertNotIn("tests.B", r.out)
        self.assertTrue(self.new_lines_naming(r.text, normal, REPORT), "要有一行警告点名报告路径:\n" + r.text)

    def test_命令没写报告(self):
        self.assertDegraded("none", "RED")

    def test_报告坏了(self):
        self.assertDegraded("garbage", "RED")

    def test_退出码非零而报告全绿(self):
        """⑰:套件跑到一半崩了的形状。"""
        self.assertDegraded("lying-green", "RED")

    def test_退出码为零而报告有红(self):
        """⑰:测试命令吞掉了退出码的形状。"""
        self.layout(green=["A"], red=["B"])
        self.repo.write("src/B")   # 布局全绿 → 退出 0;lying-red 照样把每条写成红
        normal = self.normal_out()
        r = self.status(env={"PAIR_TEST_CMD": self.cmd("lying-red")})
        self.assertIn("GREEN", self.state_line(r.out))
        self.assertNotIn("tests.A", r.out)
        self.assertTrue(self.new_lines_naming(r.text, normal, REPORT), "要有一行警告点名报告路径:\n" + r.text)

    def test_上一次的报告还在而这一次没写_不读上一次的(self):
        self.layout(green=["A"], red=["B"])
        first = self.status()
        self.assertIn("tests.B", first.out, "前提:第一次写了报告、列出了 B")
        r = self.status(env={"PAIR_TEST_CMD": self.cmd("none")})
        self.assertNotIn("tests.B", r.out, "执行之前要删掉旧报告")
        self.assertFalse((self.repo.dir / REPORT).exists())


class TestReuseWithReport(JunitBase):
    """与 W57 对齐:报告路径不进指纹;记录里有报告的哈希,对不上就照常执行。"""

    def setUp(self):
        super().setUp()
        self.layout(green=["A"], red=["B"])
        self.status()
        self.base = self.runs()

    def test_报告没动_复用_照样列出红用例(self):
        r = self.status()
        self.assertEqual(self.runs(), self.base, "报告是产物,不该让指纹每次都变")
        self.assertIn("tests.B", r.out)

    def test_报告被改过_照常执行(self):
        p = self.repo.dir / REPORT
        p.write_text(p.read_text(encoding="utf-8") + "<!-- 被改过 -->", encoding="utf-8")
        self.status()
        self.assertEqual(self.runs(), self.base + 1)

    def test_报告被删了_照常执行(self):
        (self.repo.dir / REPORT).unlink()
        r = self.status()
        self.assertEqual(self.runs(), self.base + 1)
        self.assertIn("tests.B", r.out)


class TestReportNotCommitted(JunitBase):
    """报告放在冻结路径 `.pair/` 下:写权限边界不因它拒绝,交接之后它不在提交里,也还在工作区。"""

    def committed(self):
        return self.repo.git_paths("show", "--name-only", "--format=", "-z", "HEAD")

    def test_spec_与_impl_两次交接都不提交报告(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.pair("handoff", "写了 W1 的失败用例"))
        self.assertIn("tests/W1", self.committed(), "前提:这一次确实提交了测试")
        self.assertNotIn(REPORT, self.committed())
        self.assertTrue((self.repo.dir / REPORT).exists(), "报告留在工作区")
        self.repo.write("src/W1")
        self.assertAccepted(self.pair("handoff", "实现 W1", role="dev"))
        self.assertIn("src/W1", self.committed())
        self.assertNotIn(REPORT, self.committed())
        self.assertNotIn(REPORT, self.repo.git_paths("ls-files", "-z"))


class TestReportOutsideRoles(JunitBase):
    """报告放在两个角色都不拥有的目录:同样不因它拒绝、不提交。"""

    report_rel = "reports/junit.xml"

    def test_交接不因报告拒绝(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.pair("handoff", "写了 W1 的失败用例"))
        self.assertNotIn("reports/junit.xml",
                         self.repo.git_paths("show", "--name-only", "--format=", "-z", "HEAD"))


if __name__ == "__main__":
    unittest.main()
