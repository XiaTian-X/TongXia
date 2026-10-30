# -*- coding: utf-8 -*-
"""W78:用例改名的声明(开放条目 56)—— `handoff --renamed "旧用例ID=新用例ID"`。

契约「用例改名的声明」。

- 沿用 W61 的假全量(`test_v1_full_vanished.VanishBase`):`suite/` 下文件名是用例名,内容决定这一次报红、绿、跳过(`skip`)还是不出现(`gone`);
  用例 ID 是 `suite.<名>`。"改名"由人类提交 `suite/` 的变化来造 —— `suite/` 不在任何角色名下;tester 那一回合另改 `tests/W1`,满足"改动了 tester 路径"。
- 被拒时断言提交数与 `.pair/state.json` 不变。
- 提交正文的两种行用 ASCII 括号与冒号,箭头是 U+2192(契约原文)。
"""

import json
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import EVIDENCE, PairTestCase, with_loc
from test_v1_full_vanished import FULL_REPORT, FULL_RUNNER, VanishBase

ARROW = chr(0x2192)
GAP = "空输入那条路径没有用例,补一条"
PROPOSAL = "docs/proposals/用例要不要改名.md"
REG = "checks/mutations.txt"


def R(old, new):
    return ("--renamed", "%s=%s" % (old, new))


def declared(old, new):
    return "改名(声明): %s %s %s" % (old, ARROW, new)


def matched(old, new):
    return "改名(对上了): %s %s %s" % (old, ARROW, new)


class RenameBase(VanishBase):

    def setUp(self):
        """同 `VanishBase` 的假全量,另配提案目录(讨论回合那条要用)与 tester 的只追加登记表
        (`checks/mutations.txt`,同 `test_v1_review_append`);不挂门禁计数。"""
        self.outside = Path(tempfile.mkdtemp(prefix="pair-rename-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        (self.outside / "full.py").write_text(FULL_RUNNER, encoding="utf-8")
        q = lambda *a: " ".join(shlex.quote(str(x)) for x in a)
        self.config = {
            "full_test_cmd": q(sys.executable, self.outside / "full.py", FULL_REPORT),
            "full_test_report": FULL_REPORT,
            "proposal_paths": ["docs/proposals"],
            "roles": {"tester": ["tests", "checks"], "dev": ["src"]},
            "review_append_paths": {"tester": [REG]},
        }
        PairTestCase.setUp(self)

    # --- 动作 ---------------------------------------------------------
    def to_spec(self):
        """spec 回合写好失败用例(tests/W1 没有 src/W1,红),只差交接。"""
        self.repo.advance_to("spec")
        self.repo.write("tests/W1", "W1 的失败用例\n")

    def spec_handoff(self, *extra):
        return self.pair("handoff", "写了 W1 的失败用例", *extra)

    def to_review_test_after_spec(self, *spec_extra):
        """spec 回合(可带声明)→ impl → review-impl approve,停在 review-test。"""
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*spec_extra))
        self.repo.write("src/W1", "实现\n")
        self.assertAccepted(self.pair("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.pair("handoff", "approve", "查过无硬编码", *EVIDENCE))
        self.assertEqual(self.phase(), "review-test")

    def gap_approve(self, *extra):
        """review-impl 里补一条绿的用例并带 `--test-gap` 通过。"""
        self.repo.write("tests/W1", self.repo.read("tests/W1") + "\n补一条断言\n")
        return self.pair("handoff", "approve", "实现没问题,只缺覆盖", *EVIDENCE, "--test-gap", GAP, *extra)

    # --- 观察 ---------------------------------------------------------
    def phase(self):
        return self.repo.state()["phase"]

    def pairs(self):
        """状态里的 `renamed_tests`,统一成 {(旧, 新)};没有这个键或为空 → 空集合。"""
        raw = self.repo.state().get("renamed_tests") or {}
        items = raw.items() if isinstance(raw, dict) else [tuple(x) for x in raw]
        return set(items)

    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(".pair/state.json")

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒时提交数或状态文件变了")


class TestDeclare(RenameBase):

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()

    def test_spec_回合带声明放行_状态记下_正文含声明行(self):
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*R("suite.B", "suite.C")))
        self.assertEqual(self.pairs(), {("suite.B", "suite.C")})
        self.assertIn(declared("suite.B", "suite.C"), self.last_body())

    def test_多条一次给出都记下(self):
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*R("suite.A", "suite.X") + R("suite.B", "suite.C")))
        self.assertEqual(self.pairs(), {("suite.A", "suite.X"), ("suite.B", "suite.C")})
        body = self.last_body()
        self.assertIn(declared("suite.A", "suite.X"), body)
        self.assertIn(declared("suite.B", "suite.C"), body)

    def test_review_impl_带_test_gap_时声明放行(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.gap_approve(*R("suite.B", "suite.C")))
        self.assertEqual(self.pairs(), {("suite.B", "suite.C")})

    def test_分两回合给出合并(self):
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*R("suite.B", "suite.C")))
        self.repo.write("src/W1", "实现\n")
        self.assertAccepted(self.pair("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.gap_approve(*R("suite.A", "suite.X")))
        self.assertEqual(self.pairs(), {("suite.A", "suite.X"), ("suite.B", "suite.C")})


class TestWhoAndWhere(RenameBase):
    """只有 tester、只在 spec 或带 `--test-gap` 的 review-impl。"""

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()

    def test_dev_在_impl_带被拒(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1", "实现\n")
        before = self.snapshot()
        self.assertNothingHappened(self.pair("handoff", "实现 W1", *R("suite.B", "suite.C"), role="dev"), before)

    def test_dev_在_review_test_带被拒(self):
        self.repo.advance_to("review-test")
        before = self.snapshot()
        self.assertNothingHappened(self.dev_approve(*R("suite.B", "suite.C")), before)

    def test_review_impl_不带_test_gap_带被拒_对照组不带声明照常通过(self):
        """往只追加的登记表里加一行:不带 `--test-gap` 也合法、也算改动了 tester 路径 ——
        不这样做,拒它的是"本回合必须改动了 tester 路径",拆掉"只在带 `--test-gap` 的 review-impl"照样绿(探针证实过)。"""
        self.repo.write(REG, "第一条\n")
        self.repo.git("add", REG)
        self.repo.git("commit", "-q", "-m", "人类先放一份登记表")
        self.repo.advance_to("review-impl")
        self.repo.write(REG, "第一条\n第二条\n")
        before = self.snapshot()
        r = self.pair("handoff", "approve", "实现没问题", *EVIDENCE, *R("suite.B", "suite.C"))
        self.assertNothingHappened(r, before)
        self.assertAccepted(self.pair("handoff", "approve", "实现没问题", *EVIDENCE))

    def test_讨论回合带被拒(self):
        self.repo.advance_to("spec")
        self.repo.write(PROPOSAL, "# 用例要不要改名\n\n## tester\n\nsuite.B 的名字和契约对不上,要不要改名。\n")
        self.assertAccepted(self.pair("discuss", "--proposal", PROPOSAL, "用例名与契约对不上"))
        self.assertEqual(self.phase(), "discuss")
        self.repo.write(PROPOSAL, self.repo.read(PROPOSAL) + "\n## dev\n\n同意改名。\n")
        before = self.snapshot()
        r = self.pair("handoff", "dev 的看法", *R("suite.B", "suite.C"), role="dev")
        self.assertNothingHappened(r, before)


class TestDeclarationChecked(RenameBase):
    """声明不合格就拒绝,提交数与状态不变。被拒什么都不改,所以同一个回合里可以逐个试。"""

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()

    def assertEachRefused(self, cases):
        self.to_spec()
        for args in cases:
            with self.subTest(args=args):
                before = self.snapshot()
                self.assertNothingHappened(self.spec_handoff(*args), before)

    def test_格式不对被拒_没有等号_一边为空_两边相同(self):
        self.assertEachRefused([
            ("--renamed", "suite.B suite.C"),
            ("--renamed", "suite.B="),
            ("--renamed", "=suite.C"),
            ("--renamed", "  =  "),
            ("--renamed", "suite.B=suite.B"),
            ("--renamed", "suite.B = suite.B"),
        ])

    def test_一旧对两新_两旧对一新_链_被拒(self):
        self.assertEachRefused([
            R("suite.B", "suite.C") + R("suite.B", "suite.D"),
            R("suite.A", "suite.C") + R("suite.B", "suite.C"),
            R("suite.A", "suite.B") + R("suite.B", "suite.C"),
        ])

    def test_与状态里已记的合起来不是一对一被拒(self):
        """spec 回合记下 B → C,review-impl 再声明 A → C:两旧对一新。"""
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*R("suite.B", "suite.C")))
        self.repo.write("src/W1", "实现\n")
        self.assertAccepted(self.pair("handoff", "实现 W1", role="dev"))
        before = self.snapshot()
        self.assertNothingHappened(self.gap_approve(*R("suite.A", "suite.C")), before)

    def test_旧名不在全量基线里被拒(self):
        self.assertEachRefused([R("suite.Z", "suite.C")])

    def test_本回合没改_tester_路径被拒_对照组不带声明照常交接(self):
        """失败用例由人类先提交:套件已经红,本回合只写笔记 —— 能拒它的只剩"必须改动了 tester 路径"。"""
        self.repo.advance_to("spec")
        self.repo.write("tests/W1", "W1 的失败用例\n")
        self.repo.git("add", "tests/W1")
        self.repo.git("commit", "-q", "-m", "人类先放了一条失败用例")
        self.repo.write("docs/notes/W1.md", "这一回合只记笔记。\n")
        before = self.snapshot()
        self.assertNothingHappened(self.spec_handoff(*R("suite.B", "suite.C")), before)
        self.assertAccepted(self.spec_handoff())


class TestNoBaseline(RenameBase):

    def test_读不出全量基线时不判旧名在不在(self):
        """`旧名不在基线里被拒` 的对照组:没跑过 verify-setup,基线文件不存在。"""
        self.suite(A="green", B="green")
        self.to_spec()
        self.assertAccepted(self.spec_handoff(*R("suite.Z", "suite.C")))
        self.assertEqual(self.pairs(), {("suite.Z", "suite.C")})


class TestCompletion(RenameBase):
    """spec 回合声明 B → C;到 review-test 时人类把 suite.B 改名。"""

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()
        self.to_review_test_after_spec(*R("suite.B", "suite.C"))

    def test_新名在跑_完成成功_正文含对上了_状态清空(self):
        self.suite(B="gone", C="green")
        r = self.dev_approve()
        self.assertEqual(self.phase(), "idle", "本应完成:\n%r" % r)
        self.assertIn(matched("suite.B", "suite.C"), self.last_body())
        self.assertEqual(self.pairs(), set(), "完成时要清空")
        self.assertEqual(self.committed_executed(), ["suite.A", "suite.C"])

    def test_新名没跑_照旧被拒并列出旧名(self):
        self.suite(B="gone")
        self.assertCompletionRefused(self.dev_approve(), "suite.B")

    def test_新名是跳过的不算跑过(self):
        """跑过的集合不含跳过的(W61 同一口径)。"""
        self.suite(B="gone", C="skip")
        self.assertCompletionRefused(self.dev_approve(), "suite.B")

    def test_对上一条_另一条不再跑的照旧被拒_只列它(self):
        """声明只扣它自己那一条:B → C 对上了,A 也不再跑,照旧按消失拒,文案里只有 A。"""
        self.suite(A="gone", B="gone", C="green")
        r = self.dev_approve()
        self.assertCompletionRefused(r, "suite.A")
        self.assertNotIn("suite.B", r.text, "对上了的改名不该再列成消失")


class TestRefusalHint(RenameBase):

    def test_不再跑的拒绝文案提到_renamed(self):
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(B="gone", C="green")
        self.assertCompletionRefused(self.dev_approve(), "suite.B", "--renamed")


class TestShortcut(RenameBase):
    """改名当时没声明,完成被"不再跑"拒绝;dev 为一处只改测试的问题打回;tester 在修正回合补上声明。"""

    def setUp(self):
        super().setUp()
        self.suite(A="green", B="green")
        self.baseline()
        self.repo.advance_to("review-test")
        self.suite(B="gone", C="green")
        self.assertCompletionRefused(self.dev_approve())
        self.assertAccepted(self.pair("handoff", "changes", with_loc("W1 的断言少了一句说明"), role="dev"))
        self.assertEqual(self.phase(), "spec")
        self.repo.write("tests/W1", "补了一句断言说明\n")

    def test_补上声明_修正回合走捷径回_review_test_再完成对上了(self):
        self.assertAccepted(self.pair("handoff", "按打回意见补了 W1 的说明", *R("suite.B", "suite.C")))
        self.assertEqual(self.phase(), "review-test")
        r = self.dev_approve()
        self.assertEqual(self.phase(), "idle", "本应完成:\n%r" % r)
        self.assertIn(matched("suite.B", "suite.C"), self.last_body())

    def test_对照组_不声明进_impl(self):
        self.assertAccepted(self.pair("handoff", "按打回意见补了 W1 的说明"))
        self.assertEqual(self.phase(), "impl")


class TestClaimClears(RenameBase):

    def test_认领时清空(self):
        """正常流程里完成就清空了,下一项认领时本来就空 —— 所以由人类直接提交一份带着键的状态(空闲时),再认领。"""
        state = self.repo.state()
        state["renamed_tests"] = {"suite.B": "suite.C"}
        self.repo.write(".pair/state.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        self.repo.git("add", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "人类提交了带声明的旧状态")
        self.assertAccepted(self.pair("claim", "W1"))
        self.assertEqual(self.pairs(), set())


if __name__ == "__main__":
    import unittest
    unittest.main()
