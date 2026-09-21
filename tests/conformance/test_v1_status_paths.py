# -*- coding: utf-8 -*-
"""W25:status 的「可写路径」按执行命令的角色显示。

契约「status 的可写路径按本角色显示」。第九轮 tester 在 impl 阶段跑 `status`,那一行显示的是 dev 的
`src …`,同一屏又写着"现在不是你的回合"。拦截一直是对的(边界在 `handoff`),这是一条显示缺陷。

**判据**:`status` 头部 ` 可写路径 :` 那一行。每条非归属方的用例都配一条同一阶段归属方的对照 ——
"永远只显示共享路径"的实现过得了前者,过不了后者。
"""

from harness import PairTestCase


class PathsLineBase(PairTestCase):

    def line(self, role):
        r = self.repo.run("status", role=role)
        self.assertAccepted(r)
        lines = [l for l in r.text.splitlines() if " 可写路径 :" in l]
        self.assertEqual(len(lines), 1, r.text)
        return lines[0]


class TestNonOwnerDoesNotSeeOwnerPaths(PathsLineBase):

    def test_impl_阶段_tester_看不到_dev_的路径(self):
        """第九轮的原样。"""
        self.repo.advance_to("impl")
        line = self.line("tester")
        self.assertNotIn("src", line)
        self.assertIn("docs/reviews", line, "共享路径任何阶段都可写,照旧显示")

    def test_impl_阶段_dev_看到的与今天一致(self):
        self.repo.advance_to("impl")
        line = self.line("dev")
        self.assertIn("src", line)
        self.assertIn("docs/reviews", line)

    def test_spec_阶段_dev_看不到_tester_的路径(self):
        self.repo.advance_to("spec")
        line = self.line("dev")
        self.assertNotIn("tests", line)
        self.assertIn("docs/reviews", line)

    def test_spec_阶段_tester_看到的与今天一致(self):
        self.repo.advance_to("spec")
        self.assertIn("tests", self.line("tester"))


class TestSharedOnlyPhasesUnchanged(PathsLineBase):
    """idle 与评审阶段今天就只给共享路径(评审阶段另有执行者名下的只追加路径,见 `test_v1_review_append`)。"""

    def test_idle_时两个角色看到同一行(self):
        self.assertEqual(self.line("tester").split(":", 1)[1], self.line("dev").split(":", 1)[1])

    def test_review_test_阶段两个角色看到同一行(self):
        """默认配置没有只追加路径,评审阶段两边都只有共享路径。"""
        self.repo.advance_to("review-test")
        self.assertEqual(self.line("tester").split(":", 1)[1], self.line("dev").split(":", 1)[1])
