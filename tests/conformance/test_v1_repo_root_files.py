# -*- coding: utf-8 -*-
"""W64:`pyproject.toml` 与仓库根 `.gitignore` 的内容校验。

契约「仓库根两个文件的内容校验」(cover)。两个文件第三轮划归 dev 之后内容零覆盖:
- `force-include` 那一行决定协议目录进不进 wheel —— `pair init` 分发的就是它;
- 根 `.gitignore` 少了 `__pycache__/`,跑一次测试 `.pyc` 就会进 git、落到对方路径下。

**不用 `tomllib`**:3.11 起才有,CI 矩阵有 3.9。按节标题切出那一节、逐行认 `"键" = "值"`。
**`.gitignore` 按整行比**:`test_v1_shipped` 查样板那条用的是子串(`l not in have`),`.pair/whoami` 会被一行 `.pair/whoami-old` 满足。
"""

import importlib.util
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_REL = ".agents/skills/pair-protocol"
FORCE_INCLUDE = "tool.hatch.build.targets.wheel.force-include"


def _load_pair():
    spec = importlib.util.spec_from_file_location(
        "pair_for_root_files", REPO / SKILL_REL / "scripts" / "pair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAIR = _load_pair()


def toml_section(text, name):
    """`[name]` 那一节的正文(到下一个 `[` 开头的节标题为止);没有这一节返回 None。"""
    m = re.search(r"(?m)^\[%s\][ \t]*(?:#.*)?$" % re.escape(name), text)
    if m is None:
        return None
    rest = text[m.end():]
    nxt = re.search(r"(?m)^\[", rest)
    return rest[:nxt.start()] if nxt else rest


def force_include_map(text):
    """`force-include` 节里的 `"源" = "目标"` 映射;注释行与空行忽略。"""
    body = toml_section(text, FORCE_INCLUDE)
    if body is None:
        return None
    out = {}
    for line in body.splitlines():
        m = re.match(r'\s*"([^"]+)"\s*=\s*"([^"]+)"\s*(?:#.*)?$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def gitignore_missing(text, required):
    """`required` 里没有作为**整行**出现在 `text` 里的那些(行首行尾空白不计)。"""
    have = {l.strip() for l in text.splitlines()}
    return [l for l in required if l not in have]


class TestPyprojectShipsSkill(unittest.TestCase):

    def test_wheel_的_force_include_把协议目录打进包(self):
        mapping = force_include_map((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIsNotNone(mapping, "pyproject.toml 里没有 [%s] 这一节" % FORCE_INCLUDE)
        self.assertIn(SKILL_REL, mapping, "协议目录没有被 force-include 进 wheel:%s" % mapping)
        self.assertTrue(mapping[SKILL_REL].strip(), "映射的目标是空的")

    def test_被打进包的目录真实存在(self):
        """映射的源路径改错了(比如少了一层),上一条照样能找到键名 —— 这一条看它指向的东西在不在。"""
        mapping = force_include_map((REPO / "pyproject.toml").read_text(encoding="utf-8")) or {}
        for src in mapping:
            self.assertTrue((REPO / src / "SKILL.md").exists(), "%s 下没有 SKILL.md" % src)


class TestRootGitignore(unittest.TestCase):

    def test_GITIGNORE_LINES_每一行都在仓库根的_gitignore_里(self):
        missing = gitignore_missing((REPO / ".gitignore").read_text(encoding="utf-8"), PAIR.GITIGNORE_LINES)
        self.assertEqual(missing, [], "仓库根的 .gitignore 缺了这几行(init 给新项目写的,本仓库自己要跟上):%s" % missing)


class TestReading(unittest.TestCase):
    """读法的几格,各用造出来的文字钉住。"""

    def test_节在中间_后面还有别的节(self):
        text = '[a]\nx = 1\n[%s]\n".agents/skills/pair-protocol" = "pkg/skill"\n[b]\n"y" = "z"\n' % FORCE_INCLUDE
        self.assertEqual(force_include_map(text), {".agents/skills/pair-protocol": "pkg/skill"})

    def test_注释掉的映射不算(self):
        text = '[%s]\n# ".agents/skills/pair-protocol" = "pkg/skill"\n' % FORCE_INCLUDE
        self.assertEqual(force_include_map(text), {})

    def test_没有这一节(self):
        self.assertIsNone(force_include_map('[tool.hatch.build.targets.wheel]\npackages = ["x"]\n'))

    def test_gitignore_按整行比_子串不算(self):
        self.assertEqual(gitignore_missing(".pair/whoami-old\n*.pyc\n", [".pair/whoami", "*.pyc"]), [".pair/whoami"])

    def test_gitignore_行首行尾空白不计(self):
        self.assertEqual(gitignore_missing("  __pycache__/  \n", ["__pycache__/"]), [])


if __name__ == "__main__":
    unittest.main()
