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
import shutil
import subprocess
import sys
import tempfile
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


def wheel_packages(text):
    """`[tool.hatch.build.targets.wheel]` 的 `packages = [...]` 里的路径。"""
    body = toml_section(text, "tool.hatch.build.targets.wheel") or ""
    m = re.search(r"(?m)^\s*packages\s*=\s*\[([^\]]*)\]", body)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def script_module(text):
    """`[project.scripts]` 第一条入口的模块名(`pair = "pair_bootstrap:main"` → `pair_bootstrap`)。"""
    body = toml_section(text, "project.scripts") or ""
    m = re.search(r'(?m)^\s*[\w-]+\s*=\s*"([\w.]+):', body)
    return m.group(1) if m else None


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


class TestWheelLayoutFindsSkill(unittest.TestCase):
    """按 `pyproject.toml` 搭出装好之后的布局,问 CLI 自己找不找得到协议(W64 review-test 打回补)。

    映射的目标改错了(比如 `pair_bootstrap/skills`),上面两条照绿、`test_v1_cli.TestPackagedLayout` 也照绿(它把布局写死成 `pkg/skill`、
    不读 `pyproject.toml`)—— 而装好的包在 site-packages 里找不到协议,`pair init` 分发不出去。这里不写死目标名:
    包目录取自 `packages`,入口模块取自 `[project.scripts]`,协议放到 `force-include` 的目标处,`find_bundled_skill()` 要正好返回那里。"""

    def test_CLI_在_force_include_的目标处找到协议(self):
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        mapping = force_include_map(text) or {}
        self.assertIn(SKILL_REL, mapping, "前提:有协议目录的映射")
        packages, module = wheel_packages(text), script_module(text)
        self.assertTrue(packages, "前提:wheel 的 packages 读得出")
        self.assertTrue(module, "前提:[project.scripts] 的入口模块读得出")

        stage = Path(tempfile.mkdtemp(prefix="pair-wheel-layout-")).resolve()
        self.addCleanup(shutil.rmtree, stage, True)
        for pkg in packages:                 # hatch 把 packages 里的目录按目录名装进包根
            shutil.copytree(REPO / pkg, stage / Path(pkg).name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        target = stage / mapping[SKILL_REL]
        target.mkdir(parents=True)
        shutil.copy2(REPO / SKILL_REL / "SKILL.md", target / "SKILL.md")

        proc = subprocess.run([sys.executable, "-c", "import %s as b; print(b.find_bundled_skill())" % module],
                              cwd=str(stage), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        found = proc.stdout.decode("utf-8").strip()
        self.assertEqual(proc.returncode, 0, found)
        self.assertEqual(found, str(target),
                         "force-include 把协议放到 %s,CLI 却在别处找(或找不到)—— 装好的包分发不出协议" % mapping[SKILL_REL])


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

    def test_packages_与入口模块(self):
        text = ('[project.scripts]\npair = "pair_bootstrap:main"\n\n'
                '[tool.hatch.build.targets.wheel]\npackages = ["cli/pair_bootstrap", "cli/extra"]\n')
        self.assertEqual(wheel_packages(text), ["cli/pair_bootstrap", "cli/extra"])
        self.assertEqual(script_module(text), "pair_bootstrap")

    def test_gitignore_按整行比_子串不算(self):
        self.assertEqual(gitignore_missing(".pair/whoami-old\n*.pyc\n", [".pair/whoami", "*.pyc"]), [".pair/whoami"])

    def test_gitignore_行首行尾空白不计(self):
        self.assertEqual(gitignore_missing("  __pycache__/  \n", ["__pycache__/"]), [])


if __name__ == "__main__":
    unittest.main()
