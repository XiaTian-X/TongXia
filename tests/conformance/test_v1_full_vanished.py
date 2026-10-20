# -*- coding: utf-8 -*-
"""W61:完成时"上一次跑过、这一次没跑"的用例也拦下。

契约「完成时不再跑的用例也拦下」。

**假的全量命令**(同 W59 的写法):读仓库里的 `suite/`,文件名是用例名,内容决定这一次怎么报 ——
`red` 红、`green` 绿、`skip` 带 `<skipped/>`、`gone` 不出现在报告里(没被收集)。`suite/` 由用例以人类身份提交。
门禁 `test_cmd` 前面挂一个仓库外的计数脚本,用来判"只改基线文件不重跑"。
"""

import json
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import EVIDENCE, TEST_CMD, VERIFY_OK, PairTestCase, setup_report, with_loc

FULL_RUNNER = r'''
import os, sys
report = sys.argv[1]
names = sorted(n for n in os.listdir("suite") if not n.startswith("."))
kind = {n: open(os.path.join("suite", n)).read().strip() for n in names}
cases = []
for n in names:
    k = kind[n]
    if k == "gone":
        continue
    body = {"red": '<failure message="red"/>', "skip": "<skipped/>"}.get(k, "")
    cases.append('<testcase classname="suite" name="%s">%s</testcase>' % (n, body))
os.makedirs(os.path.dirname(report), exist_ok=True)
open(report, "w").write('<?xml version="1.0"?><testsuites><testsuite name="full">%s</testsuite></testsuites>' % "".join(cases))
sys.exit(1 if any(kind[n] == "red" for n in names) else 0)
'''
GATE_COUNTER = r'''
import sys
open(sys.argv[1], "a").write("x\n")
'''

FULL_REPORT = ".pair/junit-full.xml"
BASELINE = ".pair/full-baseline.json"
NO_FRESH = {"PAIR_FRESH_TESTS": ""}
PROTOCOL_LEFTOVERS = {".pair/.last-test.log", ".pair/.last-full-test.log", ".pair/.last-brief.md", FULL_REPORT}
ACCEPT_REASON = "suite.B 这一项里有意删掉了,换成了 suite.C"


class VanishBase(PairTestCase):

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-vanish-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        (self.outside / "full.py").write_text(FULL_RUNNER, encoding="utf-8")
        (self.outside / "gate.py").write_text(GATE_COUNTER, encoding="utf-8")
        self.gate = self.outside / "gate"
        q = lambda *a: " ".join(shlex.quote(str(x)) for x in a)
        self.config = {
            "test_cmd": "%s && %s" % (q(sys.executable, self.outside / "gate.py", self.gate), TEST_CMD),
            "full_test_cmd": q(sys.executable, self.outside / "full.py", FULL_REPORT),
            "full_test_report": FULL_REPORT,
        }
        super().setUp()

    # --- 场景 ---------------------------------------------------------
    def suite(self, **cases):
        for name, kind in cases.items():
            self.repo.write("suite/%s" % name, kind)
        self.repo.git("add", "suite")
        self.repo.git("commit", "-q", "-m", "chore: 全量套件的场景")

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def baseline(self):
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK))

    def dev_approve(self, *extra):
        return self.pair("handoff", "approve", "测试没问题", *EVIDENCE, *extra, role="dev")

    def assertCompletionRefused(self, r, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.repo.state()["phase"], "review-test", "本应拒绝完成:\n%r" % r)

    def executed(self):
        p = self.repo.dir / BASELINE
        return json.loads(p.read_text(encoding="utf-8")).get("executed") if p.exists() else None

    def committed_executed(self):
        out = self.repo.git("show", "HEAD:%s" % BASELINE)
        return json.loads(out.stdout.decode("utf-8")).get("executed") if out.returncode == 0 else None

    def leftovers(self):
        out = self.repo.git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.decode("utf-8")
        return sorted(rec[3:] for rec in out.split("\0") if rec and rec[3:] not in PROTOCOL_LEFTOVERS)

    def last_body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")


class TestBaselineFile(VanishBase):

    def test_verify_setup_写入跑过的集合_随提交落地_工作区干净(self):
        self.suite(A="green", B="red", S="skip")
        self.baseline()
        self.assertEqual(self.executed(), ["suite.A", "suite.B"], "跑过的含红的,不含 skipped 的")
        self.assertEqual(self.committed_executed(), ["suite.A", "suite.B"], "基线文件要随 verify-setup 的提交落地")
        self.assertEqual(self.leftovers(), [], "冻结路径下的基线文件不能留在工作区里")

    def test_基线文件不在时照旧放行_完成后写入并提交(self):
        self.suite(A="green", B="green")
        self.repo.advance_to("review-test")
        self.suite(B="gone")
        r = self.dev_approve()
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.repo.state()["phase"], "idle")
        self.assertEqual(self.committed_executed(), ["suite.A"])

    def test_只改基线文件不重跑门禁(self):
        """基线文件排除出 W57 的指纹。"""
        self.suite(A="green")
        self.baseline()
        self.assertAccepted(self.pair("status"))
        before = sum(1 for _ in open(self.gate))
        p = self.repo.dir / BASELINE
        p.write_text(json.dumps({"executed": ["suite.A", "suite.Z"]}), encoding="utf-8")
        self.repo.git("add", BASELINE)
        self.repo.git("commit", "-q", "-m", "chore: 只动基线文件")
        self.assertAccepted(self.pair("status"))
        self.assertEqual(sum(1 for _ in open(self.gate)), before)


class TestVanishedRefused(VanishBase):

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")

    def test_没被收集的用例拒绝完成_点名_什么都没提交(self):
        self.suite(B="gone")
        before = self.repo.commit_count()
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.B", "changes")
        self.assertNotIn("suite.A", r.text)
        self.assertEqual(self.repo.commit_count(), before)
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.executed(), ["suite.A", "suite.B"], "被拒时基线文件不动")

    def test_变成_skipped_的也算不再跑(self):
        self.suite(B="skip")
        self.assertCompletionRefused(self.dev_approve(), "suite.B")

    def test_新增与消失同时出现_两段都点名(self):
        self.suite(A="red", B="gone")
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.A", "suite.B")

    def test_声明之后放行_正文有声明_基线更新为这一次跑过的(self):
        self.suite(B="gone", C="green")
        r = self.dev_approve("--accept-new-failures", ACCEPT_REASON)
        self.assertEqual(self.repo.state()["phase"], "idle", "本应放行:\n%r" % r)
        self.assertIn(ACCEPT_REASON, self.last_body())
        self.assertIn("suite.B", self.last_body())
        self.assertEqual(self.committed_executed(), ["suite.A", "suite.C"])

    def test_对照组_只是多了新用例不拒绝_基线随之更新(self):
        self.suite(C="green")
        r = self.dev_approve()
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.committed_executed(), ["suite.A", "suite.B", "suite.C"])


class TestVanishedReboundGoesToImpl(VanishBase):
    """W59 ⑱ 的同一个坑:被"消失的用例"拒绝之后,打回的 spec 回合不走 W17 捷径。"""

    def test_被拒_打回_只改测试_GREEN_进_impl(self):
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(B="gone")
        self.assertCompletionRefused(self.dev_approve())
        self.assertAccepted(self.pair("handoff", "changes", with_loc("全量里 suite.B 不再被收集"), role="dev"))
        self.repo.write("tests/W1", "补了一句断言说明")
        self.assertAccepted(self.pair("handoff", "按打回意见补了 W1 的说明"))
        self.assertEqual(self.repo.state()["phase"], "impl")


if __name__ == "__main__":
    import unittest
    unittest.main()
