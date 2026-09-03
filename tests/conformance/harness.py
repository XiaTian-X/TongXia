# -*- coding: utf-8 -*-
"""协议一致性测试的公共脚手架。

每个测试在临时目录里建一个**真的** git 仓库,装上协议,然后扮演一个
作弊的 agent,断言 pair.py 拒绝它。
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_SRC = REPO / ".agents" / "skills" / "pair-protocol"
PAIR_PY = ".agents/skills/pair-protocol/scripts/pair.py"

# 微型 TDD:tests/ 下每有一个文件,src/ 下就必须有同名文件,否则红。
# 空的 tests/ 算绿 —— 真实项目接入时基线必须是全绿的,init 与 verify-setup
# 都依赖这一点。红绿状态完全由文件布局决定,便于测试驱动。
TEST_CMD = (
    "python3 -c \""
    "import os,sys;"
    "t=[n for n in os.listdir('tests') if not n.startswith('.')];"
    "sys.exit(0 if all(os.path.exists(os.path.join('src',n)) for n in t) else 1)"
    "\""
)

PLAN_TEMPLATE = """# 项目规划

## 工作项

- [ ] **W1** [feature] — 第一个工作项
  - 验收标准:tests/W1 存在时 src/W1 也存在
  - 对应契约:`docs/CONTRACT.md` → W1
- [ ] **W2** [feature] — 第二个工作项
  - 验收标准:同上
  - 对应契约:`docs/CONTRACT.md` → W2
"""

CONTRACT_TEMPLATE = """# 接口契约

## W1

- 依据: 人类定稿

**行为** tests/W1 存在时 src/W1 必须存在。

## W2

- 依据: 人类定稿

**行为** tests/W2 存在时 src/W2 必须存在。
"""

ARCHAEOLOGY_NOTE = """## 现状考古

这个函数原本把解析和格式化揉在一起,是因为早期调用方依赖它同时返回两种形态,
那个调用方现在已经删了,但形状留了下来。

## 我保留了哪些契约外行为

输入为空时返回空字符串而不是抛错。契约里没写这条,但现有调用方依赖它,
改成抛错会让上游多出一处它没准备好的异常路径,所以原样保留。

## 我不确定的地方

拆分之后异常的抛出时机从解析时挪到了格式化时,如果有调用方在中间捕获过,
行为会变。测试没有覆盖到这条路径。
"""

# --- 评审证据 ---------------------------------------------------------
# approve 必须交出检查清单,changes 必须指到 `路径:行号`。用例里大量出现,
# 抽成常量,免得每处都重写一遍。
EVIDENCE = ("--checked", "查过 src/W1 无针对测试输入的特判",
            "--uncovered", "超长输入,下轮补")

# 始终存在的被引用位置。用 CONTRACT 是因为它在任何阶段都已被提交,
# 用例不必关心此刻哪些源文件已经生成。
LOC = "docs/CONTRACT.md:3"


def with_loc(reason, loc=LOC):
    """给打回理由补一处位置引用。"""
    return "%s,见 %s" % (reason, loc)


DISPUTE_DOC = """## 哪条用例

`tests/W1` 那条。它断言 tests/W1 存在时 src/W1 不存在,而这跟契约写的正好相反。

## 和契约的哪一条矛盾

`docs/CONTRACT.md` 的 W1 小节写明:tests/W1 存在时 src/W1 必须存在。
用例假设的是相反的关系,两者不可能同时成立。

## 应该改成什么

把断言反过来:tests/W1 存在时断言 src/W1 也存在。契约不用动,是用例写反了。
"""

COVER_NOTE = """## 行为来源

读了实现并在本地跑了一遍:空输入返回空字符串而不抛错。契约里没有这一条,
所以这次断言的依据是这次观察本身,不是任何文档。

## 我冻结了哪些可疑行为

空输入返回空字符串看着像遗漏 —— 更像该抛 ValueError。但现有调用方依赖它,
我照原样固化了。如果这其实是缺陷,应当另开一个 [bug] 工作项来修。
"""


def setup_report(*sections):
    """一份能过 verify-setup 的契约审查结论。

    它要满足三条:够长、点到每个被引用的小节、说明作者有没有参与起草。
    抽成函数是因为用例里到处都要它,而三条要求以后还可能变。
    """
    body = "\n\n".join(
        "## %s\n\n返回值的类型和字段精确到能直接写断言。错误条件已经穷举:"
        "抛什么、什么时候抛都写明了。边界情况里空串和超长两种都在契约里,"
        "null 与并发不适用。逐句读过,没有可以有两种合理解读的地方。" % name
        for name in sections)
    return ("# 契约审查结论\n\n我没有参与这份契约的起草,"
            "以下结论是逐节读过之后写的。\n\n" + body + "\n")


CONFIG = {
    "test_cmd": TEST_CMD,
    "roles": {"tester": ["tests"], "dev": ["src"]},
    "shared_paths": ["docs/reviews"],
    "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md", ".agents", ".pair"],
    "plan_file": "docs/PLAN.md",
    "contract_file": "docs/CONTRACT.md",
    "ignore_paths": [],
    "sync": False,
    # 绝大多数用例不测这条门禁,单独有一组用例专门测它
    "require_setup_verification": False,
}


def install_protocol(target: Path, config=None):
    """把协议装进 target 目录。真实接入项目时做的也是这件事。"""
    dest = target / ".agents" / "skills" / "pair-protocol"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SRC, dest, dirs_exist_ok=True)

    pair = target / ".pair"
    pair.mkdir(exist_ok=True)
    cfg = dict(CONFIG)
    if config:
        cfg.update(config)
    (pair / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (pair / "state.json").write_text(json.dumps({
        "round": 0, "phase": "idle", "item": None, "item_type": None,
        "last_actor": None, "changes_count": 0, "completed_items": [],
        "setup_verified": False,
    }, indent=2), encoding="utf-8")

    for d in ("src", "tests", "docs/reviews", "docs/notes"):
        (target / d).mkdir(parents=True, exist_ok=True)
        (target / d / ".gitkeep").write_text("", encoding="utf-8")
    (target / "docs" / "PLAN.md").write_text(PLAN_TEMPLATE, encoding="utf-8")
    (target / "docs" / "CONTRACT.md").write_text(CONTRACT_TEMPLATE, encoding="utf-8")
    (target / ".gitignore").write_text(
        ".pair/.last-test.log\n.pair/whoami\n", encoding="utf-8")
    # 入口文件:真实项目由 init 铺设,这里手工放两个主要的
    (target / "AGENTS.md").write_text(
        "本仓库是双 AI agent 结对开发项目,先读 "
        ".agents/skills/pair-protocol/SKILL.md\n", encoding="utf-8")
    (target / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")


class Result:
    def __init__(self, proc):
        self.code = proc.returncode
        self.out = proc.stdout.decode("utf-8", "replace")
        self.err = proc.stderr.decode("utf-8", "replace")

    @property
    def text(self):
        return self.out + self.err

    def __repr__(self):
        return "Result(code=%d)\n--- stdout ---\n%s\n--- stderr ---\n%s" % (
            self.code, self.out, self.err)


class PairRepo:
    """一个装好协议、可被驱动的临时结对仓库。"""

    def __init__(self, config=None):
        self.dir = Path(tempfile.mkdtemp(prefix="pair-conf-"))
        install_protocol(self.dir, config)
        self.git("init", "-q")
        self.git("config", "user.email", "conformance@test")
        self.git("config", "user.name", "conformance")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: 装上结对协议")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # --- 底层 ---------------------------------------------------------
    def git(self, *args):
        return subprocess.run(("git",) + args, cwd=self.dir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def run(self, *args, role="tester", env=None):
        e = dict(os.environ)
        e.pop("PAIR_TEST_CMD", None)
        if role is not None:
            e["PAIR_ROLE"] = role
        else:
            e.pop("PAIR_ROLE", None)
        if env:
            e.update(env)
        return Result(subprocess.run(
            ["python3", PAIR_PY] + list(args),
            cwd=self.dir, env=e,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE))

    # --- 文件操作(扮演 agent) ----------------------------------------
    def write(self, rel, content="x"):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def delete(self, rel):
        (self.dir / rel).unlink()

    def read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")

    def exists(self, rel):
        return (self.dir / rel).exists()

    # --- 状态 ---------------------------------------------------------
    def state(self):
        return json.loads(self.read(".pair/state.json"))

    def tamper_state(self, **kw):
        """直接改状态文件 —— 这正是协议必须拦住的作弊行为。"""
        st = self.state()
        st.update(kw)
        self.write(".pair/state.json", json.dumps(st, indent=2))

    # --- 记忆层(扮演 agent 写笔记与决策)-------------------------------
    def write_archaeology(self, item="R1"):
        """refactor 的考古记录。三个小节,每节要够长。"""
        self.write("docs/notes/%s.md" % item, ARCHAEOLOGY_NOTE)

    def write_dispute(self, item="W1"):
        """impl 阶段异议的规范文件。三要素来自 rules.md 规则 2。"""
        self.write("docs/reviews/%s-dispute.md" % item, DISPUTE_DOC)

    def write_cover_note(self, item="C1"):
        """cover 的特征测试记录。两个小节,每节要够长。"""
        self.write("docs/notes/%s.md" % item, COVER_NOTE)

    def append_decision(self, item="W1", title="改用毫秒时间戳做排序键",
                        reason="ISO 字符串跨时区排序和真实先后不一致,验收标准直接依赖排序",
                        rejected="存 ISO 再解析后排序 —— 每次读都要解析,失败没有兜底",
                        paths=None):
        """往决策记录追加一条合规条目。追加式,绝不改动已有内容。"""
        rel = "docs/DECISIONS.md"
        old = self.read(rel) if self.exists(rel) else ""
        if paths is None:
            paths = "`src/%s`, `tests/%s`" % (item, item)
        entry = ("\n## %s — %s\n\n- 理由: %s\n- 已否决: %s\n- 影响路径: %s\n"
                 % (item, title, reason, rejected, paths))
        self.write(rel, old + entry)

    def set_plan(self, text, contract=None):
        """以人类身份改写 PLAN/CONTRACT 并提交(agent 不能做这件事)。"""
        self.write("docs/PLAN.md", text)
        if contract is not None:
            self.write("docs/CONTRACT.md", contract)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "docs: 人类更新了规划")

    def head_subject(self):
        return self.git("log", "-1", "--format=%s").stdout.decode("utf-8").strip()

    def commit_count(self):
        return int(self.git("rev-list", "--count", "HEAD").stdout.decode().strip())

    # --- 合法地推进回合 ------------------------------------------------
    def advance_to(self, phase, item="W1"):
        """通过合法交接把状态推到指定阶段。测试用来搭场景。"""
        if phase == "idle":
            return
        r = self.run("claim", item, role="tester")
        assert r.code == 0, r
        if phase == "spec":
            return
        self.write("tests/%s" % item)
        r = self.run("handoff", "写了 %s 的失败用例" % item, role="tester")
        assert r.code == 0, r
        if phase == "impl":
            return
        self.write("src/%s" % item)
        r = self.run("handoff", "实现 %s" % item, role="dev")
        assert r.code == 0, r
        if phase == "review-impl":
            return
        r = self.run("handoff", "approve", "查过无硬编码", *EVIDENCE,
                     role="tester")
        assert r.code == 0, r
        if phase == "review-test":
            return
        raise ValueError("未知阶段 %s" % phase)


class PairTestCase(unittest.TestCase):
    config = None

    def setUp(self):
        self.repo = PairRepo(self.config)
        self.addCleanup(self.repo.cleanup)

    def assertRefused(self, result, *needles):
        """断言这次调用被拒绝,且理由里包含指定关键词。"""
        self.assertNotEqual(
            result.code, 0,
            "本应被拒绝,却成功了。\n%r" % result)
        for n in needles:
            self.assertIn(n, result.text,
                          "拒绝理由里没提到 %r。\n%r" % (n, result))

    def assertAccepted(self, result):
        self.assertEqual(result.code, 0, "本应放行,却被拒绝。\n%r" % result)


# Go 同目录布局:每个 X_test.go 都要有对应的 X.go,否则红。
GO_TEST_CMD = (
    "python3 -c \""
    "import os,sys,glob;"
    "t=glob.glob('**/*_test.go',recursive=True);"
    "sys.exit(0 if all(os.path.exists(f[:-8]+'.go') for f in t) else 1)"
    "\""
)

GO_CONFIG = {
    "test_cmd": GO_TEST_CMD,
    "roles": {
        "tester": ["**/*_test.go"],
        "dev": ["**/*.go", "!**/*_test.go"],
    },
}


class BareRepo:
    """一个只有源码、还没装协议的 git 仓库 —— 用来测 init 与 CLI bootstrap。"""

    def __init__(self, files=None, install_skill=True):
        self.dir = Path(tempfile.mkdtemp(prefix="pair-bare-"))
        for rel, content in (files or {}).items():
            p = self.dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        if install_skill:
            dest = self.dir / ".agents" / "skills" / "pair-protocol"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(SKILL_SRC, dest, dirs_exist_ok=True)
        self.git("init", "-q")
        self.git("config", "user.email", "conformance@test")
        self.git("config", "user.name", "conformance")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(("git",) + args, cwd=self.dir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def run(self, *args, role="tester"):
        e = dict(os.environ)
        e.pop("PAIR_TEST_CMD", None)
        e["PAIR_ROLE"] = role
        return Result(subprocess.run(["python3", PAIR_PY] + list(args),
                                     cwd=self.dir, env=e,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE))

    def exists(self, rel):
        return (self.dir / rel).exists()

    def read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")
