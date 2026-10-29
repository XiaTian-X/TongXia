# -*- coding: utf-8 -*-
"""W75:review-impl 的测试缺口 —— `handoff --test-gap "说明"` 让 tester 在 review-impl 写自己的测试。

契约「review-impl 的测试缺口」。

- `changes --test-gap`:加一条复现漏洞的用例,交 RED,进 impl;`approve --test-gap`:实现没错只缺覆盖,交 GREEN,进 review-test。
- 布局照 `test_v1_review_append`:tester 拥有 `tests` 与 `checks`,`checks/mutations.txt` 是 tester 的只追加文件(已在 HEAD 里)。
- harness 的测试命令按布局判红绿:`tests/X` 没有 `src/X` 就红。所以**红用例 = 新增 `tests/W1-缺口`**,
  **绿用例 = 改已有的 `tests/W1` 的内容**(布局不变);`src/` 是 dev 的,tester 造不出带实现的新用例。
- 被拒时一律断言:提交数不变、`.pair/state.json` 逐字节不变。
"""

from harness import EVIDENCE, PairTestCase, with_loc

REG = "checks/mutations.txt"
BASE = "第一条\n第二条\n第三条\n"
ROLES = {"tester": ["tests", "checks"], "dev": ["src"]}

GAP = "空输入那条路径没有用例,补一条复现"
RED_TEST = "tests/W1-缺口"

REFACTOR_PLAN = """# 规划

## 工作项

- [ ] **R1** [refactor] — 重构实现
  - 对应契约:`docs/CONTRACT.md` → W1
  - 保护测试: tests
"""


class GapBase(PairTestCase):

    config = {"roles": ROLES, "review_append_paths": {"tester": [REG]}}

    def setUp(self):
        super().setUp()
        self.repo.write(REG, BASE)
        self.repo.git("add", "--", REG)
        self.repo.git("commit", "-q", "-m", "人类先放一份登记表")

    # --- 动作 ---------------------------------------------------------
    def red(self):
        """新增一条没有实现的用例:套件变红。"""
        self.repo.write(RED_TEST, "复现:空输入时应当返回空串\n")

    def green(self):
        """改已有用例的内容,布局不变:套件仍绿。"""
        self.repo.write("tests/W1", self.repo.read("tests/W1") + "\n补一条断言:空输入返回空串\n")

    def changes(self, *extra, role="tester"):
        return self.repo.run("handoff", "changes", with_loc("空输入时实现抛了异常"), *extra, role=role)

    def approve(self, *extra, role="tester"):
        return self.repo.run("handoff", "approve", "实现没问题,只缺覆盖", *EVIDENCE, *extra, role=role)

    # --- 观察 ---------------------------------------------------------
    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(".pair/state.json")

    def phase(self):
        return self.repo.state()["phase"]

    def body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")

    def in_head(self, rel):
        return rel in self.repo.git_paths("ls-tree", "-r", "-z", "--name-only", "HEAD")

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒的交接改了提交数或状态文件")


class TestChangesWithGap(GapBase):

    def test_加一条红用例进_impl_正文含测试缺口(self):
        self.repo.advance_to("review-impl")
        self.red()
        self.assertAccepted(self.changes("--test-gap", GAP))
        self.assertEqual(self.phase(), "impl")
        self.assertTrue(self.in_head(RED_TEST), "新用例没有随这次交接入库")
        body = self.body()
        self.assertIn("测试缺口:", body)
        self.assertIn(GAP, body)

    def test_套件是绿的被拒_文案提示_approve_test_gap(self):
        """新用例没红 = 抓不到所说的漏洞;实现没错只缺覆盖时该用 approve。"""
        self.repo.advance_to("review-impl")
        self.green()
        before = self.snapshot()
        self.assertNothingHappened(self.changes("--test-gap", GAP), before, "approve --test-gap")


class TestApproveWithGap(GapBase):

    def test_加一条绿用例进_review_test_正文含测试缺口(self):
        self.repo.advance_to("review-impl")
        self.green()
        self.assertAccepted(self.approve("--test-gap", GAP))
        self.assertEqual(self.phase(), "review-test")
        self.assertIn("补一条断言", self.repo.git("show", "HEAD:tests/W1").stdout.decode("utf-8"))
        body = self.body()
        self.assertIn("测试缺口:", body)
        self.assertIn(GAP, body)


class TestWithoutFlagUnchanged(GapBase):
    """不带旗标:review-impl 照旧只读,改测试是越界。"""

    def test_approve_不带旗标改测试被拒(self):
        self.repo.advance_to("review-impl")
        self.green()
        before = self.snapshot()
        self.assertNothingHappened(self.approve(), before)

    def test_changes_不带旗标加红用例被拒(self):
        self.repo.advance_to("review-impl")
        self.red()
        before = self.snapshot()
        self.assertNothingHappened(self.changes(), before)


class TestMustTouchTests(GapBase):
    """带旗标就得真的补了用例:`roles.tester` 名下、只追加文件以外、不是删除。"""

    def test_带旗标没动测试被拒(self):
        self.repo.advance_to("review-impl")
        before = self.snapshot()
        self.assertNothingHappened(self.approve("--test-gap", GAP), before)

    def test_只追加了登记表被拒(self):
        """只登记变异点不算补用例 —— 它本来不带旗标就能做。"""
        self.repo.advance_to("review-impl")
        self.repo.write(REG, BASE + "第四条\n")
        before = self.snapshot()
        self.assertNothingHappened(self.approve("--test-gap", GAP), before)

    def test_只删了测试被拒(self):
        """删除不算补用例。带上 `--allow-deletion`,免得被删除测试的防护先替本节拒掉。"""
        self.repo.advance_to("review-impl")
        self.repo.delete("tests/W1")
        before = self.snapshot()
        self.assertNothingHappened(
            self.approve("--test-gap", GAP, "--allow-deletion", "这条用例与新补的重复"), before)

    def test_带旗标改写登记表已有行被拒(self):
        """放开的是 `roles.tester`,只追加文件仍只追加 —— 哪怕同时补了真用例。"""
        self.repo.advance_to("review-impl")
        self.green()
        self.repo.write(REG, "第一条\n第二条被改了\n第三条\n")
        before = self.snapshot()
        self.assertNothingHappened(self.approve("--test-gap", GAP), before, "追加")

    def test_补用例同时追加登记表放行(self):
        """上一条的对照组:登记表只追加、另外补了真用例,照常放行。"""
        self.repo.advance_to("review-impl")
        self.green()
        self.repo.write(REG, BASE + "第四条\n")
        self.assertAccepted(self.approve("--test-gap", GAP))
        self.assertEqual(self.phase(), "review-test")


class TestWhereAllowed(GapBase):
    """只在 review-impl、只在之后还有 review-test 的流程里,只由 tester 用;说明不能为空。"""

    def test_空说明被拒(self):
        self.repo.advance_to("review-impl")
        self.green()
        before = self.snapshot()
        self.assertNothingHappened(self.approve("--test-gap", "   "), before)

    def test_spec_阶段_tester_带被拒(self):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1", "W1 的失败用例\n")
        before = self.snapshot()
        self.assertNothingHappened(
            self.repo.run("handoff", "写了 W1 的失败用例", "--test-gap", GAP, role="tester"), before)

    def test_impl_阶段带被拒(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1", "实现\n")
        before = self.snapshot()
        self.assertNothingHappened(
            self.repo.run("handoff", "实现 W1", "--test-gap", GAP, role="dev"), before)

    def test_dev_在_review_test_带被拒(self):
        """dev 同样改了 tester 名下的用例:否则"必须补了用例"那一道会替本节拒掉。"""
        self.repo.advance_to("review-test")
        self.green()
        before = self.snapshot()
        self.assertNothingHappened(
            self.repo.run("handoff", "approve", "覆盖够", *EVIDENCE, "--test-gap", GAP, role="dev"), before)

    def test_refactor_的_review_impl_带被拒_提示开_cover(self):
        """refactor 的 review-impl 通过即完成,补的用例没人评审。"""
        self.repo.set_plan(REFACTOR_PLAN)
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))
        self.repo.write_archaeology("R1")
        self.repo.write("src/W1", "重构后的实现\n")
        self.assertAccepted(self.repo.run("handoff", "把 W1 拆成两部分", role="dev"))
        self.assertEqual(self.phase(), "review-impl")
        self.repo.write("tests/W1", "重构后补的一条用例\n")
        before = self.snapshot()
        self.assertNothingHappened(self.approve("--test-gap", GAP), before, "[cover]")


class TestDiscussTurn(GapBase):
    """讨论回合也是"其他阶段"(W77)。讨论回合的交接走 `discuss_handoff` 那一支、不经过 `cmd_handoff` 里那次判定,
    那边单独调了一次 —— 这两条守的是那一次调用:拆掉它,旗标就在讨论里被静默吞掉。"""

    config = dict(GapBase.config, proposal_paths=["docs/proposals"])
    PROPOSAL = "docs/proposals/空输入要不要补用例.md"

    def say(self, role, text):
        old = self.repo.read(self.PROPOSAL) if self.repo.exists(self.PROPOSAL) else "# 空输入要不要补用例\n"
        self.repo.write(self.PROPOSAL, old + "\n## %s\n\n%s\n" % (role, text))

    def to_dev_turn(self):
        """spec 里 tester 开讨论,停在 dev 的讨论回合。"""
        self.repo.advance_to("spec")
        self.say("tester", "W1 的空输入路径契约没写清,先讨论要不要补用例。")
        self.assertAccepted(self.repo.run("discuss", "--proposal", self.PROPOSAL, "空输入路径没写清", role="tester"))
        self.assertEqual(self.phase(), "discuss")

    def reply(self, *extra):
        self.say("dev", "同意补,空输入返回空串。")
        return self.repo.run("handoff", "dev 的看法", *extra, role="dev")

    def test_轮到的一方带_test_gap_交接被拒(self):
        self.to_dev_turn()
        before = self.snapshot()
        self.assertNothingHappened(self.reply("--test-gap", GAP), before)
        self.assertEqual(self.phase(), "discuss")

    def test_对照组_不带旗标照常交接(self):
        self.to_dev_turn()
        self.assertAccepted(self.reply())


class TestFullRound(GapBase):

    def test_打回补红用例_修绿_两次评审通过_走到完成_打回计数为一(self):
        self.repo.advance_to("review-impl")
        self.red()
        self.assertAccepted(self.changes("--test-gap", GAP))
        self.repo.write("src/W1-缺口", "修好空输入\n")
        self.assertAccepted(self.repo.run("handoff", "修好空输入", role="dev"))
        self.assertEqual(self.phase(), "review-impl")
        self.assertAccepted(self.approve())
        self.assertEqual(self.phase(), "review-test")
        self.assertEqual(self.repo.state()["changes_count"], 1)
        self.assertAccepted(self.repo.run("handoff", "approve", "补的用例对上漏洞", *EVIDENCE, role="dev"))
        self.assertEqual(self.phase(), "idle")
        self.assertIn("- [x] **W1**", self.repo.read("docs/PLAN.md"))


class TestBrief(GapBase):

    def test_review_impl_的简报说明这个旗标(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("status", role="tester")
        self.assertIn("--test-gap", r.text)


if __name__ == "__main__":
    import unittest
    unittest.main()
