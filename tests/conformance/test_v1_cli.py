# -*- coding: utf-8 -*-
"""bootstrap CLI。

CLI 存在的唯一理由是解决 init 的鸡生蛋:安装器在被安装物里,永远没法安装
自己。所以这里最重要的一条断言是 —— 目标项目**事先没有任何协议文件**。

同时守住 CLI 的硬约束:它不含协议逻辑,只搬运 + 交接。
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from harness import REPO, BareRepo

CLI_DIR = REPO / "cli"

SMOKE = ("import unittest\n\n"
         "class T(unittest.TestCase):\n"
         "    def test_ok(self):\n        self.assertTrue(True)\n")

PY_PROJECT = {
    "pyproject.toml": "[project]\nname = \"demo\"\n",
    "src/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_smoke.py": SMOKE,
}


def run_cli(target, *args):
    env = dict(os.environ)
    env.pop("PAIR_TEST_CMD", None)
    env["PYTHONPATH"] = str(CLI_DIR)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import pair_bootstrap,sys; sys.exit(pair_bootstrap.main(%r))" % list(args)],
        cwd=str(target), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")


class TestBootstrap(unittest.TestCase):

    def _bare(self, files, install_skill=False):
        r = BareRepo(files, install_skill=install_skill)
        self.addCleanup(r.cleanup)
        return r

    def test_从零装进没有任何协议文件的仓库(self):
        repo = self._bare(PY_PROJECT)
        self.assertFalse(repo.exists(".agents"), "前提:目标事先没有协议")

        code, out = run_cli(repo.dir, "init", ".")
        self.assertEqual(code, 0, out)
        self.assertTrue(repo.exists(".agents/skills/pair-protocol/SKILL.md"))
        self.assertTrue(repo.exists(".agents/skills/pair-protocol/scripts/pair.py"))
        self.assertTrue(repo.exists(".pair/config.json"))
        self.assertTrue(repo.exists("AGENTS.md"))

    def test_建立_Claude_Code_需要的软链接(self):
        repo = self._bare(PY_PROJECT)
        run_cli(repo.dir, "init", ".")
        link = repo.dir / ".claude" / "skills" / "pair-protocol"
        self.assertTrue(link.exists(), "Claude Code 读 .claude/skills/")
        self.assertTrue((link / "SKILL.md").exists(), "软链接应能解析到真源")

    def test_把后续交给_pair_py_而不是自己实现(self):
        """CLI 的输出里必须出现 pair.py init 的痕迹 —— 它是交接壳子,不是实现。"""
        repo = self._bare(PY_PROJECT)
        code, out = run_cli(repo.dir, "init", ".")
        self.assertIn("交给 pair.py init", out)
        self.assertIn("结对协议初始化", out, "pair.py init 应当真的被执行了")

    def test_基线不绿时整体失败(self):
        files = dict(PY_PROJECT)
        files["tests/test_bad.py"] = (
            "import unittest\n\nclass B(unittest.TestCase):\n"
            "    def test_bad(self):\n        self.assertTrue(False)\n")
        repo = self._bare(files)
        code, out = run_cli(repo.dir, "init", ".")
        self.assertNotEqual(code, 0, out)
        self.assertIn("基线不是全绿", out)

    def test_非_git_目录被拒绝(self):
        import shutil
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="pair-nogit-"))
        self.addCleanup(shutil.rmtree, d, True)
        code, out = run_cli(d, "init", ".")
        self.assertNotEqual(code, 0)
        self.assertIn("不是 git 仓库", out)

    def test_可重复运行(self):
        repo = self._bare(PY_PROJECT)
        self.assertEqual(run_cli(repo.dir, "init", ".")[0], 0)
        code, out = run_cli(repo.dir, "init", ".")
        self.assertEqual(code, 0, out)
        self.assertIn("已存在,跳过", out)


class TestCliHasNoProtocolLogic(unittest.TestCase):
    """硬约束:CLI 里一旦出现协议逻辑,它就会和 skill 漂移。"""

    def test_不出现任何协议判定关键词(self):
        src = (CLI_DIR / "pair_bootstrap" / "__init__.py").read_text(encoding="utf-8")
        for banned in ("PHASE_OWNER", "TRANSITIONS", "FLOWS", "handoff",
                       "changes_count", "DEADLOCK", "review-impl"):
            self.assertNotIn(
                banned, src,
                "CLI 里出现了协议逻辑关键词 %r —— 它只应该搬运和交接" % banned)

    def test_协议真源只有一份(self):
        """CLI 不得夹带自己的 SKILL.md 或 pair.py 副本。"""
        stray = [p for p in (CLI_DIR).rglob("*")
                 if p.is_file() and p.name in ("SKILL.md", "pair.py")]
        self.assertEqual(stray, [], "CLI 目录里出现了协议文件副本:%s" % stray)


class TestPackagedLayout(unittest.TestCase):
    """装成 wheel 之后,协议目录被 force-include 到 pair_bootstrap/skill/。

    这里模拟那个布局,验证 find_bundled_skill 能优先找到包内副本。
    （真正的 wheel 构建需要 hatchling,不在本机验证范围内。）
    """

    def test_优先使用包内的协议副本(self):
        import shutil
        import tempfile

        stage = Path(tempfile.mkdtemp(prefix="pair-wheel-")).resolve()
        self.addCleanup(shutil.rmtree, stage, True)

        pkg = stage / "pair_bootstrap"
        shutil.copytree(CLI_DIR / "pair_bootstrap", pkg)
        shutil.copytree(REPO / ".agents" / "skills" / "pair-protocol", pkg / "skill")

        proc = subprocess.run(
            [sys.executable, "-c",
             "import pair_bootstrap as b; print(b.find_bundled_skill())"],
            cwd=str(stage), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        found = proc.stdout.decode("utf-8").strip()
        self.assertEqual(proc.returncode, 0, found)
        self.assertEqual(found, str(pkg / "skill"),
                         "打包后应当用包内副本,而不是回溯到源码仓库")
