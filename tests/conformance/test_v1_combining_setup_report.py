# -*- coding: utf-8 -*-
"""W39:开工前审查结论里新写的组合符,`verify-setup` 也给出提示。

契约「审查结论里新写的组合符也要提示」。W37 只在 `handoff` 时看新增行,而审查结论由 `verify-setup` 提交 ——
第二十轮 26 个裸组合符里有 14 个在两份审查结论里。与 W37 同一个判定,不拒绝、不改退出码。

组合符用具名 `chr(0x...)` 常量拼(条目 27)。行号判据同 W37:点名文件之后出现一个两边不挨字母数字的那个数。
"""

import re

from harness import VERIFY_OK, PairTestCase, setup_report

ACUTE = chr(0x0301)
REPORT_REL = "docs/reviews/setup-verification-dev.md"
BASE = setup_report("W1", "W2")


def number(n):
    return re.compile(r"(?<![0-9A-Za-z])%d(?![0-9A-Za-z])" % n)


class SetupHintBase(PairTestCase):

    config = {"require_setup_verification": True}

    def verify(self):
        r = self.repo.run(*VERIFY_OK, role="dev")
        self.assertAccepted(r)               # 不拒绝、退出码不变
        self.assertIn("开工前校验全部通过", r.text)
        return r.text

    def commit_report(self, text):
        self.repo.write(REPORT_REL, text)
        self.repo.git("add", REPORT_REL)
        self.repo.git("commit", "-q", "-m", "人类:早先提交的 dev 结论")


class TestNewReport(SetupHintBase):

    def test_新写的结论里的组合符_点名文件_行号_码位(self):
        text = BASE + "\n补一句:e" + ACUTE + " 会被丢弃\n"
        n = len(text.splitlines())
        self.repo.write(REPORT_REL, text)
        out = self.verify()
        self.assertIn(REPORT_REL, out)
        self.assertIn("U+0301", out)
        self.assertRegex(out.split(REPORT_REL, 1)[1], number(n))
        self.assertIn(REPORT_REL, self.repo.git_paths("ls-files", "-z"), "照常提交")

    def test_对照组_写成_U_XXXX_文字不提示(self):
        self.repo.write(REPORT_REL, BASE + "\n补一句:U+0301 会被丢弃\n")
        self.assertNotIn("U+0301", self.verify())


class TestAppendedNote(SetupHintBase):

    def test_旧行里的组合符不再提示(self):
        self.commit_report(BASE + "\n早先写下的 e" + ACUTE + "\n")
        self.repo.write(REPORT_REL, self.repo.read(REPORT_REL) + "\n## 补记\n\n契约没变的地方照旧成立。\n")
        self.assertNotIn("U+0301", self.verify())

    def test_追加的补记里的组合符照样提示_行号是补记那一行(self):
        """W37 打回过同一个缺口:只钉新文件的行号,从 1 编号的实现照绿。"""
        self.commit_report(BASE)
        text = self.repo.read(REPORT_REL) + "\n## 补记\n\n拆出来的 " + ACUTE + "\n"
        n = len(text.splitlines())
        self.repo.write(REPORT_REL, text)
        out = self.verify()
        self.assertIn("U+0301", out)
        self.assertRegex(out.split(REPORT_REL, 1)[1], number(n))


class TestReportOutsideSharedPaths(SetupHintBase):
    """结论固定落在 `docs/reviews/`,但某个项目的 `shared_paths` 不含它 —— 按评审目录与记忆层过滤的话,提示静默消失。
    契约要复用的是"新增行里的 `M` 类字符"这个判定,不是那道路径过滤。W39 的 review-test 里 dev 实测:去掉 `only`、
    走 `shared_paths` 过滤,默认配置下的 4 条全绿。"""

    config = {"require_setup_verification": True, "shared_paths": ["docs/other"]}

    def test_shared_paths_不含评审目录时照样点名(self):
        text = BASE + "\n补一句:e" + ACUTE + " 会被丢弃\n"
        n = len(text.splitlines())
        self.repo.write(REPORT_REL, text)
        out = self.verify()
        self.assertIn("U+0301", out)
        self.assertRegex(out.split(REPORT_REL, 1)[1], number(n))

