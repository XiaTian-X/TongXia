# -*- coding: utf-8 -*-
"""回合归属与状态文件不可篡改。

这两条是协议的地基:回合能被抢,或状态能被改,其余所有强制都失效。
"""

from harness import PairTestCase


class TestTurnOwnership(PairTestCase):

    def test_不是自己的回合不能交接(self):
        # 初始是 spec,归 tester。dev 不该能动。
        r = self.repo.run("handoff", "我想插队", role="dev")
        self.assertRefused(r, "不是你")

    def test_不是自己的回合时_status_命令你停下(self):
        r = self.repo.run("status", role="dev")
        self.assertAccepted(r)
        self.assertIn("不是你的回合", r.text)
        self.assertIn("停止", r.text)


class TestStateTamper(PairTestCase):

    def test_篡改状态抢回合被拒绝(self):
        # 这是 bash 版的 P0-1:dev 把 phase 改成 impl 就能抢到回合。
        self.repo.tamper_state(phase="impl")
        self.repo.write("src/sneaky")
        r = self.repo.run("handoff", "我自己把回合改成了我的", role="dev")
        self.assertRefused(r, "state.json", "违规")

    def test_篡改后状态被自动还原(self):
        self.repo.tamper_state(phase="impl", changes_count=99)
        self.repo.run("handoff", "抢回合", role="dev")
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle", "状态没有被还原")
        self.assertEqual(st["changes_count"], 0, "打回计数没有被还原")

    def test_篡改不会产生提交(self):
        before = self.repo.commit_count()
        self.repo.tamper_state(phase="impl")
        self.repo.write("src/sneaky")
        self.repo.run("handoff", "抢回合", role="dev")
        self.assertEqual(self.repo.commit_count(), before,
                         "被拒绝的交接不应该留下提交")

    def test_清零打回计数绕过死锁闸被拒绝(self):
        self.repo.advance_to("review-impl")
        self.repo.run("handoff", "changes", "第一次", role="tester")
        self.repo.run("handoff", "修好了", role="dev")
        self.repo.run("handoff", "changes", "第二次", role="tester")
        self.repo.run("handoff", "又修好了", role="dev")
        # tester 想把计数清零来躲开死锁闸
        self.repo.tamper_state(changes_count=0)
        r = self.repo.run("handoff", "changes", "第三次", role="tester")
        self.assertRefused(r, "state.json")

    def test_status_会警告状态被篡改(self):
        self.repo.tamper_state(changes_count=42)
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("被修改过", r.text)
