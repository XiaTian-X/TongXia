# -*- coding: utf-8 -*-
"""文档规范。

agent 产出的文档里,治理程度长期极不均匀:`DECISIONS.md` 有四个必填字段和
追加式保护,而 `docs/reviews/` 曾经是**零治理** —— 没有命名约定、没有形状,
`approve` 甚至可以一个文件都不产出。而那里恰恰是评审的一手证据。

这一组测的是补上的那几条,以及**它们不该误伤谁** —— 命名规则最容易造成的
伤害是把人类留下的文件算到 agent 头上,而 agent 的唯一出路会变成
改名或删掉不是它写的东西。
"""

import json
import unittest
from pathlib import Path

from harness import (EVIDENCE, PLAN_TEMPLATE, BareRepo, PairTestCase,
                     setup_report, with_loc)

REVIEWS = "docs/reviews"


class TestReviewNaming(PairTestCase):
    """名字要能对上某个工作项 —— 这样人和脚本都找得到它属于哪一轮。"""

    def _到评审回合(self):
        self.repo.advance_to("review-impl")

    def test_对不上任何工作项的名字被拒(self):
        self._到评审回合()
        self.repo.write("%s/随手起的名.md" % REVIEWS, "一些意见。")
        r = self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "对不上任何工作项")

    def test_拒绝文案要告诉它别动别人的文件(self):
        """最容易的误伤:人类往这里放了文件却没提交。agent 的唯一出路
        会变成改名或删掉**人类写的东西**,而那两件事它都不该做。"""
        self._到评审回合()
        self.repo.write("%s/人类的裁决.md" % REVIEWS, "我看了一下……")
        r = self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "不是你写的", "不要改名")

    def test_带前缀的名字放行(self):
        self._到评审回合()
        self.repo.write("%s/W1-review-impl.md" % REVIEWS, "查过了,无硬编码。")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))

    def test_没有连字符的_W1_md_也放行(self):
        """现有用例就是这么写的。规范只管前缀,不管后半截。"""
        self._到评审回合()
        self.repo.write("%s/W1.md" % REVIEWS, "查过了。")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))

    def test_ID_互为前缀时不许蒙混(self):
        """`W11-x.md` 不能在 W1 的回合里靠 startswith 混过去 ——
        而 PLAN 里根本没有 W11。"""
        self._到评审回合()
        self.repo.write("%s/W11-review.md" % REVIEWS, "意见。")
        r = self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "对不上任何工作项")

    def test_认的是_PLAN_里的全部_ID_不是当前那个(self):
        """上一个工作项遗留在工作区里的评审文件,不该把这一轮卡死。"""
        self._到评审回合()
        self.repo.write("%s/W2-review-impl.md" % REVIEWS, "上一项留下的。")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))

    def test_固定名永远放行(self):
        self._到评审回合()
        self.repo.write("%s/setup-verification.md" % REVIEWS, "结论。")
        self.repo.write("%s/baseline.md" % REVIEWS,
                        "## 放弃了哪些用例\n\n" + "老套件里那批集成用例,它们依赖外部服务。" * 3
                        + "\n\n## 为什么\n\n" + "跑一次要二十分钟,每回合都跑会让协议没法用。" * 3)
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))

    def test_子目录与附件不受管辖(self):
        """命名规则的用处是让人找得到评审记录,不是管辖整个目录。"""
        self._到评审回合()
        self.repo.write("%s/图/流程.svg" % REVIEWS, "<svg/>")
        self.repo.write("%s/W1/细节.md" % REVIEWS, "拆出去的细节。")
        self.repo.write("%s/.gitkeep" % REVIEWS, "")
        self.repo.write("%s/.草稿.md" % REVIEWS, "编辑器留下的点文件。")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))


class TestDisputeShape(PairTestCase):
    """异议是**全协议唯一豁免红绿不变量**的入口,而它此前是一份零形状的散文。"""

    def _到_impl(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")

    def test_没写规范异议文件被拒(self):
        self._到_impl()
        self.repo.write("%s/W1-想法.md" % REVIEWS, "tests/W1:1 这条测试不对。")
        r = self.repo.run("handoff", "changes",
                          with_loc("tests/W1 与契约矛盾"), role="dev")
        self.assertRefused(r, "W1-dispute.md", "豁免红绿不变量")

    def test_缺小节被拒并指名(self):
        self._到_impl()
        self.repo.write("%s/W1-dispute.md" % REVIEWS,
                        "## 哪条用例\n\n" + "tests/W1 那条,它的断言和契约相反。" * 3)
        r = self.repo.run("handoff", "changes",
                          with_loc("tests/W1 与契约矛盾"), role="dev")
        self.assertRefused(r, "和契约的哪一条矛盾")

    def test_小节在但正文太短也被拒(self):
        """光有标题不算数 —— 三个空标题过关的话,这条强制就只是排版要求。"""
        self._到_impl()
        self.repo.write("%s/W1-dispute.md" % REVIEWS,
                        "## 哪条用例\n\ntests/W1\n\n"
                        "## 和契约的哪一条矛盾\n\nW1 那条\n\n"
                        "## 应该改成什么\n\n反过来\n")
        r = self.repo.run("handoff", "changes",
                          with_loc("tests/W1 与契约矛盾"), role="dev")
        self.assertRefused(r, "正文太短")

    def test_三节齐了就放行(self):
        self._到_impl()
        self.repo.write_dispute()
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("tests/W1 与契约矛盾"), role="dev"))


class TestContractChangeShape(PairTestCase):
    """契约变更会改动那份"唯一会致命"的文件,四要素 rules.md 早写了、零强制。"""

    def test_缺小节被拒(self):
        self.repo.advance_to("review-impl")
        self.repo.write("%s/contract-change-W1.md" % REVIEWS,
                        "## 现在的契约是什么\n\n" + "W1 小节说 tests/W1 存在时 src/W1 必须存在。" * 3)
        r = self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "为什么不行")

    def test_四节齐了就放行(self):
        self.repo.advance_to("review-impl")
        long = lambda t: t * 3
        self.repo.write("%s/contract-change-W1.md" % REVIEWS, "\n\n".join(
            "## %s\n\n%s" % (h, long(b)) for h, b in [
                ("现在的契约是什么", "W1 小节说 tests/W1 存在时 src/W1 必须存在。"),
                ("为什么不行", "这条把目录布局写进了契约,换个布局就得改契约。"),
                ("提议改成什么", "改成按导出的符号描述,不提目录。"),
                ("影响哪些测试和实现", "tests/W1 的断言要改,src/W1 不用动。")]))
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))


class TestArchaeologySha(PairTestCase):
    """`考古观察@<sha>` 是三档依据里唯一可被脚本校验的一档,靠的就是这个 sha。"""

    def test_编的_sha_被拒(self):
        self.repo.advance_to("review-impl")
        self.repo.write("%s/W1-draft.md" % REVIEWS,
                        "## 计费周期换算\n\n- 依据: 考古观察@deadbeef\n")
        r = self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "找不到", "deadbeef")

    def test_真实的_sha_放行(self):
        self.repo.advance_to("review-impl")
        sha = self.repo.git("rev-parse", "--short", "HEAD").stdout.decode().strip()
        self.repo.write("%s/W1-draft.md" % REVIEWS,
                        "## 计费周期换算\n\n- 依据: 考古观察@%s\n" % sha)
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "没问题", *EVIDENCE, role="tester"))


class TestSetupReportNamesSections(PairTestCase):
    """长度是地板不是门。这道门守着协议自称唯一会致命的失败模式。"""

    config = {"require_setup_verification": True}

    def test_没点名被拒并指名道姓(self):
        self.repo.write("%s/setup-verification.md" % REVIEWS,
                        "# 结论\n\n我没有参与起草。" + "逐条看过了,契约写得很清楚,没有歧义。" * 8)
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "没有点到这些小节", "W1")

    def test_把契约粘进围栏不算点名(self):
        """否则最优敷衍解就是复制粘贴,那是这条检查要消灭的东西的加强版。"""
        self.repo.write("%s/setup-verification.md" % REVIEWS,
                        "# 结论\n\n我没有参与起草。\n\n```\n## W1\n## W2\n```\n"
                        + "以上均无歧义。" * 12)
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "没有点到这些小节")

    def test_不声明作者身份被拒(self):
        """起草人审自己写的东西看不见自己的盲区 —— 读的人有权知道谁写的。"""
        body = "\n\n".join("## %s\n\n返回值精确到能写断言,错误条件已穷举,边界都写明了。" % n
                           for n in ("W1", "W2"))
        self.repo.write("%s/setup-verification.md" % REVIEWS, body * 2)
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "有没有参与过这份契约的起草")

    def test_逐节点名且声明了就通过(self):
        self.repo.write("%s/setup-verification.md" % REVIEWS, setup_report("W1", "W2"))
        self.assertAccepted(self.repo.run("verify-setup", role="dev"))


class TestBaselineNote(PairTestCase):
    """收窄了门禁套件 = 红绿的覆盖面被缩小了,那份说明是唯一留痕。"""

    config = {"require_setup_verification": True,
              "full_test_cmd": 'python3 -c "import sys; sys.exit(0)"'}

    def test_收窄了套件却没有基线说明会被警告(self):
        self.repo.write("%s/setup-verification.md" % REVIEWS, setup_report("W1", "W2"))
        r = self.repo.run("verify-setup", role="dev")
        self.assertAccepted(r)
        self.assertIn("baseline.md", r.text)
        self.assertIn("[警告]", r.text)


if __name__ == "__main__":
    unittest.main()
