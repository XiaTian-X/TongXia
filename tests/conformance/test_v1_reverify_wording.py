# -*- coding: utf-8 -*-
"""W38:从没校验过与契约变了,提示分开说。

契约「从没校验过与契约变了,提示分开说」。第二十轮刚开工,tester 先通过开工前校验,idle 归 dev,dev 看到的是
"通读契约里变了的那几节,往 `setup-verification-dev.md` **末尾追加**一段补记" —— 那时文件根本不存在;
`stale_verification` 还说"存量项目升级上来就是这样"。

**判据**:两处 —— dev 的 `status`(idle 提示)与 tester 的 `claim` 被拒的理由 —— 出现哪种说法。
三种情况:从没校验过(状态里没有记录、角色结论文件也不在)、契约变了、存量升级(没有记录但结论文件已在)。
"""

from harness import VERIFY_OK, PairTestCase, setup_report

REPORT = setup_report("W1", "W2")
DEV_REPORT = "docs/reviews/setup-verification-dev.md"
APPEND = "末尾追加"
LEGACY = "存量项目升级"
NEW = "写一份"


class WordingBase(PairTestCase):

    config = {"require_setup_verification": True}

    def verify(self, role):
        self.repo.write("docs/reviews/setup-verification-%s.md" % role, REPORT)
        self.assertAccepted(self.repo.run(*VERIFY_OK, role=role))

    def dev_status(self):
        r = self.repo.run("status", role="dev")
        self.assertAccepted(r)
        return r.text

    def claim_refusal(self):
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "dev")
        return r.text


class TestNeverVerified(WordingBase):
    """第二十轮的原样:tester 先校验,dev 从没校验过、它那份结论也还没有。"""

    def setUp(self):
        super().setUp()
        self.verify("tester")
        self.assertFalse(self.repo.exists(DEV_REPORT), "前提:dev 那份结论还不存在")

    def test_dev_的_status_说新建_不说末尾追加(self):
        out = self.dev_status()
        self.assertNotIn(APPEND, out)
        self.assertNotIn(LEGACY, out)
        self.assertIn(NEW, out)
        self.assertIn(DEV_REPORT.rsplit("/", 1)[1], out)

    def test_claim_被拒的理由说新建_不说存量升级(self):
        out = self.claim_refusal()
        self.assertNotIn(APPEND, out)
        self.assertNotIn(LEGACY, out)
        self.assertIn(NEW, out)


class TestContractChanged(WordingBase):
    """对照组:dev 校验过、之后契约变了 —— 照旧说往末尾追加。"""

    def setUp(self):
        super().setUp()
        self.verify("tester")
        self.verify("dev")
        self.repo.set_plan(self.repo.read("docs/PLAN.md"),
                           contract=self.repo.read("docs/CONTRACT.md") + "\n**补充** 人类改了一句。\n")
        self.verify("tester")

    def test_dev_的_status_照旧说末尾追加(self):
        out = self.dev_status()
        self.assertIn(APPEND, out)
        self.assertNotIn(NEW, out)

    def test_claim_被拒的理由也说末尾追加(self):
        out = self.claim_refusal()
        self.assertIn(APPEND, out)
        self.assertNotIn(NEW, out)


class TestLegacyUpgrade(WordingBase):
    """状态里没有 dev 的记录,但它那份结论文件已经在(存量项目升级上来)—— 照"存量升级"说,不说"写一份"。"""

    def setUp(self):
        super().setUp()
        self.repo.write(DEV_REPORT, REPORT)
        self.repo.git("add", DEV_REPORT)
        self.repo.git("commit", "-q", "-m", "人类:旧版本留下的 dev 结论")
        self.verify("tester")

    def test_claim_被拒的理由说存量升级(self):
        out = self.claim_refusal()
        self.assertIn(LEGACY, out)
        self.assertNotIn(NEW, out)
