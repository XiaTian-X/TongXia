# -*- coding: utf-8 -*-
"""出厂物是不是真的能用。

样板项目和驱动器都是**用户第一眼碰到的东西**,而它们不在协议的一致性测试
覆盖面里 —— 于是每次给协议加一道门禁,它们都可能悄悄失效。

这已经真实发生过:加了"契约小节必须写 `依据`"之后,自带的样板项目
过不了自己的 `verify-setup`;加了 `__pycache__` 到 `GITIGNORE_LINES` 之后,
样板项目的 `.gitignore` 没跟上,跑一次测试就把 `.pyc` 写进对方的路径里。
"""

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "examples" / "demo-project"
SCRIPTS = REPO / ".agents" / "skills" / "pair-protocol" / "scripts"


def _pair():
    spec = importlib.util.spec_from_file_location("pair_shipped", SCRIPTS / "pair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAIR = _pair()

REPORT = ("# 契约审查结论\n\n逐条核对了两节的返回值、错误条件与边界情况,"
          "未发现歧义。空串与超长输入契约里都写明了,断言可以直接照写。" * 2)


class TestDemoProject(unittest.TestCase):
    """`python3 examples/make-demo.py` 出来的东西必须立刻能开工。"""

    def _make(self):
        d = Path(tempfile.mkdtemp(prefix="demo-"))
        self.addCleanup(shutil.rmtree, d, True)
        target = d / "proj"
        proc = subprocess.run(
            [sys.executable, str(REPO / "examples" / "make-demo.py"), str(target)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout.decode("utf-8", "replace"))
        return target

    def test_gitignore_跟得上_GITIGNORE_LINES(self):
        """漂了的话,跑一次测试生成的 .pyc 会落在对方的路径下,两个角色互相卡死。"""
        have = (DEMO / ".gitignore").read_text(encoding="utf-8")
        missing = [l for l in PAIR.GITIGNORE_LINES if l not in have]
        self.assertFalse(
            missing, "样板项目的 .gitignore 缺了这几行:%s" % missing)

    def test_开工前校验只卡在契约审查结论那一步(self):
        """出厂的样板项目必须能通过全部脚本检查。卡在别处 = 出厂物坏了。"""
        proj = self._make()
        (proj / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (proj / "docs" / "reviews" / "setup-verification.md").write_text(
            REPORT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, ".agents/skills/pair-protocol/scripts/pair.py",
             "verify-setup"],
            cwd=str(proj), env={"PAIR_ROLE": "dev", "PATH": "/usr/bin:/bin"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        self.assertNotIn("[失败]", out, out)
        self.assertIn("开工前校验全部通过", out, out)


class TestWhoseTurn(unittest.TestCase):
    """驱动器只认这一行输出,所以它的形状是接口,不是随手打印。"""

    def test_输出形态只有两种(self):
        src = (SCRIPTS / "pair.py").read_text(encoding="utf-8")
        body = src.split("def cmd_whose_turn")[1].split("\ndef ")[0]
        prints = re.findall(r'print\("(turn |stop )', body)
        self.assertTrue(prints, "whose-turn 什么都不输出")
        self.assertTrue(
            all(p in ("turn ", "stop ") for p in prints),
            "whose-turn 输出了 turn/stop 之外的东西:%s" % prints)

    def test_不跑测试(self):
        """它会被驱动器循环调用。跑一遍套件要几十秒,那会让自动驱动没法用。"""
        src = (SCRIPTS / "pair.py").read_text(encoding="utf-8")
        body = src.split("def cmd_whose_turn")[1].split("\ndef ")[0]
        self.assertNotIn("run_tests", body,
                         "whose-turn 里跑了测试 —— 它是被循环调用的查询")


class TestDriverHasNoProtocolLogic(unittest.TestCase):
    """和 CLI 那条约束同源:判定一旦在驱动器里复制一份,它就成了协议的
    第二个实现,而防漂移是这个项目从头到尾在做的事。"""

    FORBIDDEN = ("PHASE_OWNER", "DEADLOCK_LIMIT", "REVIEW_PHASES", "FLOWS",
                 "setup_verified", "plan_all_done", "item_type", "frozen_paths")

    def test_不出现任何协议判定关键词(self):
        src = (SCRIPTS / "drive.py").read_text(encoding="utf-8")
        hits = [w for w in self.FORBIDDEN if w in src]
        self.assertFalse(
            hits, "驱动器里出现了协议判定的东西:%s —— 它只该认 whose-turn 的输出" % hits)

    def test_不碰_git(self):
        """结对期间任何人提交东西都可能把某一方的产出从工作区搬走,
        而"打回之后必须真的动了测试"那条检查按工作区判断。"""
        src = (SCRIPTS / "drive.py").read_text(encoding="utf-8")
        calls = re.findall(r'"git"|\bgit (?:add|commit|checkout|reset|push)\b', src)
        allowed = ['"git"']          # rev-parse 定位仓库根是只读的
        bad = [c for c in calls if c not in allowed]
        self.assertFalse(bad, "驱动器动了 git:%s" % bad)
        self.assertNotIn("git add", src)
        self.assertNotIn("git commit", src)


if __name__ == "__main__":
    unittest.main()
