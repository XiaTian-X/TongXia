# -*- coding: utf-8 -*-
"""W16:评审回合可以只追加变异点登记。

契约「评审回合可以只追加变异点登记」。新代码的锚点要到 impl 落地才知道,而 tester 在一个
工作项里能写测试的只有 spec 回合 —— 第五轮连续三次把锚点欠到下一个工作项。新配置键
`review_append_paths` 让评审阶段的执行者往它名下**已在 HEAD 里**的文件**只追加**。

**场景用 `checks/` 而不是 `tests/`**:harness 的测试命令要求 `tests/` 下每个文件在 `src/`
下都有同名文件,否则红 —— 在 `tests/` 下放一份登记表会让套件本身变红,分不清是谁拒的。
`checks/` 归 tester,和本仓库 `mutation_check.py` 归 tester 是同一个形状。

**"追加" = 没有删除行,不是"加在末尾"。** 契约写死:判据不许写成"中间插入被拒" ——
`MUTATIONS` 是列表,新条目必须插在收尾的 `]` 之前。

**判据尽量不碰措辞**:拒绝文案契约里有两处说法("只能往它追加"与 PLAN 里的"只能追加"),
这里只断言它提到了"追加"和那份文件。
"""

import unittest

from harness import EVIDENCE, PairTestCase

REG = "checks/mutations.txt"
DEV_REG = "checks/dev.txt"
BASE = "第一条\n第二条\n第三条\n"
ROLES = {"tester": ["tests", "checks"], "dev": ["src"]}


class AppendBase(PairTestCase):

    config = {"roles": ROLES, "review_append_paths": {"tester": [REG]}}

    def setUp(self):
        super().setUp()
        self.repo.write(REG, BASE)
        self.repo.git("add", "--", REG)
        self.repo.git("commit", "-q", "-m", "人类先放一份登记表")

    def approve_impl(self):
        return self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")

    def phase(self):
        return self.repo.state()["phase"]


class TestAppendIsAllowed(AppendBase):

    def test_评审回合往末尾追加被接受(self):
        self.repo.advance_to("review-impl")
        self.repo.write(REG, BASE + "第四条(W1 的新锚点)\n")
        self.assertAccepted(self.approve_impl())
        self.assertEqual(self.phase(), "review-test")

    def test_评审回合往中间插入也被接受(self):
        """契约:**"追加"指没有删除行,不指"加在文件末尾"** —— `MUTATIONS` 的新条目
        必须插在收尾的 `]` 之前。只认末尾追加的实现会让本节的用途走不通。"""
        self.repo.advance_to("review-impl")
        self.repo.write(REG, "第一条\n第二条\n插进来的一条\n第三条\n")
        self.assertAccepted(self.approve_impl())


class TestAnythingElseIsRefused(AppendBase):

    def test_改了已有行被拒_文案说只能追加(self):
        self.repo.advance_to("review-impl")
        self.repo.write(REG, "第一条\n第二条被改了\n第三条\n")
        r = self.approve_impl()
        self.assertRefused(r, "追加", REG)
        self.assertEqual(self.phase(), "review-impl")

    def test_删掉整个文件被拒(self):
        """**带上 `--allow-deletion`。** `checks/` 在 tester 的角色路径下,删掉它会先被既有的
        "删除测试防护"拒掉 —— 不带这个旗标,这条用例拒绝的原因根本不是本节,参考实现里
        拆掉"只追加"判定它照样绿。带上之后,能拒绝这次删除的就只剩本节那一道。"""
        self.repo.advance_to("review-impl")
        self.repo.delete(REG)
        r = self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE,
                          "--allow-deletion", "评审时顺手删掉登记表", role="tester")
        self.assertRefused(r, REG)
        self.assertEqual(self.phase(), "review-impl")

    def test_改名被拒(self):
        """改名在 HEAD 那一侧就是一次删除。"""
        self.repo.advance_to("review-impl")
        self.repo.git("mv", REG, "checks/改了名.txt")
        self.assertRefused(self.approve_impl())
        self.assertEqual(self.phase(), "review-impl")

    def test_不在_HEAD_里的名下路径_新建被拒(self):
        """**新建文件不算追加** —— 否则评审回合能新写一整个测试文件。`has_rewrite` 对
        未跟踪文件的删除行数是 0,会被当成纯追加,契约因此单独写了"必须已在 HEAD 里"。"""
        self.repo.advance_to("review-impl")
        cfg_new = "checks/新登记表.txt"
        self.repo.write(".pair/config.json", self.repo.read(".pair/config.json").replace(
            '"%s"' % REG, '"%s", "%s"' % (REG, cfg_new)))
        self.repo.git("add", "--", ".pair/config.json")
        self.repo.git("commit", "-q", "-m", "人类把一份还不存在的文件也配进去")
        self.repo.write(cfg_new, "评审回合新写的一整份\n")
        self.assertRefused(self.approve_impl())
        self.assertEqual(self.phase(), "review-impl")

    def test_没配置的测试文件照旧越界(self):
        """放开的只有名下那几个文件,不是整个 tester 路径。"""
        self.repo.advance_to("review-impl")
        self.repo.write("tests/W1", self.repo.read("tests/W1") + "\n评审时顺手加一句\n")
        self.assertRefused(self.approve_impl())
        self.assertEqual(self.phase(), "review-impl")


class TestKeyAbsentIsUnchanged(PairTestCase):
    """不配这个键时,行为一个字不变:评审回合往那份文件追加照旧越界。"""

    config = {"roles": ROLES}

    def test_没配置时评审回合追加照旧被拒(self):
        self.repo.write(REG, BASE)
        self.repo.git("add", "--", REG)
        self.repo.git("commit", "-q", "-m", "人类先放一份登记表")
        self.repo.advance_to("review-impl")
        self.repo.write(REG, BASE + "第四条\n")
        r = self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        self.assertRefused(r)


class TestNotSharedPaths(AppendBase):
    """**不并进 `shared_paths`** —— 那一组另有语义:任何阶段都可写、异议举证认它。"""

    config = {"roles": ROLES,
              "review_append_paths": {"tester": [REG], "dev": [DEV_REG]}}

    def setUp(self):
        super().setUp()
        self.repo.write(DEV_REG, BASE)
        self.repo.git("add", "--", DEV_REG)
        self.repo.git("commit", "-q", "-m", "人类再放一份 dev 名下的")

    def test_impl_回合不能写自己名下的追加路径(self):
        """并进 `shared_paths` 的实现会让它在 impl 也可写 —— 只放开评审阶段。"""
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write(DEV_REG, BASE + "impl 回合追加\n")
        self.assertRefused(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertEqual(self.phase(), "impl")

    def test_idle_时可写路径里没有它(self):
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertNotIn(REG, r.text)

    def test_评审阶段只放开执行者名下的(self):
        """review-test 的执行者是 dev:dev 名下的能追加,tester 名下的不能。"""
        self.repo.advance_to("review-test")
        self.repo.write(REG, BASE + "dev 往 tester 名下追加\n")
        r = self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.assertRefused(r)
        self.repo.write(REG, BASE)
        self.repo.write(DEV_REG, BASE + "dev 往自己名下追加\n")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))


class TestStatusMarksAppendOnly(AppendBase):

    def test_评审阶段的可写路径里标出只追加(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn(REG, r.text)
        self.assertIn("只追加", r.text)


if __name__ == "__main__":
    unittest.main()
