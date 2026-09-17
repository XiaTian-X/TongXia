# -*- coding: utf-8 -*-
"""W19:claim 看两个角色的开工前校验。

契约「claim 看两个角色的开工前校验」。W13 起校验按角色记,但只有 tester 能 `claim`,
dev 那一份没有任何时机被强制刷新 —— 第五轮 dev 的每一次 `status` 都打"校验不作数"。
照契约写实现的是 dev,W13 那条理由对它一字不差地成立。

**以及谁来解锁**(W19 的 spec 回合带声明补的):dev 那一份过期时,唯一能解锁的是 dev,
而 idle 的归属写死是 tester —— 驱动器会反复调度 tester、tester 反复被拒。
所以 idle 时 tester 作数、dev 过期,归属是 dev。

**判据**:`claim` 的退出码与拒绝文案里点名的角色;`whose-turn` 的那一行;`status` 的归属那一行。
状态里校验记录的键名一次都不碰。
"""

import unittest

from harness import PairTestCase, VERIFY_OK, setup_report

CONTRACT = "docs/CONTRACT.md"
PLAN = "docs/PLAN.md"


class BothRolesBase(PairTestCase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def verify(self, role):
        self.repo.write("docs/reviews/setup-verification-%s.md" % role, self.REPORT)
        self.assertAccepted(self.repo.run(*VERIFY_OK, role=role))

    def change_contract(self):
        self.repo.set_plan(self.repo.read(PLAN),
                           contract=self.repo.read(CONTRACT) + "\n**补充** 人类改了一句。\n")

    def claim(self):
        return self.repo.run("claim", "W1", role="tester")

    def whose_turn(self):
        r = self.repo.run("whose-turn", role="tester")
        self.assertAccepted(r)
        return r.out.strip()


class TestClaimLooksAtBothRoles(BothRolesBase):

    def test_两个角色都作数时放行(self):
        self.verify("tester")
        self.verify("dev")
        self.assertAccepted(self.claim())

    def test_只有_tester_校验过时拒绝_点名_dev(self):
        """照契约写实现的是 dev —— 它读的若是旧契约,两边照样各自"对"。"""
        self.verify("tester")
        r = self.claim()
        self.assertRefused(r, "verify-setup", "dev")
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_契约变了_只有_tester_重跑_照样拒绝_点名_dev(self):
        """**对方重跑替不了**(W13 的原则),反过来也一样。"""
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        self.verify("tester")
        self.assertRefused(self.claim(), "verify-setup", "dev")
        self.verify("dev")
        self.assertAccepted(self.claim())

    def test_只有_dev_校验过时拒绝_点名_tester(self):
        self.verify("dev")
        self.assertRefused(self.claim(), "verify-setup", "tester")

    def test_两个都过期时两个都点名(self):
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        self.assertRefused(self.claim(), "verify-setup", "tester", "dev")

    def test_工作项中途契约变了照旧不挡交接(self):
        """dev 那一份过期,但工作项已经在进行中 —— 本节只作用于 `claim`。"""
        self.verify("tester")
        self.verify("dev")
        self.assertAccepted(self.claim())
        self.change_contract()
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例", role="tester"))


class TestWhoseTurnAtIdle(BothRolesBase):
    """**不然驱动器会死循环**:只有 dev 能解锁,归属却写死是 tester。"""

    def test_tester_作数_dev_过期时轮到_dev(self):
        self.verify("tester")
        self.assertEqual(self.whose_turn(), "turn dev")

    def test_dev_的_status_归属那一行是_dev_且给出重跑指引(self):
        self.verify("tester")
        r = self.repo.run("status", role="dev")
        self.assertAccepted(r)
        self.assertIn("归属: dev", r.text)
        self.assertIn("verify-setup", r.text)
        # 上一句单独守不住回合说明:status 先打的"校验不作数"提示里早有 verify-setup,
        # idle 归 dev 时照旧打认领说明它也成立。dev 认领不了,所以说明里不该叫它去认领。
        self.assertNotIn("claim <ID>", r.text)

    def test_dev_重跑之后又轮到_tester(self):
        self.verify("tester")
        self.assertEqual(self.whose_turn(), "turn dev")
        self.verify("dev")
        self.assertEqual(self.whose_turn(), "turn tester")

    def test_tester_过期时照旧轮到_tester(self):
        """先让认领的一方读新契约 —— 不管 dev 那一份怎样。"""
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        self.assertEqual(self.whose_turn(), "turn tester")

    def test_两个都作数时照旧轮到_tester(self):
        self.verify("tester")
        self.verify("dev")
        self.assertEqual(self.whose_turn(), "turn tester")

    def test_工作项进行中_dev_过期也不改归属(self):
        """例外只在 idle:进行中契约变了、tester 在 spec 里重跑、dev 没跑 ——
        仍是 tester 的回合,驱动器不能在这时去调度 dev。"""
        self.verify("tester")
        self.verify("dev")
        self.assertAccepted(self.claim())
        self.change_contract()
        self.verify("tester")
        self.assertEqual(self.repo.state()["phase"], "spec")
        self.assertEqual(self.whose_turn(), "turn tester")


class TestWhoseTurnGateOff(BothRolesBase):
    """门禁关着时 dev 根本不需要校验,tester 顺手校验过也不该把 idle 让给 dev。"""

    config = {"require_setup_verification": False}

    def test_门禁关着_只有_tester_校验过时照旧轮到_tester(self):
        self.verify("tester")
        self.assertEqual(self.whose_turn(), "turn tester")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("归属: tester", r.text)


if __name__ == "__main__":
    unittest.main()
