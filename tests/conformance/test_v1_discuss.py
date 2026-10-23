# -*- coding: utf-8 -*-
"""W67:`discuss` / 讨论回合 / `resume` —— 工作项原样挂起、原样恢复(P0-5 的 D2)。

契约「discuss 阶段:挂起与恢复」(含 spec 回合带声明补的「补充」,开工前审查 ㉑:进入与 resume 都先查状态篡改)。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;评审目录 `docs/reviews`;本文件的类配 `proposal_paths: ["docs/proposals"]`。
"""

import json

from harness import EVIDENCE, PairTestCase, with_loc

PROPOSAL = "docs/proposals/缓存的方向.md"
OPENING = "# 缓存的方向\n\n## tester\n\n做 W1 时发现缓存失效规则与契约「W1」冲突,先讨论清楚再写用例。\n"
WHY = "缓存失效规则与契约冲突,写用例之前要先对齐"


class DiscussBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}

    # --- 动作 ---------------------------------------------------------
    def append(self, text, path=PROPOSAL):
        old = self.repo.read(path) if self.repo.exists(path) else ""
        self.repo.write(path, old + text)

    def open(self, role="tester", why=WHY, text=OPENING, path=PROPOSAL):
        if text:
            self.append(text, path)
        return self.repo.run("discuss", "--proposal", path, why, role=role)

    def speak(self, role, text):
        self.append("\n## %s\n\n%s\n" % (role, text))
        return self.repo.run("handoff", "%s 的看法" % role, role=role)

    def resume(self, role, conclusion="维持契约原意,缓存规则另开工作项", append=None):
        if append:
            self.append("\n## %s\n\n%s\n" % (role, append))
        return self.repo.run("resume", conclusion, role=role)

    # --- 观察 ---------------------------------------------------------
    def state(self):
        return self.repo.state()

    def turn(self):
        return self.repo.run("whose-turn", role="tester").out.split("\n", 1)[0].strip()

    def head_body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")

    def snapshot(self):
        st = self.state()
        return {k: st.get(k) for k in ("phase", "last_actor", "after_rebound", "rebound_from", "item", "item_type",
                                       "changes_count")}


class TestEnterFromEveryWorkingPhase(DiscussBase):

    def assertOpened(self, opener, other):
        before = self.snapshot()
        r = self.open(role=opener)
        self.assertAccepted(r)
        st = self.state()
        self.assertEqual(st["phase"], "discuss")
        self.assertEqual(self.turn(), "turn %s" % other)
        self.assertEqual((st["item"], st["changes_count"]), (before["item"], before["changes_count"]))
        self.assertTrue(self.repo.head_subject().startswith("discuss:"), self.repo.head_subject())

    def test_spec_tester(self):
        self.repo.advance_to("spec")
        self.assertOpened("tester", "dev")

    def test_impl_dev(self):
        self.repo.advance_to("impl")
        self.assertOpened("dev", "tester")

    def test_review_impl_tester(self):
        self.repo.advance_to("review-impl")
        self.assertOpened("tester", "dev")

    def test_review_test_dev(self):
        self.repo.advance_to("review-test")
        self.assertOpened("dev", "tester")


class TestEnterRefused(DiscussBase):

    def assertNotOpened(self, r, *needles):
        self.assertRefused(r, *needles)
        self.assertNotEqual(self.state()["phase"], "discuss")

    def test_idle_拒绝(self):
        self.assertNotOpened(self.open())

    def test_不是自己的回合拒绝(self):
        self.repo.advance_to("spec")
        self.assertNotOpened(self.open(role="dev"))

    def test_为什么为空拒绝(self):
        self.repo.advance_to("spec")
        self.assertNotOpened(self.open(why=" "))

    def test_提案不在提案目录拒绝(self):
        self.repo.advance_to("spec")
        self.assertNotOpened(self.open(path="docs/reviews/W1-方向.md"))

    def test_本回合没写提案拒绝(self):
        """提案早就提交过、这一回合一个字没动 —— 讨论要有这一回合的发言。"""
        self.repo.advance_to("spec")
        self.repo.write(PROPOSAL, OPENING)
        self.repo.git("add", PROPOSAL)
        self.repo.git("commit", "-q", "-m", "chore: 人类先放了一份提案")
        self.assertNotOpened(self.open(text=None))

    def test_工作区有代码改动拒绝_点名文件(self):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1", "写到一半的用例")
        self.assertNotOpened(self.open(), "tests/W1")

    def test_对照组_工作区只有评审与记忆层改动时放行(self):
        self.repo.advance_to("spec")
        self.repo.write("docs/reviews/W1-想法.md", "# 想法\n")
        self.repo.write("docs/notes/W1.md", "# 笔记\n")
        self.assertAccepted(self.open())


class TestEnterWithoutProposalPaths(PairTestCase):

    def test_没配_proposal_paths_拒绝(self):
        self.repo.advance_to("spec")
        self.repo.write(PROPOSAL, OPENING)
        r = self.repo.run("discuss", "--proposal", PROPOSAL, WHY, role="tester")
        self.assertRefused(r)
        self.assertNotEqual(self.repo.state()["phase"], "discuss")


class TestTamper(DiscussBase):
    """㉑:进入与 resume 都会提交状态文件 —— 不先查篡改,手改的部分就随协议自己的提交落地。"""

    def test_手改状态之后_discuss_被拒_状态还原_没有新提交(self):
        self.repo.advance_to("spec")
        good = self.repo.read(".pair/state.json")
        before = self.repo.commit_count()
        self.repo.tamper_state(changes_count=0, deadlock_hits=["W9 x3"])
        self.assertRefused(self.open())
        self.assertEqual(self.repo.read(".pair/state.json"), good)
        self.assertEqual(self.repo.commit_count(), before)

    def test_手改状态之后_resume_被拒_状态还原_没有新提交(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertAccepted(self.speak("dev", "同意先对齐。"))
        good = self.repo.read(".pair/state.json")
        before = self.repo.commit_count()
        self.repo.tamper_state(discussed=[])
        self.assertRefused(self.resume("tester"))
        self.assertEqual(self.repo.read(".pair/state.json"), good)
        self.assertEqual(self.repo.commit_count(), before)


class TestDiscussTurn(DiscussBase):

    def setUp(self):
        super().setUp()
        self.repo.advance_to("spec")
        self.before = self.snapshot()
        self.assertAccepted(self.open())

    def test_对方追加提案交接_回合翻转(self):
        r = self.speak("dev", "我倾向维持契约原意。")
        self.assertAccepted(r)
        self.assertEqual(self.turn(), "turn tester")
        self.assertTrue(self.repo.head_subject().startswith("discuss:"), self.repo.head_subject())

    def test_讨论回合不计数_不碰打回标记(self):
        self.assertAccepted(self.speak("dev", "我倾向维持契约原意。"))
        st = self.state()
        self.assertEqual((st["changes_count"], st.get("after_rebound"), st.get("rebound_from")),
                         (self.before["changes_count"], self.before["after_rebound"], self.before["rebound_from"]))

    def test_没追加提案被拒(self):
        r = self.repo.run("handoff", "我没写什么", role="dev")
        self.assertRefused(r)
        self.assertEqual(self.turn(), "turn dev")

    def test_写代码被拒(self):
        self.append("\n## dev\n\n顺手写了实现。\n")
        self.repo.write("src/W1")
        self.assertRefused(self.repo.run("handoff", "dev 的看法", role="dev"))

    def test_改写已提交的提案被拒(self):
        self.repo.write(PROPOSAL, OPENING.replace("先讨论清楚", "不用讨论") + "\n## dev\n\n改了你的话。\n")
        self.assertRefused(self.repo.run("handoff", "dev 的看法", role="dev"))

    def test_不是讨论回合的一方交接被拒(self):
        self.append("\n## tester\n\n抢着再说一句。\n")
        self.assertRefused(self.repo.run("handoff", "tester 抢话", role="tester"))


class TestResume(DiscussBase):

    def test_只有发起方发过言时_resume_被拒(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertRefused(self.resume("dev"))
        self.assertEqual(self.state()["phase"], "discuss")

    def test_对方本回合追加之后直接_resume(self):
        self.repo.advance_to("spec")
        before = self.snapshot()
        self.assertAccepted(self.open())
        self.assertAccepted(self.resume("dev", append="同意,维持契约原意。"))
        self.assertEqual(self.snapshot(), before)

    def test_双方发言后发起方_resume_原样恢复(self):
        self.repo.advance_to("impl")
        before = self.snapshot()
        self.assertAccepted(self.open(role="dev"))
        self.assertAccepted(self.speak("tester", "同意另开工作项。"))
        r = self.resume("dev", conclusion="缓存规则另开工作项,本项照契约做")
        self.assertAccepted(r)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.turn(), "turn dev")
        st = self.state()
        self.assertIsNone(st.get("discuss"))
        self.assertIn("W1", st.get("discussed") or [])
        self.assertTrue(self.repo.head_subject().startswith("discuss(resume):"), self.repo.head_subject())
        self.assertIn("缓存规则另开工作项", self.repo.head_subject() + self.head_body())

    def test_结论为空被拒(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertRefused(self.resume("dev", conclusion=" ", append="同意。"))

    def test_同一工作项第二次进入被拒(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertAccepted(self.resume("dev", append="同意。"))
        r = self.open(text="\n## tester\n\n又想讨论一次。\n")
        self.assertRefused(r, "提案")
        self.assertEqual(self.state()["phase"], "spec")

    def test_恢复之后照常交接并完成工作项(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertAccepted(self.resume("dev", append="同意。"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "查过无硬编码", *EVIDENCE, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))
        self.assertEqual(self.state()["phase"], "idle")


class TestResumeAfterRebound(DiscussBase):
    """打回之后挂起、再恢复:`after_rebound` / `rebound_from` 原样回来,W17 捷径照判。"""

    def test_review_test_打回后挂起_恢复后只改测试_GREEN_走捷径(self):
        self.repo.advance_to("review-test")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("用例漏了边界"), role="dev"))
        before = self.snapshot()
        self.assertEqual((before["phase"], before["after_rebound"], before["rebound_from"]), ("spec", True, "review-test"),
                         "前提:打回进了 spec")
        self.assertAccepted(self.open())
        self.assertAccepted(self.speak("dev", "边界那条确实该补。"))
        self.assertAccepted(self.resume("tester"))
        self.assertEqual(self.snapshot(), before)
        self.repo.write("tests/W1", "补了边界")
        self.assertAccepted(self.repo.run("handoff", "按打回补边界", role="tester"))
        self.assertEqual(self.state()["phase"], "review-test", "恢复之后 W17 捷径应当照常成立")


class TestResumeUsesSnapshot(DiscussBase):
    """恢复取的是**挂起时记下的现场**,不是恢复那一刻状态里的值。契约里讨论回合不碰这几个键,所以只用命令走不出差别
    ("恢复不还原"在正常流程里与"还原"等价);这里让人类在讨论中途直接改状态并提交(人类有这个权限),恢复之后仍应回到挂起前。"""

    def test_挂起期间状态被人类改过_恢复仍回到挂起时的现场(self):
        self.repo.advance_to("review-test")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("用例漏了边界"), role="dev"))
        before = self.snapshot()
        self.assertAccepted(self.open())
        self.assertAccepted(self.speak("dev", "边界那条确实该补。"))
        st = self.state()
        st.update(after_rebound=False, rebound_from=None, last_actor="dev")
        (self.repo.dir / ".pair" / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        self.repo.git("add", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "chore: 人类在讨论中途改了状态")
        self.assertAccepted(self.resume("tester"))
        self.assertEqual(self.snapshot(), before)


class TestOwnershipAndOthers(DiscussBase):

    def setUp(self):
        super().setUp()
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())

    def test_status_给出讨论回合的一方(self):
        r = self.repo.run("status", role="dev")
        self.assertAccepted(r)
        self.assertIn("discuss", r.out)
        self.assertIn(PROPOSAL, r.out)
        self.assertEqual(self.turn(), "turn dev")

    def test_request_在讨论阶段被拒(self):
        r = self.repo.run("request", "--path", "src/W1", "改一下", "--reason", "不归我", role="dev")
        self.assertRefused(r)
        self.assertNotIn("Traceback", r.text)

    def test_fulfill_在讨论阶段被干净地拒绝(self):
        """`_request_turn` 直接查 `PHASE_OWNER`,discuss 不在表里 —— 不得抛异常。"""
        r = self.repo.run("fulfill", "R1", "说明", role="dev")
        self.assertRefused(r)
        self.assertNotIn("Traceback", r.text)

    def test_report_不把讨论回合算成交接(self):
        def handoffs():
            out = self.repo.run("report", role="tester").out
            line = [l for l in out.splitlines() if "交接提交" in l][0]
            return line.split(":", 1)[1].split()[0]
        n = handoffs()
        self.assertAccepted(self.speak("dev", "我倾向维持契约原意。"))
        self.assertAccepted(self.resume("tester", append="好,维持。"))
        self.assertEqual(handoffs(), n)


if __name__ == "__main__":
    import unittest
    unittest.main()
