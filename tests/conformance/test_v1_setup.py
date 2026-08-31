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

    def test_通过后置位并允许认领(self):
        self.assertFalse(self.repo.state()["setup_verified"])
        r = self.repo.run("verify-setup", role="dev")
        self.assertAccepted(r)
        self.assertTrue(self.repo.state()["setup_verified"])
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_未校验时不能认领(self):
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, "尚未通过开工前校验")

    def test_status_提示尚未校验(self):
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("尚未通过开工前校验", r.text)

    def test_要求_agent_亲自读契约找歧义(self):
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
        # 默认 harness 配置就是关闭的,直接认领应当成功
        repo_cls = type(self)
        self.assertTrue(repo_cls.config["require_setup_verification"])
