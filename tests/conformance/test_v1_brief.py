# -*- coding: utf-8 -*-
"""status 简报落盘 —— 头部四行(W1)。

这个特性存在的唯一理由:**"这一回合 agent 到底看到了什么"在此之前不可观测。**
简报只活在那一次终端输出里,agent 说"我没看到那条决策"时人类无从对质。

本轮只钉头部四行和"不添乱"。记忆段落是 W2,写不成时的降级是 W3。

头部的四个字段全都必须**随状态变化**,所以这里逐个字段都有一条能把它写死的
反例:角色写死 tester 就过不了 dev 那条,测试写死 GREEN 就过不了 RED 那条。
只留一条"正常路径通过"的用例,等于允许实现返回一份常量。
"""

import json

from harness import PairTestCase

BRIEF = ".pair/.last-brief.md"

# 全部勾掉的 PLAN。协议在这种状态下会提前收尾,而契约明确要求
# "只要轮到自己就写,与后面还打不打印阶段简报无关"。
PLAN_ALL_DONE = """# 项目规划

## 工作项

- [x] **W1** [feature] — 第一个工作项
  - 对应契约:`docs/CONTRACT.md` → W1
- [x] **W2** [feature] — 第二个工作项
  - 对应契约:`docs/CONTRACT.md` → W2
"""


class TestBriefHeader(PairTestCase):

    def _lines(self):
        self.assertTrue(
            self.repo.exists(BRIEF),
            "轮到自己时应当写出 %s,但它不存在" % BRIEF)
        text = self.repo.read(BRIEF)
        self.assertTrue(text.endswith("\n"),
                        "契约要求文件以一个换行符结束,实际结尾:%r" % text[-5:])
        return text.split("\n")

    def test_轮到自己时写出头部四行(self):
        """标题、空行、四个字段,顺序和写法都由契约逐字节钉死。"""
        self.repo.advance_to("spec")
        self.assertAccepted(self.repo.run("status", role="tester"))
        lines = self._lines()
        self.assertEqual(lines[0], "# 回合简报")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "- 角色: tester")
        self.assertEqual(lines[3], "- 工作项: W1 [feature]")
        self.assertEqual(lines[4], "- 阶段: spec")
        self.assertEqual(lines[5], "- 测试: GREEN")

    def test_测试为红时如实写红(self):
        """写死 GREEN 也能过头部那条用例 —— 所以红必须单独钉一次。"""
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")          # 没有 src/W1,套件转红
        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertEqual(self._lines()[5], "- 测试: RED")

    def test_轮到_dev_时写的是_dev(self):
        """角色和阶段同理:写死 tester/spec 也能过第一条。"""
        self.repo.advance_to("impl")
        self.assertAccepted(self.repo.run("status", role="dev"))
        lines = self._lines()
        self.assertEqual(lines[2], "- 角色: dev")
        self.assertEqual(lines[4], "- 阶段: impl")

    def test_没有工作项时工作项字段写无(self):
        """idle 归 tester,契约点名这是容易漏掉的一种"轮到自己"。"""
        self.assertAccepted(self.repo.run("status", role="tester"))
        lines = self._lines()
        self.assertEqual(lines[3], "- 工作项: (无)")
        self.assertEqual(lines[4], "- 阶段: idle")

    def test_工作项全部完成时仍然写(self):
        """协议此时提前收尾、不再打印阶段简报 —— 契约要求简报照写不误。"""
        self.repo.set_plan(PLAN_ALL_DONE)
        self.assertAccepted(self.repo.run("status", role="tester"))
        lines = self._lines()
        self.assertEqual(lines[0], "# 回合简报")
        self.assertEqual(lines[2], "- 角色: tester")
        self.assertEqual(lines[4], "- 阶段: idle")

    def test_旧状态没有类型时按_feature_写(self):
        """`item_type` 这个键是 v1 才加的,`load_state` 明确支持从没有它的
        状态迁移过来。协议其余部分把空类型一律当 feature(`flow_of(None)`
        就是这么解释的),简报必须跟着走 —— 契约给的两种形态里没有裸 ID。

        这条守的是一次评审打回换来的修复。把它去掉,那个修复就完全不设防。"""
        self.repo.advance_to("spec")
        st = self.repo.state()
        del st["item_type"]                  # v0 的 state.json 没有这个键
        self.repo.write(".pair/state.json", json.dumps(st, indent=2))
        # 以人类身份提交:模拟的是一个 state.json 早于 item_type 的旧仓库,
        # 不是 agent 在本回合篡改状态。
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "旧版本留下的 state.json")

        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertEqual(self._lines()[3], "- 工作项: W1 [feature]")

    def test_写过简报之后交接不被拒(self):
        """简报落在 .pair/ 下,而 .pair 是冻结路径。不处理的话,写出来的
        第一份简报就会让下一次 handoff 判越界,而且 agent 删不干净 ——
        下一次 status 又会生成一份。"""
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertTrue(self.repo.exists(BRIEF))
        self.assertAccepted(
            self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))
