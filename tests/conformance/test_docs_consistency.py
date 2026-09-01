# -*- coding: utf-8 -*-
"""文档与代码的一致性。

这个项目的中心论点是"散文规则靠不住,必须编码进脚本"。docs/ 里那几张表
(不变量表、强制力分布表、状态 schema、命令表)是 pair.py 控制流的**手抄副本**,
contributing.md 也写下了纪律 ——"文档描述行为,pair.py 定义行为,不一致是 bug"
—— 但在这个文件出现之前,没有任何东西强制它。

于是这里把那条纪律本身变成测试:**改了 pair.py 而没改文档,会红。**

这些检查全部只比对结构,不判断文案好坏。
"""

import importlib.util
import json
import os
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".agents" / "skills" / "pair-protocol"
PAIR_PY = SKILL / "scripts" / "pair.py"
PAIR_SRC = PAIR_PY.read_text(encoding="utf-8")

# 参与检查的规范性文档。improvements.md 是提案,写的是**还不存在**的东西,
# 拿现状去卡它等于禁止提案,所以只查它的链接,不查它的键与命令。
NORMATIVE = ([SKILL / "SKILL.md", SKILL / "references" / "rules.md",
              REPO / "README.md", REPO / "INSTALL.md"]
             + sorted((REPO / "docs").glob("*.md")))
PROPOSALS = {"improvements.md"}


def _load_pair():
    spec = importlib.util.spec_from_file_location("pair_under_test", PAIR_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pair = _load_pair()


def _rel(p):
    return str(p.relative_to(REPO))


def _marker(path, doc):
    """取出 `<!-- pair-enforcements: a b c -->` 里的 id 列表。"""
    m = re.search(r"<!--\s*pair-enforcements:\s*(.*?)\s*-->", doc, re.S)
    assert m, "%s 里找不到 pair-enforcements 标记" % path
    return m.group(1).split()


def _json_blocks(doc):
    """```json 围栏里的内容,尽量解析成 dict;解析不了的片段跳过。"""
    out = []
    for body in re.findall(r"```json\n(.*?)```", doc, re.S):
        body = re.sub(r"//.*", "", body)          # 允许块内注释
        for candidate in (body, "{%s}" % body.rstrip().rstrip(",")):
            try:
                val = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(val, dict):
                out.append(val)
            break
    return out


def _slug(heading):
    """GitHub 风格锚点:小写、去标点、空格转连字符。中文原样保留。"""
    s = heading.strip().lower()
    s = re.sub(r"[`*_\[\]()。,、:;!?“”‘’]", "", s)
    s = re.sub(r"[^\w\s一-鿿-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


class TestDocsConsistency(unittest.TestCase):

    # --- 命令 ---------------------------------------------------------
    def _subcommands(self):
        return set(re.findall(r'sub\.add_parser\(\s*"([a-z-]+)"', PAIR_SRC))

    def test_文档里提到的子命令都真实存在(self):
        real = self._subcommands()
        self.assertTrue(real, "没能从 pair.py 里解析出任何子命令")
        for path in NORMATIVE:
            for cmd in set(re.findall(r"pair\.py\s+([a-z][a-z-]+)",
                                      path.read_text(encoding="utf-8"))):
                if path.name in PROPOSALS:
                    continue
                self.assertIn(
                    cmd, real,
                    "%s 提到 `pair.py %s`,但 pair.py 里没有这个子命令 —— "
                    "文档漂移了,或者命令被删了" % (_rel(path), cmd))

    def test_每个子命令都写进了命令参考(self):
        doc = (REPO / "docs" / "command-reference.md").read_text(encoding="utf-8")
        for cmd in self._subcommands():
            self.assertIn(
                "pair.py %s" % cmd, doc,
                "pair.py 有子命令 `%s`,但 docs/command-reference.md 没写它。"
                "新增命令时要同步文档。" % cmd)

    # --- 配置与状态 ---------------------------------------------------
    def test_文档里的配置键都存在(self):
        known = set(re.findall(r'cfg\.setdefault\("([^"]+)"', PAIR_SRC))
        known.add("test_cmd")                      # 必填项,没有 setdefault
        self.assertTrue(known)
        for path in NORMATIVE:
            if path.name in PROPOSALS:
                continue
            for block in _json_blocks(path.read_text(encoding="utf-8")):
                # 只认"看起来是配置对象"的块。文档里也有单独展示 roles 内层的
                # 片段(键是 tester/dev),那不是配置键,拿它报错只会逼人删测试。
                if not (set(block) & known):
                    continue
                for key in block:
                    self.assertIn(
                        key, known,
                        "%s 的 json 示例里有配置键 `%s`,但 load_config 不认识它"
                        % (_rel(path), key))

    def test_状态_schema_与代码双向一致(self):
        doc = (REPO / "docs" / "protocol-spec.md").read_text(encoding="utf-8")
        section = doc.split("## 8.")[1].split("## 9.")[0]
        documented = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.M))
        actual = set(pair.DEFAULT_STATE)
        self.assertEqual(
            documented, actual,
            "protocol-spec.md §8 的状态字段表与 DEFAULT_STATE 不一致。\n"
            "  只在文档里: %s\n  只在代码里: %s"
            % (sorted(documented - actual), sorted(actual - documented)))

    # --- 强制点登记表 -------------------------------------------------
    def test_不变量表与校验顺序一致(self):
        path = REPO / "docs" / "protocol-spec.md"
        listed = _marker(_rel(path), path.read_text(encoding="utf-8"))
        self.assertEqual(
            listed, list(pair.HANDOFF_INVARIANTS),
            "protocol-spec.md §4 的不变量表与 pair.py 的 HANDOFF_INVARIANTS 不一致"
            "(顺序也算)。这张表是 cmd_handoff 校验顺序的手抄副本,必须跟着改。")

    def test_强制力分布表里的_id_都真实存在(self):
        path = REPO / "docs" / "architecture.md"
        for eid in _marker(_rel(path), path.read_text(encoding="utf-8")):
            self.assertIn(eid, pair.ENFORCEMENTS,
                          "architecture.md 的强制力分布表提到 `%s`,"
                          "但它不在 pair.py 的 ENFORCEMENTS 里" % eid)

    def test_每个强制点至少被一份文档记录(self):
        covered = set()
        for name in ("protocol-spec.md", "architecture.md"):
            path = REPO / "docs" / name
            covered.update(_marker(name, path.read_text(encoding="utf-8")))
        missing = set(pair.ENFORCEMENTS) - covered
        self.assertFalse(
            missing,
            "这些强制点没有出现在任何一份文档的 pair-enforcements 标记里:%s\n"
            "新增防护时要在 protocol-spec.md 或 architecture.md 登记。"
            % sorted(missing))

    # --- 链接 ---------------------------------------------------------
    def test_相对链接与锚点都能解析(self):
        broken = []
        for path in NORMATIVE:
            doc = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", doc):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if not dest.exists():
                    broken.append("%s -> %s(文件不存在)" % (_rel(path), target))
                    continue
                if anchor and dest.suffix == ".md":
                    slugs = {_slug(h) for h in re.findall(
                        r"^#{1,6}\s+(.+?)\s*$", dest.read_text(encoding="utf-8"), re.M)}
                    if anchor.lower() not in slugs:
                        broken.append("%s -> %s(锚点不存在)" % (_rel(path), target))
        self.assertFalse(broken, "失效的文档链接:\n  " + "\n  ".join(broken))

    # --- 变异点 -------------------------------------------------------
    @unittest.skipIf(os.environ.get("PAIR_MUTATION_RUN"),
                     "变异运行故意改坏了 pair.py,这条必然失配")
    def test_变异点仍能匹配到源码(self):
        """变异点失配现在只有跑完整套变异检查才会暴露,那要几分钟。"""
        spec = importlib.util.spec_from_file_location(
            "mutation_under_test", Path(__file__).with_name("mutation_check.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name, old, _ in mod.MUTATIONS:
            self.assertEqual(
                PAIR_SRC.count(old), 1,
                "变异点「%s」在 pair.py 里匹配到 %d 处(应为 1)。"
                "改过强制逻辑之后要同步更新 MUTATIONS。"
                % (name, PAIR_SRC.count(old)))


if __name__ == "__main__":
    unittest.main()
