# -*- coding: utf-8 -*-
"""W73:契约形状检查(P0-3)—— `verify-setup` 查被引用的契约小节有没有能被断言的东西。

契约「契约形状检查」。

- 三条检查:形状(非空代码块,或带非空数据行的表)、返回或错误(关键词)、疑似漂移(只对 cover/refactor/bug);
  默认警告,`strict_contract: true` 时前两条失败,漂移始终只警告。
- 输出按既有出口 `[警告]` / `[失败]` 切成一条一条,用小节名挑出说它的那几条。用例只造"只有一条检查会触发"的小节,
  所以不依赖检查之间怎么分条;只有散文的小节两条都触发,只断言至少一条。
- 小节标题一律不含关键词(标题算不算正文,契约两读都通,见开工前审查的读法)。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;PLAN `docs/PLAN.md`,契约 `docs/CONTRACT.md`。
`verify-setup` 要一份逐节点名的审查结论才放行,每条用例照写一份(dev 的)。
"""

import re

from harness import (BareRepo, GO_CONFIG, PairTestCase, VERIFY_OK, setup_report)

REPORT = "docs/reviews/setup-verification-dev.md"
FENCE = "```"

NAME = "部件构造"
PROSE = "**行为** 按规格造一个部件。"
KEYWORD = "**错误** 规格为空时返回空部件。"
CODE = FENCE + "python\nwidget = make_widget(spec)\n" + FENCE
TABLE = "| 规格 | 部件 |\n|---|---|\n| 空 | 空部件 |"
EMPTY_TABLE = "| 规格 | 部件 |\n|---|---|\n|  |  |"

GREEN_TEST = ("import unittest\n\n"
              "class T(unittest.TestCase):\n"
              "    def test_ok(self):\n        self.assertTrue(True)\n")
PY_PROJECT = {
    "pyproject.toml": "[project]\nname = \"legacy\"\n",
    "src/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_ok.py": GREEN_TEST,
}


def section(name, *lines, basis="人类定稿", level=2):
    return "\n%s %s\n\n- 依据: %s\n\n%s\n" % ("#" * level, name, basis, "\n\n".join(lines))


def item(item_id, name, typ="feature", done=False):
    text = ("- [%s] **%s** [%s] — 给%s写用例\n  - 验收标准:见契约\n  - 对应契约:`docs/CONTRACT.md` → %s\n"
            % ("x" if done else " ", item_id, typ, name, name))
    if typ == "refactor":
        text += "  - 保护测试: tests\n"
    return text


class ShapeBase(PairTestCase):

    def lay(self, sections, items, files=None, report=None):
        """以人类身份提交 PLAN、契约与 `files`(漂移查的是已跟踪文件),再写一份点到每个被引用小节的结论。"""
        for rel, text in (files or {}).items():
            self.repo.write(rel, text)
        self.repo.set_plan("# 项目规划\n\n## 工作项\n\n" + "".join(items),
                           "# 接口契约\n" + "".join(sections))
        names = report or sorted({m for m in re.findall(r"→ (.+)", "".join(items))})
        self.repo.write(REPORT, setup_report(*names))

    def verify(self):
        return self.repo.run(*VERIFY_OK, role="dev")

    def chunks(self, r):
        """[(警告|失败, 那一条的全文)]。只看 stdout 里摘要之前那一段。"""
        out = "\n" + r.out.split("脚本能查的都通过了")[0]
        parts = re.split(r"\n  \[(警告|失败)\] ", out)
        return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]

    def about(self, r, name=NAME, kind="警告"):
        return [t for k, t in self.chunks(r) if k == kind and name in t]

    def assertWarned(self, r, name=NAME):
        self.assertAccepted(r)
        hits = self.about(r, name)
        self.assertTrue(hits, "没有一条 [警告] 提到小节「%s」:\n%s" % (name, r.out))
        return hits

    def assertQuiet(self, r, name=NAME):
        self.assertAccepted(r)
        self.assertEqual([t for _, t in self.chunks(r) if name in t], [],
                         "不该有任何一条提到小节「%s」:\n%s" % (name, r.out))


class TestShape(ShapeBase):
    """形状:非空围栏代码块,或"表头 + 分隔行 + 至少一行有非空单元格的数据行"的表。"""

    def test_只有散文的小节警告_文案含小节名与工作项(self):
        self.lay([section(NAME, PROSE)], [item("W1", NAME)])
        hits = self.assertWarned(self.verify())
        self.assertTrue(any("W1" in t for t in hits), "警告里没有工作项 ID:\n%s" % hits)

    def test_非严格模式下附一句严格时会阻断开工(self):
        """有关键词没形状:只有形状这一条会触发。"""
        self.lay([section(NAME, KEYWORD)], [item("W1", NAME)])
        hits = self.assertWarned(self.verify())
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("strict_contract", hits[0])
        self.assertIn("阻断", hits[0])

    def test_有代码块不警告(self):
        self.lay([section(NAME, KEYWORD, CODE)], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_波浪线围栏也算代码块(self):
        self.lay([section(NAME, KEYWORD, "~~~\nwidget = make_widget(spec)\n~~~")], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_只有空白的代码块不算形状(self):
        self.lay([section(NAME, KEYWORD, FENCE + "\n   \n" + FENCE)], [item("W1", NAME)])
        self.assertWarned(self.verify())

    def test_有填了数据行的表不警告(self):
        self.lay([section(NAME, KEYWORD, TABLE)], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_只有空数据行的表警告(self):
        self.lay([section(NAME, KEYWORD, EMPTY_TABLE)], [item("W1", NAME)])
        self.assertWarned(self.verify())

    def test_原样复制的模板警告(self):
        """`init` 铺出来的 PLAN 与契约原样提交:签名写在标题里,两张表只有空数据行。"""
        bare = BareRepo(PY_PROJECT)
        self.addCleanup(bare.cleanup)
        self.assertEqual(bare.run("init").code, 0)
        plan, contract = bare.read("docs/PLAN.md"), bare.read("docs/CONTRACT.md")
        self.assertIn("→ <小节名>", plan)
        self.repo.set_plan(plan, contract)
        self.repo.write(REPORT, setup_report("<小节名>"))
        hits = self.assertWarned(self.verify(), "<小节名>")
        self.assertTrue(any("W1" in t for t in hits), hits)


class TestKeywords(ShapeBase):
    """返回或错误:正文(含代码块)里有没有任一关键词,大小写不敏感;HTML 注释先去掉。"""

    def test_有形状但没有返回或错误字样警告(self):
        self.lay([section(NAME, PROSE, CODE)], [item("W1", NAME)])
        hits = self.assertWarned(self.verify())
        self.assertTrue(any("W1" in t for t in hits), hits)

    def test_关键词只在_HTML_注释里仍警告(self):
        self.lay([section(NAME, PROSE, "<!-- 规格为空时返回空部件,失败抛出异常 -->", CODE)],
                 [item("W1", NAME)])
        self.assertWarned(self.verify())

    def test_关键词只在代码块里也算(self):
        self.lay([section(NAME, PROSE, FENCE + "python\nwidget = make_widget(spec)\nraise EmptySpec\n" + FENCE)],
                 [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_英文关键词大小写不敏感(self):
        self.lay([section(NAME, PROSE, FENCE + "\nwidget = make_widget(spec)  # RETURN a widget\n" + FENCE)],
                 [item("W1", NAME)])
        self.assertQuiet(self.verify())


class TestSectionBody(ShapeBase):
    """小节正文到下一个同级或更高级标题为止,含子小节;围栏里的 `#` 行不是标题。"""

    def test_代码块在_子小节里不警告(self):
        self.lay([section(NAME, KEYWORD) + "\n### 示例\n\n" + CODE + "\n"], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_代码块在下一个同级小节里警告(self):
        self.lay([section(NAME, KEYWORD), section("部件拆卸", KEYWORD, CODE)], [item("W1", NAME)])
        self.assertWarned(self.verify())

    def test_代码块里的井号注释行不截断小节(self):
        """Python 代码块里的 `# 注释` 按 Markdown 不是标题。拿它当一级标题,小节就在围栏中间断了,代码块不再完整。"""
        code = FENCE + "python\n# 先校验规格\nwidget = make_widget(spec)\n" + FENCE
        self.lay([section(NAME, KEYWORD, code)], [item("W1", NAME)])
        self.assertQuiet(self.verify())


class TestScope(ShapeBase):
    """只查未完成工作项引用、存在、依据可断言的小节;同一节只报一次。"""

    def test_依据待核实的不查(self):
        """用 cover 项:feature 项指向待核实小节本来就有一条提到小节名的警告(不可断言)。"""
        self.lay([section(NAME, PROSE, basis="已有文档 docs/old.md(待核实)")], [item("C1", NAME, "cover")])
        self.assertQuiet(self.verify())

    def test_已完成工作项引用的不查(self):
        self.lay([section(NAME, PROSE), section("部件拆卸", KEYWORD, CODE)],
                 [item("W0", NAME, done=True), item("W1", "部件拆卸")])
        self.assertQuiet(self.verify())

    def test_两个工作项引用同一节只报一次_列出两个工作项(self):
        """有关键词没形状:只有形状这一条会触发,两个工作项也只该有一条。"""
        self.lay([section(NAME, KEYWORD)], [item("W1", NAME), item("W2", NAME)])
        hits = self.assertWarned(self.verify())
        self.assertEqual(len(hits), 1, "同一节报了 %d 次:\n%s" % (len(hits), hits))
        self.assertIn("W1", hits[0])
        self.assertIn("W2", hits[0])

    def test_不加配置时只有散文的小节_verify_setup_仍通过(self):
        self.lay([section(NAME, PROSE)], [item("W1", NAME)])
        r = self.verify()
        self.assertAccepted(r)
        self.assertTrue(self.repo.state()["setup_verified"])


class TestStrict(ShapeBase):
    """`strict_contract: true`:形状、返回或错误升为失败,漂移仍只警告。"""

    config = {"strict_contract": True}

    def test_没有形状使_verify_setup_失败(self):
        self.lay([section(NAME, KEYWORD)], [item("W1", NAME)])
        r = self.verify()
        self.assertNotEqual(r.code, 0, r)
        self.assertTrue(self.about(r, kind="失败"), r.out)

    def test_没有返回或错误使_verify_setup_失败(self):
        self.lay([section(NAME, PROSE, CODE)], [item("W1", NAME)])
        r = self.verify()
        self.assertNotEqual(r.code, 0, r)
        self.assertTrue(self.about(r, kind="失败"), r.out)

    def test_形状齐全时照样通过(self):
        """对照组:严格模式本身不让一份合格的契约失败。"""
        self.lay([section(NAME, KEYWORD, CODE)], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_漂移仍只警告(self):
        self.lay([section(NAME, KEYWORD, CODE)], [item("C1", NAME, "cover")])
        r = self.verify()
        self.assertWarned(r)
        self.assertEqual(self.about(r, kind="失败"), [], r.out)


class TestStrictValue(ShapeBase):

    config = {"strict_contract": "yes"}

    def test_不是布尔值失败_文案写明只接受_true_false(self):
        """契约形状齐全:失败只可能来自这一项。"""
        self.lay([section(NAME, KEYWORD, CODE)], [item("W1", NAME)])
        r = self.verify()
        self.assertRefused(r, "strict_contract", "true", "false")


class TestDrift(ShapeBase):
    """疑似漂移:cover/refactor/bug 项引用的小节,代码块里抽出的标识符一个都不在两个角色名下的已跟踪文件里(整词)。

    小节有关键词也有代码块,所以提到它的警告只可能是漂移那一条。"""

    SECTION = section(NAME, KEYWORD, CODE)

    def test_cover_项小节的函数名在_src_下不存在警告并列出名字(self):
        self.lay([self.SECTION], [item("C1", NAME, "cover")])
        hits = self.assertWarned(self.verify())
        self.assertTrue(any("make_widget" in t and "C1" in t for t in hits), hits)

    def test_漂移那条不说会阻断开工(self):
        """漂移永远不阻断,附上"严格时会阻断"就是假话。"""
        self.lay([self.SECTION], [item("C1", NAME, "cover")])
        for t in self.assertWarned(self.verify()):
            self.assertNotIn("阻断", t)

    def test_函数名在_src_下存在不警告(self):
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"src/widget.py": "def make_widget(spec):\n    return spec\n"})
        self.assertQuiet(self.verify())

    def test_函数名在测试目录下存在也不警告(self):
        """两个角色名下都算。harness 的测试命令要求 tests/ 下每个文件在 src/ 下有同名文件,一并放一个。"""
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"tests/probe.py": "make_widget(spec)\n", "src/probe.py": "x\n"})
        self.assertQuiet(self.verify())

    def test_同样的小节被_feature_项引用不查(self):
        self.lay([self.SECTION], [item("W1", NAME)])
        self.assertQuiet(self.verify())

    def test_只出现在_docs_里不算存在(self):
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"docs/guide.md": "调用 make_widget(spec) 造部件。\n"})
        self.assertWarned(self.verify())

    def test_只作为更长名字的一部分不算存在(self):
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"src/widget.py": "def make_widget_v2(spec):\n    return spec\n"})
        self.assertWarned(self.verify())

    def test_class_后的名字也抽(self):
        code = FENCE + "python\nclass GadgetFactory:\n    pass\n" + FENCE
        self.lay([section(NAME, KEYWORD, code)], [item("C1", NAME, "cover")])
        hits = self.assertWarned(self.verify())
        self.assertTrue(any("GadgetFactory" in t for t in hits), hits)

    def test_抽不到标识符不查(self):
        code = FENCE + "json\n{\"size\": 3}\n" + FENCE
        self.lay([section(NAME, KEYWORD, code)], [item("C1", NAME, "cover")])
        self.assertQuiet(self.verify())

    def test_中文紧挨着的调用名也抽(self):
        """`\\b` 按 Unicode 判,"用"与 `b` 之间不算边界;抽不出来整节就"抽不到不查",漂移漏报。"""
        code = FENCE + "\n// 调用build_gadget(spec)\n" + FENCE
        self.lay([section(NAME, KEYWORD, code)], [item("C1", NAME, "cover")])
        hits = self.assertWarned(self.verify())
        self.assertTrue(any("build_gadget" in t for t in hits), hits)

    def test_bug_项同样查(self):
        self.lay([self.SECTION], [item("B1", NAME, "bug")])
        self.assertWarned(self.verify())

    def test_refactor_项同样查(self):
        self.lay([self.SECTION], [item("R1", NAME, "refactor")])
        self.assertWarned(self.verify())


class TestDriftNegativePatterns(ShapeBase):
    """Go 同目录布局:dev 是 `**/*.go` + `!**/*_test.go`。两个角色的模式拼成一个列表时,dev 的负模式会把 tester 的 `_test.go` 也排除掉。"""

    config = GO_CONFIG
    SECTION = section(NAME, KEYWORD, CODE)

    def test_名字只在_tester_的测试文件里_不报漂移(self):
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"pkg/widget_test.go": "func TestWidget() { make_widget(spec) }\n",
                        "pkg/widget.go": "package pkg\n"})
        self.assertQuiet(self.verify())

    def test_对照_两边都没有照报(self):
        """上一条的对照组:同样的布局只差测试文件里有没有这个名字 —— 证明 Go 布局下漂移检查确实在跑。"""
        self.lay([self.SECTION], [item("C1", NAME, "cover")],
                 files={"pkg/widget_test.go": "package pkg\n", "pkg/widget.go": "package pkg\n"})
        self.assertWarned(self.verify())


class TestSkeleton(ShapeBase):

    def test_契约模板在边界情况之后有不做(self):
        bare = BareRepo(PY_PROJECT)
        self.addCleanup(bare.cleanup)
        self.assertEqual(bare.run("init").code, 0)
        text = bare.read("docs/CONTRACT.md")
        self.assertIn("**边界情况**", text)
        self.assertIn("**不做**", text)
        self.assertGreater(text.index("**不做**"), text.index("**边界情况**"))


if __name__ == "__main__":
    import unittest
    unittest.main()
