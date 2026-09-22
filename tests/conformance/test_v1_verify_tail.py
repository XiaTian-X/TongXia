# -*- coding: utf-8 -*-
"""W27:verify-setup 的结尾要看另一方。

契约「verify-setup 的结尾要看另一方」。第十一轮 tester 通过校验、看到"现在可以认领工作项了",
紧接着 `claim` 被拒 —— W19 起认领要两个角色的校验都作数。本仓库第十二轮开工时又原样发生了一次。

**判据只看结尾那一段**(`开工前校验全部通过` 之后):"点名另一方"若在整段输出里找角色名,
警告与路径里本来就可能出现 `tester`/`dev`。每条"只有一方"的用例都配一条两方都作数的对照。
"""

from harness import VERIFY_OK, PairTestCase, setup_report

CLAIM_OK = "现在可以认领工作项了"
PASSED = "开工前校验全部通过"
CONTRACT = "docs/CONTRACT.md"
PLAN = "docs/PLAN.md"


class TailBase(PairTestCase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def verify(self, role):
        self.repo.write("docs/reviews/setup-verification-%s.md" % role, self.REPORT)
        r = self.repo.run(*VERIFY_OK, role=role)
        self.assertAccepted(r)
        self.assertIn(PASSED, r.text, "这一句两种情况都照旧出现")
        return r.text.split(PASSED, 1)[1]

    def change_contract(self):
        self.repo.set_plan(self.repo.read(PLAN),
                           contract=self.repo.read(CONTRACT) + "\n**补充** 人类改了一句。\n")


class TestOnlyOneSideVerified(TailBase):

    def test_只有_tester_通过时不说可以认领_点名_dev(self):
        """第十一轮与本仓库第十二轮的原样。"""
        tail = self.verify("tester")
        self.assertNotIn(CLAIM_OK, tail)
        self.assertIn("dev", tail)
        self.assertIn("verify-setup", tail)

    def test_只有_dev_通过时不说可以认领_点名_tester(self):
        tail = self.verify("dev")
        self.assertNotIn(CLAIM_OK, tail)
        self.assertIn("tester", tail)

    def test_另一方过期也算不作数(self):
        """另一方校验过、但契约之后变了 —— 不作数的另一种来源,不只是"从没校验过"。"""
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        tail = self.verify("tester")
        self.assertNotIn(CLAIM_OK, tail)
        self.assertIn("dev", tail)

    def test_提示说的与_claim_的判定一致(self):
        """结尾不说可以认领时,认领确实被拒 —— 只改提示,判定一个字不动。"""
        self.verify("tester")
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "dev")


class TestBothSidesVerified(TailBase):

    def test_两方都作数时照旧说可以认领(self):
        self.verify("dev")
        tail = self.verify("tester")
        self.assertIn(CLAIM_OK, tail)
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_后跑的是_dev_时也照旧(self):
        self.verify("tester")
        self.assertIn(CLAIM_OK, self.verify("dev"))
