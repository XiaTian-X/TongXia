# -*- coding: utf-8 -*-
"""W63:跑过的集合只要全量报告读得出就比;新增的红仍要求与退出码一致。

契约「跑过的集合读得出就比」。

**假的全量命令**(沿用 W61 的写法):读仓库里的 `suite/`,文件名是用例名,内容决定这一次怎么报 ——
`red` 红、`green` 绿、`gone` 不出现在报告里;另有两个开关文件(以人类身份提交):
`suite/.crash` 存在时 —— 退出 1,报告里只写到第一个 `gone` 之前、全写成绿(套件跑到一半崩了的形状);
`suite/.swallow` 存在时 —— 照实写红,但退出 0(命令吞掉了退出码);`suite/.garbage` 存在时写一份坏 XML。
"""

import json
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
kind = {n: open(os.path.join("suite", n)).read().strip() for n in names}
crash = os.path.exists(os.path.join("suite", ".crash"))
swallow = os.path.exists(os.path.join("suite", ".swallow"))
os.makedirs(os.path.dirname(report), exist_ok=True)
if os.path.exists(os.path.join("suite", ".garbage")):
    open(report, "w").write("<testsuites><testsuite><testcase name=")
    sys.exit(1)
cases = []
for n in names:
    k = kind[n]
    if k == "gone":
        if crash:
            break
        continue
    red = (k == "red") and not crash
    cases.append('<testcase classname="suite" name="%s">%s</testcase>' % (n, '<failure message="red"/>' if red else ""))
open(report, "w").write('<?xml version="1.0"?><testsuites><testsuite name="full">%s</testsuite></testsuites>' % "".join(cases))
if crash:
    sys.exit(1)
if swallow:
    sys.exit(0)
sys.exit(1 if any(kind[n] == "red" for n in names) else 0)
'''

FULL_REPORT = ".pair/junit-full.xml"
BASELINE = ".pair/full-baseline.json"
NO_FRESH = {"PAIR_FRESH_TESTS": ""}
PROTOCOL_LEFTOVERS = {".pair/.last-test.log", ".pair/.last-full-test.log", ".pair/.last-brief.md", FULL_REPORT}


class ExecutedBase(PairTestCase):

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-executed-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        (self.outside / "full.py").write_text(FULL_RUNNER, encoding="utf-8")
        self.config = {
            "full_test_cmd": " ".join(shlex.quote(str(a)) for a in (sys.executable, self.outside / "full.py", FULL_REPORT)),
            "full_test_report": FULL_REPORT,
        }
        super().setUp()

    def suite(self, **cases):
        for name, kind in cases.items():
            self.repo.write("suite/%s" % name, kind)
        self.repo.git("add", "suite")
        self.repo.git("commit", "-q", "-m", "chore: 全量套件的场景")

    def switch(self, name):
        self.repo.write("suite/.%s" % name, "1")
        self.repo.git("add", "suite")
        self.repo.git("commit", "-q", "-m", "chore: 打开 %s" % name)

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def baseline(self, role="tester"):
        self.repo.write("docs/reviews/setup-verification-%s.md" % role, setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK, role=role))

    def dev_approve(self, *extra):
        return self.pair("handoff", "approve", "测试没问题", *EVIDENCE, *extra, role="dev")

    def assertCompletionRefused(self, r, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.repo.state()["phase"], "review-test", "本应拒绝完成:\n%r" % r)

    def executed(self):
        p = self.repo.dir / BASELINE
        return json.loads(p.read_text(encoding="utf-8")).get("executed") if p.exists() else None

    def leftovers(self):
        out = self.repo.git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.decode("utf-8")
        return sorted(rec[3:] for rec in out.split("\0") if rec and rec[3:] not in PROTOCOL_LEFTOVERS)


class TestCrashHalfway(ExecutedBase):
    """①:套件跑到一半崩了 —— 退出 1、报告只有崩之前的、一条红都没有。"""

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green", C="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(B="gone")       # B 之后(含 B)都没跑到
        self.switch("crash")

    def test_拒绝完成_点名没跑到的_什么都没提交(self):
        before = self.repo.commit_count()
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.B", "suite.C")
        self.assertNotIn("suite.A", r.text.split("拒绝完成", 1)[-1], "跑到了的不该算消失")
        self.assertEqual(self.repo.commit_count(), before)
        self.assertEqual(self.leftovers(), [])

    def test_文案说明红用例这一次没有列出(self):
        """只剩"不再跑"一段会让人以为红是假的。"""
        r = self.dev_approve()
        self.assertCompletionRefused(r, "没有列出")

    def test_被拒_打回_只改测试_GREEN_进_impl(self):
        """④:⑱ 判"上一次全量有没有问题"时同一条规则。"""
        self.assertCompletionRefused(self.dev_approve())
        self.assertAccepted(self.pair("handoff", "changes", with_loc("全量跑到一半崩了"), role="dev"))
        self.repo.write("tests/W1", "补了一句断言说明")
        self.assertAccepted(self.pair("handoff", "按打回意见补了 W1 的说明"))
        self.assertEqual(self.repo.state()["phase"], "impl")


class TestSwallowedExitCode(ExecutedBase):
    """②:命令吞掉了退出码 —— 退出 0、报告里有红、跑过的集合完整。不因消失拒绝;新增的红照旧按 ⑰ 不算。"""

    def test_不因消失拒绝_也不按集合拦新增的红(self):
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(B="red")
        self.switch("swallow")
        r = self.dev_approve()
        self.assertEqual(self.repo.state()["phase"], "idle", "本应放行:\n%r" % r)


class TestNewFailuresStillNeedConsistency(ExecutedBase):
    """新增的红不放宽:崩溃形状下,报告"无红"不可信,不列红用例、不按集合拦新增 —— 拒绝只来自消失的那些。"""

    def test_崩溃时不列红用例(self):
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(A="red", B="gone")
        self.switch("crash")
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.B")
        self.assertNotIn("suite.A", r.text)


class TestVerifySetupWithInconsistentReport(ExecutedBase):
    """③:`verify-setup` 遇到对不上的报告也写基线文件。"""

    def test_崩溃形状的报告也写进基线(self):
        self.suite(A="green", B="gone", C="green")
        self.switch("crash")
        self.baseline()
        self.assertEqual(self.executed(), ["suite.A"])
        self.assertEqual(self.leftovers(), [])


class TestUnreadableReport(ExecutedBase):
    """⑤:报告读不出照旧不知道、不拦。"""

    def test_坏的_XML_照旧放行(self):
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.switch("garbage")
        r = self.dev_approve()
        self.assertEqual(self.repo.state()["phase"], "idle", "本应放行:\n%r" % r)


if __name__ == "__main__":
    import unittest
    unittest.main()
