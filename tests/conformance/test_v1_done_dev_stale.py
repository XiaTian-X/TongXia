# -*- coding: utf-8 -*-
"""W50:完成工作项时 dev 的开工前校验已失效,要当场处理。

契约「完成工作项时 dev 的校验已失效要当场处理」。工作项进行中契约被改过之后两个角色的校验都失效。tester 那一半自愈
(下一次认领被拒、被告知重跑);dev 那一半在 `cover` 里没有 impl 回合,dev 在 review-test 照样通过、完成工作项 ——
第二十七轮 W48 之后 tester 认领 W49 被拒,人类得把 dev 单独叫回来。

**契约在工作项进行中由人类改**(`set_plan` 提交):效果与 tester 带声明改契约相同(两个角色的校验都失效),
用例不必再走一遍声明与当场决策那条已有用例守着的路径。
"""

from harness import COVER_NOTE, EVIDENCE, VERIFY_OK, PairTestCase, setup_report

PLAN = """# 规划

## 工作项

- [ ] **W1** [cover] — 给 W1 补特征测试
  - 对应契约:`docs/CONTRACT.md` → W1
- [ ] **W2** [feature] — 第二个
  - 对应契约:`docs/CONTRACT.md` → W2
- [ ] **R1** [refactor] — 重构 W1
  - 对应契约:`docs/CONTRACT.md` → W1
  - 保护测试: tests
"""

REPORT = setup_report("W1", "W2")


class StaleBase(PairTestCase):

    config = {"require_setup_verification": True}

    def setUp(self):
        super().setUp()
        self.repo.write("src/W1")
        self.repo.write("tests/W1")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "chore: 已有实现")
        self.repo.set_plan(PLAN)
        self.verify("tester")
        self.verify("dev")

    def verify(self, role, addendum=""):
        rel = "docs/reviews/setup-verification-%s.md" % role
        text = (self.repo.read(rel) if self.repo.exists(rel) else REPORT) + addendum
        self.repo.write(rel, text)
        self.assertAccepted(self.repo.run(*VERIFY_OK, role=role))

    def change_contract(self):
        self.repo.set_plan(self.repo.read("docs/PLAN.md"),
                           contract=self.repo.read("docs/CONTRACT.md") + "\n**补充** 工作项进行中改了一句。\n")

    def cover_to_review_test(self, change=False):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        if change:
            self.change_contract()
        self.repo.write("tests/W1-more")
        self.repo.write("src/W1-more")
        self.repo.git("add", "src/W1-more")
        self.repo.git("commit", "-q", "-m", "chore: 已有实现(补)")
        self.repo.write("docs/notes/W1.md", COVER_NOTE)
        # 笔记够长、契约又可能变过:完成前都要有同 id 的决策(晋升闸与契约变更记录),先写上,免得拒绝来自别处。
        self.repo.append_decision("W1", title="W1 的特征测试固化了空输入行为")
        self.assertAccepted(self.repo.run("handoff", "补了 W1 的特征测试", role="tester"))
        self.assertEqual(self.repo.state()["phase"], "review-test")

    def dev_approve(self):
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")


class TestDevCompletionRefused(StaleBase):

    def test_契约改过之后_dev_的完成交接被拒_给出_verify_setup(self):
        self.cover_to_review_test(change=True)
        r = self.dev_approve()
        self.assertRefused(r, "verify-setup")
        self.assertEqual(self.repo.state()["phase"], "review-test", "被拒就不该推进")

    def test_dev_重跑之后同一条放行_tester_随后能认领(self):
        """tester 那一半自愈:它认领前照旧要自己重跑(W19),这里照做。"""
        self.cover_to_review_test(change=True)
        self.assertRefused(self.dev_approve())
        self.verify("dev", "\n## 补记\n\n契约补了一句,逐节重读过,原结论成立。\n")
        self.assertAccepted(self.dev_approve())
        self.verify("tester", "\n## 补记\n\n契约补了一句,逐节重读过,原结论成立。\n")
        self.assertAccepted(self.repo.run("claim", "W2", role="tester"))

    def test_对照组_没改契约时照常放行(self):
        self.cover_to_review_test(change=False)
        self.assertAccepted(self.dev_approve())


class TestTesterCompletionHints(StaleBase):
    """refactor 由 tester 在 review-impl 完成:不拒绝(那是 dev 的校验,tester 解不开),收尾提示 dev 先重跑。"""

    def test_tester_完成时放行_并提示_dev_先重跑(self):
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))
        self.change_contract()
        self.repo.write_archaeology("R1")
        self.repo.append_decision("R1", title="R1 的重构保留了契约外行为")
        self.repo.write("src/W1", "重构过")
        self.assertAccepted(self.repo.run("handoff", "重构 W1", role="dev"))
        r = self.repo.run("handoff", "approve", "重构没问题", *EVIDENCE, role="tester")
        self.assertAccepted(r)
        self.assertIn("verify-setup", r.text)
        self.assertIn("dev", r.text.split("已交接", 1)[1])

    def test_对照组_没改契约时不提示(self):
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))
        self.repo.write_archaeology("R1")
        self.repo.append_decision("R1", title="R1 的重构保留了契约外行为")
        self.repo.write("src/W1", "重构过")
        self.assertAccepted(self.repo.run("handoff", "重构 W1", role="dev"))
        r = self.repo.run("handoff", "approve", "重构没问题", *EVIDENCE, role="tester")
        self.assertAccepted(r)
        self.assertNotIn("verify-setup", r.text)
