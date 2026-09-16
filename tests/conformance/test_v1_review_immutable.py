# -*- coding: utf-8 -*-
"""W18:评审记录只能追加。

契约「评审记录只能追加」。W14、W15 的第二次 review-impl 各把上一版评审记录整份改写
(-72/+48、-49/+28),第一次的逐段对契约表与变异复现表在工作区里没了。`DECISIONS.md`
改写会被拒,**评审记录不会** —— 而简报其实一直给着正确的名字(`review_file_for` 在打回过
之后算的是 `-2`),缺的只是写侧的拒绝。

**范围与命名检查同一个**:评审目录的**顶层 `.md`**(`_review_top_level`)。子目录、非 `.md`、
`ignore_paths` 与协议日志都不管。**判据是"相对 HEAD 有删除行"**,与 `--basis` 判改写同口径。

**拒绝文案只断言三样**:本回合该写的文件名、"不要撤销"、"告诉人类" —— 契约与 PLAN 两处措辞
不同(`如果这份改动不是你做的` / `如果不是你改的`),取两者都有的部分。
"""

import unittest

from harness import EVIDENCE, PairTestCase, VERIFY_OK, setup_report

REVIEWS = "docs/reviews"
DONE_FILE = REVIEWS + "/W1-review-impl.md"
BASE = "# W1 review-impl\n\n裁决: approve。\n逐段对过契约。\n"
OLD_REPORT = REVIEWS + "/setup-verification.md"


class ImmutableBase(PairTestCase):

    def commit_review(self, rel=DONE_FILE, text=BASE, msg="人类先提交一份评审记录"):
        self.repo.write(rel, text)
        self.repo.git("add", "--", rel)
        self.repo.git("commit", "-q", "-m", msg)

    def approve_impl(self):
        return self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")

    def phase(self):
        return self.repo.state()["phase"]


class TestRewriteIsRefused(ImmutableBase):

    def test_评审回合改写已提交的评审记录被拒_文案给出该写的文件名(self):
        self.commit_review()
        self.repo.advance_to("review-impl")
        self.repo.write(DONE_FILE, "# W1 review-impl\n\n裁决: approve。\n(上一版没了)\n")
        r = self.approve_impl()
        self.assertRefused(r, DONE_FILE, "不要撤销", "告诉人类")
        self.assertIn("W1-review-impl.md", r.text, "文案要给出本回合该写的文件名")
        self.assertEqual(self.phase(), "review-impl")

    def test_删掉整份评审记录被拒(self):
        self.commit_review()
        self.repo.advance_to("review-impl")
        self.repo.delete(DONE_FILE)
        self.assertRefused(self.approve_impl(), DONE_FILE)
        self.assertEqual(self.phase(), "review-impl")

    def test_改名被拒(self):
        """改名在 HEAD 那一侧就是一次删除(W16 起 `git status` 带 `--no-renames`)。"""
        self.commit_review()
        self.repo.advance_to("review-impl")
        self.repo.git("mv", DONE_FILE, REVIEWS + "/W1-review-impl-旧.md")
        self.assertRefused(self.approve_impl(), DONE_FILE)
        self.assertEqual(self.phase(), "review-impl")

    def test_不分角色不分阶段_dev_在_impl_改写也被拒(self):
        """评审目录是 `shared_paths`,dev 在 impl 回合写得了它。"""
        self.commit_review()
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write(DONE_FILE, BASE.replace("逐段对过契约。", "改一句"))
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertRefused(r, DONE_FILE)
        self.assertEqual(self.phase(), "impl")


class TestAppendAndNewAreAllowed(ImmutableBase):

    def test_纯追加放行(self):
        self.commit_review()
        self.repo.advance_to("review-impl")
        self.repo.write(DONE_FILE, BASE + "\n## 第二次评审\n\n又核了一遍。\n")
        self.assertAccepted(self.approve_impl())
        self.assertEqual(self.phase(), "review-test")

    def test_新建文件放行(self):
        """打回过之后该写的是 `-2`,新建正是本节要引导的用法。"""
        self.commit_review()
        self.repo.advance_to("review-impl")
        self.repo.write(REVIEWS + "/W1-review-impl-2.md", "# 第二次评审\n\n裁决: approve。\n")
        self.assertAccepted(self.approve_impl())

    def test_ignore_paths_豁免(self):
        self.repo.write(".pair/config.json", self.repo.read(".pair/config.json").replace(
            '"ignore_paths": []', '"ignore_paths": ["%s/忽略的.md"]' % REVIEWS))
        self.commit_review(REVIEWS + "/忽略的.md", "# 随手记\n\n第一版。\n",
                           "人类放一份被忽略的文件")
        self.repo.git("add", "--", ".pair/config.json")
        self.repo.git("commit", "-q", "-m", "人类改配置")
        self.repo.advance_to("review-impl")
        self.repo.write(REVIEWS + "/忽略的.md", "# 随手记\n\n整份改写。\n")
        self.assertAccepted(self.approve_impl())

    def test_子目录与非_md_不管(self):
        """范围与命名检查同一个:只管顶层 `.md`。"""
        self.commit_review(REVIEWS + "/附件/说明.md", "# 附件\n\n第一版。\n", "人类放一份子目录文件")
        self.commit_review(REVIEWS + "/数据.txt", "第一版\n", "人类放一份非 md")
        self.repo.advance_to("review-impl")
        self.repo.write(REVIEWS + "/附件/说明.md", "# 附件\n\n整份改写。\n")
        self.repo.write(REVIEWS + "/数据.txt", "整份改写\n")
        self.assertAccepted(self.approve_impl())


class TestVerifySetupSide(ImmutableBase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def _verified_once(self):
        self.repo.write(OLD_REPORT, self.REPORT)
        self.assertAccepted(self.repo.run(*VERIFY_OK, role="tester"))

    def test_改写已提交的结论被拒_且拒绝早于写状态(self):
        """**场景要让状态真的会变**:结论由人类提交(不经过 `verify-setup`),所以
        `setup_verified` 还是 `False`;这时把结论删掉一行再**第一次**校验。

        拒绝若发生在 `save_state` 之后,状态文件就会带着 `setup_verified: true` 留在工作区 ——
        W12 与 W15 两次治过的"状态对、退出码错",而且下一次交接会判它篡改。

        第一版让 `verify-setup` 先通过一次再改写:那时 `setup_verified` 早已是 `true`,
        再写一次状态文件字节相同,**把检查挪到 `save_state` 之后也照样绿**。判据比性质宽。"""
        self.commit_review(OLD_REPORT, self.REPORT, "人类先提交一份结论")
        self.assertFalse(self.repo.state()["setup_verified"])
        rewritten = self.REPORT.replace("以下结论是逐节读过之后写的。\n\n", "")
        self.assertNotEqual(rewritten, self.REPORT, "场景前提:结论必须真的被删掉一行")
        self.repo.write(OLD_REPORT, rewritten)
        state_before = self.repo.read(".pair/state.json")
        head_before = self.repo.git("rev-parse", "HEAD").stdout

        r = self.repo.run(*VERIFY_OK, role="tester")
        self.assertRefused(r, OLD_REPORT)
        self.assertEqual(self.repo.read(".pair/state.json"), state_before,
                         "拒绝之后状态文件不该变 —— 拒绝要早于 save_state")
        self.assertFalse(self.repo.state()["setup_verified"])
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout, head_before,
                         "拒绝之后不该产生提交")

    def test_往结论末尾追加照旧放行(self):
        """W13 起的约定就是"先读、追加,不要覆盖" —— tester 每次重跑都往末尾补记。"""
        self._verified_once()
        self.repo.write(OLD_REPORT, self.REPORT + "\n## 补记\n\n契约又变了一次,重读过。\n")
        self.assertAccepted(self.repo.run(*VERIFY_OK, role="tester"))


if __name__ == "__main__":
    unittest.main()
