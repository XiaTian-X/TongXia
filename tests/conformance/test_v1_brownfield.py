# -*- coding: utf-8 -*-
"""接入现有项目会踩到的那几道门。

这些机制没有 mode 开关 —— 它们在新项目里同样成立,只是现有项目更容易撞上。
共同的主题是:**协议不该建在一份未经核实的规格上,也不该在没有安全网时重构。**
"""

import unittest

from harness import (CONTRACT_TEMPLATE, EVIDENCE, PLAN_TEMPLATE, BareRepo,
                     PairTestCase, setup_report, with_loc)

GREEN_TEST = ("import unittest\n\n"
              "class T(unittest.TestCase):\n"
              "    def test_ok(self):\n        self.assertTrue(True)\n")

PY_PROJECT = {
    "pyproject.toml": "[project]\nname = \"legacy\"\n",
    "src/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_ok.py": GREEN_TEST,
}

# 一份从老文档抄来的契约:小节在,但没人核实过它还成不成立
UNVERIFIED_CONTRACT = """# 接口契约

## W1

- 依据: 已有文档 docs/api.md §3(待核实)

**行为** tests/W1 存在时 src/W1 必须存在。

## W2

- 依据: 人类定稿

**行为** tests/W2 存在时 src/W2 必须存在。
"""

NO_PROVENANCE_CONTRACT = """# 接口契约

## W1

**行为** tests/W1 存在时 src/W1 必须存在。

## W2

- 依据: 人类定稿

**行为** tests/W2 存在时 src/W2 必须存在。
"""

COVER_PLAN = """# 规划

## 工作项

- [ ] **W1** [cover] — 给已有行为补测试
  - 对应契约:`docs/CONTRACT.md` → W1
- [ ] **W2** [feature] — 新功能
  - 对应契约:`docs/CONTRACT.md` → W2
"""

COVER_NOTE = """## 行为来源

读了 src/W1 的实现并在本地跑了一遍:空输入返回空字符串,不抛错。
契约里没有这条,所以断言的依据是这次观察本身,不是文档。

## 我冻结了哪些可疑行为

空输入返回空字符串看着像遗漏 —— 更像该抛 ValueError。但现有调用方依赖它,
我照原样固化了。如果这其实是缺陷,应当另开一个 [bug] 工作项。
"""


class TestContractProvenance(PairTestCase):
    """老文档只能当线索。它写"返回 null"而实际代码抛异常时,tester 会照它
    写断言、dev 会以为发现了 bug 去改行为 —— 每一步都合规,结果是线上炸。"""

    def test_没写依据的小节在开工前被拦下(self):
        self.repo.set_plan(PLAN_TEMPLATE, NO_PROVENANCE_CONTRACT)
        self.repo.write("docs/reviews/setup-verification.md", setup_report("W1", "W2"))
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "没写 `依据`", "人类定稿")

    def test_开工前只警告不阻断(self):
        """人类应该能把完整路线图一次写进 PLAN —— 后面的项依赖前面的 cover
        把契约做实,那是**顺序**,不是配置错误。硬闸在 claim。"""
        self.repo.set_plan(COVER_PLAN.replace("[cover]", "[feature]"),
                           UNVERIFIED_CONTRACT)
        self.repo.write("docs/reviews/setup-verification.md", setup_report("W1", "W2"))
        r = self.repo.run("verify-setup", role="dev")
        self.assertAccepted(r)
        self.assertIn("不可断言", r.text)
        self.assertIn("[警告]", r.text)

    def test_待核实的规格不能开_feature(self):
        self.repo.set_plan(COVER_PLAN.replace("[cover]", "[feature]"),
                           UNVERIFIED_CONTRACT)
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "不可断言", "cover")

    def test_待核实的规格可以开_cover(self):
        """cover 的活就是把它变成事实 —— 那正是待核实小节唯一的出路。"""
        self.repo.set_plan(COVER_PLAN, UNVERIFIED_CONTRACT)
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_契约小节被改名后_claim_也拦得住(self):
        """verify-setup 之后人类还会动契约。claim 是唯一贴着开工那一刻的闸。"""
        self.repo.set_plan(COVER_PLAN.replace("[cover]", "[feature]"),
                           UNVERIFIED_CONTRACT.replace("## W1", "## W1-改了名"))
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "不存在", "没有可断言的东西")

    def test_人类定稿后就能开工(self):
        self.repo.set_plan(COVER_PLAN.replace("[cover]", "[feature]"),
                           UNVERIFIED_CONTRACT.replace(
                               "已有文档 docs/api.md §3(待核实)", "考古观察@a1b2c3d"))
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))


class TestCoverNotes(PairTestCase):
    """特征测试会把缺陷一起焊死,而全程绿的红绿不变量抓不到这件事。"""

    def _认领(self):
        # cover 的前提是"被测行为本来就在"。先把实现与既有测试落成基线,
        # 再让 tester 补一条新的特征测试 —— 全程绿。
        self.repo.write("src/W1")
        self.repo.write("src/W1-more")
        self.repo.write("tests/W1")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "chore: 已有实现")
        self.repo.set_plan(COVER_PLAN, UNVERIFIED_CONTRACT)
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1-more", "x")

    def test_没交特征测试记录不许交接(self):
        self._认领()
        r = self.repo.run("handoff", "补了 W1 的测试", role="tester")
        self.assertRefused(r, "特征测试记录", "我冻结了哪些可疑行为")

    def test_只写一半也不算(self):
        self._认领()
        self.repo.write("docs/notes/W1.md", "## 行为来源\n\n" + "读了实现并跑过。" * 8)
        r = self.repo.run("handoff", "补了 W1 的测试", role="tester")
        self.assertRefused(r, "我冻结了哪些可疑行为")

    def test_两节都交了就放行(self):
        self._认领()
        self.repo.write("docs/notes/W1.md", COVER_NOTE)
        self.assertAccepted(self.repo.run("handoff", "补了 W1 的测试", role="tester"))

    def test_feature_不受这条约束(self):
        self.repo.advance_to("spec", item="W1")
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "写了失败用例", role="tester"))


class TestRefactorNeedsSafetyNet(PairTestCase):
    """无网重构是协议唯一 police 不了的场景:测试全程绿,而绿的测试
    按定义没抓到任何问题 —— 那片代码本来就没测试时,"绿"什么都不证明。"""

    PLAN = PLAN_TEMPLATE + """- [ ] **R1** [refactor] — 重构 W1
  - 对应契约:`docs/CONTRACT.md` → W1
%s
"""

    def _plan(self, protect_line):
        return self.PLAN % protect_line

    def test_没声明保护测试就不许认领(self):
        self.repo.set_plan(self._plan(""))
        r = self.repo.run("claim", "R1", role="tester")
        self.assertRefused(r, "保护测试", "cover")

    def test_路径不存在被拒(self):
        self.repo.set_plan(self._plan("  - 保护测试: tests/根本没有这个目录"))
        r = self.repo.run("claim", "R1", role="tester")
        self.assertRefused(r, "路径不存在")

    def test_指向实现目录被拒(self):
        """保护重构的必须是测试。指向实现等于没有安全网。"""
        self.repo.set_plan(self._plan("  - 保护测试: src"))
        r = self.repo.run("claim", "R1", role="tester")
        self.assertRefused(r, "不在 tester 名下")

    def test_对应契约不在最后一行也能被解析(self):
        """回归:CONTRACT_REF_RE 曾经少了 re.M,于是"对应契约后面还有别的行"
        的工作项会被误报成"没有指向契约"。"""
        self.repo.set_plan(PLAN_TEMPLATE + """- [ ] **R1** [refactor] — 重构 W1
  - 对应契约:`docs/CONTRACT.md` → W1
  - 保护测试: tests
  - 验收标准:行为不变
""")
        self.repo.write("docs/reviews/setup-verification.md", setup_report("W1", "W2"))
        r = self.repo.run("verify-setup", role="dev")
        self.assertNotIn("没有指向契约", r.text)
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))

    def test_指向真实测试目录就放行(self):
        self.repo.set_plan(self._plan("  - 保护测试: tests"))
        self.assertAccepted(self.repo.run("claim", "R1", role="tester"))


class TestScope(PairTestCase):
    """存量项目最危险的不是结构不合适,是蔓延。"""

    # 范围覆盖 harness 推进回合时用到的 W1,但不含 src/shared
    config = {"scope": ["src/W1", "tests/W1", "src/billing/**", "tests/billing/**"]}

    def test_范围外的改动被拒(self):
        self.repo.advance_to("impl")
        self.repo.write("src/shared/util.py", "顺手改了个公共工具")
        r = self.repo.run("handoff", "实现 W1", role="dev")
        self.assertRefused(r, "本轮范围之外", "人类的决定")

    def test_范围内的改动放行(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1", "改了范围内的实现")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))

    def test_评审目录不受_scope_限制(self):
        """评审与记忆层是散文不是代码 —— 圈进 scope 会让异议无处可写。"""
        self.repo.advance_to("review-impl")
        self.repo.write("docs/reviews/W1.md", "详见下文")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("这里不对"), role="tester"))


class TestFullSuiteReport(PairTestCase):
    """门禁套件可以收窄到本轮范围,但范围之外的回归不能无声无息。"""

    config = {"full_test_cmd": "python3 -c \"import sys; sys.exit(1)\""}

    def _完成工作项(self):
        self.repo.advance_to("review-test")
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")

    def test_全量套件红时退出码是_2(self):
        r = self._完成工作项()
        self.assertEqual(r.code, 2,
                         "门禁绿、全量红时必须用退出码 2 把这件事顶出来。\n%r" % r)
        self.assertIn("全量套件红", r.text)
        self.assertIn("不要告诉人类", r.text)

    def test_交接本身仍然落地(self):
        """不阻断是有意的:范围外的代码这对结对本来就无权修,阻断等于死锁。"""
        before = self.repo.commit_count()
        self._完成工作项()
        self.assertGreater(self.repo.commit_count(), before)
        self.assertEqual(self.repo.state()["phase"], "idle")
        self.assertIn("W1", self.repo.state()["completed_items"])


    def test_全量套件日志不会卡死下一回合(self):
        """回归:.pair/.last-full-test.log 落在冻结路径 .pair 之下。
        不豁免边界检查,agent 就会被自己刚跑的那次测试永久卡住,而且删不干净
        —— 下一个工作项完成时又会生成。"""
        self._完成工作项()
        self.assertTrue(self.repo.exists(".pair/.last-full-test.log"))
        self.assertAccepted(self.repo.run("claim", "W2", role="tester"))
        self.repo.write("tests/W2")
        self.assertAccepted(self.repo.run("handoff", "写了 W2 的失败用例",
                                          role="tester"))


class TestFullSuiteGreen(PairTestCase):

    config = {"full_test_cmd": "python3 -c \"import sys; sys.exit(0)\""}

    def test_全量套件绿时不打扰(self):
        self.repo.advance_to("review-test")
        r = self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.assertEqual(r.code, 0, r)
        self.assertNotIn("全量套件红", r.text)


class TestContractSectionParsing(PairTestCase):
    """小节按标题文本检索,所以"取到哪为止"和"重名怎么办"都会影响依据判定。"""

    PARENT_INHERIT = """# 契约

## W1

### 某个子小节

- 依据: 人类定稿
"""

    DUPLICATE = """# 契约

## W1

- 依据: 人类定稿

### 同名小节

## 另一节

### 同名小节

- 依据: 人类定稿
"""

    def test_父小节不继承子小节的依据(self):
        """回归:正文若取全了(含子小节),没人背书的 `##` 会因为它下面某个
        `###` 写了依据而被放行。"""
        self.repo.set_plan(PLAN_TEMPLATE, self.PARENT_INHERIT)
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "没写 `依据`")

    def test_代码块里的标题不算小节(self):
        """契约里放 markdown 示例是正常的 —— 格式类规格本来就该用示例锚定。
        示例里的 `# 标题` 不是契约的小节,不剔掉的话一份带示例的契约会被
        误判成"小节重名",而且偏移量错位会让 `依据` 也读错。"""
        contract = """# 契约

## W1

- 依据: 人类定稿

**行为** 输出必须与下面这份示例逐字节一致:

```
# W1

- 字段: 值
```

## W2

- 依据: 人类定稿

**行为** 同样贴一份示例:

```
# W1
```
"""
        self.repo.set_plan(PLAN_TEMPLATE, contract)
        self.repo.write("docs/reviews/setup-verification.md", setup_report("W1", "W2"))
        r = self.repo.run("verify-setup", role="dev")
        self.assertNotIn("多个标题都叫", r.text)
        self.assertAccepted(r)
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_重名小节被当成歧义拦下(self):
        """回归:字典按标题建键,后者覆盖前者 —— 顺序反过来就是错误放行。"""
        self.repo.set_plan(
            PLAN_TEMPLATE.replace("→ W1", "→ 同名小节"), self.DUPLICATE)
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "多个标题都叫", "歧义")


class TestEntryFileMerge(unittest.TestCase):
    """现有项目本来就有 CLAUDE.md。"存在即跳过"会让接入"成功"而协议从未生效。"""

    def test_frontmatter_留在第一个字节(self):
        """回归:`.mdc` 的 YAML frontmatter 必须在文件开头,前面多一行 HTML
        注释就整块失效 —— alwaysApply 不再生效,而那正是这个文件的全部作用。"""
        repo = BareRepo(PY_PROJECT)
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        text = repo.read(".cursor/rules/pair.mdc")
        self.assertTrue(text.startswith("---\n"), repr(text[:40]))
        self.assertIn("alwaysApply: true", text.split("---")[1])
        self.assertIn("<!-- pair-protocol:begin -->", text)

    def test_不改写别人已有的_frontmatter(self):
        files = dict(PY_PROJECT)
        files[".cursor/rules/pair.mdc"] = "---\ndescription: 我自己的规则\n---\n\n正文。\n"
        repo = BareRepo(files)
        self.addCleanup(repo.cleanup)
        repo.run("init")
        text = repo.read(".cursor/rules/pair.mdc")
        self.assertTrue(text.startswith("---\ndescription: 我自己的规则"), repr(text[:40]))
        self.assertIn("正文。", text)
        self.assertIn("<!-- pair-protocol:begin -->", text)

    def test_已有内容保留且协议段落在最前(self):
        files = dict(PY_PROJECT)
        files["AGENTS.md"] = "# 既有约定\n\n请遵守本仓库的提交规范。\n"
        repo = BareRepo(files)
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        text = repo.read("AGENTS.md")
        self.assertIn("既有约定", text)
        self.assertIn("<!-- pair-protocol:begin -->", text)
        self.assertLess(text.index("<!-- pair-protocol:begin -->"),
                        text.index("既有约定"))
