# -*- coding: utf-8 -*-
"""W40:一致性测试起跑前自检运行环境。

契约「一致性测试起跑前自检运行环境」。harness 用 PATH 上的 `python3` 起 `pair.py`,`init` 的用例还要它跑 pytest 基线。
3.12 那次 17 条 `init` 用例全红、只报 `1 != 0`(那个解释器没有 pytest);3.9 那次全绿,`pair.py` 其实是被 PATH 上的 3.14 起的。

**分工**(W40 的 spec 回合带声明补):自检写在 `run.py` 里,那是 tester 的路径 —— 由 tester 在 spec 回合写好,
这几条自检用例 spec 回合结束时就是绿的;红的只有 `contributing.md` 那一条,由 dev 在 impl 回合写。

跑 `run.py` 的用例只选一个小模块(`test_mutation_tooling`)—— 自检若没拦住,也只多跑几秒,不会在用例里递归跑全套。
"""

import os
import re
import stat
import subprocess
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

import run as runner

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SMALL = "test_mutation_tooling"


class FakePython(unittest.TestCase):

    def fake(self, body):
        """PATH 最前面放一个叫 python3 的脚本,返回改过的环境。"""
        d = Path(tempfile.mkdtemp(prefix="fakepy-"))
        self.addCleanup(shutil.rmtree, d, True)
        exe = d / "python3"
        exe.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=str(d) + os.pathsep + os.environ.get("PATH", ""))
        return env

    def run_runner(self, env, *args):
        proc = subprocess.run([sys.executable, str(HERE / "run.py")] + list(args),
                              cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")


class TestVersionMismatch(FakePython):

    def test_PATH_上的_python3_版本不同时不跑_点名两个版本(self):
        env = self.fake('echo 2.7')
        rc, out = self.run_runner(env, SMALL)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("2.7", out)
        self.assertIn("%d.%d" % sys.version_info[:2], out)
        self.assertNotIn("个测试 /", out, "不该跑用例:\n" + out)


    def test_同主版本不同次版本也不跑(self):
        """立项起因正是这一种:3.9 / 3.12 对 3.14。上一条差的是主版本,只比主版本的实现照绿 ——
        dev 在 W40 的 review-test 实测过。次版本按本机现算,换机器也成立。"""
        other = "%d.%d" % (sys.version_info[0], sys.version_info[1] + 1)
        env = self.fake('echo %s' % other)
        rc, out = self.run_runner(env, SMALL)
        self.assertNotEqual(rc, 0, out)
        self.assertIn(other, out)
        self.assertIn("%d.%d" % sys.version_info[:2], out)
        self.assertNotIn("个测试 /", out, "不该跑用例:\n" + out)

    def test_PATH_上没有_python3_时不跑(self):
        """run.py 自己用 sys.executable 的绝对路径起,PATH 空了不影响它;找不到那一支换成"没问题"的实现在这里照绿过。"""
        d = tempfile.mkdtemp(prefix="emptypath-")
        self.addCleanup(shutil.rmtree, d, True)
        env = dict(os.environ, PATH=d)
        rc, out = self.run_runner(env, SMALL)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("找不到", out)
        self.assertNotIn("个测试 /", out, "不该跑用例:\n" + out)


class TestNoPytest(FakePython):

    def test_同版本但_import_不了_pytest_时不跑_点名_pytest(self):
        """同一个解释器以 -S 起:版本相同,site-packages 不在 —— import 不了 pytest。"""
        env = self.fake('exec "%s" -S "$@"' % sys.executable)
        rc, out = self.run_runner(env, SMALL)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("pytest", out)
        self.assertNotIn("个测试 /", out, "不该跑用例:\n" + out)


class TestListSkipsCheck(FakePython):

    def test_list_不自检(self):
        env = self.fake('echo 2.7')
        rc, out = self.run_runner(env, "--list", SMALL)
        self.assertEqual(rc, 0, out)
        self.assertIn(SMALL, out)


class TestNormalEnvironment(unittest.TestCase):

    def test_正常环境下自检通过(self):
        """本地门禁与 CI 都满足:PATH 上的 python3 就是跑这套用例的解释器、装着 pytest。"""
        self.assertEqual(runner.check_env(), [])


class TestContributingNamesPrerequisites(unittest.TestCase):

    def test_贡献指南在两条必跑的命令处写明两项前提(self):
        text = (REPO / "docs" / "contributing.md").read_text(encoding="utf-8")
        section = text.split("## 两条必跑的命令", 1)[1].split("\n## ", 1)[0]
        self.assertIn("pytest", section)
        self.assertRegex(section, r"PATH 上的 `?python3`?")
