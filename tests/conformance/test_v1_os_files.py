# -*- coding: utf-8 -*-
"""W31:操作系统写的文件不该挡住交接。

契约「操作系统写的文件不该挡住交接」。第十五轮有人用 Finder 看过项目,macOS 在根目录与 `docs/` 下写了两个 `.DS_Store`,
tester 的第一次交接被拒,文案只说"不属于任何角色,需要人类划归";`init` 写给新项目的 `.gitignore` 里没有它。

**harness 的 `.gitignore` 是手写两行**,正好扮演"已接入、还没有这几行"的项目。
**判据看那个文件自己的那一段说明**:越界文案把每个文件列成 `\\n  <路径>\\n      <说明>`,整段文案里别处(末尾的指引)
将来提到 `.gitignore` 会替判据成立。
"""

import re

from harness import BareRepo, PairTestCase
from test_v1_scratch import adopt_gitignore
from test_v1_setup import PY_PROJECT

import unittest

OS_FILES = (".DS_Store", "Thumbs.db", "desktop.ini")


def block(text, path):
    """越界文案里 `path` 那一段(到下一个文件或空行为止)。"""
    m = re.search(r"\n  %s\n((?:      .*\n?)+)" % re.escape(path), text)
    assert m, "拒绝文案里没有 %s 那一段:\n%s" % (path, text)
    return m.group(1)


class TestInitIgnoresOsFiles(unittest.TestCase):

    def test_init_写的_gitignore_含三种系统文件(self):
        repo = BareRepo(PY_PROJECT)
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        lines = repo.read(".gitignore").splitlines()
        for name in OS_FILES:
            self.assertIn(name, lines)


class TestRefusalNamesTheExit(PairTestCase):

    def spec_handoff(self, *extra_files):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        for rel in extra_files:
            self.repo.write(rel, "\0\0")
        return self.repo.run("handoff", "W1 的失败用例", role="tester")

    def test_根目录的_DS_Store_被拒且点名加进_gitignore(self):
        """第十五轮的原样。拒绝本身不变。"""
        r = self.spec_handoff(".DS_Store")
        self.assertRefused(r)
        self.assertIn(".gitignore", block(r.text, ".DS_Store"))

    def test_子目录里的也认得出(self):
        """第十五轮另一个在 `docs/` 下 —— 认的是文件名,不是路径。"""
        r = self.spec_handoff("docs/.DS_Store")
        self.assertRefused(r)
        self.assertIn(".gitignore", block(r.text, "docs/.DS_Store"))

    def test_Windows_的两种也认得出(self):
        r = self.spec_handoff("Thumbs.db", "desktop.ini")
        self.assertRefused(r)
        for name in ("Thumbs.db", "desktop.ini"):
            self.assertIn(".gitignore", block(r.text, name))

    def test_对照组_普通孤儿文件的说明不变(self):
        """同样位置、同样没被跟踪,只差文件名。"""
        r = self.spec_handoff("notes.txt")
        self.assertRefused(r)
        b = block(r.text, "notes.txt")
        self.assertNotIn(".gitignore", b)
        self.assertIn("需要人类划归", b)

    def test_同一次拒绝里各说各的(self):
        """系统文件与普通孤儿同时出现:普通孤儿那一段不能被带成"加进 .gitignore"。"""
        r = self.spec_handoff(".DS_Store", "notes.txt")
        self.assertIn(".gitignore", block(r.text, ".DS_Store"))
        self.assertNotIn(".gitignore", block(r.text, "notes.txt"))


class TestIgnoredOnceGitignoreHasThem(PairTestCase):
    """端到端:`.gitignore` 跟上 `GITIGNORE_LINES` 之后,这类文件根本不挡交接。"""

    def test_跟上之后_DS_Store_不挡交接(self):
        adopt_gitignore(self.repo)
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.repo.write(".DS_Store", "\0\0")
        self.repo.write("docs/.DS_Store", "\0\0")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例", role="tester"))
