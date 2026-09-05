# -*- coding: utf-8 -*-
"""status 简报落盘 —— 头部四行(W1)。

这个特性存在的唯一理由:**"这一回合 agent 到底看到了什么"在此之前不可观测。**
简报只活在那一次终端输出里,agent 说"我没看到那条决策"时人类无从对质。

头部四行和"不添乱"是 W1(TestBriefHeader);记忆段落是 W2
(TestBriefMemory);写不成时的降级是 W3。

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

    def test_不是自己回合时不写(self):
        """这是这批断言里唯一的**否定式**断言,也是唯一能钉住 `if me == owner`
        那个守卫的东西。上面六条全是"轮到自己时……" —— 把实现改成"每次 status
        都写",它们照样全绿。"""
        self.repo.advance_to("impl")                 # 轮到 dev
        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertFalse(
            self.repo.exists(BRIEF),
            "不是自己回合却写了简报 —— 人类会读到一份不属于当前回合的状态")

    def test_不是自己回合时也不清空已有的(self):
        """上一次的简报要留着给人类看。"不写"和"清空"是两件事。"""
        self.repo.advance_to("impl")
        self.assertAccepted(self.repo.run("status", role="dev"))
        before = self.repo.read(BRIEF)
        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertEqual(self.repo.read(BRIEF), before,
                         "不是自己回合时把上一份简报清掉了")

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


# 终端把记忆块包在这三行里。契约点名它们**不写进简报** —— 简报要的是
# 内容本身,而不是终端上那身包装。
MEM_HEADING = " 你不在场时留下的东西"

# idle 且无相干决策时的整份简报,逐字节。契约:「记忆段落连同它前面那个
# 空行一起省略,文件就是四行头部加一个末尾换行」。
IDLE_BRIEF = (
    "# 回合简报\n"
    "\n"
    "- 角色: tester\n"
    "- 工作项: (无)\n"
    "- 阶段: idle\n"
    "- 测试: GREEN\n"
)


def terminal_memory(out):
    """从 status 的终端输出里取出记忆块的**内容本身**,没注入就返回 None。

    比对两处而不是各自比对一份写死的期望值,是刻意的:契约的「不做」要求
    简报与终端来自**同一次取值**,而"两处必须逐字相同"正是那条要求唯一
    可观测的形态。写死期望值反而测不出两处各算一遍。
    """
    lines = out.split("\n")
    for i, line in enumerate(lines):
        if line == MEM_HEADING:
            # 标题下面还有一条 `=` 分隔线,内容从再下一行起
            return "\n".join(lines[i + 2:]).rstrip("\n")
    return None


class TestBriefMemory(PairTestCase):
    """简报的记忆段落(W2)。

    头部四行回答"这一回合是谁、在哪个阶段",记忆段落回答**"它读到了什么"**
    —— 后者才是 P1-4 的存在理由:agent 说"我没看到那条决策"时,人类要能
    拿着这份文件对质。

    这里每一条都用**终端输出**做期望值,而不是写死一份字符串。理由见
    `terminal_memory` 的 docstring。
    """

    def _memory_of_brief(self):
        """简报里的记忆段落。顺带把它前面那个空行的位置也钉住。"""
        text = self.repo.read(BRIEF)
        self.assertTrue(text.endswith("\n"),
                        "契约要求文件以一个换行符结束,实际结尾:%r" % text[-5:])
        lines = text.split("\n")
        self.assertGreater(
            len(lines), 7,
            "简报里没有记忆段落,只有头部:\n%s" % text)
        self.assertEqual(
            lines[6], "",
            "契约要求头部四行与记忆段落之间**恰好一个空行**,实际第 7 行:%r"
            % lines[6])
        return "\n".join(lines[7:]).rstrip("\n")

    def test_有笔记时记忆段落与终端逐字一致(self):
        """核心断言。终端注入了什么,简报里就该是什么 —— 一个字都不差。"""
        self.repo.advance_to("spec")
        self.repo.write("docs/notes/W1.md", "试过直接改 X,不行,因为 Y。")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)

        mem = terminal_memory(r.text)
        self.assertIsNotNone(mem, "有笔记时终端应当注入记忆块,实际没有")
        self.assertIn("试过直接改 X", mem, "终端注入的记忆块里没有笔记正文")
        self.assertEqual(self._memory_of_brief(), mem)

    def test_还没写笔记时那段提示也算记忆内容(self):
        """契约定稿时专门点名的一条。

        `memory_brief` 在有工作项、没笔记时返回的不是空串,而是一段
        「本工作项还没有笔记」的提示。它是 agent **实际读到**的东西,所以
        算记忆内容、要照写进简报。

        把判据实现成"没写笔记就省略整段"能过掉其余每一条用例 —— 这条是
        唯一能把那种实现钉红的。
        """
        self.repo.advance_to("spec")          # 有工作项 W1,但没写笔记
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)

        mem = terminal_memory(r.text)
        self.assertIsNotNone(mem, "有工作项时终端应当注入记忆块,实际没有")
        self.assertIn("还没有笔记", mem)
        self.assertIn("还没有笔记", self.repo.read(BRIEF),
                      "终端提示了「还没有笔记」,简报里却没有 —— "
                      "契约明确要求这段提示也算记忆内容")
        self.assertEqual(self._memory_of_brief(), mem)

    def test_相干决策也进简报(self):
        """验收标准写的是"有笔记**或**相干决策",两条来源都要覆盖。

        决策块和笔记块由 `memory_brief` 分别拼装,只测笔记那一路,实现里
        漏掉决策那一路照样全绿。
        """
        self.repo.advance_to("spec")
        self.repo.append_decision(item="W1", paths="`tests/W1`")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)

        mem = terminal_memory(r.text)
        self.assertIsNotNone(mem, "有相干决策时终端应当注入记忆块,实际没有")
        self.assertIn("相关决策", mem, "终端注入的记忆块里没有决策条目")
        self.assertEqual(self._memory_of_brief(), mem)

    def test_简报不含终端的分隔线与标题(self):
        """验收标准点名的否定式断言。

        「与终端所见逐字一致」最省事的实现是把终端那段整个抄下来,包括
        两条 `=` 分隔线和标题 —— 那样上面几条比对反而更容易过。所以这条
        必须单独钉:简报要的是内容,不是终端上那身包装。
        """
        self.repo.advance_to("spec")
        self.repo.write("docs/notes/W1.md", "试过直接改 X,不行,因为 Y。")
        self.assertAccepted(self.repo.run("status", role="tester"))

        brief = self.repo.read(BRIEF)
        self.assertNotIn("=" * 52, brief, "简报里混进了终端的 `=` 分隔线")
        self.assertNotIn(MEM_HEADING.strip(), brief,
                         "简报里混进了终端的「你不在场时留下的东西」标题")

    def test_没有记忆内容时整段连同前面的空行一起省略(self):
        """逐字节。契约把"没有记忆内容"的情形收窄到了 idle:
        没有进行中的工作项,且没有影响路径相干的决策条目。

        只断言"不含记忆段落"是不够的 —— 那条空行留没留下,是"省略整段"和
        "省略内容但留下空行"的分界,而它只有逐字节比对才看得出来。
        """
        r = self.repo.run("status", role="tester")      # idle
        self.assertAccepted(r)
        self.assertIsNone(
            terminal_memory(r.text),
            "idle 且无相干决策时终端不该注入记忆块 —— 这条用例的前提不成立了")
        self.assertEqual(self.repo.read(BRIEF), IDLE_BRIEF)
