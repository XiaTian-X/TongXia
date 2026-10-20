# -*- coding: utf-8 -*-
"""W59:工作项完成时的全量只拦"新增的红"。

契约「完成时的全量只拦新增的红」(含 spec 回合带声明补的「补充」,开工前审查 ⑱)。

**假的全量命令**:仓库外一个小脚本,读仓库里 `suite/` 下的文件 —— 文件名是用例名,内容 `red` 就是红 —— 写出 JUnit XML
(`classname="suite"`),有红就退出 1。`suite/` 由用例以人类身份直接提交:哪条红、什么时候变红,是用例搭的场景,不经过角色的写权限。
门禁 `test_cmd` 仍是 harness 的布局判定,与 `suite/` 无关 —— 正是"门禁绿、全量红"的形状。
"""

import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import EVIDENCE, VERIFY_OK, PairTestCase, setup_report, with_loc

FULL_RUNNER = r'''
import os, sys
report = sys.argv[1]
names = sorted(n for n in os.listdir("suite") if not n.startswith("."))
red = [n for n in names if open(os.path.join("suite", n)).read().strip() == "red"]
os.makedirs(os.path.dirname(report), exist_ok=True)
if os.path.exists(os.path.join("suite", ".garbage")):
    open(report, "w").write("<testsuites><testsuite><testcase name=")
else:
    cases = "".join('<testcase classname="suite" name="%s">%s</testcase>'
                    % (n, '<failure message="red"/>' if n in red else "") for n in names)
    open(report, "w").write('<?xml version="1.0"?><testsuites><testsuite name="full">%s</testsuite></testsuites>' % cases)
sys.exit(1 if red else 0)
'''

FULL_REPORT = ".pair/junit-full.xml"
NO_FRESH = {"PAIR_FRESH_TESTS": ""}
# 协议自己写、拒绝之后允许留在工作区的东西。
PROTOCOL_LEFTOVERS = {".pair/.last-test.log", ".pair/.last-full-test.log", ".pair/.last-brief.md", FULL_REPORT}
ACCEPT_REASON = "suite.B 依赖的外部服务这周停机,已报人类"


class FullBase(PairTestCase):

    with_report = True

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-full-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        runner = self.outside / "full.py"
        runner.write_text(FULL_RUNNER, encoding="utf-8")
        # 不配报告时,脚本照样写一份 —— 写到仓库外,免得它作为一个越界的未跟踪文件挡住交接(那是 W58 的事)。
        report = FULL_REPORT if self.with_report else str(self.outside / "junit-full.xml")
        self.config = {"full_test_cmd": " ".join(shlex.quote(str(a)) for a in (sys.executable, runner, report))}
        if self.with_report:
            self.config["full_test_report"] = FULL_REPORT
        super().setUp()

    # --- 场景 ---------------------------------------------------------
    def suite(self, **cases):
        """以人类身份把 `suite/` 设成给定的红绿并提交。"""
        for name, color in cases.items():
            self.repo.write("suite/%s" % name, color)
        self.repo.git("add", "suite")
        self.repo.git("commit", "-q", "-m", "chore: 全量套件的场景")

    def baseline(self):
        """tester 跑一次 verify-setup:跑全量、把红着的记成基线。"""
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK))

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def to_review_test(self):
        self.repo.advance_to("review-test")

    def dev_approve(self, *extra):
        return self.pair("handoff", "approve", "测试没问题", *EVIDENCE, *extra, role="dev")

    def assertCompletionRefused(self, r, *needles):
        """退出码 2 是"放行但全量红"—— 拒绝要看阶段没动。"""
        self.assertRefused(r, *needles)
        self.assertEqual(self.repo.state()["phase"], "review-test", "本应拒绝完成:\n%r" % r)

    def leftovers(self):
        """工作区里协议日志与报告之外的改动。"""
        out = self.repo.git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.decode("utf-8")
        return sorted(rec[3:] for rec in out.split("\0") if rec and rec[3:] not in PROTOCOL_LEFTOVERS)

    def last_body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")


class TestNewFailureRefused(FullBase):

    def setUp(self):
        super().setUp()
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()
        self.suite(B="red")                 # 这个工作项期间,B 变红了

    def test_新增的红拒绝完成_点名新增的_不点名原来红的(self):
        before = self.repo.commit_count()
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.B", "changes")
        self.assertNotIn("suite.A", r.text, "原来就红的不该算进新增")
        self.assertEqual(self.repo.commit_count(), before, "拒绝在提交之前")
        self.assertEqual(self.repo.state()["phase"], "review-test")

    def test_拒绝之后工作区与交接之前相同(self):
        """⑱:`PLAN.md` 不能被勾上 —— 冻结路径留在工作区,下一次交接会被拦下。"""
        self.dev_approve()
        self.assertEqual(self.leftovers(), [])

    def test_声明之后放行_声明进提交正文_基线更新为这一次的结果(self):
        r = self.dev_approve("--accept-new-failures", ACCEPT_REASON)
        self.assertNotEqual(self.repo.state()["phase"], "review-test", "本应放行:\n%r" % r)
        self.assertIn(r.code, (0, 2), r)
        self.assertIn(ACCEPT_REASON, self.last_body())
        self.assertEqual(self.repo.state().get("full_failures"), ["suite.A", "suite.B"])


class TestOnlyOldFailures(FullBase):

    def setUp(self):
        super().setUp()
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()

    def test_只有原来就红的_放行_退出码_2(self):
        r = self.dev_approve()
        self.assertEqual(r.code, 2, r)
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_没有新增时给了声明_也不拒绝_也不写进正文(self):
        r = self.dev_approve("--accept-new-failures", ACCEPT_REASON)
        self.assertEqual(r.code, 2, r)
        self.assertNotIn(ACCEPT_REASON, self.last_body())

    def test_原来红的修好了_完成后基线里没有它(self):
        self.suite(A="green")
        r = self.dev_approve()
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.repo.state().get("full_failures"), [])


class TestBaselineRecorded(FullBase):

    def test_verify_setup_跑全量后写入基线(self):
        self.suite(A="red", B="green")
        self.baseline()
        self.assertEqual(self.repo.state().get("full_failures"), ["suite.A"])

    def test_没有基线时与今天相同_并把这一次记成基线(self):
        """harness 的初始状态没有 `full_failures` 这个键 —— 老状态,按 null。"""
        self.assertNotIn("full_failures", self.repo.state(), "前提:老状态没有这个键")
        self.suite(A="red", B="green")
        self.to_review_test()
        self.suite(B="red")
        r = self.dev_approve()
        self.assertEqual(r.code, 2, r)
        self.assertEqual(self.repo.state()["phase"], "idle")
        self.assertEqual(self.repo.state().get("full_failures"), ["suite.A", "suite.B"])


class TestListCapped(FullBase):

    def test_新增的红最多列_20_条(self):
        self.suite(**{"T%02d" % i: "green" for i in range(25)})
        self.baseline()
        self.to_review_test()
        self.suite(**{"T%02d" % i: "red" for i in range(25)})
        r = self.dev_approve()
        self.assertCompletionRefused(r)
        listed = [i for i in range(25) if ("suite.T%02d" % i) in r.text]
        self.assertEqual(len(listed), 20, r.text)


class TestWithoutReport(FullBase):
    """不配 `full_test_report`:与今天完全相同。"""

    with_report = False

    def test_新增的红照旧只报告(self):
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()
        self.suite(B="red")
        r = self.dev_approve()
        self.assertEqual(r.code, 2, r)
        self.assertEqual(self.repo.state()["phase"], "idle")


class TestReportUnreadable(FullBase):

    def test_完成时报告读不出_照旧只报告(self):
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()
        self.repo.write("suite/.garbage", "1")
        self.suite(B="red")
        r = self.dev_approve()
        self.assertEqual(r.code, 2, r)
        self.assertEqual(self.repo.state()["phase"], "idle")


class TestReboundGoesToImpl(FullBase):
    """⑱:被拒 → dev 打回 → tester 只改测试、GREEN 交接 → 进 impl(由 dev 修),不走 W17 捷径回 review-test。"""

    def rebound_and_fix_tests(self):
        r = self.pair("handoff", "changes", with_loc("全量里 suite.B 新红了,实现要修"), role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "spec")
        self.repo.write("tests/W1", "补了一句断言说明")
        r = self.pair("handoff", "按打回意见补了 W1 的说明")
        self.assertAccepted(r)
        return self.repo.state()["phase"]

    def test_有新增的红时_修正回合进_impl(self):
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()
        self.suite(B="red")
        self.assertCompletionRefused(self.dev_approve())
        self.assertEqual(self.rebound_and_fix_tests(), "impl")

    def test_对照组_没有新增的红时照旧走捷径(self):
        self.suite(A="red", B="green")
        self.baseline()
        self.to_review_test()
        self.assertEqual(self.rebound_and_fix_tests(), "review-test")


if __name__ == "__main__":
    import unittest
    unittest.main()
