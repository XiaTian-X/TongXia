# -*- coding: utf-8 -*-
"""W70:承重文件的修改分级(P1-9 强版本)。

契约「承重文件的修改分级」。`--contract-change` 只放行 `contract_file` 的纯追加(只有新增行,插在中间也算);
`plan_file` 的任何改动、`contract_file` 的改写(相对 HEAD 有删除行)一律拒绝,文案指向提案的签字与人类 `ratify`(第三十九轮 W68)。
"""

import hashlib

from harness import PairTestCase

PLAN = "docs/PLAN.md"
CONTRACT = "docs/CONTRACT.md"
PROPOSAL = "docs/proposals/规划补一项.md"
FLAG = ("--doc-reason", "契约那一节的措辞会误导实现方", "--contract-change", "docs/DECISIONS.md")


class TierBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}

    def setUp(self):
        super().setUp()
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类先放一份决策记录")
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")                     # spec 结束时必须 RED

    def handoff(self, *extra):
        self.repo.append_decision(item="W1", title="契约这一节改成新的说法")
        return self.repo.run("handoff", "写了 W1 的失败用例", *extra, role="tester")

    def assertTierRefused(self, r):
        self.assertRefused(r, "提案", "ratify")
        self.assertEqual(self.repo.commit_count(), self.before, "拒绝时什么都不提交")
        self.assertEqual(self.repo.state()["phase"], "spec")

    def body(self):
        return self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")


class TestPlanAlwaysRefused(TierBase):

    def test_PLAN_纯追加一行也拒(self):
        self.repo.write(PLAN, self.repo.read(PLAN) + "\n- 备注一句\n")
        self.before = self.repo.commit_count()
        self.assertTierRefused(self.handoff(*FLAG))
        self.assertIn("- 备注一句", self.repo.read(PLAN), "拒绝时工作区不动")


class TestContractRewriteRefused(TierBase):

    def test_改掉契约的一个已有行被拒(self):
        text = self.repo.read(CONTRACT)
        self.assertIn("tests/W1 存在时 src/W1 必须存在。", text, "前提:模板里有这一句")
        self.repo.write(CONTRACT, text.replace("tests/W1 存在时 src/W1 必须存在。", "tests/W1 存在时 src/W1 可以不存在。"))
        self.before = self.repo.commit_count()
        self.assertTierRefused(self.handoff(*FLAG))

    def test_删掉契约的一行被拒(self):
        lines = self.repo.read(CONTRACT).splitlines(keepends=True)
        victim = next(i for i, l in enumerate(lines) if "W2 必须存在" in l)
        self.repo.write(CONTRACT, "".join(lines[:victim] + lines[victim + 1:]))
        self.before = self.repo.commit_count()
        self.assertTierRefused(self.handoff(*FLAG))


class TestContractPureAppendAllowed(TierBase):

    def test_往契约中间插一段补充_照旧放行_声明进正文(self):
        text = self.repo.read(CONTRACT)
        anchor = "tests/W1 存在时 src/W1 必须存在。\n"
        self.assertIn(anchor, text)
        self.repo.write(CONTRACT, text.replace(anchor, anchor + "\n**补充** 空输入时返回空字符串。\n", 1))
        r = self.handoff(*FLAG)
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "impl")
        self.assertIn("契约变更(已声明):", self.body())
        self.assertIn("**补充** 空输入时返回空字符串。", self.repo.git("show", "HEAD:%s" % CONTRACT).stdout.decode("utf-8"))

    def test_没留决策照旧被拒(self):
        """纯追加照旧走既有规则 —— 当场留决策不变。"""
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 一句。\n")
        r = self.repo.run("handoff", "写了 W1 的失败用例", *FLAG, role="tester")
        self.assertRefused(r, "决策")


class TestWithoutFlag(TierBase):

    def test_不带声明改契约照旧被冻结判定拒绝_文案指向提案批准(self):
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 一句。\n")
        r = self.repo.run("handoff", "写了 W1 的失败用例", "--doc-reason", "改措辞", role="tester")
        self.assertRefused(r, "冻结", CONTRACT, "ratify")


class TestSamePlanDiffViaRatify(TierBase):
    """同一段 PLAN diff:`--contract-change` 被拒,走签字加 `ratify` 生效。"""

    def test_签字加人类批准之后_PLAN_改了(self):
        plan = self.repo.read(PLAN)
        self.repo.write(PLAN, plan + "\n- [ ] **W3** [feature] — 第三个工作项\n")
        block = self.repo.git("diff", "--", PLAN).stdout.decode("utf-8")
        self.before = self.repo.commit_count()
        self.assertTierRefused(self.handoff(*FLAG))
        self.repo.write(PLAN, plan)                     # 撤回,改走提案
        self.repo.write(PROPOSAL, "# 规划补一项\n\n```diff\n%s```\n" % block)
        self.assertAccepted(self.repo.run("sign", PROPOSAL, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))
        self.assertAccepted(self.repo.run("sign", PROPOSAL, role="dev"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        r = self.repo.run("ratify", PROPOSAL, role=None, env={"PAIR_ROLE": "human"})
        self.assertAccepted(r)
        self.assertIn("**W3** [feature] — 第三个工作项", self.repo.read(PLAN))
        h = hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]
        self.assertIn("批准: 人类 sha256:%s" % h, self.repo.read(PROPOSAL))


if __name__ == "__main__":
    import unittest
    unittest.main()
