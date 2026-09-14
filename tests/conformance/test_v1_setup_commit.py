# -*- coding: utf-8 -*-
"""W15:verify-setup 的提交只带它自己 add 的那批路径。

契约「verify-setup 的提交只带它自己 add 的那批路径」。「提交范围」那条防护把
`git add` 收窄到三类,为的是不把工作区里的实现提交进开工基线 —— 但紧接着的
`git commit` 不带路径,**提交的是整个索引**。事先有人 `git add` 了一份实现,
它就跟着结论一起进了基线,spec 阶段"必须 RED"失效。W12 只堵住了"索引无差异"
那一半。

**判"在不在"一律按 `-z` 整条路径相等**(`PairRepo.git_paths`):不带 `-z` 时
中文路径被转义,子串断言恒真 —— 仓库里曾经有三处这样的死断言。

**提交的是哪一批**:契约写的是 `to_add` 里在索引中真有差异的那些。
这里不断言提交里**正好**有哪几个文件(状态文件这一次变没变取决于 W13 的记录),
只断言结论进去了、预先暂存的实现没进去。
"""

import unittest

from harness import PairTestCase, VERIFY_OK, setup_report

REVIEWS = "docs/reviews"
OLD = REVIEWS + "/setup-verification.md"
IMPL = "src/偷跑的实现"


class CommitScopeBase(PairTestCase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def verify(self, role="dev"):
        return self.repo.run(*VERIFY_OK, role=role)

    def rev(self):
        return self.repo.git("rev-parse", "HEAD").stdout

    def committed_report(self):
        return self.repo.git("show", "HEAD:" + OLD).stdout.decode("utf-8")


class TestOnlyTheAddedBatchIsCommitted(CommitScopeBase):

    def test_结论有改动时_预先暂存的实现不进这次提交_仍留在索引里(self):
        """验收 ①③④。场景就是契约「背景」里实测过的那一个:结论改了一句,
        同时有人事先 `git add` 了一份实现。

        - 提交确实发生了,结论的新内容在 HEAD 里;
        - 那份实现**不在 HEAD 的树里**(它从没被提交过,所以查树就是查"这次提交");
        - 它**仍在索引里** —— 不提交,也不撤销。这一句同时是 `-z` 判法的正向对照:
          同一个 `git_paths` 能找到它,说明前面那句 `assertNotIn` 不是恒真的;
        - 退出码 0,既有的"未提交的代码改动"警告列出它 —— 现状下它被一起提交走,
          那段警告反而不出现。"""
        self.repo.write(OLD, self.REPORT)
        self.assertAccepted(self.verify())
        before = self.rev()
        self.repo.write(OLD, self.REPORT + "\n(重读契约之后补了一句)\n")
        self.repo.write(IMPL, "本该由 dev 在 impl 回合写")
        self.repo.git("add", "--", IMPL)

        r = self.verify()
        self.assertAccepted(r)
        self.assertNotEqual(self.rev(), before, "结论有改动,这一次应当产生提交")
        self.assertIn("重读契约之后补了一句", self.committed_report())
        self.assertNotIn(IMPL, self.repo.git_paths("ls-tree", "-r", "-z", "--name-only", "HEAD"),
                         "预先暂存的实现跟着结论一起进了开工基线")
        self.assertIn(IMPL, self.repo.git_paths("ls-files", "-z"),
                      "预先暂存的改动应当原样留在索引里 —— 不提交,也不撤销")
        self.assertIn("未提交的代码改动", r.text)
        self.assertIn("偷跑的实现", r.text)

    def test_评审目录里暂存后又删掉的文件不让提交失败(self):
        """验收 ①′。`to_add` 里来自 `shared_paths` 的条目取自工作区状态,
        可能有**暂存为新增、随后又从工作区删掉**的文件(porcelain `AD`)。
        `git add` 把它从索引里拿掉之后,它既不在索引也不在 HEAD ——
        第一版修法 `git commit -- <to_add 全部>` 在这里报 pathspec 不匹配、
        `exit 1`,而状态位已经写进工作区却没提交(tester 在开工前的审查里实测过)。

        **这一条在今天的代码上是绿的**(今天的 `git commit` 不带路径)。
        它守的是"别写成第一版那一行";W15 的红靠上面那一条。"""
        self.repo.write(OLD, self.REPORT)
        self.assertAccepted(self.verify())
        self.repo.write(OLD, self.REPORT + "\n(补了一句)\n")
        draft = REVIEWS + "/草稿.md"
        self.repo.write(draft, "写了又删")
        self.repo.git("add", "--", draft)
        self.repo.delete(draft)

        r = self.verify()
        self.assertAccepted(r)
        self.assertIn("补了一句", self.committed_report())

    def test_中文名的评审文件跟着结论提交_不让提交失败(self):
        """**被测代码里的 `-z` 也要有用例守着。** 我给 harness 加了"不带 `-z` 直接炸"
        的 `git_paths`、修了三处死断言 —— 守住了"判据别被转义骗",却没守"实现别被
        转义骗"。前两条里进入 `git commit --` 的路径全是 ASCII(`AD` 那条的
        `草稿.md` 恰恰是**不进**提交的那个),dev 在 impl 回合实测:`staged_paths`
        去掉 `-z`、按换行切,全套 0 红。

        场景:结论改一句,同时在 `shared_paths` 下新写一份中文名的评审(不预先暂存,
        由 `verify-setup` 自己 add)。不带 `-z` 时 `git diff` 输出的是
        `"docs/reviews/\344\270\255…"`,交回给 `git commit --` 报 pathspec 不匹配、
        `exit 1`,而状态位已经写进工作区 —— 和 `AD` 同一类故障。契约给集合时写的就是
        `-z`,又写了"路径在 add 之后已不被 git 认得时不能让提交失败"。"""
        self.repo.write(OLD, self.REPORT)
        self.assertAccepted(self.verify())
        self.repo.write(OLD, self.REPORT + "\n(补了一句)\n")
        review = REVIEWS + "/中文评审.md"
        self.repo.write(review, "一份中文文件名的评审记录")

        r = self.verify()
        self.assertAccepted(r)
        self.assertIn(review, self.repo.git_paths("ls-tree", "-r", "-z", "--name-only", "HEAD"),
                      "shared_paths 下的中文名评审没有跟着结论进这次提交")


if __name__ == "__main__":
    unittest.main()
