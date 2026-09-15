# -*- coding: utf-8 -*-
"""W17:只涉及测试的打回不再经过 impl。

契约「只涉及测试的打回不再经过 impl」。第五轮 7 个 impl 回合里 3 个空转,全是同一类:
review-test 打回 → tester 在 spec 补测试 → dev 的 impl 回合一行代码不改 → tester 的 review-impl
只能确认"没有可实现的东西"。**一次只涉及测试的打回实际花三个回合,其中两个是仪式。**

**判据看的是下一阶段与归属**(`state.json` 的 `phase`、`whose-turn`),不是提交正文的措辞。
"回弹来自哪一阶段"与"review-impl 那一刻的契约"存在状态的哪个键里,契约没定,这里一次都不碰。
"""

import json
import unittest

from harness import PLAN_TEMPLATE, PairTestCase, with_loc

CONTRACT = "docs/CONTRACT.md"
PLAN = "docs/PLAN.md"
DECISION_ARGS = ("--doc-reason", "那一句会误导实现方", "--contract-change", "docs/DECISIONS.md")


class ShortcutBase(PairTestCase):

    def phase(self):
        return self.repo.state()["phase"]

    def rebound_from_review_test(self):
        """dev 在 review-test 以覆盖不足打回。实现已经在 review-impl 被 approve 过。"""
        self.repo.advance_to("review-test")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("测试漏了一个边界"),
                                          role="dev"))
        self.assertEqual(self.phase(), "spec")

    def fix_tests_green(self):
        """补测试:改的是已有那条,src/W1 早就在,所以套件照样绿。"""
        self.repo.write("tests/W1", self.repo.read("tests/W1") + "\n补上漏掉的边界\n")

    def spec_handoff(self, *extra):
        return self.repo.run("handoff", "补上漏掉的边界", *extra, role="tester")

    def human_changes_contract(self):
        self.repo.set_plan(self.repo.read(PLAN),
                           contract=self.repo.read(CONTRACT) + "\n**补充** 人类改了一句。\n")


class TestShortcutTaken(ShortcutBase):

    def test_打回后_spec_以绿结束_直接进_review_test_归属_dev(self):
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "review-test")
        r = self.repo.run("whose-turn", role="tester")
        self.assertEqual(r.out.strip(), "turn dev")

    def test_捷径之后_dev_放行就完成(self):
        from harness import EVIDENCE
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertAccepted(self.repo.run("handoff", "approve", "补的测试没问题", *EVIDENCE,
                                          role="dev"))
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertIn("W1", st["completed_items"])

    def test_打回计数不因捷径清零_评审文件名照旧按打回次数算(self):
        """死锁计数不因捷径清零;`review_file_for` 在打回过一次之后给的是 `-2`。"""
        self.rebound_from_review_test()
        before = self.repo.state()["changes_count"]
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.repo.state()["changes_count"], before)
        r = self.repo.run("status", role="dev")
        self.assertIn("W1-review-test-2.md", r.text)

    def test_带了声明但没真改承重文件_照样走捷径(self):
        """**按改动判,不按旗标判**(与 W14「声明只在生效时留痕」同口径)。"""
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff("--contract-change", CONTRACT))
        self.assertEqual(self.phase(), "review-test")


class TestShortcutNotTaken(ShortcutBase):

    def test_以红结束_照旧进_impl(self):
        """tester 补的测试揭出了实现的真缺陷,需要 dev 改。"""
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.repo.write("tests/W1b", "揭出实现缺陷的一条")          # src/W1b 不存在 → 红
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "impl")

    def test_回弹来自异议_以绿结束_照旧进_impl(self):
        """实现还没被 review-impl 审过。"""
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write_dispute()
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"),
                                          role="dev"))
        self.assertEqual(self.phase(), "spec")
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "impl")

    def test_这一回合改了契约_照旧进_impl(self):
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 说清楚一句。\n")
        self.repo.append_decision("W1", title="契约这一句改成更清楚的说法")
        self.assertAccepted(self.spec_handoff(*DECISION_ARGS))
        self.assertEqual(self.phase(), "impl")

    def test_这一回合改了规划_照旧进_impl(self):
        """规划文件的变化不改变契约的 sha —— "按改动判"那一条要单独管它。"""
        self.rebound_from_review_test()
        self.fix_tests_green()
        self.repo.write(PLAN, self.repo.read(PLAN) + "\n")
        self.repo.append_decision("W1", title="规划补一行")
        self.assertAccepted(self.spec_handoff(*DECISION_ARGS))
        self.assertEqual(self.phase(), "impl")

    def test_打回之后契约被人提交过_照旧进_impl(self):
        """**只看这一回合的改动看不见它。** 第五轮 W15 那一节就是这样提交的(`e62bdf5`)。"""
        self.rebound_from_review_test()
        self.human_changes_contract()
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "impl")

    def test_review_test_期间契约被人提交过_照旧进_impl(self):
        """**基准是 review-impl approve 那一刻**,不是打回那一刻 —— 实现是在那一刻被审过的。
        在打回时才记契约的实现,这一条会错误地走捷径。"""
        self.repo.advance_to("review-test")
        self.human_changes_contract()
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("测试漏了一个边界"),
                                          role="dev"))
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "impl")

    def test_旧状态没有回弹来源的记录_不走捷径(self):
        """升级上来的状态:停在打回之后的 spec,但从没被新代码记过"回弹来自哪一阶段"。
        用人类提交的状态文件模拟 —— 从 review-test 的状态手工翻到 spec,不经过新代码的打回路径。"""
        self.repo.advance_to("review-test")
        st = self.repo.state()
        st.update(phase="spec", after_rebound=True, changes_count=1, last_actor="dev")
        self.repo.write(".pair/state.json", json.dumps(st, indent=2, ensure_ascii=False))
        self.repo.git("add", "--", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "chore: 升级前的状态文件")
        self.fix_tests_green()
        self.assertAccepted(self.spec_handoff())
        self.assertEqual(self.phase(), "impl")


if __name__ == "__main__":
    unittest.main()
