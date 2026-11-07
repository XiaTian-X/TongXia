# -*- coding: utf-8 -*-
"""W81:cover 新增的用例确实跑了(路线图 P0-1 ③)。

契约「cover 新增的用例确实跑了」。

**假门禁**:仓库外一个小脚本当 `test_cmd`,`tests/` 下每个文件是一条用例,ID 是 `tests.<文件名>`,按文件内容决定这条用例怎样:
含 `hidden` = 不被收集(报告里没有它),含 `skip` = 被跳过(带 `<skipped/>`),含 `red` = 红,其余都是绿的跑过。
按"模式"写 `test_report`:`normal` 照实写,`garbage` 写一份坏 XML(读不出)。

**认领时基线**由人类在认领之前提交 `.pair/full-baseline.json`(`executed` 是 `tests.A`、`tests.B`)。
`.pair/` 在冻结路径下,"工作项中途基线被改写"按人类改写并提交来造(中途的 `verify-setup` 也是这样提交的):HEAD 里的基线与认领时那份不同。

被拒时一律断言提交数与 `.pair/state.json` 不变。
"""

import json
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import EVIDENCE, PairTestCase, with_loc

GATE = r'''
import os, sys
report, mode = sys.argv[1], sys.argv[2]
cases, red = [], False
for n in sorted(os.listdir("tests")):
    if n.startswith("."):
        continue
    text = open(os.path.join("tests", n), encoding="utf-8").read()
    if "hidden" in text:
        continue
    if "skip" in text:
        inner = "<skipped/>"
    elif "red" in text:
        inner, red = '<failure message="red"/>', True
    else:
        inner = ""
    cases.append('<testcase classname="tests" name="%s">%s</testcase>' % (n, inner))
d = os.path.dirname(report)
if d:
    os.makedirs(d, exist_ok=True)
if mode == "normal":
    open(report, "w").write('<?xml version="1.0"?><testsuite name="gate">%s</testsuite>' % "".join(cases))
elif mode == "garbage":
    open(report, "w").write("<testsuite><testcase name=")
sys.exit(1 if red else 0)
'''

REPORT = ".pair/gate.xml"
BASELINE = ".pair/full-baseline.json"
STATE = ".pair/state.json"

PLAN = """# 规划

## 工作项

- [ ] **C1** [cover] — 为已有行为补测试
  - 对应契约:`docs/CONTRACT.md` → W1
- [ ] **W1** [feature] — 一个 feature
  - 对应契约:`docs/CONTRACT.md` → W1
"""


def baseline_text(*ids):
    return json.dumps({"executed": sorted(ids)}, indent=1) + "\n"


class CoverBase(PairTestCase):

    mode = "normal"
    report = REPORT
    baseline = baseline_text("tests.A", "tests.B")     # None = 认领时没有基线文件

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-cover-exec-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        (self.outside / "gate.py").write_text(GATE, encoding="utf-8")
        cmd = " ".join(shlex.quote(str(a)) for a in
                       [sys.executable, self.outside / "gate.py", self.report or "unused.xml", self.mode])
        self.config = {"test_cmd": cmd}
        if self.report:
            self.config["test_report"] = self.report
        super().setUp()
        self.repo.write("tests/A", "已有用例 A\n")
        self.repo.write("tests/B", "已有用例 B\n")
        if self.baseline is not None:
            self.repo.write(BASELINE, self.baseline)
        self.repo.set_plan(PLAN)                        # 连同上面几个文件一起由人类提交

    # --- 动作 ---------------------------------------------------------
    def pair(self, *args, role="tester"):
        return self.repo.run(*args, role=role, env={"PAIR_FRESH_TESTS": "1"})

    def claim(self, item="C1"):
        self.assertAccepted(self.pair("claim", item))
        if item == "C1":
            self.repo.write_cover_note("C1")

    def spec(self, *extra):
        return self.pair("handoff", "为已有行为补测试", *extra)

    def human_commit(self, rel, text, msg="人类直接提交(搭场景)"):
        self.repo.write(rel, text)
        self.repo.git("add", "--", rel)
        self.repo.git("commit", "-q", "-m", msg)

    # --- 观察 ---------------------------------------------------------
    def phase(self):
        return self.repo.state()["phase"]

    def body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")

    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(STATE)

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒时提交数或状态文件变了")

    def assertPassed(self, r):
        self.assertAccepted(r)
        self.assertEqual(self.phase(), "review-test")

    def assertNoNewTestRefused(self):
        before = self.snapshot()
        self.assertNothingHappened(self.spec(), before, "认领")


class TestNewTestRan(CoverBase):

    def test_加一条新用例并跑过_放行_正文写_1_条(self):
        self.claim()
        self.repo.write("tests/C", "新用例 C\n")
        self.assertPassed(self.spec())
        self.assertIn("新用例(跑过): 1 条", self.body())

    def test_两条新用例_正文写_2_条(self):
        self.claim()
        self.repo.write("tests/C", "新用例 C\n")
        self.repo.write("tests/D", "新用例 D\n")
        self.assertPassed(self.spec())
        self.assertIn("新用例(跑过): 2 条", self.body())


class TestNoNewTestRan(CoverBase):
    """碰了测试文件,但门禁报告里没有一条新跑起来的用例。"""

    def test_新用例被跳过_被拒(self):
        self.claim()
        self.repo.write("tests/C", "新用例 C,skip\n")
        self.assertNoNewTestRefused()

    def test_新用例没被收集_被拒(self):
        self.claim()
        self.repo.write("tests/C", "新用例 C,hidden\n")
        self.assertNoNewTestRefused()

    def test_只改已有用例_被拒(self):
        self.claim()
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertNoNewTestRefused()


class TestRenameIsNotNew(CoverBase):
    """把 tests/B 改名成 tests/B2:声明了改名就不算新增;同样的改动不声明,B2 就是新用例(对照组)。"""

    def rename(self):
        self.claim()
        self.repo.delete("tests/B")
        self.repo.write("tests/B2", "已有用例 B\n")

    def test_只有声明过的改名_没有新增_被拒(self):
        self.rename()
        before = self.snapshot()
        r = self.spec("--renamed", "tests.B=tests.B2", "--allow-deletion", "B 改名成 B2")
        self.assertNothingHappened(r, before)

    def test_对照组_不声明改名_B2_算新用例_放行(self):
        self.rename()
        self.assertPassed(self.spec("--allow-deletion", "B 改名成 B2"))
        self.assertIn("新用例(跑过): 1 条", self.body())


class TestReworkRound(CoverBase):

    def test_打回后的修正回合只改已有用例_第一回合的新用例还在跑_放行(self):
        self.claim()
        self.repo.write("tests/C", "新用例 C\n")
        self.assertPassed(self.spec())
        self.assertAccepted(self.pair("handoff", "changes", with_loc("C 的断言写得太宽"), role="dev"))
        self.assertEqual(self.phase(), "spec")
        self.repo.write("tests/A", "已有用例 A,收紧断言\n")
        self.assertPassed(self.pair("handoff", "按评审收紧断言"))
        self.assertIn("新用例(跑过): 1 条", self.body())


class TestWorkspaceBaselineIgnored(CoverBase):
    """认领之后人类改写并提交了基线:判法照认领时那份。两个方向都造。"""

    def test_新用例被写进了之后的基线_照旧算新_放行(self):
        self.claim()
        self.human_commit(BASELINE, baseline_text("tests.A", "tests.B", "tests.C"))
        self.repo.write("tests/C", "新用例 C\n")
        self.assertPassed(self.spec())

    def test_已有用例从之后的基线里删掉_照旧不算新_被拒(self):
        self.claim()
        self.human_commit(BASELINE, baseline_text("tests.B"))
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertNoNewTestRefused()


class TestNoReportConfigured(CoverBase):

    report = None

    def test_没配_test_report_不判_只改已有用例照常放行(self):
        self.claim()
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())


class TestReportUnreadable(CoverBase):

    mode = "garbage"

    def test_门禁报告读不出_不判(self):
        self.claim()
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())


class TestNoBaselineAtClaim(CoverBase):

    baseline = None

    def test_认领时没有基线文件_不判(self):
        self.claim()
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())

    def test_认领之后才有基线_照旧按认领时没有_不判(self):
        """认领之后人类才提交了基线:认领那一刻没有,读不出,不判。"""
        self.claim()
        self.human_commit(BASELINE, baseline_text("tests.A", "tests.B"))
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())


class TestBadBaselineAtClaim(CoverBase):

    baseline = "{这不是 JSON\n"

    def test_认领时基线不是合法_JSON_不判(self):
        self.claim()
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())


class TestNoItemBase(CoverBase):

    def test_状态里没有_item_base_不判(self):
        self.claim()
        st = self.repo.state()
        st["item_base"] = None
        self.human_commit(STATE, json.dumps(st, ensure_ascii=False, indent=2))
        self.repo.write("tests/A", "已有用例 A,多一条断言\n")
        self.assertPassed(self.spec())


class TestFeatureNotJudged(CoverBase):

    def test_feature_的_spec_只改红已有用例_照常放行(self):
        self.claim("W1")
        self.repo.write("tests/A", "已有用例 A,改成 red\n")
        self.assertAccepted(self.spec())
        self.assertEqual(self.phase(), "impl")


if __name__ == "__main__":
    import unittest
    unittest.main()
