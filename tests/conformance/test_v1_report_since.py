# -*- coding: utf-8 -*-
"""W20:`report --since <rev>` 只统计起点之后的提交。

契约「report 可以只统计某个起点之后」。W14 之后本仓库的 `report` 把前五轮不生效的声明、
没有判定行的 impl 交接照旧算进去,实验的数只能靠人手工减。

**以及两条比率的分母**(W20 的 spec 回合带声明补,开工前审查 ②):`--no-decision` 与
`--contract-change` 两行的分子是区间里的声明数,分母原先读状态里的**全部历史**完成数 ——
带 `--since` 之后分子分母不在一个口径里,背景点名要修的正是这两行。

**判据**:报告里各行的数、退出码、表头里出现的起点。起点用完整 sha 传入,断言它的前 7 位
出现在输出里 —— 印完整 sha 或缩写都成立,不钉格式。
"""

import re
import unittest

from test_v1_effective import ReportRoundsBase
from test_v1_memory import LONG_NOTE
from harness import EVIDENCE


class SinceBase(ReportRoundsBase):

    def head(self):
        return self.repo.git("rev-parse", "HEAD").stdout.decode("utf-8").strip()

    def report(self, *args):
        r = self.repo.run("report", *args, role="tester")
        self.assertEqual(r.code, 0, r)
        return r.text

    def row(self, out, label):
        """报告表格里 `label` 那一行的值(行首锚定,不会匹配到别的行)。"""
        m = re.search(r"^\s*" + re.escape(label) + r"\s+(\S+(?: \(\d+/\d+\))?)", out, re.M)
        self.assertIsNotNone(m, "report 里没有「%s」这一行:\n%s" % (label, out))
        return m.group(1)

    def cycle_with(self, item, note=False, contract_change=False):
        """走完一个工作项。`note=True`:完成时 `--no-decision` 真的被晋升闸读到。
        `contract_change=True`:impl 回合改契约并带声明,那一次是生效的。"""
        self.repo.advance_to("impl", item=item)
        self.repo.write("src/%s" % item)
        extra = ()
        if contract_change:
            self.repo.write("docs/CONTRACT.md",
                            self.repo.read("docs/CONTRACT.md") + "\n**补充** %s 说清楚一句。\n" % item)
            self.repo.append_decision(item, title="%s 的契约补一句" % item)
            extra = ("--doc-reason", "那一句会误导", "--contract-change", "docs/DECISIONS.md")
        self.assertAccepted(self.repo.run("handoff", "实现 %s" % item, *extra, role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题",
                                          *EVIDENCE, role="tester"))
        if note:
            self.repo.write("docs/notes/%s.md" % item, LONG_NOTE)
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE,
                                          "--no-decision", "没有可沉淀的", role="dev"))


class TestSinceCountsOnlyAfter(SinceBase):

    def test_交接与认领只数起点之后(self):
        self.cycle("W1")
        since = self.head()
        self.cycle("W2")
        whole = self.report()
        out = self.report("--since", since)
        self.assertEqual(self.header(whole), 8, whole)
        self.assertEqual(self.header(out), 4, out)
        self.assertEqual(self.num(out, "认领"), 1, out)
        self.assertIn(since[:7], out, "表头要写明起点")

    def test_打回率只数起点之后的评审(self):
        """起点之前的那一次打回不该出现在分子里。"""
        self.cycle("W1", idle_bounce=True)
        since = self.head()
        self.cycle("W2")
        self.assertEqual(self.row(self.report("--since", since), "打回率"), "0% (0/2)")
        self.assertEqual(self.row(self.report(), "打回率"), "20% (1/5)")

    def test_起点之后的三行回合计数照旧满足不变量(self):
        """W14 的不变量在区间内同样成立;区间外那条旧提交与那次空转都不进区间。"""
        self.old_impl_commit()
        self.cycle("W1", idle_bounce=True)
        since = self.head()
        self.cycle("W2", idle_bounce=True)
        out = self.report("--since", since)
        self.assertEqual(self.num(out, "推进交付的回合") + self.num(out, "协议开销的回合"),
                         self.header(out), out)
        self.assertEqual(self.num(out, "协议开销的回合"), 1, out)
        self.assertEqual(self.num(out, "未判定的 impl 回合"), 0, out)

    def test_since_HEAD_时交接为零且不报错(self):
        self.cycle("W1")
        out = self.report("--since", "HEAD")
        self.assertEqual(self.header(out), 0, out)
        self.assertEqual(self.row(out, "打回率"), "—")
        self.assertEqual(self.row(out, "--no-decision"), "—")
        self.assertEqual(self.row(out, "--contract-change"), "—")


class TestSinceBadRev(SinceBase):

    def test_不是_HEAD_祖先的起点拒绝(self):
        """旁支上的提交能解析成提交,但 `<它>..HEAD` 是两条分支的差集,不是"那个提交之后" ——
        退出 0 的一张看起来合理的表,正是 report 要消灭的那种静默偏差(W20 spec 回合带声明补)。"""
        self.cycle("W1")
        self.repo.git("checkout", "-q", "-b", "旁支", "HEAD~2")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "旁支上的提交")
        side = self.head()
        self.repo.git("checkout", "-q", "-")
        r = self.repo.run("report", "--since", side, role="tester")
        self.assertNotEqual(r.code, 0, r)
        self.assertNotIn("Traceback", r.text)
        self.assertIn(side, r.text, "要点名是哪个起点")

    def test_不是合法提交时非零退出_没有_traceback(self):
        r = self.repo.run("report", "--since", "没有这个提交", role="tester")
        self.assertNotEqual(r.code, 0, r)
        self.assertNotIn("Traceback", r.text)
        self.assertIn("没有这个提交", r.text, "要说清楚是哪个起点不认得")

    def test_不是提交的对象也拒绝(self):
        """树对象是合法的 git 对象,但不是提交 —— `<tree>..HEAD` 同样不成立。"""
        tree = self.repo.git("rev-parse", "HEAD^{tree}").stdout.decode("utf-8").strip()
        r = self.repo.run("report", "--since", tree, role="tester")
        self.assertNotEqual(r.code, 0, r)
        self.assertNotIn("Traceback", r.text)


class TestStateRowsUnaffected(SinceBase):
    """读状态的两行与「记忆层空转」不受 `--since` 影响。"""

    def test_已完成与进行中照读状态(self):
        self.cycle("W1")
        self.cycle("W2")
        since = self.head()
        self.repo.advance_to("impl", item="W3")
        out = self.report("--since", since)
        self.assertIn("已完成工作项 : 2", out)
        self.assertRegex(out, r"进行中: W3")
        self.assertEqual(self.header(out), 1, out)   # 只有 W3 的 spec 交接

    def test_决策与完成项照读状态(self):
        self.cycle("W1")
        self.repo.append_decision("W1", title="人类补的一条")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类补决策")
        self.cycle("W2")
        since = self.head()
        out = self.report("--since", since)
        self.assertRegex(out, r"决策/完成项\s+1 / 2")


class TestRatesUseCompletionsInRange(SinceBase):
    """开工前审查 ②:分子在区间里,分母也要在区间里。"""

    def test_no_decision_的分母是区间内的完成数(self):
        self.cycle_with("W1", note=True)
        since = self.head()
        self.cycle_with("W2", note=True)
        self.assertEqual(self.row(self.report("--since", since), "--no-decision"), "100% (1/1)")
        self.assertEqual(self.row(self.report(), "--no-decision"), "100% (2/2)")

    def test_偏高判定也用区间内的完成数(self):
        """区间里 1/1 是偏高;判定若照读状态里的 2,`1 > 2/2` 不成立,比率写着 100% 却不报。"""
        self.cycle_with("W1")
        since = self.head()
        self.cycle_with("W2", note=True)
        out = self.report("--since", since)
        line = re.search(r"^\s*--no-decision\s.*$", out, re.M).group(0)
        self.assertIn("100% (1/1)", line, out)
        self.assertIn("偏高", line, out)

    def test_区间外的声明不进分子(self):
        self.cycle_with("W1", note=True)
        since = self.head()
        self.cycle_with("W2")
        self.assertEqual(self.row(self.report("--since", since), "--no-decision"), "0% (0/1)")

    def test_contract_change_的分母是区间内的完成数(self):
        self.cycle_with("W1")
        since = self.head()
        self.cycle_with("W2", contract_change=True)
        out = self.report("--since", since)
        self.assertEqual(self.row(out, "--contract-change"), "100% (1/1)", out)

    def test_区间里没有完成时比率为样本零(self):
        """区间里有交接、有声明的机会,但没有工作项完成 —— 分母 0,按既有处理。"""
        self.cycle_with("W1", note=True)
        since = self.head()
        self.repo.advance_to("impl", item="W2")
        out = self.report("--since", since)
        self.assertEqual(self.row(out, "--no-decision"), "—", out)


class TestWithoutSinceUnchanged(SinceBase):

    def test_不带_since_时两条比率的分母照读状态(self):
        """测试仓库里状态完成数与历史里推进到完成的交接数恒等,分不出两种口径;
        本仓库这两个数是 17 与 18。造一次历史里多出来的完成交接(旧版本、人类手工操作
        都会留下这种提交),不带 `--since` 时分母必须仍是状态里的 1。"""
        self.cycle_with("W1", note=True)
        self.repo.git("commit", "-q", "--allow-empty", "-m", "review(test)/approve: 历史里多出来的一次完成",
                      "-m", "role=dev phase=review-test -> idle item=W9 type=feature")
        self.assertEqual(self.row(self.report(), "--no-decision"), "100% (1/1)")

    def test_不带_since_时不出现起点(self):
        """「一个字不变」由既有 report 用例整体守;这里只钉不带时不去解析起点。"""
        self.cycle("W1")
        since = self.head()
        self.cycle("W2")
        out = self.report()
        self.assertNotIn(since[:7], out)
        self.assertEqual(self.header(out), 8, out)


if __name__ == "__main__":
    unittest.main()
