# -*- coding: utf-8 -*-
"""红绿不变量、评审裁决强制、死锁闸、工作项认领。"""

from harness import EVIDENCE, PairTestCase, with_loc


class TestRedGreen(PairTestCase):

    def test_spec_阶段绿着交接被拒绝(self):
        # 完成 W1 后回到 spec,此时 tests/W1 与 src/W1 配对,整体是绿的。
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", *EVIDENCE, role="dev")
        self.repo.run("claim", "W2", role="tester")
        r = self.repo.run("handoff", "我没写新用例", role="tester")
        self.assertRefused(r, "必须是 RED")

    def test_impl_阶段红着交接被拒绝(self):
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "还没做完", role="dev")
        self.assertRefused(r, "必须是 GREEN")


class TestReviewVerdict(PairTestCase):

    def test_评审必须给裁决(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "看着还行", role="tester")
        self.assertRefused(r, "必须给出裁决")

    def test_空手_approve_被拒绝(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "approve", role="tester")
        self.assertRefused(r, "必须附理由")


class TestDeadlockGate(PairTestCase):

    def test_同一工作项打回三次触发死锁闸(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("问题一"), role="tester"))
        self.assertAccepted(self.repo.run("handoff", "修好了", role="dev"))
        self.repo.append_decision("W1")     # 第二次打回必须留下结论
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("问题二"), role="tester"))
        self.assertAccepted(self.repo.run("handoff", "又修好了", role="dev"))
        r = self.repo.run("handoff", "changes", with_loc("问题三"), role="tester")
        self.assertRefused(r, "打回", "交给人类")

    def test_打回计数绑定到工作项(self):
        self.repo.advance_to("review-impl")
        self.repo.run("handoff", "changes", with_loc("问题一"), role="tester")
        self.assertEqual(self.repo.state()["changes_count"], 1)
        # 完成本项后重新认领,计数应归零
        self.repo.run("handoff", "修好了", role="dev")
        self.repo.run("handoff", "approve", "这次没问题", *EVIDENCE, role="tester")
        self.repo.run("handoff", "approve", "测试也没问题", *EVIDENCE, role="dev")
        self.repo.run("claim", "W2", role="tester")
        self.assertEqual(self.repo.state()["changes_count"], 0)


class TestClaim(PairTestCase):

    def test_未认领工作项就交接被拒绝(self):
        self.repo.write("tests/W1")
        r = self.repo.run("handoff", "写了个用例", role="tester")
        self.assertRefused(r, "还没有认领工作项")

    def test_认领不存在的工作项被拒绝(self):
        r = self.repo.run("claim", "W99", role="tester")
        self.assertRefused(r, "没有工作项")

    def test_dev_不能认领(self):
        r = self.repo.run("claim", "W1", role="dev")
        self.assertRefused(r, "tester 的职责")

    def test_不能中途改领别的工作项(self):
        self.repo.run("claim", "W1", role="tester")
        r = self.repo.run("claim", "W2", role="tester")
        self.assertRefused(r, "还在进行中")

    def test_不能重复认领已完成的工作项(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", *EVIDENCE, role="dev")
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "已经完成")
