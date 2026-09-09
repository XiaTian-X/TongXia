# -*- coding: utf-8 -*-
"""W8:文档改动要带理由,路线图的改写要有依据。

契约「文档改动要带理由」。两条独立的强制:

- `--doc-reason` —— 本回合改动含**规范性文档**(所有 `.md` 减记忆层与评审
  目录)时必须给,内容进提交正文。
- `--basis` —— 只作用于 `docs/improvements.md`,且只在**有改写**
  (删除行数 > 0)时才要;纯追加不要。

**`PLAN.md` / `CONTRACT.md` 不在这一节的管辖里** —— 它们由 W9 无条件要求
`--contract-change`,在写权限边界那一步就被拦下,走不到这里的分叉。
契约点名说过:照第一版写会写出一条"往 PLAN 追加只给 --doc-reason 应当通过"
的必然失败断言。所以这一组一个字都不碰那两份文件。

**每条 `assertRefused` 都带关键词**:这两个旗标现在还不存在,不带关键词的话
argparse 的 `unrecognized arguments` 会让断言恒真地"通过"。
"""

import unittest

from harness import EVIDENCE, PairTestCase

GUIDE = "docs/guide.md"
ROADMAP = "docs/improvements.md"


class DocReasonBase(PairTestCase):
    """tester 在 spec 回合写文档 —— 所以那两份 `.md` 要在它的可写路径里,
    否则先撞写权限边界,根本走不到本节的检查。"""

    config = {"roles": {"tester": ["tests", GUIDE, ROADMAP],
                        "dev": ["src"]}}

    def commit(self, msg="人类提交"):
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", msg)

    def claim(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")        # spec 结束时必须 RED

    def handoff(self, *extra):
        return self.repo.run("handoff", "W1 的失败用例", *extra, role="tester")


class TestDocReasonRequired(DocReasonBase):

    def test_改了规范性文档而没给理由被拒(self):
        self.repo.write(GUIDE, "# 指南\n\n一句话。\n")
        self.commit("人类先放一份文档")
        self.claim()
        self.repo.write(GUIDE, "# 指南\n\n改了一句话。\n")
        self.assertRefused(self.handoff(), "--doc-reason", GUIDE)

    def test_本回合新建的规范性文档同样要理由(self):
        """判据必须是本回合改动那一批(含未跟踪),不是 `git ls-files` ——
        照后者判,**新写一份文档就完全逃过这条要求**,而新增文档恰恰最该
        说明为什么。"""
        self.claim()
        self.repo.write(GUIDE, "# 新文档\n")
        self.assertRefused(self.handoff(), "--doc-reason", GUIDE)

    def test_理由是空字符串不算数(self):
        """`--doc-reason` 是「强制留痕」不是「放行」,空串留下的是空痕:
        提交正文里多一行 `文档改动理由: `,后面什么都没有,门却开了。
        仓库对这一类已经表过态(`--checked` / `--uncovered` 各有
        `test_空字符串不算数`)。

        **这一条后面没有第二道兜底** —— `--basis` 的空串会被
        `basis_points_at_file` 接着拦下(实测过),`--doc-reason` 不会。
        """
        self.claim()
        self.repo.write(GUIDE, "# 新文档\n")
        self.assertRefused(self.handoff("--doc-reason", ""),
                           "--doc-reason", GUIDE)

    def test_删掉一份规范性文档同样要理由(self):
        """契约写的是"本回合的**改动**里若含规范性文档" —— 删除是改动,
        而且是最该说明为什么的那一种:新增和改写至少还留着文字可读,
        删除之后连痕迹都没有。"""
        self.repo.write(GUIDE, "# 指南\n\n一句话。\n")
        self.commit("人类先放一份文档")
        self.claim()
        self.repo.delete(GUIDE)
        self.assertRefused(self.handoff(), "--doc-reason", GUIDE)

    def test_只改笔记与评审记录不要求理由(self):
        """过程文档本身就是理由,再要一句说明是纯噪音。"""
        self.claim()
        self.repo.write("docs/notes/W1.md", "随手记的东西\n")
        self.repo.write("docs/reviews/W1-想法.md", "一些想法\n")
        self.assertAccepted(self.handoff())

    def test_什么文档都没改时不要求理由(self):
        self.claim()
        self.assertAccepted(self.handoff())

    def test_理由进提交正文(self):
        self.claim()
        self.repo.write(GUIDE, "# 新文档\n")
        self.assertAccepted(self.handoff("--doc-reason", "补一份上手指南"))
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertIn("补一份上手指南", body)


class TestPlanTickDoesNotTrigger(DocReasonBase):
    """完成工作项时脚本自己去 `PLAN.md` 勾选,那次写入发生在边界校验**之后**。

    判据若取"这次提交里含哪些文件",**每一次完成工作项的交接都会被要求
    `--doc-reason`**,而那个改动根本不是 agent 做的。
    """

    def test_完成工作项时的交接不因勾选_PLAN_而被要求理由(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "用例", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "无硬编码",
                                          *EVIDENCE, role="tester"))
        r = self.repo.run("handoff", "approve", "只断言契约",
                          *EVIDENCE, role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["completed_items"], ["W1"])
        # 前提:那一次交接确实改了 PLAN.md,否则本用例恒真
        self.assertIn("- [x] **W1**", self.repo.read("docs/PLAN.md"))
        files = self.repo.git("show", "--name-only", "--format=",
                              "HEAD").stdout.decode()
        self.assertIn("docs/PLAN.md", files,
                      "前提:完成那次提交里应当含 PLAN.md")


class TestBasisOnRewrite(DocReasonBase):
    """`--basis` 只作用于 `docs/improvements.md`,且只在有改写时。"""

    FIVE = "# 路线图\n\n- 第一条\n- 第二条\n- 第三条\n"

    def setUp(self):
        super().setUp()
        self.repo.write(ROADMAP, self.FIVE)
        # 依据要指向**真实存在**的路径,所以引用对象得先入库。
        # `install_protocol` 不铺决策记录 —— 第一版用例直接引用它,
        # 参考实现下三条红,红得对:那个文件根本不存在。
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        self.commit("人类先放一份路线图与决策记录")

    def test_纯追加只要理由(self):
        """路线图的新条目往往是审查中发现的待办。一刀切会让"记录一个发现"
        也要走重流程,路线图就变成不能记录发现的死文档。"""
        self.claim()
        self.repo.write(ROADMAP, self.FIVE + "- 第四条(新发现)\n")
        self.assertAccepted(self.handoff("--doc-reason", "记一条审查中的发现"))

    def test_有改写而没给依据被拒(self):
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n- 第三条\n")
        self.assertRefused(self.handoff("--doc-reason", "删掉一条"), "--basis")

    def test_有改写且依据指向真实路径就放行(self):
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n- 第三条\n")
        self.assertAccepted(
            self.handoff("--doc-reason", "第二条已经做完",
                         "--basis", "docs/DECISIONS.md"))

    def test_依据指向不存在的路径被拒(self):
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        # 关键词取 ROADMAP 而不是 "--basis":这两个旗标现在还不存在,
        # argparse 的 `unrecognized arguments: … --basis 因为我觉得更好`
        # 里**就含 "--basis"**,拿它当关键词这条断言现在就是绿的 —— 恒真。
        # 路径名 argparse 造不出来,而且拒绝文案不说清是哪份文件,
        # agent 也没法动手。
        self.assertRefused(
            self.handoff("--doc-reason", "精简", "--basis", "因为我觉得更好"),
            ROADMAP)

    def test_依据可以是一句话里含一个真实路径(self):
        """包含匹配,不是整串匹配 —— 契约点名要求。
        "见 X 的第二节"是人会自然写出来的形式。"""
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        self.assertAccepted(
            self.handoff("--doc-reason", "精简",
                         "--basis", "见 docs/DECISIONS.md 的第二节"))

    def test_依据允许带行号后缀(self):
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        self.assertAccepted(
            self.handoff("--doc-reason", "精简",
                         "--basis", "docs/DECISIONS.md:12"))

    def test_依据可以指向本回合刚写的文件(self):
        """`known` 要含本回合改动的路径 —— 依据往往就是这一回合刚写的那份
        评审记录,只用 `tracked_files` 会让第一个真实用例就被拒。"""
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        self.repo.write("docs/reviews/W1-依据.md", "为什么删掉那两条\n")
        self.assertAccepted(
            self.handoff("--doc-reason", "精简",
                         "--basis", "docs/reviews/W1-依据.md"))

    def test_先_git_add_不能绕过依据(self):
        """判据必须是 `git diff --numstat HEAD --`,不能是不带参数的
        `git diff`(它只看未暂存的改动)—— 否则 agent 只要先 `git add`
        自己那几个文件,删除行数就变成 0,`--basis` 直接绕过。"""
        self.claim()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        self.repo.git("add", ROADMAP)
        self.assertRefused(self.handoff("--doc-reason", "精简"), "--basis")

    def test_没碰路线图时改写别的文档不要依据(self):
        """`--basis` 只作用于 `docs/improvements.md`。"""
        self.repo.write(GUIDE, "# 指南\n\n一\n二\n三\n")
        self.commit("人类先放一份文档")
        self.claim()
        self.repo.write(GUIDE, "# 指南\n\n一\n")
        self.assertAccepted(self.handoff("--doc-reason", "精简指南"))


if __name__ == "__main__":
    unittest.main()
