# -*- coding: utf-8 -*-
"""W43:最后一个工作项完成而全量套件红时,`handoff` 不再同屏说"请向人类报告完成"。

契约「最后一项完成而全量红时不宣布项目结束」。`cmd_handoff` 收尾处 `if full_failed` 与 `if plan_all_done` 互不排斥:
最后一项完成且全量红的那次交接,先打印"不要告诉人类完成",五行之后又打印"项目结束。请向人类报告完成" ——
照屏幕办事的 agent 有一半机会挑错,而挑错的方向正是向人类宣布完成。

harness 默认 PLAN 有 W1、W2;"最后一项"的用例把 PLAN 换成只有 W1。
"""

from harness import EVIDENCE, PLAN_TEMPLATE, PairTestCase

RED = "python3 -c \"import sys; sys.exit(1)\""
GREEN = "python3 -c \"import sys; sys.exit(0)\""
ONLY_W1 = PLAN_TEMPLATE.split("- [ ] **W2**", 1)[0]


class FinishBase(PairTestCase):

    def finish_w1(self):
        self.repo.advance_to("review-test")
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")


class TestLastItemFullRed(FinishBase):

    config = {"full_test_cmd": RED}

    def setUp(self):
        super().setUp()
        self.repo.set_plan(ONLY_W1)

    def test_不宣布项目结束_照旧报全量红_退出码_2(self):
        r = self.finish_w1()
        self.assertEqual(r.code, 2, r)
        self.assertIn("全量套件红", r.text)
        self.assertIn("不要告诉人类", r.text)
        self.assertNotIn("请向人类报告完成", r.text)
        self.assertNotIn("项目结束", r.text)

    def test_说明项目算不算结束由人类决定(self):
        """横幅里本来就有"由人类决定是扩大范围……"—— 只找"人类决定"恒真。按契约原文找"算不算结束"。"""
        r = self.finish_w1()
        self.assertIn("算不算结束", r.text)


class TestLastItemFullGreen(FinishBase):
    """对照组:全量绿时照旧宣布项目结束。"""

    config = {"full_test_cmd": GREEN}

    def setUp(self):
        super().setUp()
        self.repo.set_plan(ONLY_W1)

    def test_照旧项目结束_退出码_0(self):
        r = self.finish_w1()
        self.assertEqual(r.code, 0, r)
        self.assertIn("项目结束", r.text)
        self.assertIn("请向人类报告完成", r.text)


class TestNotLastItemFullRed(FinishBase):
    """③ 不是最后一项、全量红:照旧横幅加"轮到 X 了"。"""

    config = {"full_test_cmd": RED}

    def test_照旧说轮到谁(self):
        r = self.finish_w1()
        self.assertEqual(r.code, 2, r)
        self.assertIn("轮到", r.text)
        self.assertNotIn("项目结束", r.text)
