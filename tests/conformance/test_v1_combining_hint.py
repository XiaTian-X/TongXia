# -*- coding: utf-8 -*-
"""W37:评审与笔记里新写的组合符,交接时给出提示。

契约「评审与笔记里新写的组合符要提示」。第二十轮五份文档嵌了 26 个裸组合符 —— `rules.md` 那一句写对了,放在会话不去读的地方。
一段说"U+0301 会被丢弃"的文字里真嵌着 U+0301,读的人看不出来。**脚本能判。**

组合符一律用具名 `chr(0x...)` 常量拼(条目 27),测试源码里不嵌裸字符。
行号判据:把组合符放在第 17 行,断言输出里有一个两边不挨字母数字的 `17` —— 提交 sha 里的数字两边是十六进制字母,不会误中。
"""

import re

from harness import PairTestCase

ACUTE = chr(0x0301)          # Mn
VOWEL_I = chr(0x093F)        # Mc
REVIEW = "docs/reviews/W1-notes.md"
NOTE = "docs/notes/W1.md"
LINE17 = re.compile(r"(?<![0-9A-Za-z])17(?![0-9A-Za-z])")


def doc(line17, filler="普通的一行"):
    return "".join("%s\n" % (line17 if i == 17 else filler) for i in range(1, 21))


class HintBase(PairTestCase):

    def spec_with(self, files):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        for rel, text in files.items():
            self.repo.write(rel, text)
        r = self.repo.run("handoff", "W1 的失败用例", role="tester")
        self.assertAccepted(r)              # 不拒绝,退出码不变
        return r.text


class TestNewLinesAreFlagged(HintBase):

    def test_评审文件新写的组合符_点名文件_行号_码位(self):
        out = self.spec_with({REVIEW: doc("e" + ACUTE + " 会被丢弃")})
        self.assertIn(REVIEW, out)
        self.assertIn("U+0301", out)
        self.assertRegex(out.split(REVIEW, 1)[1], LINE17)

    def test_笔记里新写的也提示(self):
        out = self.spec_with({NOTE: doc("拆出来的 " + ACUTE)})
        self.assertIn(NOTE, out)
        self.assertIn("U+0301", out)

    def test_Mc_也算组合符(self):
        out = self.spec_with({REVIEW: doc("元音符号 " + VOWEL_I)})
        self.assertIn("U+093F", out)

    def test_对照组_写成_U_XXXX_文字不提示(self):
        """文件里写着 `U+0301` 这几个字符,但没有组合符 —— 输出里不该出现这个码位。"""
        out = self.spec_with({REVIEW: doc("U+0301 会被丢弃")})
        self.assertNotIn("U+0301", out)


class TestOnlyNewLinesOnlyDocs(HintBase):

    def test_已提交的旧行不再提示(self):
        self.repo.write(REVIEW, doc("早先写下的 e" + ACUTE))
        self.repo.git("add", REVIEW)
        self.repo.git("commit", "-q", "-m", "人类早先提交的评审")
        out = self.spec_with({REVIEW: self.repo.read(REVIEW) + "本回合追加的一行,没有组合符\n"})
        self.assertNotIn("U+0301", out)

    def test_旧文件里新追加的那一行照样提示(self):
        """反面:只看新增行,不是只看新文件。"""
        self.repo.write(REVIEW, doc("早先写下的一行"))
        self.repo.git("add", REVIEW)
        self.repo.git("commit", "-q", "-m", "人类早先提交的评审")
        out = self.spec_with({REVIEW: self.repo.read(REVIEW) + "追加的 " + ACUTE + "\n"})
        self.assertIn("U+0301", out)

    def test_测试文件里的组合符不提示(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1", doc("assert x == 'e" + ACUTE + "'"))
        r = self.repo.run("handoff", "W1 的失败用例", role="tester")
        self.assertAccepted(r)
        self.assertNotIn("U+0301", r.text)
