# -*- coding: utf-8 -*-
"""W21:report 只认协议写进提交正文的那几行。

契约「report 只认协议写进提交正文的那几行」。`report` 从提交里数的东西原先都是在整段正文
(或主题)里找子串,而评审旗标的值、执行者写的那句交接说明、人类手写的提交都在里面 ——
本仓库的历史里已经算错两处(`0aea588` 被算成交接、`136cabd` 被算成完成)。

每条用例都是**不需要任何恶意**的写法:正常写评审、写路线图时顺带提到了那几个字样。
第六处(死锁数在主题里找子串)是 W21 的 spec 回合带声明补的。

**判据**:报告里各行的数。反面(协议正常生成的提交照旧计数)由既有 `report` 用例整体守,
这里只补死锁那一行的正面 —— 此前没有任何用例在 `report` 里数过一次真的死锁。
"""

import unittest

from harness import EVIDENCE, with_loc
from test_v1_report_since import SinceBase


def checked(text):
    """评审旗标:`--checked` 换成给定的散文(argparse 取最后一次出现的值)。"""
    return EVIDENCE + ("--checked", text)


class AnchoredBase(SinceBase):

    def finish(self, item, review_impl=EVIDENCE, review_test=EVIDENCE):
        """走完一个工作项,两次评审的旗标可以换成指定的散文。"""
        self.repo.advance_to("review-impl", item=item)
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题",
                                          *review_impl, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题",
                                          *review_test, role="dev"))

    def human_commit(self, subject, body):
        self.repo.git("commit", "-q", "--allow-empty", "-m", subject, "-m", body)


class TestHandoffLine(AnchoredBase):
    """交接 = 行首有协议生成的那一行且 item 不是 none。"""

    def test_人类提交正文里提到_item_不算交接(self):
        """`0aea588` 的原样:路线图提交的散文里写了 `item=`。"""
        self.finish("W1")
        self.human_commit("docs: 路线图补一条",
                          "report 按正文里的 item=W9 这种写法数交接,这里记一笔。")
        self.assertEqual(self.header(self.report()), 4)

    def test_散文里写出完整的协议行也不算_只要不在行首(self):
        self.finish("W1")
        self.human_commit("docs: 解释一下提交正文",
                          "协议行长这样:role=dev phase=impl -> review-impl item=W9 type=feature")
        self.assertEqual(self.header(self.report()), 4)

    def test_行首的协议行照旧算(self):
        """反面:旧版本留下、没有判定行的 impl 交接(harness 的 `old_impl_commit`)仍是一次交接。"""
        self.finish("W1")
        self.old_impl_commit()
        self.assertEqual(self.header(self.report()), 5)


class TestFinishedLine(AnchoredBase):
    """完成 = 那一行的去向是 idle。只在带 `--since` 时它进两条比率的分母。"""

    def test_评审散文里的_phase_to_idle_不算完成(self):
        """`136cabd` 的原样:review-impl 的 `--checked` 里写着 `phase=… -> idle 的交接`。"""
        since = self.head()
        self.cycle_with("W1", note=True)
        self.finish("W2", review_impl=checked(
            "finished 只数 item 非 none 且 phase=… -> idle 的交接"))
        out = self.report("--since", since)
        # 完成 2 项,W1 带 1 次生效的 --no-decision。多数一次完成就是 33% (1/3)。
        self.assertEqual(self.row(out, "--no-decision"), "50% (1/2)", out)

    def test_散文里写出完整的完成行也不算(self):
        since = self.head()
        self.cycle_with("W1", note=True)
        self.finish("W2", review_impl=checked(
            "对照过 role=dev phase=review-test -> idle item=W2 type=feature 那一行"))
        out = self.report("--since", since)
        self.assertEqual(self.row(out, "--no-decision"), "50% (1/2)", out)


class TestImplLine(AnchoredBase):
    """impl 交接 = 那一行的来源阶段是 impl。"""

    def test_评审散文里的_phase_impl_不算未判定(self):
        """评审提交没有判定行(按构造只写在 impl 交接上),散文里一提 `phase=impl -> `,
        照子串写法它就成了一次"没有判定行的 impl 交接"。"""
        self.finish("W1", review_impl=checked("看过 phase=impl -> review-impl 那次交接的正文"))
        out = self.report()
        self.assertEqual(self.num(out, "未判定的 impl 回合"), 0, out)

    def test_行首的旧_impl_交接照旧算未判定(self):
        self.finish("W1")
        self.old_impl_commit()
        self.assertEqual(self.num(self.report(), "未判定的 impl 回合"), 1)


class TestDeclarationLines(AnchoredBase):
    """两条声明只认行首的 `未留决策(已声明): ` / `契约变更(已声明): `。"""

    def test_散文里提到未留决策不算声明(self):
        self.finish("W1", review_test=checked("这一项没有 未留决策(已声明) 那一行,笔记不够长"))
        self.assertEqual(self.row(self.report(), "--no-decision"), "0% (0/1)")

    def test_散文里提到契约变更不算声明(self):
        self.finish("W1", review_impl=checked("正文里没有 契约变更(已声明) 那一行,契约没动"))
        self.assertEqual(self.row(self.report(), "--contract-change"), "0% (0/1)")

    def test_散文里写出冒号也不算_只要不在行首(self):
        self.finish("W1", review_test=checked("别处常见的写法是 未留决策(已声明): 某某理由"))
        self.assertEqual(self.row(self.report(), "--no-decision"), "0% (0/1)")

    def test_契约变更写出冒号也不算_只要不在行首(self):
        """上一条只守了未留决策:`契约变更` 那条散文没有冒号,不锚行首的正则照样匹配不上它
        —— dev 在 W21 的 review-test 里实测拆掉 `^` 全套 0 红。"""
        self.finish("W1", review_impl=checked("别处常见的写法是 契约变更(已声明): 某某路径"))
        self.assertEqual(self.row(self.report(), "--contract-change"), "0% (0/1)")


class TestDeadlockSubject(AnchoredBase):
    """死锁只认 `handoff` 生成的那个完整主题(W21 的 spec 回合带声明补)。"""

    def test_交接说明里提到触发死锁闸不算死锁(self):
        """主题是 `<前缀>: <执行者写的一句话>`,那句话是自由文本。"""
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("再打回两次就触发死锁闸,这次先说清楚"), role="tester"))
        out = self.report()
        self.assertEqual(self.row(out, "死锁工作项占比"), "0% (0/1)", out)

    def test_真的死锁照旧算(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("问题一"), role="tester"))
        self.assertAccepted(self.repo.run("handoff", "修好了", role="dev"))
        self.repo.append_decision("W1")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("问题二"), role="tester"))
        self.assertAccepted(self.repo.run("handoff", "又修好了", role="dev"))
        self.assertRefused(self.repo.run("handoff", "changes", with_loc("问题三"), role="tester"),
                           "交给人类")
        out = self.report()
        self.assertEqual(self.row(out, "死锁工作项占比"), "100% (1/1)", out)


if __name__ == "__main__":
    unittest.main()
