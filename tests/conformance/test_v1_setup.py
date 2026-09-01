# -*- coding: utf-8 -*-
"""init 与 verify-setup:接入流程。

init 由任意 agent 或人类在结对开始**之前**跑;verify-setup 由结对的另一方
在开工前跑,只读。这一步存在的理由是防契约漂移 —— 唯一会致命的失败模式。
"""

import unittest

from harness import BareRepo, PairTestCase, Result

GREEN_TEST = ("import unittest\n\n"
              "class T(unittest.TestCase):\n"
              "    def test_ok(self):\n        self.assertTrue(True)\n")

RED_TEST = ("import unittest\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_broken(self):\n        self.assertTrue(False)\n")

PY_PROJECT = {
    "pyproject.toml": "[project]\nname = \"demo\"\n",
    "src/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_ok.py": GREEN_TEST,
}


class TestInit(unittest.TestCase):

    def _repo(self, files, **kw):
        r = BareRepo(files, **kw)
        self.addCleanup(r.cleanup)
        return r

    def test_探测技术栈与布局(self):
        repo = self._repo(PY_PROJECT)
        r = repo.run("init")
        self.assertEqual(r.code, 0, r)
        self.assertIn("pytest", r.text)
        self.assertIn("tests", r.text)
        self.assertTrue(repo.exists(".pair/config.json"))
        self.assertTrue(repo.exists(".pair/state.json"))

    def test_已有入口文件被合并而不是跳过(self):
        """现有项目本来就有 CLAUDE.md。曾经这里是"存在即跳过" ——
        于是接入"成功"了,agent 却从不知道自己在结对项目里。"""
        files = dict(PY_PROJECT)
        files["CLAUDE.md"] = "# 我自己的项目说明\n\n请遵守本仓库的既有约定。\n"
        repo = self._repo(files)
        r = repo.run("init")
        self.assertEqual(r.code, 0, r)
        text = repo.read("CLAUDE.md")
        self.assertIn("我自己的项目说明", text, "原内容必须原样保留")
        self.assertIn("<!-- pair-protocol:begin -->", text)
        self.assertLess(text.index("<!-- pair-protocol:begin -->"),
                        text.index("我自己的项目说明"),
                        "激活段落要在开头 —— 埋在三百行末尾的指令等于没有")

    def test_重跑_init_不重复插入(self):
        files = dict(PY_PROJECT)
        files["CLAUDE.md"] = "# 我自己的项目说明\n"
        repo = self._repo(files)
        repo.run("init")
        first = repo.read("CLAUDE.md")
        repo.run("init")
        self.assertEqual(repo.read("CLAUDE.md"), first)
        self.assertEqual(first.count("<!-- pair-protocol:begin -->"), 1)

    def test_人类把标记块挪走后仍能就地更新(self):
        files = dict(PY_PROJECT)
        files["CLAUDE.md"] = "# 我自己的项目说明\n"
        repo = self._repo(files)
        repo.run("init")
        text = repo.read("CLAUDE.md")
        i = text.index("<!-- pair-protocol:begin -->")
        j = text.index("<!-- pair-protocol:end -->") + len("<!-- pair-protocol:end -->")
        moved = text[:i] + text[j:] + "\n" + text[i:j] + "\n"
        (repo.dir / "CLAUDE.md").write_text(moved, encoding="utf-8")
        repo.run("init")
        after = repo.read("CLAUDE.md")
        self.assertEqual(after.count("<!-- pair-protocol:begin -->"), 1,
                         "挪走之后重跑不该再插一份")

    def test_忽略_Python_字节码(self):
        """协议自己每回合都跑测试。生成的 .pyc 落在**对方**的路径下,
        不忽略就会让两个角色互相把对方卡在越界上 —— 与目标项目的语言无关。"""
        repo = self._repo(PY_PROJECT)
        repo.run("init")
        gi = repo.read(".gitignore")
        self.assertIn("__pycache__/", gi)
        self.assertIn("*.pyc", gi)

    def test_铺设各家入口文件(self):
        repo = self._repo(PY_PROJECT)
        repo.run("init")
        for f in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".clinerules",
                  ".cursor/rules/pair.mdc", ".github/copilot-instructions.md"):
            self.assertTrue(repo.exists(f), "缺少入口文件 %s" % f)

    def test_基线不绿时拒绝接入(self):
        files = dict(PY_PROJECT)
        files["tests/test_broken.py"] = RED_TEST
        repo = self._repo(files)
        r = repo.run("init")
        self.assertNotEqual(r.code, 0, r)
        self.assertIn("基线不是全绿", r.text)

    def test_基线不绿时不留下任何残骸(self):
        files = dict(PY_PROJECT)
        files["tests/test_broken.py"] = RED_TEST
        repo = self._repo(files)
        repo.run("init")
        self.assertFalse(repo.exists(".pair/config.json"),
                         "失败的 init 不应该写下配置")
        self.assertFalse(repo.exists("AGENTS.md"))

    def test_幂等_不覆盖已有文件(self):
        repo = self._repo(PY_PROJECT)
        repo.run("init")
        plan = repo.read("docs/PLAN.md")
        (repo.dir / "docs" / "PLAN.md").write_text("# 我自己写的规划\n",
                                                   encoding="utf-8")
        r = repo.run("init")
        self.assertEqual(r.code, 0, r)
        self.assertIn("已存在,跳过", r.text)
        self.assertEqual(repo.read("docs/PLAN.md"), "# 我自己写的规划\n")
        self.assertNotEqual(plan, "# 我自己写的规划\n")

    def test_探测不到测试命令时拒绝并说明(self):
        repo = self._repo({"README.md": "# 没有任何构建文件\n"})
        r = repo.run("init")
        self.assertNotEqual(r.code, 0, r)
        self.assertIn("探测不到测试命令", r.text)

    def test_Go_布局用负模式避免重叠(self):
        repo = self._repo({
            "go.mod": "module demo\n",
            "slug.go": "package demo\n",
            "slug_test.go": "package demo\n",
        })
        r = repo.run("init")
        # go 未必装了,基线可能失败;这里只关心探测结果被打印出来
        self.assertIn("_test.go", r.text)
        self.assertIn("!", r.text, "dev 的模式应当包含负模式排除测试文件")


class TestVerifySetup(PairTestCase):

    config = {"require_setup_verification": True}

    REPORT = '# 契约审查\\n\\n逐条核对了 slugify 与 truncate 的返回值、错误条件和边界情况,未发现歧义。W1 的空串行为在契约里写明抛 ValueError,断言可以直接照写。逐条核对了 slugify 与 truncate 的返回值、错误条件和边界情况,未发现歧义。W1 的空串行为在契约里写明抛 ValueError,断言可以直接照写。'

    def test_没交契约审查结论时不放行(self):
        """脚本查不了歧义,但可以强制\"你必须交出一份结论\" ——
        否则这道最关键的门禁会退化成一句可以无视的建议。"""
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "尚未交出契约审查结论")
        self.assertFalse(self.repo.state()["setup_verified"])

    def test_敷衍的结论不算数(self):
        self.repo.write("docs/reviews/setup-verification.md", "看过了没问题\n")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "过短")

    def test_交了结论后通过并允许认领(self):
        self.assertFalse(self.repo.state()["setup_verified"])
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        r = self.repo.run("verify-setup", role="dev")
        self.assertAccepted(r)
        self.assertTrue(self.repo.state()["setup_verified"])
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_不把工作区里的代码一并提交进基线(self):
        """曾经这里是 git add -A。开工前就存在的实现会让 spec 的 RED 要求失效
        —— 测试一上来就是绿的,协议再也抓不到"没写新用例"。"""
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        self.repo.write("src/偷跑的实现", "本该由 dev 在 impl 回合写")
        r = self.repo.run("verify-setup", role="dev")
        self.assertAccepted(r)
        self.assertIn("未提交的代码改动", r.text)
        self.assertIn("偷跑的实现", r.text)
        tracked = self.repo.git("ls-files").stdout.decode("utf-8")
        self.assertNotIn("偷跑的实现", tracked,
                         "verify-setup 不该把角色路径下的改动提交进基线")

    def test_契约审查结论本身会被提交(self):
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        self.assertAccepted(self.repo.run("verify-setup", role="dev"))
        tracked = self.repo.git("ls-files").stdout.decode("utf-8")
        self.assertIn("setup-verification.md", tracked)

    def test_未校验时不能认领(self):
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "尚未通过开工前校验")

    def test_status_提示尚未校验(self):
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("尚未通过开工前校验", r.text)

    def test_未交结论时给出明确指引(self):
        r = self.repo.run("verify-setup", role="dev")
        self.assertIn("歧义", r.text)
        self.assertIn("setup-verification.md", r.text)

    def test_角色边界重叠被报出(self):
        self.repo.write(".pair/config.json", self.repo.read(".pair/config.json")
                        .replace('"dev": [\n      "src"\n    ]',
                                 '"dev": [\n      "src",\n      "tests"\n    ]'))
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类改了配置")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "同时属于两个角色")

    def test_工作项没指向契约被报出(self):
        self.repo.set_plan("# 规划\n\n- [ ] **W9** [feature] — 没有契约引用\n")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "没有指向契约")

    def test_契约小节不存在被报出(self):
        self.repo.set_plan(
            "# 规划\n\n- [ ] **W9** [feature] — 指向不存在的小节\n"
            "  - 对应契约:`docs/CONTRACT.md` → 不存在的小节\n")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "不存在的小节")

    def test_基线不绿时校验失败(self):
        """verify-setup 必须独立守住基线,不能只依赖 init 那一次检查 ——
        init 之后仓库还会继续变,红的基线会让 impl 阶段的 GREEN 要求失效。"""
        self.repo.write("tests/orphan", "没有对应实现的测试")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类提交了一条红的测试")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "基线不是全绿")

    def test_PLAN_为空被报出(self):
        self.repo.set_plan("# 规划\n\n还没写工作项。\n")
        r = self.repo.run("verify-setup", role="dev")
        self.assertRefused(r, "没有合法工作项")

    def test_可以配置关闭门禁(self):
        from harness import PairRepo
        repo = PairRepo({"require_setup_verification": False})
        self.addCleanup(repo.cleanup)
        self.assertFalse(repo.state()["setup_verified"])
        r = repo.run("claim", "W1", role="tester")
        self.assertEqual(r.code, 0, "门禁关闭时应当能直接认领。\n%r" % r)
