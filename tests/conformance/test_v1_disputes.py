# -*- coding: utf-8 -*-
"""测试异议、sync 失败、死锁留痕。

这三条来自一轮外部评审。第一条是协议级死锁:dev 拿到一条写错的测试时,
不能改测试(边界拦)、不能打回(changes 只在评审阶段解析)、不能红着交接
(红绿不变量拦)。唯一出路是照着错误断言写实现 —— 协议在逼出错误代码。
"""

from harness import EVIDENCE, PairRepo, PairTestCase, with_loc

COVER_PLAN = '''# 规划

## 工作项

- [ ] **C1** [cover] — 补测试
  - 对应契约:`docs/CONTRACT.md` → W1
'''

OBJECTION = """# 对 tests/W1 的异议

该用例断言的返回值与 CONTRACT 的 W1 小节直接矛盾。
契约写明 tests/W1 存在时 src/W1 必须存在,用例却假设了相反的关系。
建议改为按契约断言。
"""


class TestImplDispute(PairTestCase):
    """dev 在 impl 阶段打回写错的测试。"""

    def test_不能用_approve(self):
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "approve", "随便", *EVIDENCE, role="dev")
        self.assertRefused(r, "approve 只用于评审阶段")

    def test_异议必须写进_reviews(self):
        """对方看不到你的对话,不写下来等于没提。"""
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "changes", with_loc("这条测试不对"), role="dev")
        self.assertRefused(r, "没有把它写下来")

    def test_异议必须附理由(self):
        self.repo.advance_to("impl")
        r = self.repo.run("handoff", "changes", role="dev")
        self.assertRefused(r, "必须附理由")

    def test_写了异议就能红着打回(self):
        """核心:红绿不变量对异议路径豁免,否则 dev 永远出不去。"""
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        r = self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "spec",
                         "异议应当把回合退回 tester")

    def test_异议的提交前缀是_dispute(self):
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")
        self.assertTrue(self.repo.head_subject().startswith("dispute:"),
                        "实际提交:%s" % self.repo.head_subject())

    def test_dev_仍然不能借异议之名改测试(self):
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        self.repo.write("tests/W1", "我自己改了")
        r = self.repo.run("handoff", "changes", with_loc("顺手把测试改了"), role="dev")
        self.assertRefused(r, "越界")

    def test_打回后_tester_修正再走通(self):
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")

        self.repo.write("tests/W1", "按异议修正后的用例")
        self.assertAccepted(self.repo.run("handoff", "按异议修正", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))
        self.assertEqual(self.repo.state()["phase"], "review-impl")

    def test_异议计入打回次数(self):
        self.repo.advance_to("impl")
        self.repo.write_dispute()
        self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")
        self.assertEqual(self.repo.state()["changes_count"], 1)


class TestPostDisputeSpec(PairTestCase):
    """打回之后回到 spec 时,dev 的实现往往已经随之前的交接落地了。
    tester 按打回意见改完测试,套件整体就是绿的 —— 拿 spec 的 RED 要求卡它,
    等于逼它再造一条假的失败用例。

    这条豁免对**两种打回**都成立:impl 阶段的异议,和 review-test 以
    "覆盖不足"打回。后者是真实跑出来的:评审要求为一处修复补回归测试,
    而那条测试按定义是绿的(修复已经落地)。"""

    def test_review_test_打回后也豁免_RED(self):
        """回归:曾经只有 impl 阶段的异议会置位标志,review-test 打回不会 ——
        于是"评审要求补测试"这条正当路径把自己锁死在 spec。"""
        self.repo.advance_to("review-test")
        self.repo.write("docs/reviews/W1-rt.md", "覆盖不足,那处修复没有测试守着。")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("这处修复没有回归测试"), role="dev"))
        self.assertEqual(self.repo.state()["phase"], "spec")
        self.assertTrue(self.repo.state()["after_rebound"])
        # 补一条针对已落地行为的测试:它是绿的
        self.repo.write("tests/W1", "补上回归断言")
        self.assertAccepted(self.repo.run("handoff", "补上回归用例", role="tester"))

    def test_评审打回后空转也被拒绝(self):
        """补偿检查此前只被 impl 异议那条入口走到过。新入口接上之后,
        它在这条路径上同样必须生效 —— 否则"评审打回"就成了一轮免费的空转:
        豁免了 RED,而"必须动测试"没跟过来。

        这条是真实跑出来的:接上新入口后的第一个 spec 回合就撞在这条检查上。"""
        self.repo.advance_to("review-test")
        self.repo.write("docs/reviews/W1-rt.md", "覆盖不足,那处修复没有测试守着。")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("这处修复没有回归测试"), role="dev"))
        self.assertEqual(self.repo.state()["phase"], "spec")

        # 只写散文,一个测试都不动
        self.repo.write("docs/notes/W1.md", "我先不改测试,占个位。")
        r = self.repo.run("handoff", "这一回合我没动测试", role="tester")
        self.assertRefused(r, "没有改动任何测试", "空转")

    def test_cover_的_GREEN_不被这条豁免放松(self):
        """豁免只针对 RED。cover 的 spec 期望 GREEN,而 cover 同样有
        review-test changes -> spec 这条边 —— 整个置空会让红着的 cover 过关,
        而"全程绿"正是 cover 的全部纪律。"""
        # 先正常做完 W1,再认领一个 cover 项
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", *EVIDENCE, role="dev")
        self.repo.set_plan(COVER_PLAN)
        self.assertAccepted(self.repo.run("claim", "C1", role="tester"))
        self.repo.write_cover_note("C1")
        self.repo.write("tests/W1", "为已有行为补断言")   # 全程绿
        self.assertAccepted(self.repo.run("handoff", "补测试", role="tester"))

        # dev 在 review-test 打回 -> 回到 spec,after_rebound 置位
        self.repo.write("docs/reviews/C1-rt.md", "覆盖不足。")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("覆盖不足"), role="dev"))
        self.assertTrue(self.repo.state()["after_rebound"])

        # 此时把套件弄红:RED 的豁免不该顺带把 cover 的 GREEN 也豁免掉
        self.repo.write("tests/C1")                      # 没有 src/C1 -> 红
        r = self.repo.run("handoff", "改完了", role="tester")
        self.assertRefused(r, "GREEN")

    def _打回到_spec(self):
        """dev 在 impl 阶段提异议 —— 它的实现会随那次交接一起提交落地。"""
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.write_dispute()
        r = self.repo.run("handoff", "changes",
                          with_loc("tests/W1 的断言与契约冲突"), role="dev")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_修完测试后绿着交接也放行(self):
        self._打回到_spec()
        self.repo.write("tests/W1", "按异议改写后的断言")
        self.assertAccepted(self.repo.run("handoff", "按异议改写了断言", role="tester"))

    def test_空转一轮被拒绝(self):
        """回归:豁免的本意是"让 tester 能把测试改对",不是让它一个测试都不改
        就把问题原样推回去 —— feature 的 spec 本来就没有"必须动测试"这条检查,
        两者一叠加就成了免费的一轮。"""
        self._打回到_spec()
        self.repo.write("docs/notes/W1.md", "我先不改测试,占个位。")
        r = self.repo.run("handoff", "这一回合我没动测试", role="tester")
        self.assertRefused(r, "没有改动任何测试", "空转")

    def test_豁免只管紧接着的那一回合(self):
        """再下一轮 spec 必须重新受红绿约束,否则这就成了永久后门。"""
        self._打回到_spec()
        self.repo.write("tests/W1", "改写")
        self.repo.run("handoff", "按异议改写", role="tester")
        self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.repo.run("claim", "W2", role="tester")
        self.repo.write("tests/W2")
        self.repo.write("src/W2")               # 越界,但先看红绿:这会让它是绿的
        r = self.repo.run("handoff", "绿着交接", role="tester")
        self.assertRefused(r)


class TestDeadlockTrace(PairTestCase):
    """死锁闸不硬锁 approve(那是合理的收敛),但必须留痕。"""

    def _打回三次(self):
        self.repo.advance_to("review-impl")
        self.repo.run("handoff", "changes", with_loc("问题一"), role="tester")
        self.repo.run("handoff", "修好了", role="dev")
        self.repo.append_decision("W1")     # 第二次打回必须留下结论
        self.repo.run("handoff", "changes", with_loc("问题二"), role="tester")
        self.repo.run("handoff", "又修好了", role="dev")
        return self.repo.run("handoff", "changes", with_loc("问题三"), role="tester")

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
        r = self.repo.run("handoff", "approve", "分歧记录在案,接受当前实现", *EVIDENCE,
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
