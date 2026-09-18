# -*- coding: utf-8 -*-
"""W22:共用一个目录时,角色不来自 PAIR_ROLE 就警告。

契约「共用目录时角色要来自 PAIR_ROLE」。`sync` 为假时两个 agent 共用一个工作目录,
`.pair/whoami` 是一个文件、分支名在同一目录里只有一个 —— 两边会读成同一个角色,而谁都不会被拒绝。

**判据**:`status` 输出里有没有 `PAIR_ROLE=<角色>`(契约给的写法),以及退出码。
**不断言"点名来源"**:`status` 的表头本来就打 `角色来源 : .pair/whoami` / `git 分支名 pair/dev`,
那一句恒真。每条反面用例与正面用例只差一个条件(来源或 `sync`),`PAIR_ROLE=<角色>` 的有无
只能由那一个条件造成。
"""

import shutil
import subprocess
import tempfile
import unittest

from harness import PairRepo, PairTestCase


class TestWarnsWhenRoleIsNotFromEnv(PairTestCase):

    def status(self, role=None):
        r = self.repo.run("status", role=role)
        self.assertEqual(r.code, 0, "警告不阻断,status 照常退出 0。\n%r" % r)
        return r.text

    def test_角色来自_whoami_时警告并给出_PAIR_ROLE_写法(self):
        self.repo.write(".pair/whoami", "dev\n")
        self.assertIn("PAIR_ROLE=dev", self.status())

    def test_给出的写法用的是读到的那个角色(self):
        self.repo.write(".pair/whoami", "tester\n")
        out = self.status()
        self.assertIn("PAIR_ROLE=tester", out)
        self.assertNotIn("PAIR_ROLE=dev", out)

    def test_角色来自分支名时同样警告(self):
        self.repo.git("checkout", "-q", "-b", "pair/dev")
        self.assertIn("PAIR_ROLE=dev", self.status())

    def test_警告不阻断_本阶段任务照常打出(self):
        self.repo.write(".pair/whoami", "tester\n")
        out = self.status()
        self.assertIn("当前阶段", out)
        self.assertIn("轮到你了", out)

    def test_角色来自_PAIR_ROLE_时不警告(self):
        """与第一条只差来源:`.pair/whoami` 照样在,但 `PAIR_ROLE` 优先。"""
        self.repo.write(".pair/whoami", "dev\n")
        self.assertNotIn("PAIR_ROLE=dev", self.status(role="dev"))


class TestNoWarningWhenSynced(unittest.TestCase):
    """`sync` 为真 = 两个 agent 各有一份工作副本,`whoami` 在各自的副本里是对的。

    `status` 在 sync 模式下先 `pull --rebase`,没有远端就停 —— 所以给它一个真的本地裸仓库。"""

    def repo_with_remote(self, sync):
        repo = PairRepo({"sync": sync})
        self.addCleanup(repo.cleanup)
        bare = tempfile.mkdtemp(prefix="pair-remote-")
        self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        self.assertEqual(repo.git("remote", "add", "origin", bare).returncode, 0)
        push = repo.git("push", "-q", "-u", "origin", "HEAD")
        self.assertEqual(push.returncode, 0, push.stderr)
        repo.write(".pair/whoami", "dev\n")
        return repo

    def status(self, repo):
        r = repo.run("status", role=None)
        self.assertEqual(r.code, 0, r)
        return r.text

    def test_sync_为真时不警告(self):
        self.assertNotIn("PAIR_ROLE=dev", self.status(self.repo_with_remote(sync=True)))

    def test_同一设置下_sync_为假就警告(self):
        """上一条的对照组:只差 `sync`。没有它,上一条在"从不警告"的实现上也是绿的。"""
        self.assertIn("PAIR_ROLE=dev", self.status(self.repo_with_remote(sync=False)))


if __name__ == "__main__":
    unittest.main()
