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
# 空的 tests/ 也算红。这让红绿状态完全由文件布局决定,便于测试驱动。
TEST_CMD = (
    "python3 -c \""
    "import os,sys;"
    "t=[n for n in os.listdir('tests') if not n.startswith('.')];"
    "sys.exit(0 if t and all(os.path.exists(os.path.join('src',n)) for n in t) else 1)"
    "\""
)

PLAN_TEMPLATE = """# 项目规划

## 工作项

- [ ] **W1** — 第一个工作项
  - 验收标准:tests/w1 存在时 src/w1 也存在
- [ ] **W2** — 第二个工作项
  - 验收标准:同上
"""

CONFIG = {
    "test_cmd": TEST_CMD,
    "roles": {"tester": ["tests"], "dev": ["src"]},
    "shared_paths": ["docs/reviews"],
    "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md", ".agents", ".pair"],
    "plan_file": "docs/PLAN.md",
    "sync": False,
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
        "round": 0, "phase": "spec", "item": None,
        "last_actor": None, "changes_count": 0, "completed_items": [],
    }, indent=2), encoding="utf-8")

    for d in ("src", "tests", "docs/reviews"):
        (target / d).mkdir(parents=True, exist_ok=True)
        (target / d / ".gitkeep").write_text("", encoding="utf-8")
    (target / "docs" / "PLAN.md").write_text(PLAN_TEMPLATE, encoding="utf-8")
    (target / "docs" / "CONTRACT.md").write_text("# 契约\n", encoding="utf-8")
    (target / ".gitignore").write_text(
        ".pair/.last-test.log\n.pair/whoami\n", encoding="utf-8")


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

    def head_subject(self):
        return self.git("log", "-1", "--format=%s").stdout.decode("utf-8").strip()

    def commit_count(self):
        return int(self.git("rev-list", "--count", "HEAD").stdout.decode().strip())

    # --- 合法地推进回合 ------------------------------------------------
    def advance_to(self, phase, item="W1"):
        """通过合法交接把状态推到指定阶段。测试用来搭场景。"""
        if phase == "spec":
            return
        assert self.run("claim", item, role="tester").code == 0
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
        r = self.run("handoff", "approve", "查过无硬编码", role="tester")
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
