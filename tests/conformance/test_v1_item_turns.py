# -*- coding: utf-8 -*-
"""W79:工作项的回合预算 `max_item_turns`(路线图 P1-2)。

契约「工作项的回合预算」。

- 用小预算造场景(1~3),免得真跑 20 回合;"不配时是 20"按 `status` 显示判。
- 换手 = `handoff`(含讨论回合里的)、`discuss` 开场、`resume`;讨论的写法同 W69(发言 = 往提案末尾追加一段,对方可以直接 `resume`)。
- 代办三件套照 W65 的主场景:dev 在 impl 发 `request`,带着代办异议打回进 spec,tester `fulfill` / `decline`。
- 被拒时断言提交数与 `.pair/state.json` 不变 —— **第一次撞上预算除外**:那一次只把状态单独提交一次,工作区里本回合的改动原样留着。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;规划在 `docs/PLAN.md`。
"""

import json
import re

from harness import EVIDENCE, VERIFY_OK, PairRepo, PairTestCase, setup_report, with_loc

PROPOSAL = "docs/proposals/方向.md"
STATE = ".pair/state.json"


def subject(item, n):
    return "chore(pair): 工作项 %s 交接 %d 次,用完回合预算" % (item, n)


class BudgetBase(PairTestCase):

    budget = None           # None = 不配,用默认

    def setUp(self):
        self.config = {"proposal_paths": ["docs/proposals"]}
        if self.budget is not None:
            self.config["max_item_turns"] = self.budget
        super().setUp()

    # --- 动作 ---------------------------------------------------------
    def pair(self, *args, role="tester"):
        return self.repo.run(*args, role=role)

    def say(self, role, text):
        old = self.repo.read(PROPOSAL) if self.repo.exists(PROPOSAL) else "# 方向\n"
        self.repo.write(PROPOSAL, old + "\n## %s\n\n%s\n" % (role, text))

    def open(self, role="tester"):
        self.say(role, "W1 的方向没对齐,先讨论。")
        return self.pair("discuss", "--proposal", PROPOSAL, "方向没对齐", role=role)

    def reply(self, role="dev"):
        self.say(role, "%s 的看法:照原意做。" % role)
        return self.pair("handoff", "%s 的看法" % role, role=role)

    def resume(self, role="dev"):
        self.say(role, "%s:同意,维持原意。" % role)
        return self.pair("resume", "维持原意", role=role)

    def spec(self):
        self.repo.write("tests/W1", "W1 的失败用例\n")
        return self.pair("handoff", "写了 W1 的失败用例")

    def impl(self, text="实现\n"):
        self.repo.write("src/W1", text)
        return self.pair("handoff", "实现 W1", role="dev")

    def review_impl_approve(self):
        return self.pair("handoff", "approve", "查过无硬编码", *EVIDENCE)

    def review_impl_changes(self):
        return self.pair("handoff", "changes", with_loc("空输入时实现抛了异常"))

    def review_test_approve(self):
        return self.pair("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")

    def human_set_state(self, drop=(), **kw):
        """以人类身份直接改状态并提交(搭场景)。"""
        st = self.repo.state()
        st.update(kw)
        for k in drop:
            st.pop(k, None)
        self.repo.write(STATE, json.dumps(st, ensure_ascii=False, indent=2))
        self.repo.git("add", STATE)
        self.repo.git("commit", "-q", "-m", "chore: 人类直接改状态(搭场景)")

    # --- 观察 ---------------------------------------------------------
    def turns(self):
        return self.repo.state().get("item_turns", 0)

    def hits(self):
        return self.repo.state().get("item_turn_budget_hits") or []

    def phase(self):
        return self.repo.state()["phase"]

    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(STATE)

    def head_files(self):
        return self.repo.git_paths("show", "--name-only", "--format=", "-z", "HEAD")

    def status(self):
        return self.pair("status").out

    def budget_line(self):
        """`status` 里"回合预算"那一行 → (已换手次数, 上限);没有这一行 → None。"""
        m = re.search(r"回合预算[^\n]*?(\d+)\s*次[^\n]*?(\d+)", self.status())
        return (int(m.group(1)), int(m.group(2))) if m else None

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒时提交数或状态文件变了")


class TestHandoffCounts(BudgetBase):

    def test_认领时是_0_每次成功的_handoff_加_1(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertEqual(self.turns(), 0)
        self.assertAccepted(self.spec())
        self.assertEqual(self.turns(), 1)
        self.assertAccepted(self.impl())
        self.assertEqual(self.turns(), 2)
        self.assertAccepted(self.review_impl_changes())
        self.assertEqual(self.turns(), 3)

    def test_被拒的交接不加(self):
        """spec 回合什么都没写就交接:被拒,计数不动。"""
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertRefused(self.pair("handoff", "什么都没写"))
        self.assertEqual(self.turns(), 0)


class TestDiscussCounts(BudgetBase):

    def test_discuss_开场_讨论回合的_handoff_resume_各加_1(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())
        self.assertEqual(self.turns(), 1)
        self.assertAccepted(self.reply("dev"))
        self.assertEqual(self.turns(), 2)
        self.assertAccepted(self.resume("tester"))
        self.assertEqual(self.phase(), "spec")
        self.assertEqual(self.turns(), 3)


class TestRequestsDoNotCount(BudgetBase):
    """代办不换手:`request` / `fulfill` / `decline` 前后计数相同;带代办异议的那次打回是 handoff,照常加 1。"""

    def to_spec_with_open_request(self):
        self.repo.advance_to("impl")                     # spec 交接一次 → 1
        self.repo.write("src/W1", "实现\n")
        n = self.turns()
        self.assertAccepted(self.pair("request", "--path", "tests/W1", "把期望值改成 42",
                                      "--reason", "这个文件在 tester 的路径", role="dev"))
        self.assertEqual(self.turns(), n, "request 不加")
        self.repo.write_dispute()
        self.assertAccepted(self.pair("handoff", "changes", with_loc("测试的期望值与契约矛盾"), role="dev"))
        self.assertEqual(self.phase(), "spec")
        self.assertEqual(self.turns(), n + 1, "带代办异议的打回是一次 handoff")

    def test_fulfill_不加(self):
        self.to_spec_with_open_request()
        n = self.turns()
        self.repo.write("tests/W1", "期望值 42")
        self.assertAccepted(self.pair("fulfill", "R1", "按代办改成 42"))
        self.assertEqual(self.turns(), n)

    def test_decline_不加(self):
        self.to_spec_with_open_request()
        n = self.turns()
        self.assertAccepted(self.pair("decline", "R1", "期望值 41 是对的"))
        self.assertEqual(self.turns(), n)


class TestBudgetHit(BudgetBase):
    """上限 3:spec、impl、review-impl 打回各一次,用满;dev 在 impl 的第 4 次换手被拒。"""

    budget = 3

    def setUp(self):
        super().setUp()
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertAccepted(self.spec())
        self.assertAccepted(self.impl())
        self.assertAccepted(self.review_impl_changes())
        self.assertEqual((self.phase(), self.turns()), ("impl", 3))

    def test_第一次撞上_被拒_只把状态单独提交一次_工作区原样(self):
        before = self.repo.commit_count()
        r = self.impl("修好空输入\n")
        self.assertRefused(r, "max_item_turns")
        self.assertEqual(self.repo.commit_count(), before + 1, "第一次撞上要单独提交一次状态")
        self.assertEqual(self.repo.head_subject(), subject("W1", 3))
        self.assertEqual(self.head_files(), {STATE})
        self.assertEqual(self.hits(), ["W1 x3"])
        self.assertEqual((self.phase(), self.turns()), ("impl", 3), "被拒不换手、不加")
        self.assertEqual(self.repo.read("src/W1"), "修好空输入\n", "工作区里本回合的改动原样留着")
        self.assertIn("src/W1", self.repo.git_paths("diff", "--name-only", "-z", "HEAD"), "改动仍未提交")

    def test_再撞_不新增提交_记录不重复(self):
        self.assertRefused(self.impl("修好空输入\n"))
        before = self.snapshot()
        self.assertNothingHappened(self.impl("换一种修法\n"), before, "max_item_turns")
        self.assertEqual(self.hits(), ["W1 x3"])

    def test_status_显示已换手次数与上限_并列出撞过的记录(self):
        self.assertEqual(self.budget_line(), (3, 3))
        self.assertRefused(self.impl("修好空输入\n"))
        self.assertIn("W1 x3", self.status())


class TestCompletionNotBlocked(BudgetBase):

    budget = 3

    def test_用满时_review_test_approve_照常完成_完成后清零(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertAccepted(self.spec())
        self.assertAccepted(self.impl())
        self.assertAccepted(self.review_impl_approve())
        self.assertEqual((self.phase(), self.turns()), ("review-test", 3))
        r = self.review_test_approve()
        self.assertEqual(self.phase(), "idle", "用满时完成不拦:\n%r" % r)
        self.assertIn("- [x] **W1**", self.repo.read("docs/PLAN.md"))
        self.assertEqual(self.turns(), 0, "完成时清零")
        self.assertEqual(self.hits(), [], "完成没被拦,不算撞上")


class TestDiscussBlocked(BudgetBase):
    """讨论的三个入口用满后同样被拒。讨论额度都还有剩、提案都写好了 —— 能拒它们的只剩预算。"""

    def assertBlocked(self, r, phase):
        self.assertRefused(r, "max_item_turns")
        self.assertEqual(self.phase(), phase)
        self.assertEqual(self.hits(), ["W1 x%d" % self.budget])


class TestDiscussOpenBlocked(TestDiscussBlocked):

    budget = 2

    def test_用满后_discuss_开场被拒(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertAccepted(self.spec())
        self.assertAccepted(self.impl())
        self.assertEqual((self.phase(), self.turns()), ("review-impl", 2))
        self.assertBlocked(self.open("tester"), "review-impl")
        self.assertEqual(self.turns(), 2)


class TestDiscussTurnBlocked(TestDiscussBlocked):

    budget = 1

    def setUp(self):
        super().setUp()
        self.repo.advance_to("spec")
        self.assertAccepted(self.open("tester"))
        self.assertEqual((self.phase(), self.turns()), ("discuss", 1))

    def test_用满后讨论回合的_handoff_被拒(self):
        self.assertBlocked(self.reply("dev"), "discuss")
        self.assertEqual(self.turns(), 1)

    def test_用满后_resume_被拒(self):
        self.assertBlocked(self.resume("dev"), "discuss")
        self.assertEqual(self.turns(), 1)


class TestTamperedStateNotCommitted(BudgetBase):
    """agent 手改了状态文件、改出来的计数又正好撞上预算:先被"你修改了状态"拒绝并还原,
    第一次撞上的那次单独提交不能把改过的状态带进 HEAD —— 带进去之后它就不算"改过"了,篡改检查再也看不见。
    四个入口一样:被拒后提交数不变、状态文件与改之前逐字节相同。"""

    budget = 2

    def tamper(self):
        st = self.repo.state()
        st["item_turns"] = 9
        self.repo.write(STATE, json.dumps(st, ensure_ascii=False, indent=2))

    def assertTamperRefused(self, r, before):
        self.assertRefused(r)
        self.assertEqual(self.snapshot(), before, "改过的状态被提交进了 HEAD,或者没还原")

    def test_正常交接(self):
        self.repo.advance_to("impl")                     # 1
        before = self.snapshot()
        self.repo.write("src/W1", "实现\n")
        self.tamper()
        self.assertTamperRefused(self.pair("handoff", "实现 W1", role="dev"), before)

    def test_discuss_开场(self):
        self.repo.advance_to("impl")                     # 1
        before = self.snapshot()
        self.tamper()
        self.assertTamperRefused(self.open("dev"), before)

    def test_讨论回合的_handoff(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open("tester"))         # 1
        before = self.snapshot()
        self.tamper()
        self.assertTamperRefused(self.reply("dev"), before)

    def test_resume(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.open("tester"))         # 1
        before = self.snapshot()
        self.tamper()
        self.assertTamperRefused(self.resume("dev"), before)


class TestUnlimited(BudgetBase):

    budget = 0

    def test_0_不限(self):
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertAccepted(self.spec())
        self.assertAccepted(self.impl())
        self.assertAccepted(self.review_impl_changes())
        self.assertAccepted(self.impl("修好空输入\n"))
        self.assertAccepted(self.review_impl_approve())
        self.assertEqual(self.phase(), "review-test")
        self.assertEqual(self.hits(), [])


class TestDefault(BudgetBase):

    def test_不配时上限是_20(self):
        self.repo.advance_to("impl")
        self.assertEqual(self.budget_line(), (1, 20))


class TestClearing(BudgetBase):

    def test_认领时清零(self):
        """正常完成就清零了,所以由人类在空闲时提交一份带计数的状态,再认领。"""
        self.human_set_state(item_turns=7)
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertEqual(self.turns(), 0)


class TestOldState(BudgetBase):

    budget = 1

    def test_老状态没有这两个键当_0_与空(self):
        """上限 1:没有键若不当 0,dev 这一次就过不去。"""
        self.repo.advance_to("spec")
        self.human_set_state(drop=("item_turns", "item_turn_budget_hits"))
        self.assertAccepted(self.spec())
        self.assertEqual(self.turns(), 1)
        self.assertEqual(self.hits(), [])


class TestVerifySetup(PairTestCase):

    def verify(self, limit):
        self.repo.cleanup()
        self.repo = PairRepo({"max_item_turns": limit})
        self.addCleanup(self.repo.cleanup)
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        return self.repo.run(*VERIFY_OK)

    def test_不是非负整数判失败(self):
        for bad in (-1, 1.5, "20"):
            with self.subTest(max_item_turns=bad):
                self.assertRefused(self.verify(bad), "max_item_turns")

    def test_对照组_0_与_5_通过(self):
        for ok in (0, 5):
            with self.subTest(max_item_turns=ok):
                self.assertAccepted(self.verify(ok))


if __name__ == "__main__":
    import unittest
    unittest.main()
