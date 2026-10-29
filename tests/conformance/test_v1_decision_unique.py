# -*- coding: utf-8 -*-
"""W76:决策条目不能同名(开放条目 57)。

契约「决策条目不能同名」。本回合新写条目的 `(ID, 标题)` 与 HEAD 里已有条目、或与同一回合其他新条目相同 → 拒绝;四个入口共用这一条。

- 讨论、resume 的流程与 W71 同一套(`OverturnBase`:tester 在 spec 开讨论,dev 讨论回合发言,tester `resume`);
- 种子是 HEAD 里的一条 `W1 — 缓存按租户分键`。重复的那条只换理由、不换完整标题 —— 判的是标题,不是整段文本;
- 被拒时断言提交数与 `.pair/state.json` 不变;正常交接、同一回合两条的拒绝文案要出现重复的那个标题。
"""

from test_v1_decision_overturn import OLD, OLD_REF, OLD_MARK, NEW, NEW_MARK, OverturnBase, entry

DUP = entry("W1", "缓存按租户分键", "这一次换了一种理由写同一个结论丑丑丑")
TITLE = "缓存按租户分键"


class UniqueBase(OverturnBase):

    def to_spec_handoff(self):
        """spec 回合写好失败用例,只差交接。"""
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")

    def handoff(self):
        return self.repo.run("handoff", "写了 W1 的失败用例", role="tester")


class TestNormalHandoff(UniqueBase):

    def test_与_HEAD_已有条目同名被拒_文案含那条的标题(self):
        self.to_spec_handoff()
        self.add(DUP)
        before = self.snapshot()
        self.assertNothingHappened(self.handoff(), before, TITLE)

    def test_同一回合两条新条目彼此同名被拒(self):
        self.to_spec_handoff()
        self.add(entry("W1", "重试只做一次", "理由寅寅寅"))
        self.add(entry("W1", "重试只做一次", "理由卯卯卯"))
        before = self.snapshot()
        self.assertNothingHappened(self.handoff(), before, "重试只做一次")

    def test_ID_相同标题不同放行(self):
        self.to_spec_handoff()
        self.add(entry("W1", "缓存按租户分键之后还要带上版本号", "理由辰辰辰"))
        self.assertAccepted(self.handoff())

    def test_标题相同_ID_不同放行(self):
        """判的是完整标题 `ID — 结论`,不是只看结论。"""
        self.to_spec_handoff()
        self.add(entry("W2", TITLE, "理由巳巳巳"))
        self.assertAccepted(self.handoff())


class TestNotRetroactive(UniqueBase):
    """HEAD 里本来就有两条同名(人类直接提交的不经校验),不追溯。"""

    seed = OLD + entry("W1", TITLE, "人类后来又写了一遍午午午")

    def test_追加一条不同名的照常放行(self):
        self.to_spec_handoff()
        self.add(entry("W1", "缓存失效改成五分钟", "理由未未未"))
        self.assertAccepted(self.handoff())


class TestDiscussEntries(UniqueBase):
    """讨论的三个入口与正常交接同一套决策校验。"""

    def test_discuss_开场写同名条目被拒(self):
        self.repo.advance_to("spec")
        self.add(DUP)
        before_commits = self.repo.commit_count()
        self.assertRefused(self.open())
        self.assertEqual(self.repo.commit_count(), before_commits)
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_讨论回合的_handoff_写同名条目被拒(self):
        self.to_dev_reply()
        self.add(DUP)
        before = self.snapshot()
        self.assertNothingHappened(self.reply(), before)
        self.assertEqual(self.repo.state()["phase"], "discuss")

    def test_resume_时推翻者与被推翻的同名被拒(self):
        """开放条目 57 的原样:推翻者的完整标题与它推翻的旧条目一模一样。"""
        self.to_resume()
        self.add(entry("W1", TITLE, NEW_MARK, overturn=[OLD_REF]))
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before)
        self.assertEqual(self.repo.state()["phase"], "discuss")

    def test_对照组_改一个字的结论放行_被推翻的退出注入_推翻者留在注入里(self):
        """`NEW` 的结论是"缓存按用户分键",与旧条目只差一个字。"""
        self.to_resume()
        self.add(NEW)
        self.assertAccepted(self.resume())
        inj = self.injected("tester")
        self.assertIn(NEW_MARK, inj)
        self.assertNotIn(OLD_MARK, inj)


if __name__ == "__main__":
    import unittest
    unittest.main()
