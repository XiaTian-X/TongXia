# -*- coding: utf-8 -*-
"""W29:出厂样板只发被跟踪的文件。

契约「出厂样板只发被跟踪的文件」。第十三轮 tester 报告了一个空的、没纳入 git 的 `tests/conformance/` ——
`examples/demo-project/` 下的空目录,git 不跟踪所以没人发现,`make-demo.py` 整目录复制把它带进了每一个新项目。

**判据要能区分两种修法**:只删掉那个空目录,今天那一条会绿;契约要的是"今后出现的未跟踪文件也不带出去"。
所以大部分用例不碰本仓库真实的 `examples/demo-project/`(往里写会污染工作区、并发跑时互相看见),而是把
`examples/` 与技能目录里**被跟踪的**文件复制进一个临时 git 仓库、提交,再往样板里放未跟踪文件与空目录,
跑**那一份** `make-demo.py` —— 它按自己的位置找仓库根。

**不在 git 检出里**(zip 下载)时退回整目录复制、跳过空目录:W29 的 spec 回合带声明补。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GIT_ID = ("-c", "user.name=conformance", "-c", "user.email=conformance@test")


def tracked(prefix):
    out = subprocess.run(["git", "ls-files", "-z", "--", prefix], cwd=REPO,
                         stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def empty_dirs(root):
    found = []
    for d, subdirs, files in os.walk(root):
        if ".git" in Path(d).relative_to(root).parts[:1]:
            continue
        if not subdirs and not files and Path(d) != root:
            found.append(str(Path(d).relative_to(root)))
    return found


def all_paths(root):
    return {str(p.relative_to(root)) for p in Path(root).rglob("*")
            if ".git" not in p.relative_to(root).parts[:1]}


class MiniTongXia(unittest.TestCase):
    """一份只有样板、技能目录与 make-demo.py 的临时"本仓库"。"""

    def source(self, git=True):
        src = Path(tempfile.mkdtemp(prefix="tongxia-"))
        self.addCleanup(shutil.rmtree, src, True)
        for rel in tracked("examples") + tracked(".agents/skills/pair-protocol"):
            dst = src / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if (REPO / rel).is_symlink():
                os.symlink(os.readlink(REPO / rel), dst)
            else:
                shutil.copy2(REPO / rel, dst)
        if git:
            for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "样板")):
                subprocess.run(("git",) + GIT_ID + args, cwd=src, check=True,
                               stdout=subprocess.DEVNULL)
        return src

    def plant(self, src):
        """样板目录里放一个未跟踪文件与一个空目录 —— 今后任何人都可能留下的那种东西。"""
        demo = src / "examples" / "demo-project"
        (demo / "stray-notes.txt").write_text("没有纳入 git 的草稿\n", encoding="utf-8")
        (demo / "tests" / "leftover").mkdir(parents=True)

    def make(self, src):
        target = Path(tempfile.mkdtemp(prefix="demo-")) / "proj"
        self.addCleanup(shutil.rmtree, target.parent, True)
        proc = subprocess.run([sys.executable, str(src / "examples" / "make-demo.py"), str(target)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode("utf-8", "replace"))
        return target


class TestOnlyTrackedFilesShip(MiniTongXia):

    def test_未跟踪文件不带出去(self):
        src = self.source()
        self.plant(src)
        target = self.make(src)
        self.assertFalse((target / "stray-notes.txt").exists())

    def test_空目录不带出去(self):
        src = self.source()
        self.plant(src)
        target = self.make(src)
        self.assertFalse((target / "tests" / "leftover").exists())

    def test_对照组_被跟踪的样板文件一个不少(self):
        """"什么都不复制"也能让上面两条绿。"""
        src = self.source()
        self.plant(src)
        target = self.make(src)
        shipped = all_paths(target)
        for rel in tracked("examples/demo-project"):
            self.assertIn(rel[len("examples/demo-project/"):], shipped)
        self.assertTrue((target / ".agents" / "skills" / "pair-protocol" / "SKILL.md").exists())
        self.assertTrue((target / ".claude" / "skills" / "pair-protocol").is_symlink())


class TestRealDemoHasNoEmptyDirs(unittest.TestCase):

    def test_本仓库样板生成的项目里没有空目录(self):
        """第十三轮的原样:`tests/conformance/`。"""
        target = Path(tempfile.mkdtemp(prefix="demo-")) / "proj"
        self.addCleanup(shutil.rmtree, target.parent, True)
        proc = subprocess.run([sys.executable, str(REPO / "examples" / "make-demo.py"), str(target)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode("utf-8", "replace"))
        self.assertEqual(empty_dirs(target), [])


class TestNotAGitCheckout(MiniTongXia):
    """zip 下载没有 `.git`:问不了 git 哪些被跟踪,退回整目录复制、跳过空目录(spec 回合带声明补)。"""

    def test_不在_git_检出里照样能生成(self):
        target = self.make(self.source(git=False))
        self.assertTrue((target / "docs" / "PLAN.md").exists())
        self.assertTrue((target / ".agents" / "skills" / "pair-protocol" / "SKILL.md").exists())

    def test_不在_git_检出里也跳过空目录(self):
        src = self.source(git=False)
        self.plant(src)
        target = self.make(src)
        self.assertEqual(empty_dirs(target), [])


if __name__ == "__main__":
    unittest.main()
