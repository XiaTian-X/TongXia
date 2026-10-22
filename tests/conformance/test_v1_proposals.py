# -*- coding: utf-8 -*-
"""W66:`proposal_paths` —— 双方任何阶段都能写的提案目录,不冒充评审或异议。

契约「提案目录」(含 spec 回合带声明补的「补充」,开工前审查 ⑳:"重叠"= 有一个文件会同时命中两边)。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`,评审目录 `docs/reviews`,记忆层 `docs/notes` 与 `docs/DECISIONS.md`。
本文件的类默认配 `proposal_paths: ["docs/proposals"]`。

**四处不认它**用最强的形状去试:提案的**名字和小节都照异议文件写**、提案里写了**真实的位置引用** —— 把提案并进评审目录的实现,
在这几条里会被放行;只写一份随便的提案,两种实现都会被拒,区分不出来。
"""

import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from harness import (DISPUTE_DOC, EVIDENCE, TEST_CMD, VERIFY_OK, BareRepo, PairTestCase, setup_report,
                     with_loc)

PROPOSAL = "docs/proposals/拆出缓存层.md"
PROPOSAL_TEXT = ("# 提案:把缓存从 W1 里拆出去\n\n"
                 "做 W1 的时候发现缓存失效的规则和 W1 的契约无关,建议另开一个工作项。\n")


class ProposalBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}

    def committed(self):
        return self.repo.git_paths("show", "--name-only", "--format=", "-z", "HEAD")

    def head_body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")

    def commit_proposal_as_tester(self):
        """tester 在 spec 回合写下一份提案并交接 —— 之后它就是"已提交的"。"""
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.repo.write(PROPOSAL, PROPOSAL_TEXT)
        self.assertAccepted(self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))
        self.assertIn(PROPOSAL, self.committed())


class TestWritableInEveryWorkingPhase(ProposalBase):

    def test_spec_tester(self):
        self.commit_proposal_as_tester()
        self.assertIn("提案: %s" % PROPOSAL, self.head_body(), "交接正文要写一行 提案: <路径>")

    def test_impl_dev(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write("docs/proposals/dev-的方向.md", "# dev 的提案\n\n另一个方向。\n")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertIn("docs/proposals/dev-的方向.md", self.committed())

    def test_review_impl_tester(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/proposals/评审时想到的.md", "# 评审时想到的\n\n超出本项范围。\n")
        self.assertAccepted(self.repo.run("handoff", "approve", "查过无硬编码", *EVIDENCE, role="tester"))
        self.assertIn("docs/proposals/评审时想到的.md", self.committed())

    def test_review_test_dev(self):
        self.repo.advance_to("review-test")
        self.repo.write("docs/proposals/完成前想到的.md", "# 完成前想到的\n\n下一项再做。\n")
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))
        self.assertIn("docs/proposals/完成前想到的.md", self.committed())
        self.assertEqual(self.repo.state()["phase"], "idle")


class TestAppendOnly(ProposalBase):
    """已提交的提案只能追加 —— 不分阶段与角色(dev 在 impl 改 tester 写的那份)。"""

    def setUp(self):
        super().setUp()
        self.commit_proposal_as_tester()
        self.repo.write("src/W1")

    def test_改一行被拒(self):
        self.repo.write(PROPOSAL, PROPOSAL_TEXT.replace("建议另开", "不必另开"))
        self.assertRefused(self.repo.run("handoff", "实现 W1", role="dev"))

    def test_删除被拒(self):
        self.repo.delete(PROPOSAL)
        self.assertRefused(self.repo.run("handoff", "实现 W1", role="dev"))

    def test_追加放行(self):
        self.repo.write(PROPOSAL, PROPOSAL_TEXT + "\n## dev 的回应\n\n同意,另开。\n")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))


class TestNotRecognisedAsReview(ProposalBase):

    def test_异议只写在提案里_即便名字与小节都照异议文件写_被拒(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/proposals/W1-dispute.md", DISPUTE_DOC)
        r = self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")
        self.assertRefused(r)
        self.assertEqual(self.repo.state()["phase"], "impl")

    def test_对照组_同一份异议写在评审目录就放行(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", DISPUTE_DOC)
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev"))

    def test_打回理由没有位置_位置只写在提案里_被拒(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/proposals/W1-review-impl.md", "# 打回\n\n`src/W1:1` 对测试输入特判了。\n")
        r = self.repo.run("handoff", "changes", "实现有问题", role="tester")
        self.assertRefused(r, "位置")
        self.assertEqual(self.repo.state()["phase"], "review-impl")

    def test_提案名不对应工作项_命名检查不管它(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/proposals/随手记的方向.md", "# 方向\n\n以后再说。\n")
        self.assertAccepted(self.repo.run("handoff", "approve", "查过无硬编码", *EVIDENCE, role="tester"))

    def test_只改提案不要求_doc_reason(self):
        """提案不是规范性文档(和评审一样是历史记录)。"""
        self.commit_proposal_as_tester()
        self.assertNotIn("文档改动理由", self.head_body())


class TestScopeExempt(ProposalBase):

    config = {"proposal_paths": ["docs/proposals"], "scope": ["src", "tests"]}

    def test_配了_scope_时提案豁免(self):
        self.commit_proposal_as_tester()


class TestFingerprintExcludesProposals(PairTestCase):
    """只改提案,门禁不重跑(排除出 W57 的指纹)。"""

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-proposal-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        (self.outside / "gate.py").write_text("import sys\nopen(sys.argv[1], 'a').write('x\\n')\n", encoding="utf-8")
        self.counter = self.outside / "runs"
        self.config = {"proposal_paths": ["docs/proposals"],
                       "test_cmd": "%s %s %s && %s" % (shlex.quote(sys.executable), shlex.quote(str(self.outside / "gate.py")),
                                                        shlex.quote(str(self.counter)), TEST_CMD)}
        super().setUp()

    def runs(self):
        return sum(1 for _ in open(self.counter)) if self.counter.exists() else 0

    def test_只写提案不重跑(self):
        env = {"PAIR_FRESH_TESTS": ""}
        self.assertAccepted(self.repo.run("status", env=env))
        before = self.runs()
        self.repo.write(PROPOSAL, PROPOSAL_TEXT)
        self.assertAccepted(self.repo.run("status", env=env))
        self.assertEqual(self.runs(), before)


class TestInbox(ProposalBase):

    def test_对方的_inbox_摆出提案原文(self):
        self.commit_proposal_as_tester()
        out = self.repo.run("inbox", role="dev").out
        self.assertIn("建议另开一个工作项", out)


class TestDefaultOff(PairTestCase):
    """默认 `[]`:那个目录照旧受角色约束 —— 不给老项目默认开启。"""

    def test_没配时写提案目录越界(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.repo.write(PROPOSAL, PROPOSAL_TEXT)
        self.assertRefused(self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))


class TestVerifySetupOverlap(PairTestCase):
    """⑳:有一个文件会同时命中两边就算重叠;失败信息点名重叠的是哪个键。"""

    def verify(self, **extra):
        cfg = {"proposal_paths": ["docs/proposals"]}
        cfg.update(extra)
        self.repo.cleanup()
        from harness import PairRepo
        self.repo = PairRepo(cfg)
        self.addCleanup(self.repo.cleanup)
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        return self.repo.run(*VERIFY_OK)

    def test_对照组_不重叠时通过(self):
        self.assertAccepted(self.verify())

    def test_与角色重叠_前缀(self):
        """用一个别的键都不碰的目录 `plans/`:`docs` 下还有评审目录、记忆层与冻结的规划文件,拿它试会被别的检查先拒,判不出这一条。"""
        self.assertRefused(self.verify(proposal_paths=["plans/proposals"],
                                       roles={"tester": ["tests", "plans"], "dev": ["src"]}), "roles")

    def test_与评审目录重叠(self):
        self.assertRefused(self.verify(shared_paths=["docs/reviews", "docs/proposals"]), "shared_paths")

    def test_与冻结路径重叠_单个文件(self):
        self.assertRefused(self.verify(frozen_paths=["docs/PLAN.md", "docs/CONTRACT.md", ".agents", ".pair",
                                                     "docs/proposals/定稿.md"]), "frozen_paths")

    def test_与记忆层重叠(self):
        self.assertRefused(self.verify(notes_dir="docs/proposals"), "notes_dir")

    def test_与_ignore_paths_重叠_glob(self):
        self.assertRefused(self.verify(ignore_paths=["docs/proposals/*.md"]), "ignore_paths")

    def test_对照组_星号不跨目录不算重叠(self):
        self.assertAccepted(self.verify(proposal_paths=["plans/proposals"],
                                        roles={"tester": ["tests"], "dev": ["src", "plans/*.md"]}))

    def test_对照组_前缀那一条去掉重叠就通过(self):
        """与上面"前缀"那条同一份配置,只把 tester 的 `plans` 换成 `plans-old`:证明拒绝来自重叠,不是别的。"""
        self.assertAccepted(self.verify(proposal_paths=["plans/proposals"],
                                        roles={"tester": ["tests", "plans-old"], "dev": ["src"]}))


class TestInitWritesProposals(PairTestCase):

    def test_init_给新项目写_docs_proposals(self):
        import json
        repo = BareRepo({"pyproject.toml": "[project]\nname = \"demo\"\n", "src/__init__.py": "",
                         "tests/__init__.py": "",
                         "tests/test_ok.py": "import unittest\n\nclass T(unittest.TestCase):\n"
                                             "    def test_ok(self):\n        self.assertTrue(True)\n"})
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        self.assertEqual(json.loads(repo.read(".pair/config.json")).get("proposal_paths"), ["docs/proposals"])


if __name__ == "__main__":
    import unittest
    unittest.main()
