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

from harness import BareRepo
from test_v1_setup import PY_PROJECT
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

# 样板项目的契约有 slugify / truncate 两节,结论必须逐节点名并声明作者身份。
REPORT = ("# 契约审查结论\n\n我没有参与这份契约的起草。\n\n"
          "## slugify\n\n返回值精确到能写断言,空串与超长两种边界契约里都写明了,"
          "错误条件已穷举。未发现歧义。\n\n"
          "## truncate\n\n同上逐条核对过。n 为负数时的行为契约没写,"
          "tester 不得凭空假设,需要时走契约变更流程。\n")


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

    def _verify(self):
        """造一个样板仓库、交一份结论、跑 verify-setup,返回输出。"""
        proj = TestDemoProject._make(self)
        (proj / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (proj / "docs" / "reviews" / "setup-verification.md").write_text(
            REPORT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, ".agents/skills/pair-protocol/scripts/pair.py",
             "verify-setup", "--drafter", "other"],
            cwd=str(proj), env={"PAIR_ROLE": "dev", "PATH": "/usr/bin:/bin"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.stdout.decode("utf-8", "replace")

    def test_开工前校验只卡在契约审查结论那一步(self):
        """出厂的样板项目必须能通过全部脚本检查。卡在别处 = 出厂物坏了。"""
        proj = self._make()
        (proj / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (proj / "docs" / "reviews" / "setup-verification.md").write_text(
            REPORT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, ".agents/skills/pair-protocol/scripts/pair.py",
             "verify-setup", "--drafter", "other"],
            cwd=str(proj), env={"PAIR_ROLE": "dev", "PATH": "/usr/bin:/bin"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        self.assertNotIn("[失败]", out, out)
        self.assertIn("开工前校验全部通过", out, out)


class TestDemoPlanIsReady(unittest.TestCase):
    """W24:出厂样板项目要能不经人类定稿就开工。第七轮两个会话各自挑出样板 W4 缺保护测试 ——
    `claim` 会硬拦,新用户照 `INSTALL.md` 接入后的第一次开工就要人类介入。"""

    def test_样板_PLAN_里每个_refactor_项都声明了保护测试(self):
        plan = (DEMO / "docs" / "PLAN.md").read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^(?=- \[[ x]\] \*\*)", plan)
        refactors = [b for b in blocks if re.match(r"- \[[ x]\] \*\*\S+\*\* \[refactor\]", b)]
        self.assertTrue(refactors, "样板 PLAN 里没有 refactor 项 —— 这条用例什么都没检查")
        missing = [b.splitlines()[0] for b in refactors if not PAIR.PROTECT_REF_RE.search(b)]
        self.assertFalse(missing, "这些 refactor 项没声明保护测试:%s" % missing)

    def test_样板项目_verify_setup_不出现没声明保护测试的警告(self):
        """只看这一句会是单向的 —— 拆掉警告它照样绿。正面在
        `test_v1_brownfield` 的 `test_verify_setup_对没声明保护测试的_refactor_照旧警告`。"""
        out = TestDemoProject._verify(self)
        self.assertIn("开工前校验全部通过", out, out)
        self.assertNotIn("没声明保护它的测试", out, out)


class TestDemoStartsClean(unittest.TestCase):
    """W26:出厂样板项目开工前不该有警告。出厂物自带的警告会教新用户忽略警告 ——
    第九轮两个会话每一轮都把孤儿与激活段落那三条重复报上来。

    **这几条是"不出现",单向的。** 正面在 `test_v1_paths.test_开工前把孤儿列出来` 与
    `test_v1_setup.TestVerifySetup` 的激活段落两条(W26 的 spec 回合带声明补)。"""

    def setUp(self):
        self.out = TestDemoProject._verify(self)

    def test_前提_校验跑通了(self):
        self.assertIn("开工前校验全部通过", self.out, self.out)

    def test_没有孤儿那条(self):
        self.assertNotIn("孤儿", self.out, self.out)

    def test_AGENTS_md_不缺激活段落(self):
        self.assertNotIn("AGENTS.md 里没有协议激活段落", self.out, self.out)

    def test_CLAUDE_md_不缺激活段落(self):
        self.assertNotIn("CLAUDE.md 里没有协议激活段落", self.out, self.out)


class TestClaudeMdForbidsHandingOff(unittest.TestCase):
    """W28:`CLAUDE.md` 禁的是"转手",不是"谁在跑"。

    第十一轮 dev 的第一个回合停下来问人:`init` 写的那句"不要用 subagent 代跑结对回合……必须由主会话执行",
    而它自己就是被派出来的、dev 唯一的会话。**措辞本身不写成用例**(契约);能写成失败用例的有两样:
    一致性(样板与 `init` 逐字节相同),与**缺陷本身** —— 让会话误判的那两个说法不能再出现
    (W28 的 spec 回合带声明补:本项是 bug,spec 必须红,而一致性那条今天是绿的)。
    它们钉的是旧措辞里出错的那两处,不是新措辞怎么写。"""

    AMBIGUOUS = ("不要用 subagent", "主会话")

    def init_claude_md(self):
        repo = BareRepo(PY_PROJECT)
        self.addCleanup(repo.cleanup)
        self.assertEqual(repo.run("init").code, 0)
        return repo.read("CLAUDE.md")

    def test_init_写的_CLAUDE_md_不再按谁在跑来禁(self):
        text = self.init_claude_md()
        for phrase in self.AMBIGUOUS:
            self.assertNotIn(phrase, text)

    def test_本仓库的_CLAUDE_md_同一句跟着改(self):
        text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        for phrase in self.AMBIGUOUS:
            self.assertNotIn(phrase, text)

    def test_样板_CLAUDE_md_与_init_写出的逐字节一致(self):
        """W26 让它们一致了一次,没有东西守着;改 `CLAUDE_MD` 就是它漂开的第一个机会。"""
        d = Path(tempfile.mkdtemp(prefix="entry-"))
        self.addCleanup(shutil.rmtree, d, True)
        PAIR.merge_entry(d, "CLAUDE.md", PAIR.ENTRY_FILES["CLAUDE.md"])
        self.assertEqual((DEMO / "CLAUDE.md").read_text(encoding="utf-8"),
                         (d / "CLAUDE.md").read_text(encoding="utf-8"))


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


class TestDriverKeepsATrace(unittest.TestCase):
    """自动驱动如果不留痕,等于把每回合的观察窗口关掉 —— 而第一次真实运行里
    最值钱的两个发现,恰恰来自人在中间看了一眼。"""

    SRC = (SCRIPTS / "drive.py").read_text(encoding="utf-8")

    def test_边打边落盘而不是二选一(self):
        """只落盘不打印 = 为了留痕把你正在看的东西关掉;
        只打印不落盘 = 全自动跑完什么都不剩。"""
        self.assertIn("sys.stdout.buffer.write", self.SRC, "输出没有实时打给人看")
        self.assertIn("f.write(line)", self.SRC, "输出没有落盘")

    def test_日志目录进了_GITIGNORE_LINES(self):
        """它落在 .pair/ 下,而 .pair 是冻结路径。不忽略的话,第一份日志就会
        让下一次 handoff 判越界,而且 agent 删不干净 —— 下一回合又生成。"""
        self.assertIn(".pair/turns/", PAIR.GITIGNORE_LINES)

    def test_没被忽略时拒绝启动(self):
        """光加进 GITIGNORE_LINES 只管新项目。老项目里驱动器必须自己拦住。"""
        self.assertIn("check-ignore", self.SRC)
        self.assertIn("没有被 git 忽略", self.SRC)


class TestDriverHasNoProtocolLogic(unittest.TestCase):
    """和 CLI 那条约束同源:判定一旦在驱动器里复制一份,它就成了协议的
    第二个实现,而两份判定迟早不一致 —— 门禁看着还在、实际拦不住。"""

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
