# -*- coding: utf-8 -*-
"""W44:PLAN 全部完成后记得上一次全量是红的。

契约「PLAN 全部完成后记得上一次全量是红的」。W43 让"最后一项完成且全量红"那一次 `handoff` 不再说"请向人类报告完成";
之后任何一方再跑 `status`、`whose-turn` 或 `handoff`,照旧说"请向人类报告项目(已)完成"—— 状态里没有记录。

**以及记录要落进提交里**(W44 的 spec 回合带声明补,开工前审查 ⑫):全量套件在提交**之后**才跑,结果补写进状态的话,
`.pair/state.json` 留在工作区里是改过的 —— `state_is_tampered` 就是这么定义的,下一次 `status` 打"被修改过"、下一次 `handoff` 还原它,
记录被还原掉。所以断言交接之后状态文件干净。

**判据只看输出与工作区**,状态里那个键叫什么契约没定、这里不碰;"老状态没有这个键"用"把状态还原成完成前那份的键集合"来模拟。
"""

import json

from harness import EVIDENCE, PLAN_TEMPLATE, PairTestCase

RED = "python3 -c \"import sys; sys.exit(1)\""
GREEN = "python3 -c \"import sys; sys.exit(0)\""
ONLY_W1 = PLAN_TEMPLATE.split("- [ ] **W2**", 1)[0]
REPORT_DONE = "请向人类报告项目"


class DoneBase(PairTestCase):

    def finish(self, item="W1"):
        self.repo.advance_to("review-test", item=item)
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")

    def status(self):
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        return r.text

    def whose_turn(self):
        r = self.repo.run("whose-turn", role="tester")
        self.assertAccepted(r)
        return r.out.strip()


class TestRememberedRed(DoneBase):

    config = {"full_test_cmd": RED}

    def setUp(self):
        super().setUp()
        self.repo.set_plan(ONLY_W1)
        self.assertEqual(self.finish().code, 2)

    def test_status_不说报告完成_说算不算结束(self):
        out = self.status()
        self.assertNotIn(REPORT_DONE, out)
        self.assertIn("算不算结束", out)

    def test_whose_turn_仍是_stop_并点名全量(self):
        line = self.whose_turn()
        self.assertTrue(line.startswith("stop "), line)
        self.assertIn("全量", line)

    def test_再一次_handoff_被拒_理由不说报告完成(self):
        r = self.repo.run("handoff", "再交一次", role="tester")
        self.assertRefused(r)
        self.assertNotIn(REPORT_DONE, r.text)

    def test_记录落进了提交_状态文件干净(self):
        """⑫:全量在提交之后才跑,结果补写进状态会被判篡改、下一次交接还原掉。"""
        self.assertNotIn(".pair/state.json", self.repo.git_paths("diff", "--name-only", "-z", "HEAD"))
        self.assertNotIn("被修改过", self.status())


class TestGreenUnchanged(DoneBase):
    """对照组:全量绿时三处照旧。"""

    config = {"full_test_cmd": GREEN}

    def setUp(self):
        super().setUp()
        self.repo.set_plan(ONLY_W1)
        self.assertEqual(self.finish().code, 0)

    def test_status_照旧报告完成(self):
        self.assertIn(REPORT_DONE, self.status())

    def test_handoff_照旧说报告完成(self):
        r = self.repo.run("handoff", "再交一次", role="tester")
        self.assertRefused(r, REPORT_DONE)


class TestLastCompletionWins(DoneBase):
    """W1 完成时全量红、W2 完成时全量绿:每次完成都覆盖上一次。"""

    config = {"full_test_cmd": "python3 -c \"import os,sys; sys.exit(0 if os.path.exists('src/W2') else 1)\""}

    def test_最后一次是绿的就照旧报告完成(self):
        self.assertEqual(self.finish("W1").code, 2)
        self.assertEqual(self.finish("W2").code, 0)
        self.assertIn(REPORT_DONE, self.status())


class TestOldStateWithoutRecord(DoneBase):
    """存量项目零成本升级:状态里没有这条记录 → 按不红处理。"""

    config = {"full_test_cmd": RED}

    def test_删掉记录之后照旧报告完成(self):
        self.repo.set_plan(ONLY_W1)
        before = set(self.repo.state())
        self.assertEqual(self.finish().code, 2)
        state = self.repo.state()
        old = {k: v for k, v in state.items() if k in before}
        self.repo.write(".pair/state.json", json.dumps(old, ensure_ascii=False, indent=2) + "\n")
        self.repo.git("add", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "人类:换成老版本的状态(没有全量记录)")
        self.assertIn(REPORT_DONE, self.status())
