# -*- coding: utf-8 -*-
"""记忆层的一致性测试。

两个 agent 不共享对话,也不共享各自厂商的记忆。项目知识只能沉在仓库里,
并且必须在固定时刻被重新读出来。这一组用例扮演一个偷懒或作弊的 agent:
改历史、写空条目、重构不留考古、争了两轮不留结论、完事就把笔记扔掉,
断言 pair.py 拦得住;同时断言 status 真的把该读的东西读出来了。
"""

from harness import CONTRACT_TEMPLATE, EVIDENCE, PLAN_TEMPLATE, PairRepo, PairTestCase, with_loc

REFACTOR_PLAN = PLAN_TEMPLATE + """- [ ] **R1** [refactor] — 重构 W1
  - 验收标准:行为不变
  - 对应契约:`docs/CONTRACT.md` → W1
  - 保护测试: tests
"""

LONG_NOTE = ("这一项踩了两个坑,都不在任何文档里:一是缓存键漏了租户维度,"
             "二是重试逻辑会把幂等性破坏掉。都绕过去了,但值得记下来。") * 2


class TestAppendOnly(PairTestCase):
    """决策记录是追加式的。已写下的结论是双方共识的凭据,改它等于伪造共识。"""

    def _已提交一条决策(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.repo.append_decision("W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))

    def test_改动已有条目被拒绝(self):
        self._已提交一条决策()
        text = self.repo.read("docs/DECISIONS.md")
        self.repo.write("docs/DECISIONS.md",
                        text.replace("ISO 字符串", "其实无所谓"))
        r = self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "追加式", "伪造共识")

    def test_删掉已有条目被拒绝(self):
        self._已提交一条决策()
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        r = self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        self.assertRefused(r, "追加式")

    def test_纯追加放行(self):
        self._已提交一条决策()
        self.repo.append_decision("W1", title="评审时补充的第二条结论")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester"))

    def test_同一工作项可以追加第二条(self):
        """靠偏移量判定新条目,不靠 id 去重 —— 否则第二条会被当成旧的。"""
        self._已提交一条决策()
        before = len(self.repo.read("docs/DECISIONS.md"))
        self.repo.append_decision("W1", title="第二条")
        self.repo.run("handoff", "approve", "没问题", *EVIDENCE, role="tester")
        self.assertGreater(len(self.repo.read("docs/DECISIONS.md")), before)


class TestDecisionShape(PairTestCase):
    """条目要么结构完整、足够短,要么不如不写。"""

    def _在_impl(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")

    def test_缺字段被拒绝(self):
        self._在_impl()
        self.repo.write("docs/DECISIONS.md",
                        "\n## W1 — 换个排序键\n\n- 理由: 因为原来的不对\n")
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertRefused(r, "已否决", "影响路径")

    def test_解析不出条目的写入被拒绝(self):
        """写下去却没人认得,比被拒绝更糟:agent 以为记录了,status 永远召回不到。"""
        self._在_impl()
        self.repo.write("docs/DECISIONS.md",
                        "\n随手写了几句关于排序键的想法,但没按格式来。\n")
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertRefused(r, "不构成一条决策条目", "召回不到")

    def test_过长被拒绝(self):
        """决策会被注入到此后每一次 status,长了就没人读。"""
        self._在_impl()
        self.repo.append_decision("W1", reason="啰嗦" * 800)
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertRefused(r, "上限", "压缩")

    def test_合规条目放行(self):
        self._在_impl()
        self.repo.append_decision("W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))


class TestArchaeology(PairTestCase):
    """refactor 全程绿、跳过 spec,tester 评审时手上本来什么都没有 ——
    做过考古的是 dev,所以由 dev 在交接时把考古结论交出来。"""

    def _认领重构(self):
        self.repo.advance_to("review-test")
        self.repo.run("handoff", "approve", "覆盖够", *EVIDENCE, role="dev")
        self.repo.set_plan(REFACTOR_PLAN)
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))
        self.repo.write("src/W1", "重构后")

    def test_没有考古记录不许交接(self):
        self._认领重构()
        r = self.repo.run("handoff", "重构完了", role="dev")
        self.assertRefused(r, "考古记录", "现状考古")
        self.assertEqual(self.repo.state()["phase"], "impl")

    def test_小节太短不算数(self):
        self._认领重构()
        self.repo.write("docs/notes/R1.md",
                        "## 现状考古\n没啥\n\n## 我保留了哪些契约外行为\n没有\n"
                        "\n## 我不确定的地方\n不知道\n")
        r = self.repo.run("handoff", "重构完了", role="dev")
        self.assertRefused(r, "正文只有")

    def test_交出考古记录后放行(self):
        self._认领重构()
        self.repo.write_archaeology("R1")
        self.assertAccepted(self.repo.run("handoff", "重构完了", role="dev"))

    def test_feature_不要求考古记录(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))


class TestRebound(PairTestCase):
    """来回两次说明这不是笔误,是真实分歧。不写下来,人类事后翻不到争的是什么。"""

    def _到第二次打回(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(
            self.repo.run("handoff", "changes", with_loc("问题一"), role="tester"))
        self.assertAccepted(self.repo.run("handoff", "改好了", role="dev"))

    def test_第二次打回不留结论被拒绝(self):
        self._到第二次打回()
        r = self.repo.run("handoff", "changes", with_loc("问题二"), role="tester")
        self.assertRefused(r, "第 2 次打回")
        self.assertEqual(self.repo.state()["phase"], "review-impl",
                         "被拒绝的交接不应推进阶段")

    def test_留了结论就放行(self):
        self._到第二次打回()
        self.repo.append_decision("W1")
        self.assertAccepted(
            self.repo.run("handoff", "changes", with_loc("问题二"), role="tester"))

    def test_第一次打回不强制(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(
            self.repo.run("handoff", "changes", with_loc("问题一"), role="tester"))


class TestPromotion(PairTestCase):
    """笔记是工作项级的:这一项关掉之后没有任何回合会再读到它。
    完成时是它变成长期资产的唯一时机。"""

    def _到完成前一步(self, note=LONG_NOTE):
        self.repo.advance_to("review-test")
        if note is not None:
            self.repo.write("docs/notes/W1.md", note)

    def test_笔记没处理不许完成(self):
        self._到完成前一步()
        r = self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.assertRefused(r, "笔记还没被处理", "--no-decision")
        self.assertEqual(self.repo.state()["phase"], "review-test")

    def test_晋升成决策后放行(self):
        self._到完成前一步()
        self.repo.append_decision("W1")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_显式声明没有可沉淀的也放行并留痕(self):
        self._到完成前一步()
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "测试没问题", *EVIDENCE,
            "--no-decision", "只是随手记的调试过程,没有结论", role="dev"))
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertIn("未留决策(已声明)", body)
        self.assertIn("只是随手记的调试过程", body)

    def test_没写笔记就没有这道门(self):
        self._到完成前一步(note=None)
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))

    def test_一句话的笔记不触发(self):
        self._到完成前一步(note="随手记一句")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))


class TestContractChange(PairTestCase):
    """契约变更是重新推导代价最高的事:今后每个回合都会拿改过的契约当作
    理所当然,而改它的理由谁都看不到了。"""

    def _工作项期间人类改了契约(self):
        self.repo.advance_to("review-test")
        self.repo.set_plan(PLAN_TEMPLATE,
                           contract=CONTRACT_TEMPLATE + "\n**补充** 允许空输入。\n")

    def test_契约变过就必须留记录(self):
        self._工作项期间人类改了契约()
        r = self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.assertRefused(r, "被改过", "没有对应记录")

    def test_留了记录就放行(self):
        self._工作项期间人类改了契约()
        self.repo.append_decision("W1", title="契约放宽为允许空输入")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))

    def test_契约没变时不打扰(self):
        self.repo.advance_to("review-test")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))


class TestRecall(PairTestCase):
    """存了没人读等于没存。status 是协议强制的第一条命令,也是唯一能跨
    harness 保证一定被执行的时刻 —— 召回必须挂在这里。"""

    def test_status_把本工作项笔记读出来(self):
        self.repo.advance_to("impl")
        self.repo.write("docs/notes/W1.md", "缓存键漏了租户维度,别再踩一次")
        r = self.repo.run("status", role="dev")
        self.assertIn("缓存键漏了租户维度", r.text)

    def test_status_按影响路径召回决策(self):
        self.repo.advance_to("impl")           # impl 的主体是 dev 的 src/
        self.repo.append_decision("Z9", title="src 下一律用毫秒时间戳",
                                  paths="`src/W1`")
        r = self.repo.run("status", role="dev")
        self.assertIn("src 下一律用毫秒时间戳", r.text)

    def test_status_不召回无关决策(self):
        self.repo.advance_to("impl")
        self.repo.append_decision("Z9", title="和本回合毫无关系的结论",
                                  paths="`docs/无关目录/x.md`")
        r = self.repo.run("status", role="dev")
        self.assertNotIn("和本回合毫无关系的结论", r.text)

    def test_status_始终召回同工作项的决策(self):
        self.repo.advance_to("impl")
        self.repo.append_decision("W1", title="本工作项自己的结论",
                                  paths="`docs/无关目录/x.md`")
        r = self.repo.run("status", role="dev")
        self.assertIn("本工作项自己的结论", r.text)

    def test_不是自己回合时不注入(self):
        """等待的一方不该为记忆层付上下文成本。"""
        self.repo.advance_to("impl")
        self.repo.write("docs/notes/W1.md", "缓存键漏了租户维度")
        r = self.repo.run("status", role="tester")
        self.assertNotIn("缓存键漏了租户维度", r.text)

    def test_inbox_读的是整份文件而不只是这次的_diff(self):
        """只列文件名是不够的 —— 没人会主动去 cat 它。而 diff 只给你增量:
        笔记是攒出来的,早几回合写下的那条才是你现在需要的。"""
        # 第一回合:dev 写下一条发现,再垫足够多的行,把它推出 diff 的上下文范围
        self.repo.advance_to("impl")
        self.repo.write("src/W1")
        filler = "\n".join("- 无关记录 %d" % i for i in range(12))
        self.repo.write("docs/notes/W1.md", "- 重试逻辑会破坏幂等性\n" + filler)
        self.repo.run("handoff", "实现 W1", role="dev")
        self.repo.run("handoff", "changes", with_loc("有个边界没处理"), role="tester")

        # 第三回合:只往末尾追加一行。HEAD 的 diff 里只有这一行。
        self.repo.write("docs/notes/W1.md",
                        self.repo.read("docs/notes/W1.md") + "\n- 边界补上了")
        self.repo.run("handoff", "补上边界", role="dev")

        r = self.repo.run("inbox", role="tester")
        self.assertIn("边界补上了", r.text)
        self.assertIn("重试逻辑会破坏幂等性", r.text,
                      "只打印 diff 的话,早几回合写下的记录就永远读不到了")


class TestBoundaryNotWeakened(PairTestCase):
    """记忆层是新开的写入通道,不能顺手把已有防护削掉。"""

    def test_笔记不能冒充异议举证(self):
        """异议举证认的是 shared_paths。记忆层若并进去,这条防护就废了。"""
        self.repo.advance_to("impl")
        self.repo.write("docs/notes/W1.md", "我觉得这条测试和契约矛盾")
        r = self.repo.run("handoff", "changes", with_loc("测试写错了"), role="dev")
        self.assertRefused(r, "没有把它写下来")

    def test_评审回合仍然不能改代码(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/notes/W1.md", "评审时的随手记")
        self.repo.write("src/偷改", "夹带私货")
        r = self.repo.run("handoff", "changes", with_loc("有问题"), role="tester")
        self.assertRefused(r, "越界")

    def test_评审回合可以写笔记(self):
        self.repo.advance_to("review-impl")
        self.repo.write("docs/notes/W1.md", "评审时发现的:边界情况没覆盖")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "实现本身没问题", *EVIDENCE, role="tester"))


class TestMemoryOff(PairTestCase):
    """存量项目要能渐进接入,总开关必须真的关得掉。"""

    config = {"memory": False, "require_setup_verification": False}

    def test_关掉后不再有晋升门(self):
        self.repo.advance_to("review-test")
        self.repo.write("docs/notes/W1.md", LONG_NOTE)
        # 关掉记忆层后 docs/notes 不再可写,笔记本身就越界了 —— 撤掉它,
        # 断言的是门禁不再触发,不是边界被放宽。
        self.repo.delete("docs/notes/W1.md")
        self.assertAccepted(
            self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))


class TestSetupChecksMemoryPaths(PairTestCase):
    """配错路径的后果是静默的:要么记忆层变成单方私有,要么削掉一条现有防护。"""

    def _verify(self, **cfg):
        base = dict(require_setup_verification=True)
        base.update(cfg)
        repo = PairRepo(base)
        self.addCleanup(repo.cleanup)
        repo.write("docs/reviews/setup-verification.md", "逐条核对过契约。" * 30)
        return repo.run("verify-setup", role="dev")

    def test_笔记目录落在角色路径下被拒(self):
        r = self._verify(notes_dir="src/notes")
        self.assertRefused(r, "roles.dev")

    def test_笔记目录落在共享路径下被拒(self):
        r = self._verify(notes_dir="docs/reviews/notes")
        self.assertRefused(r, "shared_paths")

    def test_决策文件落在冻结路径下被拒(self):
        r = self._verify(decisions_file=".pair/DECISIONS.md")
        self.assertRefused(r, "冻结路径")
