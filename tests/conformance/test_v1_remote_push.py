# -*- coding: utf-8 -*-
"""W41:有远端之后的推送约定,`sync` 保持关闭。

契约「有远端之后的推送约定」。仓库已接 GitHub 远端、CI 与 Dependabot,`AGENTS.md` 仍写"这个仓库没有远端",拿它当两个会话
共用一个目录的理由 —— 容易被读成"有远端了,可以把 `sync` 打开"。`sync` 为真时 `status` 先 `git pull --rebase`,远端领先时
改写本地未推送交接提交的 sha,而交接正文、`考古观察@<sha>` 与评审里都引用提交 sha。

**判据**:契约列的几个字样,外加理由里那个命令(`pull --rebase`)—— 行为 ② 要求写明理由。
"""

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class TestAgentsMdOnRemote(unittest.TestCase):

    def setUp(self):
        self.text = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    def test_不再说仓库没有远端(self):
        self.assertNotIn("没有远端", self.text)

    def test_写明_sync_保持_false_及理由(self):
        self.assertIn("sync", self.text)
        self.assertIn("false", self.text)
        self.assertIn("pull --rebase", self.text)

    def test_远端先有提交时只做_ff_only(self):
        self.assertIn("--ff-only", self.text)


class TestConfigKeepsSyncOff(unittest.TestCase):

    def test_本仓库的_sync_是_false(self):
        cfg = json.loads((REPO / ".pair" / "config.json").read_text(encoding="utf-8"))
        self.assertIs(cfg.get("sync"), False)
