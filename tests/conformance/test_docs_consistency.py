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


# 文档里用 `文件.py:行号` 引用过的源码文件。basename 必须唯一 —— 重名了就
# 认不出引用指的是哪一个,下面的 setUpModule 级断言会直接红。
CITED = {p.name: p for r in (SKILL / "scripts", REPO / "tests" / "conformance",
                             REPO / "examples", REPO / "cli" / "pair_bootstrap")
         for p in sorted(r.glob("*.py"))}

# 被引文件的行数。变了就说明所有指向它的行号引用都可能错位 —— 见
# test_被引文件的行数没变过。**改这里之前先逐条核对引用,别只改数字。**
CITED_LINE_COUNTS = {
    "pair.py": 2903,
    "harness.py": 401,
    "mutation_check.py": 681,
    "make-demo.py": 94,
    "drive.py": 212,
    "__init__.py": 102,
    "test_v1_shipped.py": 149,
    "test_v1_report.py": 116,
    "test_v1_review_evidence.py": 112,
}

# `pair.py:1799` / `harness.py:204-205`。反引号可有可无 —— 两种写法文档里都有。
_CITE_RE = re.compile(r"([A-Za-z_][\w\-]*\.py):(\d+)(?:-(\d+))?")


def _citations(doc):
    """(文件名, 起, 止, 原文) —— 只认得出 CITED 里的文件。"""
    for m in _CITE_RE.finditer(doc):
        if m.group(1) in CITED:
            a = int(m.group(2))
            yield m.group(1), a, int(m.group(3) or a), m.group(0)


def _docs_with_citations():
    """提案文档也算:它的行号引用同样指向**当前**的代码。"""
    for path in NORMATIVE:
        yield path, path.read_text(encoding="utf-8")


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

    # --- 行号引用 -----------------------------------------------------
    def test_文档里的行号引用都落在文件内(self):
        """`pair.py:1799` 这类引用是**硬编码的坐标**,最起码得指到文件里面。"""
        bad = []
        for path, doc in _docs_with_citations():
            for name, a, b, _ in _citations(doc):
                src = CITED[name].read_text(encoding="utf-8").splitlines()
                if b > len(src):
                    bad.append("%s -> %s:%d-%d(该文件只有 %d 行)"
                               % (_rel(path), name, a, b, len(src)))
        self.assertFalse(bad, "指到文件外面的行号引用:\n  " + "\n  ".join(bad))

    def test_被引文件的行数没变过(self):
        """行号引用的**绊线**。

        被引文件上方插一行,下面每一处引用就都指向别处,而在这条出现之前
        没有任何东西会红 —— `fc5c212` 一次让 7 处同时失效,全部是评审证据
        级别的锚点(这个仓库的裁决门禁本身就要求 `路径:行号`)。

        **为什么不比对内容:** 试过,不成立。引用旁边的反引号片段常常是
        *描述*而不是原文(`put()` vs `def put(rel, content):`、`git commit`
        vs `subprocess.run(("git",) + args, ...)`),按片段比对会误伤。

        所以钉的是**触发条件**:被引文件的行数一变,就说明每一处引用都
        *可能*已经错位,红并把它们当前指到的内容打出来,人五秒钟核完。
        **它是绊线,不是校验器** —— 行数不变的内容修改抓不到,而且逃逸口
        (不核对就改数字)与变异缓存的基线指纹同级。别把它读成"行号引用
        已经有脚本守着了"。
        """
        drifted = []
        for name, expect in sorted(CITED_LINE_COUNTS.items()):
            actual = len(CITED[name].read_text(encoding="utf-8").splitlines())
            if actual != expect:
                drifted.append((name, expect, actual))
        if not drifted:
            return
        lines = []
        for name, expect, actual in drifted:
            src = CITED[name].read_text(encoding="utf-8").splitlines()
            lines.append("%s:%d 行 -> %d 行,受影响的引用:" % (name, expect, actual))
            for path, doc in _docs_with_citations():
                for cname, a, b, raw in _citations(doc):
                    if cname != name:
                        continue
                    body = " / ".join(x.strip() for x in src[a - 1:b] if x.strip())
                    lines.append("    %s 的 %s   现在指到:%s"
                                 % (_rel(path), raw, body[:70] or "(空行)"))
        self.fail("被引文件的行数变了,行号引用可能已经失效 ——\n  "
                  + "\n  ".join(lines)
                  + "\n\n逐条核对上面每一处指到的内容,改对之后更新 "
                    "CITED_LINE_COUNTS。\n不核对就只改数字,这条检查等于没有。")

    # --- 散文里的计数 -------------------------------------------------
    def test_散文里的_ADR_与不变量计数与代码一致(self):
        """散文里那两个数字(N 条 ADR / N 条不变量)漂起来是静默的。

        `fc5c212` 追加了一条 ADR 而两处计数一字未动,就是这么漏的。
        提案文档(improvements.md)不算:它会引用过去与将来的计数。
        """
        adrs = (REPO / "docs" / "design-decisions.md").read_text(encoding="utf-8")
        want = {"条 ADR": len(re.findall(r"^## ADR-", adrs, re.M)),
                "条不变量": len(pair.HANDOFF_INVARIANTS)}
        bad = []
        for path in NORMATIVE:
            if path.name in PROPOSALS:
                continue
            doc = path.read_text(encoding="utf-8")
            for unit, n in want.items():
                for m in re.finditer(r"(\d+)\s*%s" % unit, doc):
                    if int(m.group(1)) != n:
                        bad.append("%s 写的是「%s」,实际 %d %s"
                                   % (_rel(path), m.group(0), n, unit))
        self.assertFalse(bad, "散文里的计数与代码不一致:\n  "
                              + "\n  ".join(bad))

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
