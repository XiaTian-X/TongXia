# -*- coding: utf-8 -*-
"""写权限边界:角色隔离、评审只读、冻结文件、测试删除防护。"""

from harness import PairTestCase


class TestRoleBoundaries(PairTestCase):

    def test_tester_不能写_src(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("src/W1")           # 越界
        r = self.repo.run("handoff", "顺手把实现也写了", role="tester")
        self.assertRefused(r, "src/W1", "越界")

    def test_dev_不能写_tests(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write("tests/W1", "被 dev 改过")   # 越界
        r = self.repo.run("handoff", "顺便调了下测试", role="dev")
        self.assertRefused(r, "tests/W1", "越界")

    def test_不能修改冻结的_PLAN(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("docs/PLAN.md", "# 我改了规划\n")
        r = self.repo.run("handoff", "顺便改了规划", role="tester")
        self.assertRefused(r, "docs/PLAN.md", "冻结")


class TestReviewIsReadOnly(PairTestCase):
    """bash 版的 P1-2:评审回合可以夹带代码改动。"""

    def test_评审时不能改测试(self):
        self.repo.advance_to("review-impl")
        self.repo.write("tests/夹带", "评审时偷偷加的")
        r = self.repo.run("handoff", "approve", "看过了没问题", role="tester")
        self.assertRefused(r, "只读评审")

    def test_评审时不能改实现(self):
        self.repo.advance_to("review-test")
        self.repo.write("src/夹带", "评审时偷偷加的")
        r = self.repo.run("handoff", "approve", "测试写得不错", role="dev")
        self.assertRefused(r, "只读评审")

    def test_评审时可以写评审记录(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/reviews/W1-impl.md", "# 评审意见\n无硬编码。\n")
        r = self.repo.run("handoff", "approve", "详见 docs/reviews/W1-impl.md", role="tester")
        self.assertAccepted(r)


class TestDeletionGuard(PairTestCase):
    """bash 版的 P2:删掉难通过的测试、补一条容易的,只要整体仍红就能蒙混过关。"""

    def _到达带有已完成测试的_spec(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        self.repo.run("claim", "W2", role="tester")

    def test_删除已有测试被拒绝(self):
        self._到达带有已完成测试的_spec()
        self.repo.delete("tests/W1")     # 偷偷去掉已有验收范围
        self.repo.write("tests/W2")
        r = self.repo.run("handoff", "换了个用例", role="tester")
        self.assertRefused(r, "删除了已有测试", "tests/W1")

    def test_显式声明后允许删除(self):
        self._到达带有已完成测试的_spec()
        self.repo.delete("tests/W1")
        self.repo.write("tests/W2")
        r = self.repo.run("handoff", "W1 用例已被 W2 覆盖",
                          "--allow-deletion", "W1 的断言是 W2 的真子集",
                          role="tester")
        self.assertAccepted(r)

    def test_声明的删除理由会进提交记录(self):
        self._到达带有已完成测试的_spec()
        self.repo.delete("tests/W1")
        self.repo.write("tests/W2")
        self.repo.run("handoff", "替换用例",
                      "--allow-deletion", "理由写在这里",
                      role="tester")
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertIn("理由写在这里", body)
        self.assertIn("tests/W1", body)
