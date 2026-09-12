# -*- coding: utf-8 -*-
"""W14:声明只在生效时留痕,`report` 分开净回合与协议开销。

契约「声明的生效条件与 report 的净回合」。`report` 的每一行都该被它自己的事实推动:

- **声明类旗标只在这一回合真的有某条检查读到它时,才写进提交正文。**
  五个旗标各只在一处被检查读到;正文那五行却都是无条件的 `if args.<旗标>:`。
- **`report` 用两个绝对计数取代「每工作项回合数」**,再加一行「未判定的 impl 回合」
  报告覆盖面(W14 的 spec 回合带声明改的契约)。

**判据尽量不碰措辞。** 正文里那五行声明的前缀是既有文案,既有用例早就钉着
(`未留决策(已声明)` / `文档改动理由` / `改写依据` / `删除测试(已声明)` /
`契约变更(已声明)`);`report` 的三个行标签是契约给的字面。
**判定行本身的字面契约没给,这里一次都不碰** —— 它只通过 `report` 的计数被观察。
"""

import re
import unittest

from harness import EVIDENCE, PairTestCase, with_loc
from test_v1_memory import LONG_NOTE
from test_v1_report import CONTRACT_3, PLAN_3

CONTRACT = "docs/CONTRACT.md"
ROADMAP = "docs/improvements.md"


class DeclBase(PairTestCase):

    def body(self):
        return self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")

    def done(self, *extra):
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, *extra,
                             role="dev")

    def spec_handoff(self, *extra):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        return self.repo.run("handoff", "W1 的失败用例", *extra, role="tester")


class TestNoDecisionOnlyWhenRead(DeclBase):
    """`--no-decision` 只被晋升闸读到:完成时、笔记够长、本工作项没有同 id 决策。
    契约点名:这是五个旗标里唯一"读到"与"处在该出现的地方"分叉的一个。"""

    def test_没写笔记时不留痕(self):
        """冷审实测过的原样:`_cycle` 从不写笔记,却每项都带 `--no-decision`。"""
        self.repo.advance_to("review-test")
        r = self.done("--no-decision", "没有可沉淀的")
        self.assertAccepted(r)                       # 不生效也不拒绝
        self.assertNotIn("未留决策(已声明)", self.body())

    def test_笔记已沉淀成同_id_决策时不留痕(self):
        """W13 之后晋升闸看的是 `settled`:impl 回合就留了 `## W1 — …`,
        完成时闸不成立,旗标没被读到。PLAN 说 W14 必须排在 W13 之后,
        就是因为这一条在两个顺序下结果不同。"""
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write("docs/notes/W1.md", LONG_NOTE)
        self.repo.append_decision("W1", title="impl 回合就沉淀下来的结论")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题",
                                          *EVIDENCE, role="tester"))
        self.assertAccepted(self.done("--no-decision", "其实已经沉淀过了"))
        self.assertNotIn("未留决策(已声明)", self.body())

    def test_不在完成那一次时不留痕(self):
        """**先写一份够长的笔记**,再在 spec 回合带上旗标 —— 这样"不生效"的原因
        只剩"不是完成那一次"。第一版没写笔记,笔记长度那一项先把条件否掉了,
        于是"看不看 `target == DONE`"根本分不出来:dev 在 review-test 实测,
        把 `no_decision_is_read` 里的 `or target != "DONE"` 去掉,全套 0 条红。"""
        self.repo.write("docs/notes/W1.md", LONG_NOTE)
        self.assertAccepted(self.spec_handoff("--no-decision", "顺手带上"))
        self.assertNotIn("未留决策(已声明)", self.body())

    def test_真被晋升闸读到时照样留痕(self):
        """反面:笔记够长、没沉淀 —— 旗标是这一次放行的理由,必须写进正文。"""
        self.repo.advance_to("review-test")
        self.repo.write("docs/notes/W1.md", LONG_NOTE)
        self.assertAccepted(self.done("--no-decision", "只是调试过程"))
        self.assertIn("未留决策(已声明)", self.body())


class TestOtherFlagsOnlyWhenRead(DeclBase):
    """其余四个旗标:"读到"与"处在该出现的地方"不分叉,但照样要按事实判。"""

    def test_没碰规范性文档时_doc_reason_不留痕(self):
        self.assertAccepted(self.spec_handoff("--doc-reason", "顺手写的理由"))
        self.assertNotIn("文档改动理由", self.body())

    def test_没删测试时_allow_deletion_不留痕(self):
        self.assertAccepted(self.spec_handoff("--allow-deletion", "顺手写的理由"))
        self.assertNotIn("删除测试(已声明)", self.body())

    def test_没碰承重文件时_contract_change_不留痕(self):
        self.assertAccepted(self.spec_handoff("--contract-change", CONTRACT))
        self.assertNotIn("契约变更(已声明)", self.body())

    def test_完成时脚本自己勾选_PLAN_不算承重文件改动(self):
        """**以写权限边界那一步的同一批改动为准,不是提交内容。** 完成交接时
        `tick_plan_item` 会改 `PLAN.md`,那次写入发生在抓改动之后。按提交内容判,
        每一次完成交接都会被判成 `--contract-change` 生效 —— 统计恒偏高。"""
        self.repo.advance_to("review-test")
        self.assertAccepted(self.done("--contract-change", CONTRACT))
        self.assertNotIn("契约变更(已声明)", self.body())


class TestBasisOnlyWhenRewrite(DeclBase):
    """`--basis` 只被"路线图有改写"那一支读到;纯追加时它不生效。"""

    config = {"roles": {"tester": ["tests", ROADMAP], "dev": ["src"]}}

    def setUp(self):
        super().setUp()
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n")
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类先放一份路线图与决策记录")

    def test_纯追加时_basis_不留痕_理由照留(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条\n- 第二条(新发现)\n")
        r = self.repo.run("handoff", "W1 的失败用例", "--doc-reason", "记一条发现",
                          "--basis", "docs/DECISIONS.md", role="tester")
        self.assertAccepted(r)
        body = self.body()
        self.assertIn("文档改动理由", body, "理由这次是生效的,应当留痕")
        self.assertNotIn("改写依据", body)

    def test_有改写时_basis_照样留痕(self):
        """反面,五个旗标里只有 `--basis` 缺这一条:dev 在 review-test 实测,
        把那一行换成 `if False:`(从不写依据),全套 **0 条红** —— 另外四个旗标
        改成从不写都各有 1-3 条既有用例接住。契约要的是"在它实际生效时才写进",
        两个方向都要钉。"""
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.repo.write(ROADMAP, "# 路线图\n\n- 第一条(改写过)\n")
        r = self.repo.run("handoff", "W1 的失败用例", "--doc-reason", "第一条的说法会误导",
                          "--basis", "docs/DECISIONS.md", role="tester")
        self.assertAccepted(r)
        self.assertIn("改写依据", self.body())


class ReportRoundsBase(DeclBase):

    def setUp(self):
        super().setUp()
        self.repo.set_plan(PLAN_3, CONTRACT_3)

    def report(self):
        r = self.repo.run("report", role="tester")
        self.assertEqual(r.code, 0, r)
        return r.text

    def num(self, out, label):
        m = re.search(re.escape(label) + r"\s*:?\s*(\d+)", out)
        self.assertIsNotNone(m, "report 里没有「%s」这一行:\n%s" % (label, out))
        return int(m.group(1))

    def header(self, out):
        return self.num(out, "交接提交")

    def cycle(self, item, idle_bounce=False):
        """走完一个工作项。`idle_bounce=True` 时 review-impl 打回一次,
        dev 重新交接时**什么都没改** —— 那就是一个空转的 impl 回合。"""
        self.repo.advance_to("review-impl", item=item)
        if idle_bounce:
            self.assertAccepted(self.repo.run("handoff", "changes",
                                              with_loc("这里不对"), role="tester"))
            self.assertAccepted(self.repo.run("handoff", "没改", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题",
                                          *EVIDENCE, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题",
                                          *EVIDENCE, role="dev"))

    def old_impl_commit(self, item="W9"):
        """一次**旧版本**留下的 impl 交接:正文有 `role=… phase=impl … item=…`,
        但没有判定行 —— W14 之前的每一个提交都长这样。"""
        self.repo.git("commit", "-q", "--allow-empty", "-m", "feat: 旧版本留下的实现",
                      "-m", "role=dev phase=impl -> review-impl item=%s type=feature" % item)


class TestReportSplitsRounds(ReportRoundsBase):

    def test_老那一行删掉_新的行在(self):
        """背景已经把「每工作项回合数」判成"比没有这个指标更糟"。"""
        self.cycle("W1")
        out = self.report()
        self.assertNotIn("每工作项回合数", out)
        self.num(out, "推进交付的回合")
        self.num(out, "协议开销的回合")
        self.num(out, "未判定的 impl 回合")

    def test_两数之和恒等于交接提交(self):
        """契约写明的不变量。没有它,任何一对数都合规。"""
        self.cycle("W1")
        self.cycle("W2", idle_bounce=True)
        self.old_impl_commit()
        out = self.report()
        self.assertEqual(self.num(out, "推进交付的回合") + self.num(out, "协议开销的回合"),
                         self.header(out), out)

    def test_空转的_impl_回合计入开销(self):
        self.cycle("W1", idle_bounce=True)
        self.assertEqual(self.num(self.report(), "协议开销的回合"), 1)

    def test_评审回合不算开销(self):
        """评审回合按构造只读,每一次都"没有改动落在角色路径下"。契约原句没限定
        阶段,照字面实现会把每一次评审都算成开销 —— W14 的 spec 回合改了契约。"""
        self.cycle("W1")
        self.cycle("W2")
        self.assertEqual(self.num(self.report(), "协议开销的回合"), 0)

    def test_只改了承重文件的_impl_回合不算开销(self):
        """W9 刚合法化的那类交付。`contract_file` 按构造不在任何角色路径下,
        纯角色判据会把它判成空转 —— 第四轮 W11 的交付本身就是这样被误判的。"""
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("契约措辞有歧义"),
                                          role="tester"))
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 说清楚一句。\n")
        self.repo.append_decision("W1", title="契约这一句改成更清楚的说法")
        self.assertAccepted(self.repo.run(
            "handoff", "只改了契约", "--doc-reason", "那一句会误导实现方",
            "--contract-change", "docs/DECISIONS.md", role="dev"))
        self.assertEqual(self.num(self.report(), "协议开销的回合"), 0)

    def test_异议回合不算开销(self):
        """异议只能写 `shared_paths`,按定义没有改动落在角色路径下 —— 但提异议是
        协议的正常运转。"""
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        self.assertAccepted(self.repo.run("handoff", "changes",
                                          with_loc("测试与契约矛盾"), role="dev"))
        self.assertEqual(self.num(self.report(), "协议开销的回合"), 0)


class TestUnjudgedHistory(ReportRoundsBase):
    """**没有判定行的 impl 交接不猜。** 只在空转时才写一行的实现,分不出
    "这一回合没空转"和"那时还没有这一行" —— W14 之前的历史空转会被静默计成 0。"""

    def test_旧提交单独计数_新的不算未判定(self):
        """同一个仓库里:两个新的 impl 交接(一个没空转、一个空转)各带判定行,
        一个旧的没有。只在空转时写判定行的实现会把那个"没空转"的新交接也算成
        未判定,这里就会是 2。"""
        self.cycle("W1", idle_bounce=True)
        self.old_impl_commit()
        out = self.report()
        self.assertEqual(self.num(out, "未判定的 impl 回合"), 1, out)
        self.assertEqual(self.num(out, "协议开销的回合"), 1, out)

    def test_全是新提交时未判定为零(self):
        self.cycle("W1")
        self.assertEqual(self.num(self.report(), "未判定的 impl 回合"), 0)


if __name__ == "__main__":
    unittest.main()
