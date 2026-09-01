# -*- coding: utf-8 -*-
"""工作项类型与多流程状态机。

v0 只有"先红后绿"一种纪律,导致已完成项目的两个主要场景走不通:
补测试(为已有正确行为写的测试直接是绿的)和重构(全程绿,没有 RED 阶段)。
"""

from harness import PairTestCase

COVER_PLAN = """# 规划

## 工作项

- [ ] **C1** [cover] — 为已有行为补测试
  - 对应契约:`docs/CONTRACT.md` → W1
"""

REFACTOR_PLAN = """# 规划

## 工作项

- [ ] **R1** [refactor] — 重构实现
  - 对应契约:`docs/CONTRACT.md` → W1
"""

BAD_TYPE_PLAN = """# 规划

## 工作项

- [ ] **X1** [chore] — 类型不存在
"""


class TestIdlePhase(PairTestCase):

    def test_初始处于_idle_而非_spec(self):
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_idle_时不能交接(self):
        r = self.repo.run("handoff", "还没认领就想交接", role="tester")
        self.assertRefused(r, "还没有认领工作项")

    def test_工作项完成后回到_idle(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertIsNone(st["item_type"])


class TestCoverFlow(PairTestCase):
    """补测试:全程绿,跳过 impl。"""

    def _claim(self):
        # 先让 tests/ 与 src/ 配平,基线才是绿的
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        self.repo.set_plan(COVER_PLAN)
        self.assertAccepted(self.repo.run("claim", "C1", role="tester"))

    def test_起始阶段是_spec_且类型被记录(self):
        self._claim()
        st = self.repo.state()
        self.assertEqual(st["phase"], "spec")
        self.assertEqual(st["item_type"], "cover")

    def test_绿着交接被放行(self):
        self._claim()
        # 新增一对配平的文件,保持 GREEN
        self.repo.write("tests/C1")
        self.repo.write("src/C1")   # 越界!先验证边界仍然生效
        r = self.repo.run("handoff", "补测试", role="tester")
        self.assertRefused(r, "越界")

    def test_只写测试且保持绿可以交接(self):
        self._claim()
        # 复用已有的 src/W1:新测试断言的是已有行为,所以整体仍绿
        self.repo.write("tests/W1", "追加对已有行为的断言")
        r = self.repo.run("handoff", "为 W1 的已有行为补断言", role="tester")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "review-test",
                         "cover 应当跳过 impl 直接进 review-test")

    def test_没新增测试就交接被拒绝(self):
        """cover 全程绿,红绿不变量抓不到空手交接,所以要单独拦。"""
        self._claim()
        r = self.repo.run("handoff", "我什么都没干", role="tester")
        self.assertRefused(r, "没有新增或修改任何测试")

    def test_新测试变红时提示改成_bug_类型(self):
        self._claim()
        self.repo.write("tests/C1")     # 没有对应的 src/C1 -> 红
        r = self.repo.run("handoff", "补测试", role="tester")
        self.assertRefused(r, "发现了一个真实缺陷", "[bug]")

    def test_dev_评审通过后工作项完成(self):
        self._claim()
        self.repo.write("tests/W1", "追加断言")
        self.repo.run("handoff", "补断言", role="tester")
        r = self.repo.run("handoff", "approve", "这条断言确实能发现回归", role="dev")
        self.assertAccepted(r)
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertEqual(st["completed_items"], ["W1", "C1"])
        self.assertIn("- [x] **C1**", self.repo.read("docs/PLAN.md"))


class TestRefactorFlow(PairTestCase):
    """重构:全程绿,跳过 spec,从 impl 起步。"""

    def _claim(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        self.repo.set_plan(REFACTOR_PLAN)
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))
        # refactor 的 impl 回合必须交出考古记录,否则交接一律被拒。
        # 这里先写好,让各用例能测到它们各自要测的那条不变量。
        self.repo.write_archaeology("R1")

    def test_起始阶段是_impl(self):
        self._claim()
        st = self.repo.state()
        self.assertEqual(st["phase"], "impl", "refactor 应当跳过 spec")
        self.assertEqual(st["item_type"], "refactor")

    def test_认领后提示轮到_dev(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        self.repo.set_plan(REFACTOR_PLAN)
        r = self.repo.run("claim", "R1", role="tester")
        self.assertIn("轮到 dev", r.text)

    def test_dev_重构后保持绿可交接(self):
        self._claim()
        self.repo.write("src/W1", "重构后的实现")
        r = self.repo.run("handoff", "把 W1 拆成两部分", role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "review-impl")

    def test_重构弄红被拒绝(self):
        self._claim()
        self.repo.delete("src/W1")      # 重构把行为改坏了 -> 测试变红
        r = self.repo.run("handoff", "重构时删掉了 W1", role="dev")
        self.assertRefused(r, "必须是 GREEN")
        self.assertEqual(self.repo.state()["phase"], "impl",
                         "被拒绝的交接不应推进阶段")

    def test_tester_评审通过后完成(self):
        self._claim()
        self.repo.write("src/W1", "重构后")
        self.repo.run("handoff", "重构 W1", role="dev")
        # refactor 一定有考古记录,所以完成时必然撞上晋升 gate:
        # 要么把结论沉淀成决策,要么显式声明没有。
        self.repo.append_decision("R1", title="拆分后异常抛出时机的变化记录在案")
        r = self.repo.run("handoff", "approve", "行为未变,测试仍全绿", role="tester")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "idle")
        self.assertIn("- [x] **R1**", self.repo.read("docs/PLAN.md"))


class TestItemType(PairTestCase):

    def test_非法类型被拒绝(self):
        self.repo.set_plan(BAD_TYPE_PLAN)
        r = self.repo.run("claim", "X1", role="tester")
        self.assertRefused(r, "类型", "非法")

    def test_省略类型时缺省为_feature(self):
        self.repo.set_plan("# 规划\n\n- [ ] **N1** — 没写类型\n")
        self.assertAccepted(self.repo.run("claim", "N1", role="tester"))
        st = self.repo.state()
        self.assertEqual(st["item_type"], "feature")
        self.assertEqual(st["phase"], "spec")

    def test_勾选时保留类型标记(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", role="dev")
        self.assertIn("- [x] **W1** [feature]", self.repo.read("docs/PLAN.md"))
