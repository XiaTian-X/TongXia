# -*- coding: utf-8 -*-
"""W82:契约里的待澄清标记挡住认领,review-impl 查契约没要求的行为。

契约「契约的未决点与越界」。

- feature / bug 项认领时,引用小节(标题行、正文、子小节)里有 `[待澄清: …]` / `[NEEDS CLARIFICATION: …]` → 拒绝,
  提交数与 `state.json` 不变;cover / refactor 不拦;围栏与行内代码里的不算,HTML 注释里的照算。
- `verify-setup` 对未完成的 feature / bug 项按小节聚合提醒,不判失败。
- review-impl 简报加"契约没要求";契约骨架与 `contract-templates.md` 的「不做」口径统一。

用例里一节之内只放被测的那一处反引号,不依赖跨段落的反引号怎么配对。
全角括号与冒号用 `chr(0x...)` 拼(`\\uXXXX` 写进文件会被转成字面字符,测试会悄悄失去区分力)。
"""

import re

from harness import BareRepo, PairTestCase, SKILL_SRC, VERIFY_OK, setup_report

REPORT = "docs/reviews/setup-verification-dev.md"
FENCE = "```"

FW_COLON = chr(0xFF1A)          # 全角冒号
FW_LB, FW_RB = chr(0xFF3B), chr(0xFF3D)        # 全角方括号
CJK_LB, CJK_RB = chr(0x3010), chr(0x3011)      # 黑括号

NAME = "部件构造"
OTHER = "部件拆卸"
PROSE = "**行为** 按规格造一个部件。"
KEYWORD = "**错误** 规格为空时返回空部件。"
TABLE = "| 规格 | 部件 |\n|---|---|\n| 空 | 空部件 |"
MARK = "[待澄清: 部件的单位是什么]"

GREEN_TEST = ("import unittest\n\n"
              "class T(unittest.TestCase):\n"
              "    def test_ok(self):\n        self.assertTrue(True)\n")
PY_PROJECT = {
    "pyproject.toml": "[project]\nname = \"legacy\"\n",
    "src/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_ok.py": GREEN_TEST,
}


def section(name, *lines, level=2):
    return "\n%s %s\n\n- 依据: 人类定稿\n\n%s\n" % ("#" * level, name, "\n\n".join(lines))


def item(item_id, name, typ="feature", done=False):
    text = ("- [%s] **%s** [%s] — 给%s写用例\n  - 验收标准:见契约\n  - 对应契约:`docs/CONTRACT.md` → %s\n"
            % ("x" if done else " ", item_id, typ, name, name))
    if typ == "refactor":
        text += "  - 保护测试: tests\n"
    return text


class ClaimBase(PairTestCase):

    def lay(self, sections, items):
        """以人类身份提交 PLAN 与契约。"""
        self.repo.set_plan("# 项目规划\n\n## 工作项\n\n" + "".join(items),
                           "# 接口契约\n" + "".join(sections))

    def claim(self, item_id="W1"):
        self.before = (self.repo.commit_count(), self.repo.read(".pair/state.json"))
        return self.repo.run("claim", item_id, role="tester")

    def assertClaimRefused(self, r, *needles):
        self.assertRefused(r, *needles)
        self.assertEqual((self.repo.commit_count(), self.repo.read(".pair/state.json")), self.before,
                         "拒绝认领时提交数与状态都不该变")

    def assertClaimed(self, r, item_id="W1"):
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["item"], item_id)

    def refused_with(self, *lines, typ="feature"):
        """引用小节的正文里放 `lines`,认领应被拒。"""
        self.lay([section(NAME, PROSE, *lines)], [item("W1", NAME, typ)])
        r = self.claim()
        self.assertClaimRefused(r)
        return r

    def claimed_with(self, *lines, typ="feature"):
        self.lay([section(NAME, PROSE, *lines)], [item("W1", NAME, typ)])
        self.assertClaimed(self.claim())


class TestRefused(ClaimBase):

    def test_没有标记照常认领(self):
        self.claimed_with(KEYWORD)

    def test_正文里有标记_拒绝且文案原样含它(self):
        r = self.refused_with(MARK)
        self.assertIn(MARK, r.text)

    def test_文案说明交给人类与重跑开工前校验(self):
        r = self.refused_with(MARK)
        self.assertIn("人类", r.text)
        self.assertTrue("开工前校验" in r.text or "verify-setup" in r.text,
                        "文案没提契约改了之后要重跑开工前校验:\n%r" % r)

    def test_bug_项同样被拒(self):
        r = self.refused_with(MARK, typ="bug")
        self.assertIn(MARK, r.text)

    def test_标记在子小节里_拒绝(self):
        self.lay([section(NAME, PROSE) + section("细节", MARK, level=3)], [item("W1", NAME)])
        r = self.claim()
        self.assertClaimRefused(r, MARK)

    def test_标记在标题行里_拒绝(self):
        title = "%s %s" % (NAME, MARK)
        self.lay([section(title, PROSE)], [item("W1", title)])
        r = self.claim()
        self.assertClaimRefused(r, MARK)

    def test_标记在_HTML_注释里_照样拒绝(self):
        r = self.refused_with("<!-- %s -->" % MARK)
        self.assertIn(MARK, r.text)

    def test_围栏之后正文里的标记_照样拒绝(self):
        self.refused_with(FENCE + "\n部件 = 规格\n" + FENCE, MARK)

    def test_去掉标记之后放行(self):
        self.lay([section(NAME, PROSE, MARK)], [item("W1", NAME)])
        self.assertClaimRefused(self.claim())
        self.lay([section(NAME, PROSE, "部件的单位是毫米。")], [item("W1", NAME)])
        self.assertClaimed(self.claim())


class TestSpellings(ClaimBase):
    """契约表里列的每一种写法各一条,都要认得出。"""

    def test_全角冒号(self):
        self.refused_with("[待澄清%s部件的单位是什么]" % FW_COLON)

    def test_没有冒号与问题(self):
        self.refused_with("[待澄清]")

    def test_英文大写(self):
        r = self.refused_with("[NEEDS CLARIFICATION: unit of the gadget]")
        self.assertIn("[NEEDS CLARIFICATION: unit of the gadget]", r.text)

    def test_英文大小写混写(self):
        self.refused_with("[Needs Clarification: unit of the gadget]")

    def test_英文两词之间换行(self):
        self.refused_with("[NEEDS\nCLARIFICATION: unit of the gadget]")

    def test_全角方括号(self):
        self.refused_with("%s待澄清: 部件的单位是什么%s" % (FW_LB, FW_RB))

    def test_黑括号(self):
        self.refused_with("%s待澄清: 部件的单位是什么%s" % (CJK_LB, CJK_RB))

    def test_没有右括号的不算标记(self):
        self.claimed_with("[待澄清: 部件的单位是什么")


class TestCodeExempt(ClaimBase):
    """围栏代码块与行内代码(N 个反引号开、恰好 N 个关)里的不算。"""

    def test_围栏代码块里的放行(self):
        self.claimed_with(FENCE + "\n" + MARK + "\n" + FENCE)

    def test_波浪线围栏里的放行(self):
        """反引号围栏的两行自己就能配成一对行内代码,只有波浪线围栏能看出围栏有没有单独抹掉。"""
        self.claimed_with("~~~\n" + MARK + "\n~~~")

    def test_单反引号行内代码里的放行(self):
        self.claimed_with("写法是 `%s`。" % MARK)

    def test_双反引号行内代码里的放行(self):
        self.claimed_with("写法是 `` `[待澄清]` ``。")

    def test_单反引号开_双反引号串不算关_标记在代码外_拒绝(self):
        self.refused_with("写法是 `%s``。" % MARK)

    def test_没关上的反引号之后的标记_拒绝(self):
        self.refused_with("这里有一个落单的反引号 ` 之后是 %s" % MARK)


class TestScope(ClaimBase):

    def test_标记只在未被引用的小节里_放行(self):
        self.lay([section(NAME, PROSE), section(OTHER, PROSE, MARK)], [item("W1", NAME)])
        self.assertClaimed(self.claim())

    def test_子小节之后的同级小节里的标记不算(self):
        self.lay([section(NAME, PROSE) + section("细节", PROSE, level=3), section(OTHER, PROSE, MARK)],
                 [item("W1", NAME)])
        self.assertClaimed(self.claim())

    def test_cover_项不拦(self):
        self.lay([section(NAME, PROSE, MARK)], [item("C1", NAME, "cover")])
        self.assertClaimed(self.claim("C1"), "C1")

    def test_refactor_项不拦(self):
        self.lay([section(NAME, PROSE, MARK)], [item("R1", NAME, "refactor")])
        self.assertClaimed(self.claim("R1"), "R1")


class TestListing(ClaimBase):
    """文案原样列出标记,最多 5 条,超出写"另有 N 处"。哪 5 条不断言。"""

    @staticmethod
    def marks(n):
        return ["[待澄清: 第%d个问题]" % i for i in range(1, n + 1)]

    def test_六处标记_列五处并写另有一处(self):
        marks = self.marks(6)
        r = self.refused_with(*marks)
        self.assertEqual(sum(m in r.text for m in marks), 5, "6 处里应恰好列出 5 处:\n%r" % r)
        self.assertRegex(r.text, r"另有\s*1\s*处")

    def test_五处标记_全列不写另有(self):
        marks = self.marks(5)
        r = self.refused_with(*marks)
        for m in marks:
            self.assertIn(m, r.text)
        self.assertNotIn("另有", r.text)


class TestVerifySetup(PairTestCase):
    """只提醒不判失败;同一节只报一次,点名工作项与标记条数。小节给齐形状,免得 W73 的形状警告也提到它。"""

    def lay(self, sections, items):
        self.repo.set_plan("# 项目规划\n\n## 工作项\n\n" + "".join(items),
                           "# 接口契约\n" + "".join(sections))
        names = sorted({m for m in re.findall(r"→ (.+)", "".join(items))})
        self.repo.write(REPORT, setup_report(*names))

    def verify(self):
        r = self.repo.run(*VERIFY_OK, role="dev")
        self.assertAccepted(r)
        self.assertTrue(self.repo.state()["setup_verified"])
        return r

    def about(self, r, name=NAME):
        """提到小节 `name` 的那几条 [警告] / [失败]。只看摘要之前那一段。"""
        out = "\n" + r.out.split("脚本能查的都通过了")[0]
        parts = re.split(r"\n  \[(?:警告|失败)\] ", out)
        return [t for t in parts[1:] if name in t]

    def three_marks(self):
        return section(NAME, KEYWORD, TABLE, "[待澄清: 甲]", "[待澄清: 乙]", "[NEEDS CLARIFICATION: c]")

    def test_有标记时放行并提醒_点名工作项与条数(self):
        self.lay([self.three_marks()], [item("W1", NAME)])
        hits = self.about(self.verify())
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("W1", hits[0])
        self.assertIn("3", hits[0], "提醒里没有标记条数")

    def test_两个工作项引用同一节_只提醒一次_点名两个(self):
        self.lay([self.three_marks()], [item("W1", NAME), item("W2", NAME)])
        hits = self.about(self.verify())
        self.assertEqual(len(hits), 1, "同一节报了 %d 次:\n%s" % (len(hits), hits))
        self.assertIn("W1", hits[0])
        self.assertIn("W2", hits[0])

    def test_bug_项引用的同样提醒(self):
        self.lay([self.three_marks()], [item("B1", NAME, "bug")])
        hits = self.about(self.verify())
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("B1", hits[0])

    def test_只被_cover_或_refactor_引用的不提醒(self):
        self.lay([self.three_marks()], [item("C1", NAME, "cover"), item("R1", NAME, "refactor")])
        self.assertEqual(self.about(self.verify()), [])

    def test_只被已完成项引用的不提醒(self):
        self.lay([self.three_marks(), section(OTHER, KEYWORD, TABLE)],
                 [item("W0", NAME, done=True), item("W1", OTHER)])
        self.assertEqual(self.about(self.verify()), [])

    def test_没有标记不提醒(self):
        self.lay([section(NAME, KEYWORD, TABLE)], [item("W1", NAME)])
        self.assertEqual(self.about(self.verify()), [])


class TestReviewImplBrief(PairTestCase):

    def test_review_impl_的简报有契约没要求那一条(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("契约没要求", r.out)


class TestSkeleton(PairTestCase):
    """`init` 生成的契约骨架:注释里有标记用法(写成行内代码),整份当契约用时不挡认领;「不做」口径统一。"""

    def skeleton(self):
        bare = BareRepo(PY_PROJECT)
        self.addCleanup(bare.cleanup)
        self.assertEqual(bare.run("init").code, 0)
        return bare.read("docs/CONTRACT.md")

    def test_骨架注释里有行内代码写的标记用法(self):
        self.assertIn("`[待澄清", self.skeleton())

    def test_骨架整份当契约_认领指向骨架小节的_feature_项放行(self):
        text = self.skeleton()
        self.assertIn("\n## <小节名>\n", text, "前提:骨架里有这一节")
        self.repo.set_plan("# 项目规划\n\n## 工作项\n\n" + item("W1", "<小节名>"), text)
        r = self.repo.run("claim", "W1", role="tester")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["item"], "W1")

    def test_骨架的不做口径统一(self):
        text = self.skeleton()
        self.assertIn("tester 不断言", text)
        self.assertIn("dev 不该实现", text)
        self.assertNotIn("dev 也不必实现", text)

    def test_契约模板的不做口径统一(self):
        text = (SKILL_SRC / "references" / "contract-templates.md").read_text(encoding="utf-8")
        self.assertIn("tester 不断言", text)
        self.assertIn("dev 不该实现", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
