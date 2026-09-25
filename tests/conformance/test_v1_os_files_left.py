# -*- coding: utf-8 -*-
"""W35:操作系统写的文件不随执行者的改动被提交。

契约「操作系统写的文件不随执行者的改动被提交」。W31 只管被拒的那一条;`.DS_Store` 落在执行者**自己的**路径下时
不会被拒,而是随 `git add -A` 被提交进仓库 —— 仓库里多了一个谁都没写过的文件。

**以及下一回合**(W35 的 spec 回合带声明补,开工前审查 ⑩):不提交、留在工作区的文件,到下一回合对方交接时
就在对方的 `changed_entries` 里;它在 tester 的路径下、不在 dev 的路径下,照原文 dev 会被写权限边界拒绝 ——
介入只是挪了一个回合。所以:**落在任一角色路径(或共享路径)下的未跟踪系统文件,既不进提交、也不算越界**,
交接输出点名它;**孤儿位置**(根目录、`docs/` 这种不属于任何角色的地方)照旧按 W31 拒绝 —— W31 的用例放的正是那里。

harness 的两行 `.gitignore` 扮演"还没跟上 `GITIGNORE_LINES`"的项目。
"""

from harness import EVIDENCE, PairTestCase

DS = "tests/.DS_Store"


class LeftBase(PairTestCase):

    def tracked(self):
        return self.repo.git_paths("ls-files", "-z")

    def spec_with(self, *extra):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        for rel in extra:
            self.repo.write(rel, "\0\0")
        return self.repo.run("handoff", "W1 的失败用例", role="tester")


class TestOwnPathNotCommitted(LeftBase):

    def test_自己路径下的_DS_Store_不进提交_留在工作区(self):
        r = self.spec_with(DS)
        self.assertAccepted(r)
        tracked = self.tracked()
        self.assertIn("tests/W1", tracked, "其余改动照常提交")
        self.assertNotIn(DS, tracked)
        self.assertTrue(self.repo.exists(DS), "不删它 —— 它不是 agent 写的")

    def test_输出点名它并给出_gitignore_出口(self):
        r = self.spec_with(DS)
        self.assertAccepted(r)
        self.assertIn(DS, r.text)
        self.assertIn(".gitignore", r.text)

    def test_对照组_没有系统文件时不出现这段说明(self):
        r = self.spec_with()
        self.assertAccepted(r)
        self.assertNotIn(".gitignore", r.text)

    def test_Windows_的也一样(self):
        r = self.spec_with("tests/Thumbs.db", "tests/sub/desktop.ini")
        self.assertAccepted(r)
        tracked = self.tracked()
        self.assertNotIn("tests/Thumbs.db", tracked)
        self.assertNotIn("tests/sub/desktop.ini", tracked)

    def test_dev_自己路径下的也不进提交(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write("src/.DS_Store", "\0\0")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertNotIn("src/.DS_Store", self.tracked())
        self.assertIn("src/W1", self.tracked())


class TestNextTurnNotBlocked(LeftBase):
    """⑩:留下来的那个文件不能在下一回合挡住对方。"""

    def test_tester_留下的_DS_Store_不挡_dev_的交接(self):
        self.assertAccepted(self.spec_with(DS))
        self.repo.write("src/W1")
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertAccepted(r)
        self.assertNotIn(DS, self.tracked())
        self.assertTrue(self.repo.exists(DS))

    def test_评审回合也不挡(self):
        """评审阶段只读 —— 一个不是任何人写的未跟踪文件不算这一回合的改动。"""
        self.assertAccepted(self.spec_with(DS))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester"))


class TestOrphanPositionStillRefused(LeftBase):
    """W31 不变:孤儿位置的系统文件照旧被拒、给出 `.gitignore` 出口。"""

    def test_根目录的照旧被拒(self):
        r = self.spec_with(".DS_Store")
        self.assertRefused(r, ".gitignore")
