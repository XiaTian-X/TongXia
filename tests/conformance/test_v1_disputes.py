# -*- coding: utf-8 -*-
"""测试异议、sync 失败、死锁留痕。

这三条来自一轮外部评审。第一条是协议级死锁:dev 拿到一条写错的测试时,
不能改测试(边界拦)、不能打回(changes 只在评审阶段解析)、不能红着交接
(红绿不变量拦)。唯一出路是照着错误断言写实现 —— 协议在逼出错误代码。
"""

from harness import PairRepo, PairTestCase

OBJECTION = """# 对 tests/W1 的异议

该用例断言的返回值与 CONTRACT 的 W1 小节直接矛盾。
契约写明 tests/W1 存在时 src/W1 必须存在,用例却假设了相反的关系。
建议改为按契约断言。
"""


class TestImplDispute(PairTestCase):
    """dev 在 impl 阶段打回写错的测试。"""

    def test_不能用_approve(self):
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "approve", "随便", role="dev")
        self.assertRefused(r, "approve 只用于评审阶段")

    def test_异议必须写进_reviews(self):
        """对方看不到你的对话,不写下来等于没提。"""
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "changes", "这条测试不对", role="dev")
        self.assertRefused(r, "没有把它写下来")

    def test_异议必须附理由(self):
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "changes", role="dev")
        self.assertRefused(r, "必须附理由")

    def test_写了异议就能红着打回(self):
        """核心:红绿不变量对异议路径豁免,否则 dev 永远出不去。"""
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", OBJECTION)
        r = self.repo.run("handoff", "changes", "测试与契约矛盾", role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "spec",
                         "异议应当把回合退回 tester")

    def test_异议的提交前缀是_dispute(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", OBJECTION)
        self.repo.run("handoff", "changes", "测试与契约矛盾", role="dev")
        self.assertTrue(self.repo.head_subject().startswith("dispute:"),
                        "实际提交:%s" % self.repo.head_subject())

    def test_dev_仍然不能借异议之名改测试(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", OBJECTION)
        self.repo.write("tests/W1", "我自己改了")
        r = self.repo.run("handoff", "changes", "顺手把测试改了", role="dev")
        self.assertRefused(r, "越界")

    def test_打回后_tester_修正再走通(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", OBJECTION)
        self.repo.run("handoff", "changes", "测试与契约矛盾", role="dev")

        self.repo.write("tests/W1", "按异议修正后的用例")
        self.assertAccepted(self.repo.run("handoff", "按异议修正", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))
        self.assertEqual(self.repo.state()["phase"], "review-impl")

    def test_异议计入打回次数(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", OBJECTION)
        self.repo.run("handoff", "changes", "测试与契约矛盾", role="dev")
        self.assertEqual(self.repo.state()["changes_count"], 1)


class TestDeadlockTrace(PairTestCase):
    """死锁闸不硬锁 approve(那是合理的收敛),但必须留痕。"""

    def _打回三次(self):
        self.repo.advance_to("review-impl")
        self.repo.run("handoff", "changes", "问题一", role="tester")
        self.repo.run("handoff", "修好了", role="dev")
        self.repo.append_decision("W1")     # 第二次打回必须留下结论
        self.repo.run("handoff", "changes", "问题二", role="tester")
        self.repo.run("handoff", "又修好了", role="dev")
        return self.repo.run("handoff", "changes", "问题三", role="tester")

    def test_触发后被记进状态(self):
        self.assertRefused(self._打回三次(), "打回")
        self.assertIn("W1 x3", self.repo.state()["deadlock_hits"])

    def test_status_显示曾经触发过(self):
        self._打回三次()
        r = self.repo.run("status", role="tester")
        self.assertIn("曾触发死锁闸", r.text)
        self.assertIn("W1 x3", r.text)

    def test_仍允许带理由的_approve_收敛(self):
        """硬锁死会让项目卡住,需要人去改冻结文件才能解开。
        带理由的 approve 是合理收敛 —— 它进提交记录,人类看得见。"""
        self._打回三次()
        r = self.repo.run("handoff", "approve", "分歧记录在案,接受当前实现",
                          role="tester")
        self.assertAccepted(r)


class TestSyncFailures(PairTestCase):
    """通信只走 git —— 推拉失败被吞掉,两个副本就会静默分叉。"""

    def _带坏远端的仓库(self):
        repo = PairRepo({"sync": True, "require_setup_verification": False})
        self.addCleanup(repo.cleanup)
        repo.git("remote", "add", "origin", "/nonexistent/pair-remote.git")
        return repo

    def test_pull_失败时停下(self):
        repo = self._带坏远端的仓库()
        r = repo.run("status", role="tester")
        self.assertNotEqual(r.code, 0, "拉不下来就可能在陈旧的回合上动手")
        self.assertIn("git pull --rebase 失败", r.text)

    def test_push_失败时不报告已交接(self):
        repo = self._带坏远端的仓库()
        repo.run("claim", "W1", role="tester")
        repo.write("tests/W1")
        r = repo.run("handoff", "W1 用例", role="tester")
        self.assertNotEqual(r.code, 0, "push 失败等于没交接")
        self.assertIn("推送失败", r.text)
        self.assertIn("不要告诉人类", r.text)

    def test_不开_sync_时不受远端影响(self):
        self.repo.git("remote", "add", "origin", "/nonexistent/pair-remote.git")
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "W1 用例", role="tester"))
