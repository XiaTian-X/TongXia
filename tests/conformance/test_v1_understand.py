# -*- coding: utf-8 -*-
"""W72:understand 模式(P0-6)—— `discuss --understand` 空闲时进入、至少三次发言、`resume` 交出双方签字的草案或带声明不交。

契约「understand 模式」。

- 发言 = 往提案末尾追加一段(同 W67 的写法);
- 草案用真的 `git diff` 造:把 PLAN 与契约改成新内容、取 diff、再还原(同 W68 的写法);
- 最短的合规流程:tester 开场;dev 在讨论回合写独立理解、交叉检查与草案并 `sign`;tester `resume` 时追加交叉检查并 `sign`(第三次发言)。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;PLAN `docs/PLAN.md`,契约 `docs/CONTRACT.md`;harness 不要求开工前校验,idle 归 tester。
"""

import re

from harness import PairTestCase

PROPOSAL = "docs/proposals/读懂解析器.md"
WHY = "接入的存量项目里解析器没人说得清,先读懂再立 cover 项"
HUMAN = {"PAIR_ROLE": "human"}

SECTION = "解析器的现状"
COVER = """- [ ] **C1** [cover] — 给解析器的现状补特征测试
  - 验收标准:空输入返回空字符串
  - 对应契约:`docs/CONTRACT.md` → %s
"""


def contract_section(title=SECTION, basis="考古观察@%(sha)s"):
    return "\n## %s\n\n- 依据: %s\n\n**行为** 空输入返回空字符串。\n" % (title, basis)


class UnderstandBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}

    def setUp(self):
        super().setUp()
        self.sha = self.repo.git("rev-parse", "HEAD").stdout.decode().strip()

    # --- 动作 ---------------------------------------------------------
    def say(self, role, text):
        old = self.repo.read(PROPOSAL) if self.repo.exists(PROPOSAL) else "# 读懂解析器\n"
        self.repo.write(PROPOSAL, old + "\n## %s\n\n%s\n" % (role, text))

    def open(self, role="tester", understand=True, write=True):
        if write:
            self.say(role, "我的独立理解:解析器空输入时返回空字符串,调用方依赖这一点。")
        args = ["discuss"] + (["--understand"] if understand else []) + ["--proposal", PROPOSAL, WHY]
        return self.repo.run(*args, role=role)

    def reply(self, role="dev", text="我的独立理解与交叉检查:同意空输入那条;另外读到重试会破坏幂等。"):
        self.say(role, text)
        return self.repo.run("handoff", "%s 的理解与交叉检查" % role, role=role)

    def resume(self, *extra, role="tester", speak=True):
        if speak:
            self.say(role, "交叉检查:对方说的重试那条我复核过,成立。")
        return self.repo.run("resume", "读懂了解析器", *extra, role=role)

    def sign(self, role):
        return self.repo.run("sign", PROPOSAL, role=role)

    def ratify(self):
        return self.repo.run("ratify", PROPOSAL, role=None, env=HUMAN)

    # --- 草案 ---------------------------------------------------------
    def draft(self, contract_add=None, plan_add=None, extra=None):
        """PLAN 与契约(以及可选的别的文件)一起改、取 diff、再还原。"""
        if contract_add is None:
            contract_add = contract_section()
        if plan_add is None:
            plan_add = COVER % SECTION
        changes = {"docs/CONTRACT.md": contract_add % {"sha": self.sha}, "docs/PLAN.md": plan_add}
        changes.update(extra or {})
        olds = {rel: self.repo.read(rel) for rel in changes}
        for rel, add in changes.items():
            self.repo.write(rel, olds[rel] + add)
        d = self.repo.git("diff", "--", *sorted(changes)).stdout.decode("utf-8")
        for rel, old in olds.items():
            self.repo.write(rel, old)
        return d

    def fence(self, block):
        return "草案如下。\n\n```diff\n%s```" % block

    def to_draft_resume(self, block, tester_signs=True):
        """dev 在讨论回合写草案并签;停在 tester 的讨论回合,tester 追加交叉检查(并签)。"""
        self.assertAccepted(self.open())
        self.say("dev", "我的独立理解与交叉检查:同意空输入那条。")
        self.say("dev", self.fence(block))
        self.assertAccepted(self.sign("dev"))
        self.assertAccepted(self.repo.run("handoff", "dev 的理解、交叉检查与草案", role="dev"))
        self.say("tester", "交叉检查:草案与我们两份理解对得上。")
        if tester_signs:
            self.assertAccepted(self.sign("tester"))

    # --- 观察 ---------------------------------------------------------
    def snapshot(self):
        return self.repo.commit_count(), self.repo.read(".pair/state.json")

    def first_line(self):
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        return body.strip("\n").split("\n", 1)[0]

    def body(self):
        return self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")

    def turn(self):
        return self.repo.run("whose-turn", role="tester").out.split("\n", 1)[0].strip()

    def assertNothingHappened(self, r, before, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual(self.snapshot(), before, "被拒时什么都不提交、状态不变")


class TestOpen(UnderstandBase):

    def test_idle_时放行_轮到对方_工作项为空_正文第一行(self):
        self.assertAccepted(self.open())
        st = self.repo.state()
        self.assertEqual(st["phase"], "discuss")
        self.assertIsNone(st["item"])
        self.assertEqual(st["discuss"]["mode"], "understand")
        self.assertEqual(st["discuss"]["speeches"], 1)
        self.assertEqual(self.turn(), "turn dev")
        self.assertTrue(self.first_line().startswith("understand=open role=tester"), self.first_line())

    def test_工作阶段带它被拒(self):
        self.repo.advance_to("spec")
        before = self.snapshot()
        self.assertNothingHappened(self.open(), before)
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_idle_不带它被拒_文案含_understand(self):
        before = self.snapshot()
        self.assertNothingHappened(self.open(understand=False), before, "--understand")

    def test_不是自己回合被拒(self):
        before = self.snapshot()
        self.assertNothingHappened(self.open(role="dev"), before)

    def test_提案本回合没写被拒(self):
        before = self.snapshot()
        self.assertNothingHappened(self.open(write=False), before)

    def test_工作区有代码被拒(self):
        self.repo.write("src/W1")
        before = self.snapshot()
        self.assertNothingHappened(self.open(), before)


class TestQuotaNotUsed(UnderstandBase):

    config = {"proposal_paths": ["docs/proposals"], "discuss_limit": 0}

    def test_不计额度_额度为_0_也能进_resume_后_discussed_不变(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.assertAccepted(self.resume("--no-draft", "只读懂了,还没到能写契约的程度"))
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertEqual(st.get("discussed") or [], [])


class TestSpeeches(UnderstandBase):

    def test_讨论回合后_speeches_递增_正文第一行(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.assertEqual(self.repo.state()["discuss"]["speeches"], 2)
        self.assertTrue(self.first_line().startswith("understand=reply role=dev"), self.first_line())

    def test_两次发言后_resume_被拒且状态不变_第三次放行(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        before = self.snapshot()
        self.assertNothingHappened(self.resume("--no-draft", "谈不出草案", speak=False), before)
        self.assertEqual(self.repo.state()["phase"], "discuss")
        self.assertAccepted(self.resume("--no-draft", "谈不出草案"))
        self.assertEqual(self.repo.state()["phase"], "idle")


class TestNoDraft(UnderstandBase):

    def test_no_draft_空理由被拒(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.say("tester", "交叉检查:成立。")
        before = self.snapshot()
        self.assertNothingHappened(self.resume("--no-draft", "  ", speak=False), before, "--no-draft")

    def test_没草案也没声明被拒(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.say("tester", "交叉检查:成立。")
        before = self.snapshot()
        self.assertNothingHappened(self.resume(speak=False), before)

    def test_带声明放行_正文有声明_恢复到_idle(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.assertAccepted(self.resume("--no-draft", "双方理解还对不上,先不写契约"))
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertIsNone(st.get("discuss"))
        self.assertEqual(self.turn(), "turn tester")
        self.assertTrue(self.first_line().startswith("understand=resume role=tester"), self.first_line())
        self.assertIn("未产出草案(已声明): 双方理解还对不上,先不写契约", self.body())


class TestDraftAccepted(UnderstandBase):

    def test_合规草案放行_恢复到_idle_之后人类_ratify_落地(self):
        block = self.draft()
        self.to_draft_resume(block)
        r = self.resume(speak=False)
        self.assertAccepted(r)
        self.assertIn("ratify", r.text)
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertEqual(st.get("discussed") or [], [])
        self.assertTrue(self.first_line().startswith("understand=resume role=tester"), self.first_line())
        body = self.body()
        self.assertIn(PROPOSAL, body)
        import hashlib
        self.assertIn(hashlib.sha256(block.encode("utf-8")).hexdigest()[:16], body)
        self.assertAccepted(self.ratify())
        self.assertIn("## %s" % SECTION, self.repo.read("docs/CONTRACT.md"))
        self.assertIn("**C1** [cover]", self.repo.read("docs/PLAN.md"))


class TestDraftRefused(UnderstandBase):
    """草案各条不满足,`resume` 各被拒,什么都不提交、状态不变。"""

    def assertDraftRefused(self, block, tester_signs=True, after=None):
        self.to_draft_resume(block, tester_signs=tester_signs)
        if after:
            after()
        before = self.snapshot()
        self.assertNothingHappened(self.resume(speak=False), before)
        self.assertEqual(self.repo.state()["phase"], "discuss")

    def test_缺一方签字(self):
        self.assertDraftRefused(self.draft(), tester_signs=False)

    def test_签的不是最后一个_diff_块(self):
        def later_block():
            self.say("tester", self.fence(self.draft(contract_add=contract_section(title="解析器的另一种现状"),
                                                    plan_add=COVER % "解析器的另一种现状")))
        self.assertDraftRefused(self.draft(), after=later_block)

    def test_diff_碰了别的文件(self):
        self.repo.write("docs/其他.md", "# 其他\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类放一份别的文档")
        self.assertDraftRefused(self.draft(extra={"docs/其他.md": "顺手改一句\n"}))

    def test_契约没新增小节(self):
        self.assertDraftRefused(self.draft(contract_add="\n**补充** 依据: 考古观察@%(sha)s,空输入返回空字符串。\n",
                                           plan_add=COVER % "W1"))

    def test_新增小节没写考古观察(self):
        self.assertDraftRefused(self.draft(contract_add=contract_section(basis="人类定稿")))

    def test_考古观察的_sha_不存在(self):
        self.assertDraftRefused(self.draft(contract_add=contract_section(basis="考古观察@deadbeef0123")))

    def test_PLAN_新增的不是_cover(self):
        feature = COVER.replace("**C1** [cover]", "**W3** [feature]") % SECTION
        self.assertDraftRefused(self.draft(plan_add=COVER % SECTION + feature))

    def test_某个新增小节没被_cover_引用(self):
        self.assertDraftRefused(self.draft(contract_add=contract_section() + contract_section(title="重试的现状")))

    # review-impl 第一次打回修掉的那处:引用只认**新增 cover 项自己的块**里的。
    # draft() 把 plan_add 接在 PLAN 末尾,紧跟模板里 W2 的块 —— 没有工作项行开头的新增行就落进 W2 的块。
    REF = "  - 对应契约:`docs/CONTRACT.md` → %s\n" % SECTION

    def test_一个_cover_项都不加_只在已有工作项块里引用新节(self):
        self.assertDraftRefused(self.draft(plan_add=self.REF))

    def test_cover_项引用别处_新节的引用挂在已有工作项块里(self):
        self.assertDraftRefused(self.draft(plan_add=self.REF + COVER % "W1"))


class TestStatusBrief(UnderstandBase):

    def test_后发言方第一次发言前_简报含独立(self):
        self.assertAccepted(self.open())
        self.assertIn("独立", self.repo.run("status", role="dev").out)


class Rows(dict):

    def __missing__(self, key):
        raise AssertionError("report 里没有「%s」这一行:%s" % (key, dict(self)))


class TestReport(UnderstandBase):

    def test_report_的讨论次数不算_understand(self):
        self.assertAccepted(self.open())
        self.assertAccepted(self.reply())
        self.assertAccepted(self.resume("--no-draft", "先不写"))
        found = Rows()
        for line in self.repo.run("report", role="tester").out.splitlines():
            m = re.match(r"^\s*(讨论 / 认领|讨论|人类批准的提案)\s{2,}(.*?)\s{2,}(\S.*)?$", line)
            if m:
                found[m.group(1)] = m.group(2).strip()
        self.assertEqual(found["讨论"], "0", found)


if __name__ == "__main__":
    import unittest
    unittest.main()
