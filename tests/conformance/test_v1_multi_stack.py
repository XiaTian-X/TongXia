# -*- coding: utf-8 -*-
"""W42:探测到多个技术栈时 init 拒绝自动配置。

契约「探测到多个技术栈时 init 拒绝自动配置」。`_detect_stack` 第一个命中就返回:同时有 `package.json` 与 `pyproject.toml`
的仓库只配上 `npm test`,基线绿、每回合绿,Python 那半从头到尾没有门禁,而且没有任何提示。

拒绝发生在跑基线之前 —— 这里的用例不需要机器上有 npm。
"""

import json
import unittest

from harness import BareRepo
from test_v1_setup import PY_PROJECT

PACKAGE_JSON = '{"name": "demo", "scripts": {"test": "echo ok"}}\n'


class MultiBase(unittest.TestCase):

    def repo(self, extra):
        files = dict(PY_PROJECT)
        files.update(extra)
        r = BareRepo(files)
        self.addCleanup(r.cleanup)
        return r


class TestRefusesOnTwoStacks(MultiBase):

    def test_两种测试命令时拒绝_点名文件与命令(self):
        repo = self.repo({"package.json": PACKAGE_JSON})
        r = repo.run("init")
        self.assertNotEqual(r.code, 0, r)
        for s in ("package.json", "pyproject.toml", "npm test", "python3 -m pytest"):
            self.assertIn(s, r.text)
        self.assertIn(".pair/config.json", r.text, "要给出手工写 config 的出路")

    def test_拒绝时不写任何文件(self):
        repo = self.repo({"package.json": PACKAGE_JSON})
        repo.run("init")
        self.assertFalse(repo.exists(".pair"))
        self.assertFalse(repo.exists("AGENTS.md"))
        self.assertFalse(repo.exists(".gitignore"))


class TestStillConfigures(MultiBase):

    def test_同一条命令的两个探测文件算一个栈(self):
        """`pyproject.toml` 与 `setup.py` 都是 `python3 -m pytest`。"""
        repo = self.repo({"setup.py": "from setuptools import setup\nsetup(name='demo')\n"})
        r = repo.run("init")
        self.assertEqual(r.code, 0, r)
        self.assertIn("python3 -m pytest", r.text)
        self.assertTrue(repo.exists(".pair/config.json"))

    def test_已有_config_的_test_cmd_时照旧用它(self):
        """人类已经做过选择 —— 不因为仓库里有多个栈而拒绝。"""
        repo = self.repo({"package.json": PACKAGE_JSON,
                          ".pair/config.json": json.dumps({"test_cmd": "python3 -m pytest -q"}) + "\n"})
        r = repo.run("init")
        self.assertEqual(r.code, 0, r)
        self.assertIn("python3 -m pytest -q", r.text)
        self.assertIn("已有 config", r.text)

    def test_只有一个栈时行为不变(self):
        r = self.repo({}).run("init")
        self.assertEqual(r.code, 0, r)
        self.assertIn("python3 -m pytest", r.text)
