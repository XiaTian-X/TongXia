# -*- coding: utf-8 -*-
"""W30:验证副本的去处写进每回合的简报。

契约「简报里写明验证副本放哪」。W23 给了 `.pair/scratch/`,但只写在 `rules.md` 的一个小节里;
四轮独立运行它一次都没被用上,会话用的是自己工具的草稿目录 —— 每回合必读的是简报。

**判据**:归属方 `status` 里"轮到你了"之后那一段(本阶段任务)含不含 `.pair/scratch/`。
只看那一段:整段输出里别处将来若提到这个路径(警告、路径清单),判据会被它替着成立。
路径与 `GITIGNORE_LINES` 同源是代码层面的要求,用例测不出,review-impl 看。
"""

from harness import PairTestCase

SCRATCH = ".pair/scratch/"


class BriefBase(PairTestCase):

    def brief(self, role):
        r = self.repo.run("status", role=role)
        self.assertAccepted(r)
        self.assertIn("轮到你了", r.text, "前提:%s 是这一阶段的归属方" % role)
        return r.text.split("轮到你了", 1)[1]


class TestWorkingPhasesMentionScratch(BriefBase):

    def test_spec(self):
        self.repo.advance_to("spec")
        self.assertIn(SCRATCH, self.brief("tester"))

    def test_impl(self):
        self.repo.advance_to("impl")
        self.assertIn(SCRATCH, self.brief("dev"))

    def test_review_impl(self):
        self.repo.advance_to("review-impl")
        self.assertIn(SCRATCH, self.brief("tester"))

    def test_review_test(self):
        self.repo.advance_to("review-test")
        self.assertIn(SCRATCH, self.brief("dev"))


class TestIdleDoesNot(BriefBase):

    def test_idle_整段输出都不含(self):
        """idle 没有要验证的东西。这一条看整段 —— 契约写的是"idle 的输出不含"。"""
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertNotIn(SCRATCH, r.text)
