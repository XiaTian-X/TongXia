# -*- coding: utf-8 -*-
"""W60:回合内只跑受影响的测试。

契约「回合内只跑受影响的测试」。

**怎么看出跑的是哪一条**:都在仓库外 ——
- 假选择器 `affected_test_cmd`:把收到的每个参数一行一个写进 `selected`(每次调用前写一行 `---`),再跑 harness 原来的布局判定(红绿照旧);
- 门禁 `test_cmd`:先往 `gate` 追加一行,再跑同样的判定。
全量命令写一份全绿的 JUnit 报告 —— 只为让"配了 `full_test_cmd` 与 `full_test_report`"这一前提成立。
"""

import json
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import TEST_CMD, VERIFY_OK, PairTestCase, setup_report

SELECTOR = r'''
import sys
with open(sys.argv[1], "a") as f:
    f.write("---\n")
    for a in sys.argv[2:]:
        f.write(a + "\n")
'''
GATE = r'''
import sys
open(sys.argv[1], "a").write("x\n")
'''
FULL = r'''
import os, sys
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
open(sys.argv[1], "w").write('<?xml version="1.0"?><testsuites><testsuite name="full"><testcase classname="suite" name="ok"/></testsuite></testsuites>')
'''
FULL_REPORT = ".pair/junit-full.xml"
NO_FRESH = {"PAIR_FRESH_TESTS": ""}


def q(*parts):
    return " ".join(shlex.quote(str(p)) for p in parts)


class AffectedBase(PairTestCase):

    full = True          # 配不配全量兜底
    full_report = True

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-affected-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        for name, body in (("sel.py", SELECTOR), ("gate.py", GATE), ("full.py", FULL)):
            (self.outside / name).write_text(body, encoding="utf-8")
        self.selected = self.outside / "selected"
        self.gate = self.outside / "gate"
        self.config = {
            "test_cmd": "%s && %s" % (q(sys.executable, self.outside / "gate.py", self.gate), TEST_CMD),
            "affected_test_cmd": "%s {paths} && %s" % (q(sys.executable, self.outside / "sel.py", self.selected), TEST_CMD),
        }
        if self.full:
            self.config["full_test_cmd"] = q(sys.executable, self.outside / "full.py", FULL_REPORT)
        if self.full_report:
            self.config["full_test_report"] = FULL_REPORT
        super().setUp()

    # --- 观察 ---------------------------------------------------------
    def calls(self):
        """选择器每次被调用时收到的参数列表。"""
        if not self.selected.exists():
            return []
        blocks = self.selected.read_text(encoding="utf-8").split("---\n")[1:]
        return [[l for l in b.split("\n") if l] for b in blocks]

    def last_call(self):
        calls = self.calls()
        self.assertTrue(calls, "选择器一次都没被调用 —— 门禁没走 affected_test_cmd")
        return calls[-1]

    def gate_runs(self):
        return sum(1 for _ in open(self.gate)) if self.gate.exists() else 0

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def status(self, role="tester", env=None):
        r = self.pair("status", role=role, env=env)
        self.assertAccepted(r)
        return r

    def human_commit(self, *rels, message="chore: 人类的提交"):
        self.repo.git("add", "--", *rels)
        self.repo.git("commit", "-q", "-m", message)


class TestSelectorUsedDuringItem(AffectedBase):

    def test_工作项进行中门禁执行选择器_路径是本工作项改动的(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.status()
        self.assertEqual(len(self.calls()), 1, "工作项进行中、有改动,门禁该走选择器")
        self.assertEqual(self.gate_runs(), 0)
        self.assertIn("tests/W1", self.last_call())

    def test_协议产物不进路径(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.repo.write("docs/reviews/W1-review-impl.md", "# 评审\n")
        self.repo.write("docs/notes/W1.md", "# 笔记\n")
        self.repo.write(".pair/.last-brief.md", "# 简报\n")
        self.status()
        paths = self.last_call()
        self.assertEqual(paths, ["tests/W1"], "评审目录、记忆层、状态与协议日志都不该进路径:%s" % paths)

    def test_删除的文件不进路径(self):
        self.repo.write("src/old")
        self.human_commit("src/old")
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.repo.delete("src/old")
        self.status()
        self.assertNotIn("src/old", self.last_call())
        self.assertIn("tests/W1", self.last_call())

    def test_从认领起算_dev_回合里有_tester_写的测试(self):
        """只算本回合(相对 HEAD)的实现在这里只给 `src/W1`。"""
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.pair("handoff", "写了 W1 的失败用例"))
        self.repo.write("src/W1")
        self.status(role="dev")
        self.assertEqual(sorted(self.last_call()), ["src/W1", "tests/W1"])

    def test_路径逐个转义(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W 1")
        self.status()
        self.assertIn("tests/W 1", self.last_call(), "带空格的路径要作为一个参数传过去")


class TestFallsBackToGate(AffectedBase):

    def assertGate(self, **kw):
        before = len(self.calls())
        self.status(**kw)
        self.assertEqual(len(self.calls()), before, "这里不该走选择器")

    def test_空闲时(self):
        self.repo.write("tests/W9")
        self.assertGate()
        self.assertEqual(self.gate_runs(), 1)

    def test_PAIR_TEST_CMD_覆盖时(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.assertGate(env={"PAIR_TEST_CMD": TEST_CMD})

    def test_认领之后还没有改动(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertGate()
        self.assertEqual(self.gate_runs(), 1)

    def test_路径超过_200_条(self):
        self.assertAccepted(self.pair("claim", "W1"))
        for i in range(201):
            self.repo.write("src/many/f%03d" % i)
        self.assertGate()
        self.assertEqual(self.gate_runs(), 1)

    def test_路径正好_200_条仍走选择器(self):
        """对照组:上一条若是"凡是很多就退回",这里也会退回。"""
        self.assertAccepted(self.pair("claim", "W1"))
        for i in range(200):
            self.repo.write("src/many/f%03d" % i)
        self.status()
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(len(self.last_call()), 200)

    def test_老状态没有_item_base(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertIn("item_base", self.repo.state(), "前提:认领时记下了 item_base")
        st = self.repo.state()
        del st["item_base"]
        (self.repo.dir / ".pair" / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        self.human_commit(".pair/state.json", message="chore: 模拟老状态")
        self.repo.write("tests/W1")
        self.assertGate()
        self.assertEqual(self.gate_runs(), 1)


class TestNoFullSuiteFallsBack(AffectedBase):
    """第 1 层没有第 2 层兜底:运行时一律用门禁。"""

    full_report = False

    def test_没配全量报告时工作项进行中也走门禁(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.status()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.gate_runs(), 1)


class VerifyBase(AffectedBase):

    def verify(self):
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        return self.pair(*VERIFY_OK)


class TestVerifySetupWithBackstop(VerifyBase):

    def test_对照组_两个键都配时_verify_setup_通过(self):
        self.assertAccepted(self.verify())


class TestVerifySetupWithoutFullCmd(VerifyBase):

    full = False
    full_report = False

    def test_没配全量命令时_verify_setup_失败并说明(self):
        self.assertRefused(self.verify(), "affected_test_cmd", "full_test_cmd")


class TestVerifySetupWithoutFullReport(VerifyBase):

    full_report = False

    def test_没配全量报告时_verify_setup_失败并说明(self):
        self.assertRefused(self.verify(), "affected_test_cmd", "full_test_report")


class TestReuseAcrossCommands(AffectedBase):

    def test_status_与紧跟的_handoff_只执行一次选择器(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.repo.write("tests/W1")
        self.status()
        self.assertAccepted(self.pair("handoff", "写了 W1 的失败用例"))
        self.assertEqual(len(self.calls()), 1, "同样的内容、同样的命令,第二次复用(W57)")


if __name__ == "__main__":
    import unittest
    unittest.main()
