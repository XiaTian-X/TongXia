# -*- coding: utf-8 -*-
"""健康度报告。

这个命令唯一的存在理由:**"两个 agent 互相点头"在此之前不可观测。**
脚本能强制评审带证据(结构),强制不了评审有内容 —— 打回率长期接近 0
是那件事唯一的量化证据。

所以这里最重要的一条用例是:全 approve 的历史必须被标出来。
"""

from harness import EVIDENCE, PairTestCase, with_loc

PLAN_3 = """# 项目规划

## 工作项

- [ ] **W1** [feature] — 第一个
  - 对应契约:`docs/CONTRACT.md` → W1
- [ ] **W2** [feature] — 第二个
  - 对应契约:`docs/CONTRACT.md` → W2
- [ ] **W3** [feature] — 第三个
  - 对应契约:`docs/CONTRACT.md` → W3
"""

CONTRACT_3 = """# 接口契约

## W1

- 依据: 人类定稿

**行为** tests/W1 存在时 src/W1 必须存在。

## W2

- 依据: 人类定稿

**行为** tests/W2 存在时 src/W2 必须存在。

## W3

- 依据: 人类定稿

**行为** tests/W3 存在时 src/W3 必须存在。
"""


class ReportBase(PairTestCase):

    def setUp(self):
        super().setUp()
        self.repo.set_plan(PLAN_3, CONTRACT_3)

    def _cycle(self, item, bounce=False):
        """走完一个 feature 工作项。bounce=True 时在 review-impl 打回一次。"""
        self.repo.advance_to("review-impl", item=item)
        if bounce:
            self.repo.run("handoff", "changes", with_loc("这里不对"), role="tester")
            self.repo.write("src/%s" % item, "改好了")
            self.repo.run("handoff", "重新实现", role="dev")
        self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE,
                      "--no-decision", "没有可沉淀的", role="dev")

    def report(self):
        r = self.repo.run("report", role="tester")
        self.assertEqual(r.code, 0, r)
        return r.text


class TestReportIsReadOnly(ReportBase):

    def test_不产生提交也不改状态(self):
        before = self.repo.commit_count()
        self.report()
        self.assertEqual(self.repo.commit_count(), before)
        self.assertEqual(self.repo.state()["phase"], "idle")


class TestSmallSample(ReportBase):

    def test_样本不足时不下结论(self):
        out = self.report()
        self.assertIn("样本不足", out)
        self.assertIn("说明不了任何事", out)
        self.assertNotIn("打回率偏低", out)


class TestNoddingIsFlagged(ReportBase):
    """全 approve 的历史 —— 这正是协议要防的那件事。"""

    def test_打回率为零被标红(self):
        for item in ("W1", "W2", "W3"):
            self._cycle(item)
        out = self.report()
        self.assertIn("0% (0/6)", out)
        self.assertIn("!! 偏低", out)
        self.assertIn("打回率偏低", out)
        self.assertIn("互相点头", out)


class TestHealthyHistory(ReportBase):

    def test_有打回时不报警(self):
        self._cycle("W1", bounce=True)
        self._cycle("W2", bounce=True)
        self._cycle("W3")
        out = self.report()
        self.assertNotIn("打回率偏低", out)
        self.assertIn("已完成工作项 : 3", out)

    def test_显式声明没有决策会被统计(self):
        self._cycle("W1")
        self._cycle("W2")
        out = self.report()
        # 每个工作项都用了 --no-decision,应当显示 100%
        self.assertIn("100% (2/2)", out)
