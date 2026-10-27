# -*- coding: utf-8 -*-
"""W71:决策的推翻(P1-11)。

契约「决策的推翻」(含 spec 回合带声明补的「补充」,开工前审查 ㉓:判"已被推翻"时不算这条新条目自己)。

- 推翻走真的 discuss / 讨论回合 / resume(同 W67 的写法:发言 = 往提案末尾追加一段);
- 注入只看 `status` 的「相关决策」那一块。断言旧条目还在不在注入里,看的是它**理由里独有的词**,不看标题 ——
  推翻它的新条目自己的 `推翻:` 行就带着旧标题。
- 只测注入那一步的用例直接往工作区的决策文件里写(`status` 读工作区,契约「不做」写明人类提交里的 `推翻:` 照样生效),不经过 resume 的校验。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;决策文件 `docs/DECISIONS.md`。
"""

from harness import EVIDENCE, PairTestCase

DFILE = "docs/DECISIONS.md"
PROPOSAL = "docs/proposals/旧结论要不要推翻.md"

OLD_REF = "W1 — 缓存按租户分键"
OLD_MARK = "租户维度漏掉会串数据甲"          # 旧条目理由里独有的词
NEW_MARK = "按用户分键才对得上验收标准乙"

LONG_NOTE = ("这一项踩了两个坑,都不在任何文档里:一是缓存键漏了租户维度,"
             "二是重试逻辑会把幂等性破坏掉。都绕过去了,但值得记下来。") * 2


def entry(eid, title, reason, paths="`tests/W1`", overturn=()):
    """一条合规条目;`推翻:` 写在 `影响路径` 之后(契约点名的那种位置)。"""
    text = ("\n## %s — %s\n\n- 理由: %s\n- 已否决: 原样保留旧结论 —— 它已经被证明是错的\n- 影响路径: %s\n"
            % (eid, title, reason, paths))
    for ref in overturn:
        text += "- 推翻: %s\n" % ref
    return text


OLD = entry("W1", "缓存按租户分键", OLD_MARK)
NEW = entry("W1", "缓存按用户分键", NEW_MARK, overturn=[OLD_REF])


class OverturnBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}
    seed = OLD

    def setUp(self):
        super().setUp()
        self.commit_as_human(self.seed)

    # --- 动作 ---------------------------------------------------------
    def commit_as_human(self, text):
        old = self.repo.read(DFILE) if self.repo.exists(DFILE) else "# 决策记录\n"
        self.repo.write(DFILE, old + text)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类直接提交决策记录")

    def add(self, text):
        self.repo.write(DFILE, self.repo.read(DFILE) + text)

    def rewrite_old(self):
        self.repo.write(DFILE, self.repo.read(DFILE).replace(OLD_MARK, "其实无所谓"))

    def say(self, role, text):
        old = self.repo.read(PROPOSAL) if self.repo.exists(PROPOSAL) else "# 旧结论要不要推翻\n"
        self.repo.write(PROPOSAL, old + "\n## %s\n\n%s\n" % (role, text))

    def open(self, role="tester"):
        self.say(role, "做 W1 时发现旧结论「缓存按租户分键」与验收标准冲突,先讨论要不要推翻。")
        return self.repo.run("discuss", "--proposal", PROPOSAL, "旧结论与验收标准冲突", role=role)

    def reply(self, role="dev"):
        self.say(role, "同意推翻,改成按用户分键。")
        return self.repo.run("handoff", "%s 的看法" % role, role=role)

    def to_dev_reply(self):
        """spec 里 tester 开讨论,停在 dev 的讨论回合。"""
        self.repo.advance_to("spec")
        self.assertAccepted(self.open())

    def to_resume(self):
        """两方都发过言,停在 tester 的讨论回合 —— 可以 resume 了。"""
        self.to_dev_reply()
        self.assertAccepted(self.reply())

    def resume(self):
        return self.repo.run("resume", "推翻旧结论,改为按用户分键", role="tester")

    # --- 观察 ---------------------------------------------------------
    def injected(self, role):
        """`status` 里「相关决策」那一块;没有就是空串。"""
        out = self.repo.run("status", role=role).text
        return out.split("--- 相关决策", 1)[1] if "--- 相关决策" in out else ""

    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(".pair/state.json")

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒时什么都不提交、状态不变")


class TestOverturnAtResume(OverturnBase):

    def test_resume_时推翻放行_旧条目留在文件里_status_不再注入它(self):
        self.to_resume()
        self.add(NEW)
        self.assertAccepted(self.resume())
        self.assertEqual(self.repo.state()["phase"], "spec")
        committed = self.repo.git("show", "HEAD:%s" % DFILE).stdout.decode("utf-8")
        self.assertIn(OLD_MARK, committed, "旧条目留在文件里")
        self.assertIn(NEW_MARK, committed)
        inj = self.injected("tester")
        self.assertIn(NEW_MARK, inj, "推翻它的新条目照常按工作项召回")
        self.assertNotIn(OLD_MARK, inj, "被推翻的条目退出注入")

    def assertRefAccepted(self, ref):
        self.to_resume()
        self.add(entry("W1", "缓存按用户分键", NEW_MARK, overturn=[ref]))
        self.assertAccepted(self.resume())
        self.assertNotIn(OLD_MARK, self.injected("tester"))

    def test_引用可带前导井号并用反引号包住(self):
        self.assertRefAccepted("`## W1 — 缓存按租户分键`")

    def test_引用的分隔符按标题行规则宽容(self):
        self.assertRefAccepted("W1 - 缓存按租户分键")


class TestTwoOverturnLines(OverturnBase):

    seed = OLD + entry("W1", "重试三次", "重试理由丙丙丙")

    def test_一条新条目两行推翻_两条都退出注入(self):
        self.to_resume()
        self.add(entry("W1", "缓存按用户分键且不重试", NEW_MARK, overturn=[OLD_REF, "W1 — 重试三次"]))
        self.assertAccepted(self.resume())
        inj = self.injected("tester")
        self.assertIn(NEW_MARK, inj)
        self.assertNotIn(OLD_MARK, inj)
        self.assertNotIn("重试理由丙丙丙", inj)


class TestOnlyAtResume(OverturnBase):
    """带 `推翻:` 的新条目在 resume 以外的入口被拒,文案指向 discuss / resume。"""

    def test_正常交接被拒(self):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")
        self.add(NEW)
        before = self.snapshot()
        r = self.repo.run("handoff", "写了 W1 的失败用例", role="tester")
        self.assertNothingHappened(r, before, "discuss", "resume")

    def test_discuss_开场被拒(self):
        self.repo.advance_to("spec")
        self.add(NEW)
        before_commits = self.repo.commit_count()
        r = self.open()
        self.assertRefused(r, "resume")
        self.assertEqual(self.repo.commit_count(), before_commits)
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_讨论回合的_handoff_被拒(self):
        self.to_dev_reply()
        self.add(NEW)
        before = self.snapshot()
        r = self.reply()
        self.assertNothingHappened(r, before, "resume")
        self.assertEqual(self.repo.state()["phase"], "discuss")


class TestReferenceChecked(OverturnBase):
    """每条引用要正好对上 HEAD 里的一条已有条目;对不上就拒,文案点出那一行。"""

    def assertResumeRefused(self, *needles):
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before, *needles)
        self.assertEqual(self.repo.state()["phase"], "discuss")

    def test_只写_ID_被拒(self):
        self.to_resume()
        self.add(entry("W1", "缓存按用户分键", NEW_MARK, overturn=["W1"]))
        self.assertResumeRefused()

    def test_标题不符被拒_文案点出那一行(self):
        self.to_resume()
        self.add(entry("W1", "缓存按用户分键", NEW_MARK, overturn=["W1 — 缓存按租户分片"]))
        self.assertResumeRefused("缓存按租户分片")

    def test_ID_不符被拒(self):
        self.to_resume()
        self.add(entry("W1", "缓存按用户分键", NEW_MARK, overturn=["W2 — 缓存按租户分键"]))
        self.assertResumeRefused("W2")

    def test_引用本回合新写的条目被拒(self):
        self.to_resume()
        self.add(entry("W1", "本回合先写的结论", "理由丁丁丁"))
        self.add(entry("W1", "再把它推翻", "理由戊戊戊", overturn=["W1 — 本回合先写的结论"]))
        self.assertResumeRefused("本回合先写的结论")


class TestAlreadyOverturned(OverturnBase):

    seed = OLD + entry("SETUP", "早先已推翻租户分键", "理由己己己", paths="`docs/无关/x.md`", overturn=[OLD_REF])

    def test_重复推翻被拒_点名已推翻它的那一条(self):
        self.to_resume()
        self.add(NEW)
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before, "早先已推翻租户分键")


class TestSameTurnDoubleOverturn(OverturnBase):

    def test_同一回合两条新条目推翻同一条被拒(self):
        """㉓ 的另一半:不算自己,但本回合**其他**新条目的 `推翻:` 算。"""
        self.to_resume()
        self.add(NEW)
        self.add(entry("W1", "另一种说法", "理由庚庚庚", overturn=[OLD_REF]))
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before)


class TestDiscussDecisionChecks(OverturnBase):
    """讨论回合的三个入口与正常交接同一套决策校验。"""

    def test_讨论回合的_handoff_改写已有条目被拒(self):
        self.to_dev_reply()
        self.rewrite_old()
        before = self.snapshot()
        self.assertNothingHappened(self.reply(), before, "追加")

    def test_resume_改写已有条目被拒(self):
        self.to_resume()
        self.rewrite_old()
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before, "追加")

    def test_discuss_开场改写已有条目被拒(self):
        self.repo.advance_to("spec")
        self.rewrite_old()
        before_commits = self.repo.commit_count()
        self.assertRefused(self.open(), "追加")
        self.assertEqual(self.repo.commit_count(), before_commits)
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_讨论回合的_handoff_写了内容却不构成条目被拒(self):
        self.to_dev_reply()
        self.add("\n随手记几句关于缓存键的想法,没按格式来。\n")
        before = self.snapshot()
        self.assertNothingHappened(self.reply(), before, "不构成")

    def test_resume_新条目缺字段被拒(self):
        self.to_resume()
        self.add("\n## W1 — 只写了理由\n\n- 理由: 因为原来的不对\n")
        before = self.snapshot()
        self.assertNothingHappened(self.resume(), before, "已否决")

    def test_对照组_讨论回合追加一条合规的普通条目照旧放行(self):
        self.to_dev_reply()
        self.add(entry("W1", "讨论中记下的一条事实", "理由辛辛辛"))
        self.assertAccepted(self.reply())


class TestNormalHandoffTexts(OverturnBase):

    def test_追加式拒绝文案指向_discuss_与_resume(self):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")
        self.rewrite_old()
        r = self.repo.run("handoff", "写了 W1 的失败用例", role="tester")
        self.assertRefused(r, "追加式", "伪造共识", "discuss", "resume", "推翻")

    def test_条目格式提示补了推翻这个可选字段(self):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")
        self.add("\n## W1 — 只写了理由\n\n- 理由: 因为原来的不对\n")
        r = self.repo.run("handoff", "写了 W1 的失败用例", role="tester")
        self.assertRefused(r, "已否决", "- 推翻:")


SIX = "".join(entry("W1", "结论%s" % n, "标记%s%s%s" % (n, n, n)) for n in "一二三四五六")
SIX_MARKS = ["标记%s%s%s" % (n, n, n) for n in "一二三四五六"]


class TestInjectionBudget(OverturnBase):
    """先跳过被推翻的,再取最后 5 条。推翻者与当前阶段无关,不挤进后五条(见开工前审查的读法)。"""

    seed = SIX

    def test_对照组_没有推翻时最早那条被挤掉(self):
        self.repo.advance_to("spec")
        inj = self.injected("tester")
        self.assertNotIn(SIX_MARKS[0], inj)
        for m in SIX_MARKS[1:]:
            self.assertIn(m, inj)

    def test_六条里推翻一条_注入其余五条_最早那条回来了(self):
        self.repo.advance_to("spec")
        self.add(entry("SETUP", "推翻第三条", "理由壬壬壬", paths="`docs/无关/x.md`", overturn=["W1 — 结论三"]))
        inj = self.injected("tester")
        self.assertNotIn(SIX_MARKS[2], inj)
        for m in SIX_MARKS[:2] + SIX_MARKS[3:]:
            self.assertIn(m, inj)


class TestOverturnOfOverturn(OverturnBase):
    """「推翻的推翻」不恢复旧条目。"""

    seed = (entry("W1", "结论甲", "标记甲甲甲")
            + entry("W1", "推翻甲", "标记乙乙乙", overturn=["W1 — 结论甲"]))

    def test_被推翻的推翻者也退出_旧条目不回来(self):
        self.repo.advance_to("spec")
        self.add(entry("W1", "推翻乙", "标记丙丙丙", overturn=["W1 — 推翻甲"]))
        inj = self.injected("tester")
        self.assertIn("标记丙丙丙", inj)
        self.assertNotIn("标记甲甲甲", inj)
        self.assertNotIn("标记乙乙乙", inj)


class TestFieldParsing(OverturnBase):
    """`推翻:` 写在 `影响路径` 后面时不当续行。被推翻的标题里含一个 dev 路径 —— 当成续行,召回就会多出这条(开工前审查的读法)。"""

    seed = entry("W5", "不再改 src/W1 的接口", "标记癸癸癸", paths="`docs/无关/y.md`")
    OVERTURNER = entry("Z9", "接口照旧可以改", "标记子子子", paths="`tests/W1`", overturn=["W5 — 不再改 src/W1 的接口"])

    def test_dev_主体的阶段不召回(self):
        self.repo.advance_to("impl")
        self.add(self.OVERTURNER)
        self.assertNotIn("标记子子子", self.injected("dev"))

    def test_对照组_tester_主体的阶段照常按影响路径召回(self):
        self.repo.advance_to("spec")
        self.add(self.OVERTURNER)
        self.assertIn("标记子子子", self.injected("tester"))


class TestPromotionGateStillCounts(OverturnBase):
    """「不做」:晋升闸判"本工作项有没有决策"时,被推翻的仍算。"""

    seed = OLD + entry("SETUP", "早先已推翻租户分键", "理由己己己", paths="`docs/无关/x.md`", overturn=[OLD_REF])

    def test_本工作项只有一条被推翻的决策_完成照样放行(self):
        self.repo.advance_to("review-test")
        self.repo.write("docs/notes/W1.md", LONG_NOTE)
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))
        self.assertEqual(self.repo.state()["phase"], "idle")


if __name__ == "__main__":
    import unittest
    unittest.main()
