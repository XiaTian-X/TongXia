# -*- coding: utf-8 -*-
"""W23:验证用的副本放在 `.pair/scratch/`。

契约「验证用的副本放在 .pair/scratch/」。第七轮两个会话都自发做变异验证,四次在仓库外建副本 ——
写权限边界只管仓库里的路径,在仓库里换入错误实现又会留下被判越界的改动。

**被 git 忽略的文件不出现在 `git status` 里**,所以只要 `init` 写的 `.gitignore` 有这一行,
边界、提交、`verify-setup` 的警告都看不见它们。

**harness 的 `.gitignore` 是手写的两行**,不是 `GITIGNORE_LINES`。这里的用例要守的是
"`GITIGNORE_LINES` 里有这一行就够了",所以先以人类身份把 `GITIGNORE_LINES` 原样写进去 ——
在 harness 里手加 `.pair/scratch/` 的话,用例就与实现无关,拆掉那一行也照样绿。
"""

import unittest

from harness import GO_CONFIG, VERIFY_OK, BareRepo, PairTestCase, setup_report
from test_v1_setup import PY_PROJECT
from test_v1_shipped import PAIR, REPO

SCRATCH = ".pair/scratch/"


def adopt_gitignore(repo):
    """以人类身份把 `init` 会写的那几行追加进 `.gitignore` 并提交。"""
    have = repo.read(".gitignore")
    add = [ln for ln in PAIR.GITIGNORE_LINES if ln not in have.splitlines()]
    repo.write(".gitignore", have + "".join(ln + "\n" for ln in add))
    repo.git("add", ".gitignore")
    repo.git("commit", "-q", "-m", "人类:.gitignore 跟上 init")


class TestInitIgnoresScratch(unittest.TestCase):

    def test_init_写的_gitignore_含_scratch(self):
        repo = BareRepo(PY_PROJECT)
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        self.assertIn(SCRATCH, repo.read(".gitignore").splitlines())

    def test_本仓库自己的_gitignore_也有(self):
        self.assertIn(SCRATCH, (REPO / ".gitignore").read_text(encoding="utf-8").splitlines())


class TestScratchIsInvisible(PairTestCase):

    def setUp(self):
        super().setUp()
        adopt_gitignore(self.repo)

    def scratch_copy(self):
        """一份验证副本:换入了错误实现的源码与一个探针脚本。"""
        self.repo.write(SCRATCH + "copy/src/W1", "故意改错的实现")
        self.repo.write(SCRATCH + "probe.py", "print('变异探针')\n")

    def test_评审回合写_scratch_不被拒_也不进提交(self):
        self.repo.advance_to("review-impl")
        self.scratch_copy()
        r = self.repo.run("handoff", "approve", "查过", "--checked", "在副本里换入错误实现,用例红了",
                          "--uncovered", "无", role="tester")
        self.assertAccepted(r)
        tracked = self.repo.git_paths("ls-files", "-z")
        self.assertNotIn(SCRATCH + "copy/src/W1", tracked)
        self.assertNotIn(SCRATCH + "probe.py", tracked)

    def test_dev_在_impl_回合写_scratch_不被拒(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.scratch_copy()
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertNotIn(SCRATCH + "probe.py", self.repo.git_paths("ls-files", "-z"))


class TestVerifySetupDoesNotListScratch(PairTestCase):
    """`verify-setup` 的"未提交的代码改动"只列**角色路径**下的文件。默认布局里 `.pair/scratch/`
    不是任何角色的路径,那样写这条用例恒绿 —— 所以用 glob 布局:`**/*.go` 会命中副本里的源码。"""

    config = dict(GO_CONFIG, require_setup_verification=True)

    def setUp(self):
        super().setUp()
        adopt_gitignore(self.repo)
        self.repo.write("docs/reviews/setup-verification.md", setup_report("W1", "W2"))

    def test_警告不列副本里的源码(self):
        self.repo.write(SCRATCH + "copy/pkg/slug.go", "package slug // 故意改错")
        r = self.repo.run(*VERIFY_OK, role="tester")
        self.assertAccepted(r)
        self.assertNotIn(SCRATCH, r.text)

    def test_对照组_仓库里的源码照样被列出(self):
        """上一条的对照:同一布局、同一份结论,换成仓库里真的源码就被列出 ——
        证明上一条不是因为这个布局根本不列。"""
        self.repo.write("pkg/slug.go", "package slug // 偷跑")
        r = self.repo.run(*VERIFY_OK, role="tester")
        self.assertAccepted(r)
        self.assertIn("pkg/slug.go", r.text)


if __name__ == "__main__":
    unittest.main()
