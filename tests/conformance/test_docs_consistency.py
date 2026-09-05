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

# --- 定位口径 -------------------------------------------------------------
# 目的层只有一种表述:共同把 PLAN 里的工作项交付出来。手段词(防漂移 /
# 防点头 / 对抗)出现在目的槽位就是定位漂移 —— ADR-022 摆正过一次,
# 而它自己的 sweep 漏了五处,其中三处会随 wheel 扩散到每个接入的项目。
POSITION_ENTRIES = [REPO / "README.md", SKILL / "SKILL.md",
                    REPO / "docs" / "README.md",
                    REPO / "docs" / "design-philosophy.md",
                    REPO / "docs" / "contributing.md"]
# 定位要在开头,不能被挤到文档深处 —— 窗口就是这条的全部意义。
POSITION_HEAD_LINES = 40
DELIVERY_WORDS = ("交付", "做完", "做出来", "完成")

# 豁免:这三份是记录,不是主张。理由见 test_手段词没有出现在目的槽位。
POSITION_EXEMPT = {"design-decisions.md", "improvements.md", "dogfood-run-1.md"}

MEANS = "防漂移|防点头|防互相点头|对抗"
MEANS_IN_PURPOSE_SLOT = tuple(re.compile(p) for p in (
    r"这个项目(?:在做|要做成)的事[^。\n]{0,20}(?:%s)" % MEANS,
    r"(?:%s)[^。\n]{0,12}(?:正是|就是)这个项目" % MEANS,
    r"(?:协议|项目)存在的(?:全部)?(?:理由|目的|意义)[^。\n]{0,12}(?:%s)" % MEANS,
    r"从头到尾在(?:做|防)的事",
))


def _positioning_scope():
    """查散文,也查随包分发的代码 —— 漏掉的四处里有三处正是在 .py 里。"""
    for p in NORMATIVE:
        if p.name not in POSITION_EXEMPT:
            yield p
    for p in [SKILL / "scripts" / "pair.py", SKILL / "scripts" / "drive.py",
              REPO / "cli" / "pair_bootstrap" / "__init__.py"]:
        yield p
    for p in sorted((SKILL / "references").glob("*.md")):
        yield p
    for p in sorted((REPO / "tests" / "conformance").glob("*.py")):
        # 本文件除外:它必须原样含有这些句式才能拿它们去查别人。
        # 同 mutation_check.py 必须含有被变异的源码片段,是同一类自指豁免。
        if p.resolve() != Path(__file__).resolve():
            yield p


# 文档里用 `文件.py:行号` 引用过的源码文件。basename 必须唯一 —— 重名了就
# 认不出引用指的是哪一个,下面的 setUpModule 级断言会直接红。
CITED = {p.name: p for r in (SKILL / "scripts", REPO / "tests" / "conformance",
                             REPO / "examples", REPO / "cli" / "pair_bootstrap")
         for p in sorted(r.glob("*.py"))}

# 被引文件的行数。变了就说明所有指向它的行号引用都可能错位 —— 见
# test_被引文件的行数没变过。**改这里之前先逐条核对引用,别只改数字。**
CITED_LINE_COUNTS = {
    "pair.py": 2926,
    "harness.py": 401,
    "mutation_check.py": 690,
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

    # --- 定位口径 -----------------------------------------------------
    def test_入口文档都写明了交付目的(self):
        """定位的**正向锚**:每个入口都得在开头说清楚这套协议是干什么的。

        ADR-022 把层级摆正(目的=共同交付,防点头/防漂移=手段),但那一轮是
        人工 sweep。这条钉的是"目的层的话没被删掉、没被挤到文档深处"。

        反向自证:删掉 design-philosophy 开头那句交付表述,本条变红。
        """
        bad = []
        for path in POSITION_ENTRIES:
            head = "\n".join(
                path.read_text(encoding="utf-8").splitlines()[:POSITION_HEAD_LINES])
            if "PLAN.md" in head and any(w in head for w in DELIVERY_WORDS):
                continue
            bad.append(_rel(path))
        self.assertFalse(
            bad,
            "这些入口文档的前 %d 行里没有交付目的的表述:\n  %s\n\n"
            "每个入口都要在开头说明:两个 agent 共同把 `PLAN.md` 里的工作项"
            "交付出来。\n判据很松 —— 提到 PLAN.md,并出现 %s 之一。"
            % (POSITION_HEAD_LINES, "\n  ".join(bad), "/".join(DELIVERY_WORDS)))

    def test_手段词没有出现在目的槽位(self):
        """定位的**反向绊线**。

        ADR-022 的 sweep 漏掉了 `docs/contributing.md` 的第一句
        ("这个项目在做的事,一句话概括:防漂移")——因为那轮搜的是"防点头",
        没搜"防漂移":两个不同的手段被放进同一个槽位,只查了一个。
        四处活的分发物(drive.py / cli / cmd_whose_turn / test_v1_shipped)
        同样漏了一整轮,而前三处会被打进 wheel、再复制进每个接入的项目。

        **这和 ADR-014 / ADR-024「不解析散文」不冲突,因为被查的东西不一样。**
        那两条管的是 **agent 为了过门禁而产出的文字** —— 换个说法就绕过去,
        而且会把协议绑死在一种语言上。这里查的是**本仓库自己的文档**,
        由本仓库的测试跑,没有人在试图绕过它:失效方式是**忘了改**,不是规避。
        同 `CITED_LINE_COUNTS` 一样,**它是绊线,不是校验器** —— 换一种没列进
        表里的句式照样能漂,别把它读成"定位已经有脚本守着了"。

        **豁免的三份是记录,不是主张:** design-decisions.md 里的既有 ADR
        按追加式纪律不改写(由 ADR-022 在顶层解释)、improvements.md 描述的是
        这个问题本身、dogfood-run-1.md 是运行报告(已在头部加按语)。

        反向自证:把 contributing.md 开篇改回旧写法、把 drive.py 里那句旧口径
        塞回去(那是随 wheel 分发的那一类),两次都变红。
        """
        hits = []
        for path in _positioning_scope():
            text = path.read_text(encoding="utf-8")
            for rx in MEANS_IN_PURPOSE_SLOT:
                for m in rx.finditer(text):
                    line = text[:m.start()].count("\n") + 1
                    hits.append("%s:%d  %s" % (_rel(path), line,
                                               m.group(0).replace("\n", " ")))
        self.assertFalse(
            hits,
            "手段被放进了目的槽位:\n  %s\n\n"
            "目的是**两个 agent 共同把 PLAN 里的工作项交付出来**;\n"
            "防漂移、防点头、对抗性都是保障交付质量的手段(ADR-022)。\n"
            "把这句话改成说同一个机制、但摆回手段层 —— 例如\n"
            "  「两份判定迟早不一致,门禁看着还在、实际拦不住」。\n"
            "如果这处是历史记录(既有 ADR / 运行报告),把它加进豁免名单,\n"
            "并说明为什么它是记录而不是主张。" % "\n  ".join(hits))

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
