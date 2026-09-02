#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双 AI agent 结对编程协议 —— 执行层。

单文件,仅依赖 Python 3 标准库。用法:

    python3 pair.py init [目标目录]     # 初始化(结对开始之前跑)
    python3 pair.py verify-setup        # 另一方开工前的只读校验
    python3 pair.py status
    python3 pair.py claim W1
    python3 pair.py handoff "说明"
    python3 pair.py handoff approve "摘要" --checked "…" --uncovered "…"
    python3 pair.py handoff changes "问题清单"
    python3 pair.py inbox [N]

本脚本是协议的强制执行点。它校验写权限边界、红绿不变量和回合归属,
不合规就拒绝提交。agent 不应绕过它,也不应修改它。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath

ROLES = ("tester", "dev")

# 阶段 -> 负责角色
PHASE_OWNER = {
    "idle": "tester",          # 无工作项在进行,等 tester 认领
    "spec": "tester",
    "impl": "dev",
    "review-impl": "tester",
    "review-test": "dev",
}
REVIEW_PHASES = ("review-impl", "review-test")

# 允许用 `handoff changes` 提出异议、但不是评审回合的阶段。
# dev 在 impl 阶段发现测试与契约矛盾时用它打回,由 tester 修测试。
DISPUTE_PHASES = ("impl",)

# 工作项类型 -> 流程。DONE 表示工作项完成,回到 idle。
#
# 阶段序列与红绿不变量按类型分开:补测试(cover)和重构(refactor)天然
# 没有 RED 阶段,套用 feature 的"先红后绿"会直接卡死。
FEATURE_FLOW = {
    "start": "spec",
    "transitions": {
        ("spec", None): "impl",
        ("impl", None): "review-impl",
        # dev 拿到一条写错的测试时的唯一出路。没有它,dev 三条路全堵死
        # (不能改测试、不能打回、不能红着交接),只能照错误断言写实现。
        ("impl", "changes"): "spec",
        ("review-impl", "approve"): "review-test",
        ("review-impl", "changes"): "impl",
        ("review-test", "approve"): "DONE",
        ("review-test", "changes"): "spec",
    },
    "expect": {"spec": "RED", "impl": "GREEN",
               "review-impl": "GREEN", "review-test": "GREEN"},
    "require_new_tests": (),
}

FLOWS = {
    "feature": FEATURE_FLOW,
    "bug": FEATURE_FLOW,
    "cover": {
        "start": "spec",
        "transitions": {
            ("spec", None): "review-test",
            ("review-test", "approve"): "DONE",
            ("review-test", "changes"): "spec",
        },
        "expect": {"spec": "GREEN", "review-test": "GREEN"},
        # 全程绿,所以必须另外证明这一回合真的写了测试
        "require_new_tests": ("spec",),
    },
    "refactor": {
        "start": "impl",
        "transitions": {
            ("impl", None): "review-impl",
            ("review-impl", "approve"): "DONE",
            ("review-impl", "changes"): "impl",
        },
        "expect": {"impl": "GREEN", "review-impl": "GREEN"},
        "require_new_tests": (),
    },
}
ITEM_TYPES = tuple(FLOWS)

COMMIT_PREFIX = {
    "spec": "test",
    "impl": "feat",
    "review-impl": "review(impl)",
    "review-test": "review(test)",
}

DEADLOCK_LIMIT = 3

# --- 强制点登记表 -----------------------------------------------------
# 纯数据,不参与任何判定。存在的理由只有一个:让文档与代码之间有一条**会红**
# 的关系。docs/ 里那几张表(不变量表、强制力分布表)是本文件控制流的手抄副本,
# contributing.md 已经写下"文档描述行为、pair.py 定义行为,不一致是 bug",
# 但在此之前没有任何东西强制它 —— 而这个项目的中心论点正是"散文规则靠不住"。
#
# 新增一条防护时,除了加拒绝分支、加一致性测试、补变异点,还要:
#   1. 在这里登记一个 id
#   2. 在对应文档表格上方的 `<!-- pair-enforcements: ... -->` 注释里加上它
# 漏掉第 2 步,test_docs_consistency.py 会红。

# cmd_handoff 的校验顺序。顺序即语义:纸面问题排在跑测试之前。
HANDOFF_INVARIANTS = (
    "turn-ownership",      # 执行者必须是当前阶段的归属角色
    "project-done",        # PLAN 里还有未完成的工作项
    "state-untampered",    # .pair/state.json 未被手工改动
    "verdict-valid",       # 评审必须给 approve/changes 且理由非空
    "transition-valid",    # (阶段, 裁决) 在该类型的转移表里
    "write-boundary",      # 改动文件命中可写路径、不在 frozen_paths 下、
                           # 且(配了 scope 时)落在 scope 内
    "test-deletion",       # 删测试必须带 --allow-deletion
    "new-tests",           # cover 的 spec 回合必须真的碰了测试文件
    "dispute-evidence",    # impl 阶段的 changes 必须写进 shared_paths
    "review-evidence",     # approve 要检查清单,changes 要 路径:行号 引用
    "memory-gate",         # 记忆层门禁,见下面几条子项
    "red-green",           # 按工作项类型的红绿期望,异议路径豁免
    "deadlock",            # 同一工作项打回 3 次即停止轮转
)

# 全部强制点 = 交接不变量 + 记忆层子门禁 + verify-setup 的门禁。
ENFORCEMENTS = HANDOFF_INVARIANTS + (
    "decision-format",       # 决策条目字段完整、长度达标、追加式
    "archaeology-note",      # refactor 的 impl 回合必须交出考古三小节
    "contract-change-note",  # 契约在工作项期间变过就必须留决策
    "note-promotion",        # 完成时笔记还有内容 -> 晋升或 --no-decision
    "scope",                 # write-boundary 的子条款:改动必须落在本轮范围内
    "setup-report",          # verify-setup 要求交出契约歧义审查结论
    "cover-note",            # cover 的 spec 回合要交出特征测试记录
    "contract-provenance",   # 契约小节必须写 `依据`,不可断言的不能开非 cover 项
    "refactor-safety-net",   # refactor 必须声明保护它的测试
    "post-dispute-fix",      # 异议后的 spec 回合豁免红绿,但必须真的改了测试
)


STATE_REL = ".pair/state.json"
CONFIG_REL = ".pair/config.json"
TESTLOG_REL = ".pair/.last-test.log"
FULL_TESTLOG_REL = ".pair/.last-full-test.log"
BRIEF_REL = ".pair/.last-brief.md"
# 协议自己写的日志。它们落在 .pair/ 下,而 .pair 是冻结路径 —— 不在这里豁免,
# agent 下一回合就会被自己刚跑的那次测试卡在越界上,而且它删不干净(下次还生成)。
PROTOCOL_LOGS = (TESTLOG_REL, FULL_TESTLOG_REL, BRIEF_REL)
WHOAMI_REL = ".pair/whoami"
SETUP_REPORT_REL = "docs/reviews/setup-verification.md"
# 契约审查结论的最小长度。门槛不高,但足以挡住空文件和一句话敷衍。
MIN_SETUP_REPORT_CHARS = 120

# --- 记忆层 -----------------------------------------------------------
# 两个 agent 不共享对话,也不共享各自厂商的记忆。项目知识只能沉在仓库里,
# 并且必须在**固定时刻**被重新读出来 —— 存了没人读等于没存。
#
#   docs/notes/<ID>.md   工作项级,随手写,记负空间(试过什么没成/否掉了什么)
#   docs/DECISIONS.md    项目级,追加式,记结论与裁决
#
# 召回点是 status:它是协议强制的第一条命令,也是唯一能跨 harness 保证的时机。

# 单条决策的长度上限。这条不是洁癖 —— 决策记录会被注入到此后每一次 status,
# 长了就没人读,然后整套机制退化成又一份没人看的文档。
MAX_DECISION_CHARS = 1500
# 注入上限,防止记忆层反过来吃掉上下文
MAX_NOTE_INJECT_CHARS = 3000
MAX_DECISION_INJECT_CHARS = 2000
MAX_DECISION_INJECT_ENTRIES = 5
# refactor 考古记录每个小节的正文下限
MIN_NOTE_SECTION_CHARS = 40
# 笔记超过这个长度,工作项完成时触发"要不要晋升成决策"的强制选择
MIN_NOTE_PROMOTE_CHARS = 80

ARCHAEOLOGY_SECTIONS = ("现状考古", "我保留了哪些契约外行为", "我不确定的地方")
# cover 的特征测试记录。特征测试的固有风险是**把缺陷一起焊死** —— 你照着
# 现状写断言,而现状里可能有 bug。第二节就是为这件事存在的。
COVER_SECTIONS = ("行为来源", "我冻结了哪些可疑行为")
DECISION_FIELDS = ("理由", "已否决", "影响路径")

DEFAULT_STATE = {
    "round": 0,
    "phase": "idle",
    "item": None,
    "item_type": None,
    "last_actor": None,
    "changes_count": 0,
    "completed_items": [],
    "setup_verified": False,
    "deadlock_hits": [],
    # claim 时记下契约的 blob sha。工作项完成时若它变了,说明这轮发生过
    # 契约变更 —— 那是最值得留下理由的时刻。老状态里没有这个键,取默认
    # None,检查自动跳过,存量仓库零成本升级。
    "contract_sha": None,
    # 上一次交接是不是一次**打回**(异议或评审 changes)。打回之后回到 spec 时,
    # dev 的实现往往已经随之前的交接落地了 —— tester 按打回意见改完测试,
    # 套件整体就是绿的,而 feature 的 spec 要求 RED。不记这一笔,
    # "打回 → 修正"这条路会在下一回合把自己卡死。
    "after_rebound": False,
}

# `- [ ] **W1** [bug] — 标题`,类型可省略(缺省 feature)
ITEM_RE = re.compile(
    r"^(?P<pre>\s*-\s*\[)(?P<mark>[ xX])(?P<mid>\]\s*\*\*)(?P<id>[^*]+)(?P<close>\*\*)"
    r"(?P<typ>\s*\[(?P<typename>[a-z]+)\])?(?P<post>.*)$")

PROG_HINT = ".agents/skills/pair-protocol/scripts/pair.py"


# --------------------------------------------------------------------------
# 基础设施
# --------------------------------------------------------------------------

def die(msg, code=1):
    sys.stderr.write("\n[结对协议] %s\n\n" % msg)
    sys.exit(code)


def git(*args, cwd=None, check=True):
    proc = subprocess.run(("git",) + args, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        if check:
            die("git %s 失败:\n%s" % (" ".join(args),
                                      proc.stderr.decode("utf-8", "replace")))
        return None
    return proc.stdout.decode("utf-8", "replace")


def repo_root(start=None):
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          cwd=str(start) if start else None,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        die("这里不是 git 仓库。结对协议依赖 git 做交接。")
    return Path(proc.stdout.decode("utf-8").strip())


def load_config(root, required=True):
    p = root / CONFIG_REL
    if not p.exists():
        if not required:
            return None
        die("找不到 %s。本仓库尚未初始化结对协议。\n"
            "先跑:python3 %s init" % (CONFIG_REL, PROG_HINT))
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die("%s 不是合法 JSON:%s" % (CONFIG_REL, e))
    cfg.setdefault("roles", {"tester": ["tests"], "dev": ["src"]})
    cfg.setdefault("shared_paths", ["docs/reviews"])
    cfg.setdefault("frozen_paths", [])
    cfg.setdefault("ignore_paths", [])
    # 本轮结对能碰的范围。空 = 不限。存量项目最危险的不是结构不合适,
    # 是蔓延:改一个计费 bug 顺手动了三个公共工具类。
    cfg.setdefault("scope", [])
    # 全量套件。只在工作项完成时跑一次,只报告不阻断。存在的理由是允许
    # test_cmd 收窄到本轮范围(存量项目的老套件可能红、可能极慢),
    # 同时不让范围之外的回归悄无声息。
    cfg.setdefault("full_test_cmd", None)
    cfg.setdefault("plan_file", "docs/PLAN.md")
    cfg.setdefault("contract_file", "docs/CONTRACT.md")
    cfg.setdefault("sync", False)
    cfg.setdefault("require_setup_verification", True)
    cfg.setdefault("notes_dir", "docs/notes")
    cfg.setdefault("decisions_file", "docs/DECISIONS.md")
    cfg.setdefault("memory", True)
    if STATE_REL not in cfg["frozen_paths"]:
        cfg["frozen_paths"].append(STATE_REL)
    return cfg


def load_state(root):
    p = root / STATE_REL
    if not p.exists():
        return dict(DEFAULT_STATE)
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die("%s 不是合法 JSON:%s\n状态文件已损坏,需要人类修复。" % (STATE_REL, e))
    merged = dict(DEFAULT_STATE)
    merged.update(st)
    if merged["phase"] not in PHASE_OWNER:
        die("%s 里的 phase='%s' 非法。状态文件已损坏,需要人类修复。"
            % (STATE_REL, merged["phase"]))
    # v0 状态迁移:没有 item 却停在 spec,视为 idle
    if merged["phase"] == "spec" and not merged["item"]:
        merged["phase"] = "idle"
    return merged


def save_state(root, state):
    p = root / STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


# --------------------------------------------------------------------------
# 路径匹配 —— 支持目录前缀、glob 与 `!` 负模式
# --------------------------------------------------------------------------

_GLOB_CHARS = "*?["


def _glob_to_regex(pattern):
    """`**` 匹配任意层级(含 0 层),`*` 单层内任意字符,`?` 单字符。"""
    out = ["^"]
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**", i):
                i += 2
                if pattern.startswith("/", i):     # `**/` 可匹配零层
                    i += 1
                    out.append("(?:[^/]+/)*")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i)
            if j < 0:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1:j]
                body = ("^" + body[1:]) if body.startswith("!") else body
                out.append("[" + body + "]")
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


_RE_CACHE = {}


def path_matches(path, pattern):
    """单个模式。不含通配符时按目录前缀语义(向后兼容 v0 配置)。"""
    if not any(c in pattern for c in _GLOB_CHARS):
        p, q = PurePosixPath(path), PurePosixPath(pattern)
        return p == q or q in p.parents
    rx = _RE_CACHE.get(pattern)
    if rx is None:
        rx = _RE_CACHE[pattern] = _glob_to_regex(pattern)
    return bool(rx.match(path))


def matches_any(path, patterns):
    """命中至少一个正模式,且不命中任何 `!` 负模式。"""
    hit = False
    for pat in patterns:
        if pat.startswith("!"):
            if path_matches(path, pat[1:]):
                return False
        elif path_matches(path, pat):
            hit = True
    return hit


# --------------------------------------------------------------------------
# 角色解析
# --------------------------------------------------------------------------

ROLE_HELP = """无法确定你的角色,已停止。

这不是你能自己解决的问题,请把下面的内容告诉人类:

  结对协议需要知道我扮演哪个角色。三种配置方式任选其一:

  1. 环境变量(适合从终端启动的 agent):
       PAIR_ROLE=tester <你的 agent 命令>
       PAIR_ROLE=dev    <你的 agent 命令>

  2. 写入 .pair/whoami(适合 GUI / 云端 agent,该文件已被 gitignore,
     要求两个 agent 各自使用独立的工作副本):
       echo tester > .pair/whoami

  3. 用 git 分支名(适合 worktree 拓扑):
       git switch -c pair/tester
"""


def resolve_role(root):
    env = os.environ.get("PAIR_ROLE", "").strip()
    if env:
        if env not in ROLES:
            die("PAIR_ROLE='%s' 无效,只能是 tester 或 dev。" % env)
        return env, "PAIR_ROLE 环境变量"

    whoami = root / WHOAMI_REL
    if whoami.exists():
        val = whoami.read_text(encoding="utf-8").strip()
        if val not in ROLES:
            die("%s 内容为 '%s',无效,只能是 tester 或 dev。" % (WHOAMI_REL, val))
        return val, WHOAMI_REL

    branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root, check=False)
    if branch:
        m = re.fullmatch(r"pair/(tester|dev)", branch.strip())
        if m:
            return m.group(1), "git 分支名 %s" % branch.strip()

    die(ROLE_HELP)


# --------------------------------------------------------------------------
# git 工作区
# --------------------------------------------------------------------------

def changed_entries(root):
    """[(xy, path)]。用 -z 输出,绕开中文/空格路径的转义问题。"""
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=root)
    parts = out.split("\0")
    entries, i = [], 0
    while i < len(parts):
        rec = parts[i]
        if not rec:
            i += 1
            continue
        xy, path = rec[:2], rec[3:]
        entries.append((xy, path))
        i += 2 if ("R" in xy or "C" in xy) else 1
    return entries


def tracked_files(root):
    out = git("ls-files", "-z", cwd=root, check=False) or ""
    return [p for p in out.split("\0") if p]


def writable_paths(cfg, phase):
    """按角色 + 阶段计算可写路径。评审阶段只读:仅允许写评审记录与记忆层。

    记忆层的路径**不能**并进 shared_paths —— 异议举证检查(见 handoff)靠
    "本回合是否写了 shared_paths 下的文件"来判断异议有没有落到纸面,把随手
    写的笔记算进去,那条防护就被静默削掉了。
    """
    shared = list(cfg["shared_paths"])
    if memory_on(cfg):
        shared = shared + [cfg["notes_dir"], cfg["decisions_file"]]
    if phase in REVIEW_PHASES or phase == "idle":
        return shared
    return list(cfg["roles"][PHASE_OWNER[phase]]) + shared


def run_tests(root, cfg, cmd=None, log_rel=None):
    cmd = cmd or os.environ.get("PAIR_TEST_CMD") or cfg.get("test_cmd")
    if not cmd:
        die("未配置 test_cmd。请编辑 %s 填入本项目的测试命令。" % CONFIG_REL)
    log = root / (log_rel or TESTLOG_REL)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as f:
        rc = subprocess.call(cmd, shell=True, cwd=str(root),
                             stdout=f, stderr=subprocess.STDOUT)
    return rc == 0


def state_is_tampered(root):
    """state.json 在工作区里被改动过 = agent 动了它。脚本只在提交前一刻写它。"""
    return any(p == STATE_REL for _, p in changed_entries(root))


def restore_state(root):
    return git("checkout", "HEAD", "--", STATE_REL, cwd=root, check=False) is not None


# --------------------------------------------------------------------------
# PLAN.md
# --------------------------------------------------------------------------

def parse_plan(root, cfg):
    """[(id, type, done, lineno)]"""
    p = root / cfg["plan_file"]
    if not p.exists():
        return []
    items = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        m = ITEM_RE.match(line)
        if m:
            items.append((m.group("id").strip(),
                          (m.group("typename") or "feature"),
                          m.group("mark") in "xX", n))
    return items


def tick_plan_item(root, cfg, item_id):
    """脚本可以改冻结文件,agent 不可以。"""
    p = root / cfg["plan_file"]
    if not p.exists():
        return False
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    for n, line in enumerate(lines):
        m = ITEM_RE.match(line.rstrip("\n"))
        if m and m.group("id").strip() == item_id:
            nl = "\n" if line.endswith("\n") else ""
            lines[n] = (m.group("pre") + "x" + m.group("mid") + m.group("id")
                        + m.group("close") + (m.group("typ") or "")
                        + m.group("post") + nl)
            p.write_text("".join(lines), encoding="utf-8")
            return True
    return False


def plan_all_done(root, cfg):
    items = parse_plan(root, cfg)
    return bool(items) and all(done for _, _, done, _ in items)


def flow_of(item_type):
    return FLOWS.get(item_type or "feature", FEATURE_FLOW)


# --------------------------------------------------------------------------
# 记忆层 —— 笔记(工作项级)与决策记录(项目级)
# --------------------------------------------------------------------------

# `## W1 — 一句话结论`。分隔符宽容一点:全角破折号、半角连字符都收。
DECISION_HEAD_RE = re.compile(
    r"^##[ \t]+(?P<id>\S+)[ \t]*[—–-]{1,2}[ \t]*(?P<title>.+?)[ \t]*$", re.M)
_FIELD_LINE_RE = re.compile(
    r"^\s*[-*]\s*(理由|已否决|影响路径)\s*[::]\s*(.*)$")

DECISION_FORMAT_HINT = """条目格式(四个字段缺一不可):

  ## <工作项ID> — <一句话结论>

  - 理由: <为什么是这个结论,具体到会导致什么错误行为>
  - 已否决: <考虑过但放弃的方案和放弃原因 —— 这是本文件最值钱的字段>
  - 影响路径: `src/foo.py`, `tests/test_foo.py`

`影响路径` 是检索键:今后谁要动这些路径,status 会自动把这条结论摆到他面前。
故意没有"分析"字段 —— 只共享事实和裁决,不共享推理过程。"""


def memory_on(cfg):
    return bool(cfg.get("memory", True))


def _read(p):
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _clip_tail(text, limit):
    """保留尾部 —— 笔记是往后追加的,新的更相关。"""
    if len(text) <= limit:
        return text
    return "…（前文已截断,完整内容见文件）\n" + text[-limit:]


def notes_path(root, cfg, item):
    return root / cfg["notes_dir"] / ("%s.md" % item)


def blob_sha(root, path):
    out = git("rev-parse", "HEAD:%s" % path, cwd=root, check=False)
    return out.strip() if out else None


def decisions_at_head(root, cfg):
    """决策记录在上一次提交时的样子。追加式校验的基准。"""
    return git("show", "HEAD:%s" % cfg["decisions_file"],
               cwd=root, check=False) or ""


def parse_decisions(text):
    """[(id, title, body, start, end)]"""
    heads = list(DECISION_HEAD_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group("id").strip(), m.group("title").strip(),
                    text[m.end():end], m.start(), end))
    return out


def parse_decision_fields(body):
    fields, cur = {}, None
    for line in body.splitlines():
        m = _FIELD_LINE_RE.match(line)
        if m:
            cur = m.group(1)
            fields[cur] = m.group(2).strip()
        elif cur and line.strip() and not line.lstrip().startswith("#"):
            fields[cur] = (fields[cur] + " " + line.strip()).strip()
        elif not line.strip():
            cur = None
    return fields


def decision_paths(body):
    raw = parse_decision_fields(body).get("影响路径") or ""
    return [t.strip().strip("`,,、") for t in re.split(r"[\s,,、]+", raw)
            if t.strip().strip("`,,、")]


def validate_decision(title, body):
    problems = []
    if not title:
        problems.append("标题里没有结论。`## <ID> — <一句话结论>` 的结论部分不能空")
    fields = parse_decision_fields(body)
    for name in DECISION_FIELDS:
        if not fields.get(name):
            problems.append("缺少 `- %s:` 字段,或它是空的" % name)
    size = len(title) + len(body)
    if size > MAX_DECISION_CHARS:
        problems.append(
            "条目 %d 字符,超过上限 %d。这条结论此后每一次 status 都会被读一遍,"
            "长了就没人读 —— 压缩到结论和理由本身,过程不要写进来"
            % (size, MAX_DECISION_CHARS))
    return problems


def new_decision_entries(root, cfg):
    """本回合新追加的条目。靠"偏移量在旧内容之后"判定,所以同一工作项
    追加第二条也算新的 —— 用 id 去重会漏掉那种情况。"""
    old = decisions_at_head(root, cfg)
    cur = _read(root / cfg["decisions_file"])
    return [e for e in parse_decisions(cur) if e[3] >= len(old)]


def missing_note_sections(root, cfg, item, sections):
    """笔记里缺了哪些必需小节。脚本判不了内容,但能强制交出结构。"""
    text = _read(notes_path(root, cfg, item))
    missing = []
    for name in sections:
        m = re.search(r"^#{2,}\s*%s\s*$" % re.escape(name), text, re.M)
        if not m:
            missing.append("缺少小节 `## %s`" % name)
            continue
        rest = text[m.end():]
        nxt = re.search(r"^#{1,6}\s", rest, re.M)
        body = (rest[:nxt.start()] if nxt else rest).strip()
        if len(body) < MIN_NOTE_SECTION_CHARS:
            missing.append("小节 `## %s` 正文只有 %d 字,不足 %d"
                           % (name, len(body), MIN_NOTE_SECTION_CHARS))
    return missing


# 阶段 -> 本阶段"被生产或被评审的东西"属于谁。决策记录按这个求交集召回:
# review-impl 是 tester 在看 dev 的代码,相关的是 dev 的路径。
PHASE_SUBJECT = {
    "spec": "tester", "review-test": "tester",
    "impl": "dev", "review-impl": "dev",
}


def subject_paths(cfg, phase):
    role = PHASE_SUBJECT.get(phase)
    if role is None:
        return list(cfg["roles"]["tester"]) + list(cfg["roles"]["dev"])
    return list(cfg["roles"][role])


def relevant_decisions(root, cfg, state, phase):
    """与本回合相关的决策:同一工作项的,或影响路径落在本阶段主体上的。

    纯路径求交,不做语义检索 —— 这套协议连 LLM 的红绿判断都不信,
    更不该把召回押在检索命中率上。
    """
    entries = parse_decisions(_read(root / cfg["decisions_file"]))
    subj = subject_paths(cfg, phase)
    picked = []
    for eid, title, body, _, _ in entries:
        if eid == state["item"] or any(matches_any(p, subj)
                                       for p in decision_paths(body)):
            picked.append((eid, title, body))
    return picked[-MAX_DECISION_INJECT_ENTRIES:]


def memory_brief(root, cfg, state, phase):
    """status 注入的记忆块。这是整套机制里唯一的召回时机。"""
    if not memory_on(cfg):
        return ""
    out = []
    item = state["item"]
    if item:
        note = _read(notes_path(root, cfg, item)).strip()
        rel = "%s/%s.md" % (cfg["notes_dir"], item)
        if note:
            out.append("--- 本工作项笔记 (%s) ---" % rel)
            out.append(_clip_tail(note, MAX_NOTE_INJECT_CHARS))
        else:
            out.append("--- 本工作项还没有笔记 (%s) ---" % rel)
            out.append("发现了什么就随手写进去:试过什么没成、否掉了什么、"
                       "哪里拿不准。\n对方看不到你的推导过程,不写下来就是重新推一遍。")
    picked = relevant_decisions(root, cfg, state, phase)
    if picked:
        body = []
        for eid, title, text in picked:
            body.append("## %s — %s%s" % (eid, title, text.rstrip()))
        joined = "\n".join(body)
        if len(joined) > MAX_DECISION_INJECT_CHARS:
            joined = joined[:MAX_DECISION_INJECT_CHARS] + \
                "\n…（已截断,完整内容见 %s）" % cfg["decisions_file"]
        out.append("--- 相关决策 (%s) ---" % cfg["decisions_file"])
        out.append(joined)
    return "\n".join(out)


def check_memory(root, cfg, state, phase, verdict, target, args):
    """记忆层门禁。返回拒绝理由;None 表示放行。"""
    if not memory_on(cfg):
        return None
    item = state["item"]
    dfile = cfg["decisions_file"]

    # --- 追加式:能往后加,不能改历史 -----------------------------------
    old = decisions_at_head(root, cfg)
    if old and not _read(root / dfile).startswith(old):
        return ("拒绝交接 —— 你改动了 %s 里已经写下的内容。\n\n"
                "决策记录是追加式的。已有条目是双方共识的凭据,改它等于伪造共识,\n"
                "和手工改 %s 同级。\n\n"
                "要推翻旧结论,**追加**一条新条目说明为什么推翻,不要动旧的。"
                % (dfile, STATE_REL))

    fresh = new_decision_entries(root, cfg)

    # --- 写了东西却没构成条目 -------------------------------------------
    # 最坏的结果不是被拒绝,是写下去却没人认得 —— agent 以为自己记录了,
    # 而 status 永远召回不到它。宁可在这里吵一次。
    added = _read(root / dfile)[len(old):].strip()
    if added and not fresh:
        return ("拒绝交接 —— 你往 %s 写了内容,但它不构成一条决策条目,\n"
                "解析不出来的东西 status 永远召回不到,等于没写。\n\n"
                "(如果这只是 init 刚铺下的骨架,让人类先把它提交进去。)\n\n%s"
                % (dfile, DECISION_FORMAT_HINT))

    # --- 新条目必须结构完整、足够短 -------------------------------------
    for eid, title, body, _, _ in fresh:
        problems = validate_decision(title, body)
        if problems:
            return ("拒绝交接 —— %s 里的新条目「%s」不合格:\n  - %s\n\n%s"
                    % (dfile, eid or "(无ID)", "\n  - ".join(problems),
                       DECISION_FORMAT_HINT))

    mine = [e for e in fresh if e[0] == item]

    # --- refactor 的考古记录 --------------------------------------------
    # 重构回合里 tester 要判断的是"行为有没有被悄悄改掉",而测试全程是绿的,
    # 契约写的是目标不是现状 —— 它手上本来什么都没有。做过考古的是 dev,
    # 所以由 dev 在交接时把考古结论交出来。
    if state["item_type"] == "refactor" and phase == "impl" and verdict is None:
        miss = missing_note_sections(root, cfg, item, ARCHAEOLOGY_SECTIONS)
        if miss:
            return ("拒绝交接 —— [refactor] 的实现回合必须交出考古记录。\n\n"
                    "%s 还缺:\n  - %s\n\n"
                    "需要三个小节,每节正文至少 %d 字:\n"
                    "  ## 现状考古\n"
                    "      这段代码为什么长成现在这样。你读代码时发现的、"
                    "但任何文档里都没写的事。\n"
                    "  ## 我保留了哪些契约外行为\n"
                    "      测试没覆盖、契约没写明,但你判断必须保住的行为。\n"
                    "  ## 我不确定的地方\n"
                    "      你拿不准会不会改变行为的地方。写下来,让对方重点看这里。\n\n"
                    "对方全程看的是绿色的测试 —— 你不写,它就只能凭 diff 猜。"
                    % ("%s/%s.md" % (cfg["notes_dir"], item),
                       "\n  - ".join(miss), MIN_NOTE_SECTION_CHARS))

    # --- cover 的特征测试记录 --------------------------------------------
    # cover 是"给已经能跑的行为补测试" —— 你照着现状写断言,而现状里可能有
    # bug。特征测试的固有风险就是**把缺陷一起焊死**,而且红绿抓不到它:
    # 全程都是绿的。所以由写测试的人交出这两节,让评审方有的可查。
    if state["item_type"] == "cover" and phase == "spec" and verdict is None:
        miss = missing_note_sections(root, cfg, item, COVER_SECTIONS)
        if miss:
            return ("拒绝交接 —— [cover] 的 spec 回合必须交出特征测试记录。\n\n"
                    "%s 还缺:\n  - %s\n\n"
                    "需要两个小节,每节正文至少 %d 字:\n"
                    "  ## 行为来源\n"
                    "      你怎么确认它当前就是这样的:读了哪段代码、跑了什么、"
                    "看到了什么输出。\n"
                    "      契约里没写这条行为时,这就是断言的唯一依据。\n"
                    "  ## 我冻结了哪些可疑行为\n"
                    "      看着像 bug、但你照原样固化进测试的行为。没有就写"
                    "\"没有,逐条对过契约\"。\n\n"
                    "第二节是要害:特征测试会把缺陷一起焊死,而全程绿的红绿不变量\n"
                    "抓不到这件事。对方在 review-test 要回答的正是"
                    "\"这行为是有意的,\n还是我们刚把一个缺陷变成了规格\" —— "
                    "你不写,它无从判断。"
                    % ("%s/%s.md" % (cfg["notes_dir"], item),
                       "\n  - ".join(miss), MIN_NOTE_SECTION_CHARS))

    # --- 第二次打回:分歧是真的,留下结论 --------------------------------
    # 只卡第二次:第一次可能只是笔误,第三次有死锁闸接管并交给人类,
    # 在那里再要一份文档只是噪音。
    if verdict == "changes" and state["changes_count"] + 1 == 2 and not mine:
        return ("拒绝交接 —— 「%s」这是第 %d 次打回,必须在 %s 里留下一条结论。\n\n"
                "来回两次说明这不是笔误,是真实分歧。不写下来,第三次打回会撞上\n"
                "死锁闸,而人类到时候翻不到你们到底在争什么。\n\n"
                "%s"
                % (item, state["changes_count"] + 1, dfile,
                   DECISION_FORMAT_HINT))

    if target == "DONE":
        # --- 契约在本工作项期间被改过 -----------------------------------
        cur_sha = blob_sha(root, cfg["contract_file"])
        if (state.get("contract_sha") and cur_sha
                and cur_sha != state["contract_sha"] and not mine):
            return ("拒绝交接 —— %s 在这个工作项期间被改过,但 %s 里没有对应记录。\n\n"
                    "契约变更是重新推导代价最高的事:今后每个新回合都会拿改过的\n"
                    "契约当作理所当然,而改它的理由谁都看不到了。\n\n"
                    "追加一条 `## %s — …`,写清楚原来是什么、为什么不行、改成了什么。\n\n"
                    "%s" % (cfg["contract_file"], dfile, item,
                            DECISION_FORMAT_HINT))

        # --- 晋升 gate:笔记要随工作项一起沉底,给它一次留下的机会 -------
        note = _read(notes_path(root, cfg, item)).strip()
        if len(note) >= MIN_NOTE_PROMOTE_CHARS and not mine and not args.no_decision:
            return ("拒绝交接 —— 工作项「%s」要完成了,但它的笔记还没被处理。\n\n"
                    "笔记是工作项级的:这一项关掉之后,没有任何回合会再读到它。\n"
                    "现在是它变成长期资产的唯一时机。二选一:\n\n"
                    "  1. 有值得留下的结论 —— 追加一条 `## %s — …` 到 %s\n"
                    "  2. 确实没有 —— 显式声明:\n"
                    "       python3 %s handoff approve \"理由\" --no-decision \"为什么没有\"\n\n"
                    "声明会进提交记录,人类看得见。这不是放行,是强制留痕。\n\n"
                    "%s" % (item, item, dfile, PROG_HINT, DECISION_FORMAT_HINT))
    return None


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

PHASE_BRIEF = {
    "idle": """  当前没有进行中的工作项。从 %(plan)s 挑一个认领:

    python3 %(prog)s claim <ID>

  认领后会根据工作项类型进入对应的起始阶段。""",

    "spec": """  按 %(contract)s 的接口签名写测试。

  硬约束:
    - 只能写:%(paths)s
    - 只断言契约里的可观测行为,禁止断言私有方法名/调用次数
    - 不许删除已有测试。确需删除要显式带 --allow-deletion "理由"
%(redgreen)s%(notes)s
  完成后: python3 %(prog)s handoff "一句话说明这个用例在验证什么\"""",

    "impl": """  写实现。

  硬约束:
    - 只能写:%(paths)s
    - 禁止修改或删除任何测试。认为测试写错了 -> 写异议到 docs/reviews/,
      用 handoff changes "理由" 打回,由测试方修
    - 禁止针对测试输入硬编码返回值来蒙混过关
%(redgreen)s%(notes)s
  完成后: python3 %(prog)s handoff "一句话说明你怎么实现的\"""",

    "review-impl": """  审查对方的实现。跑 inbox 看 diff。

  重点查:
    - 有没有针对测试输入特判/硬编码
    - 有没有偏离 %(contract)s
    - 有没有明显未覆盖的边界情况

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  【裁决必须带证据】先找问题,再决定通过与否。你的价值就在于挑刺 ——
  互相点头等于这个项目白做。交出至少一处你找到的问题,或者你具体查过
  哪些地方、为什么认为那里没问题。

    打回 -> python3 %(prog)s handoff changes "问题清单,至少一处 路径:行号"
    通过 -> python3 %(prog)s handoff approve "摘要"
                --checked "你具体检查了什么" --uncovered "还没覆盖到什么\"""",

    "review-test": """  审查对方的测试。跑 inbox 看 diff。

  重点查:
    - 有没有断言私有实现细节,导致测试变成变更探测器
    - 覆盖是否够(边界值、错误路径)
    - %(cover_hint)s

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  【裁决必须带证据】先找问题,再决定通过与否。你的价值就在于挑刺 ——
  互相点头等于这个项目白做。交出至少一处你找到的问题,或者你具体查过
  哪些地方、为什么认为那里没问题。

    打回 -> python3 %(prog)s handoff changes "问题清单,至少一处 路径:行号"
    通过 -> python3 %(prog)s handoff approve "摘要"
                --checked "你具体检查了什么" --uncovered "还没覆盖到什么\"""",
}


def _brief_vars(cfg, state, phase):
    flow = flow_of(state["item_type"])
    expect = flow["expect"].get(phase)
    if phase == "spec" and expect == "RED":
        rg = "    - 交接前测试必须是 RED。绿着交接会被拒绝。\n"
    elif phase == "spec" and expect == "GREEN":
        rg = ("    - 本项是 cover 类型:测试应当通过(GREEN)。\n"
              "      但必须真的新增了测试,空手交接会被拒绝。\n"
              "      如果新测试变红,说明你发现了真实缺陷 —— 告诉人类改成 [bug] 类型。\n")
    elif phase == "impl" and expect == "GREEN":
        rg = "    - 交接前测试必须 GREEN。\n"
    else:
        rg = ""
    if not memory_on(cfg):
        notes = ""
    elif state["item_type"] == "refactor" and phase == "impl":
        notes = ("    - **本项是 refactor,交接前必须交出考古记录**:%s/%s.md,\n"
                 "      三个小节 —— 现状考古 / 我保留了哪些契约外行为 / 我不确定的地方。\n"
                 "      对方全程看的是绿色的测试,你不写它就只能凭 diff 猜。\n"
                 % (cfg["notes_dir"], state["item"]))
    else:
        notes = ("    - 发现什么就随手记进 %s/%s.md:试过什么没成、否掉了什么、\n"
                 "      哪里拿不准。记负空间,不用复述 diff。\n"
                 % (cfg["notes_dir"], state["item"] or "<ID>"))
    return {
        "plan": cfg["plan_file"],
        "contract": cfg["contract_file"],
        "paths": " ".join(writable_paths(cfg, phase)),
        "prog": PROG_HINT,
        "redgreen": rg,
        "notes": notes,
        "cover_hint": ("这条测试真的能发现回归吗(cover 类型的核心问题)"
                       if state["item_type"] == "cover"
                       else "用例是否真的对应 PLAN 里的工作项"),
    }


def render_brief(me, state, green):
    """回合简报的正文。格式由契约逐字节钉死,见 docs/pair-run/CONTRACT.md。"""
    item = state["item"]
    if item:
        # 类型为空时按 feature 算 —— flow_of(None) 就是这么解释的,协议其余
        # 部分一律跟着它走。不这样写,v0 迁移过来的状态(没有 item_type 这个键)
        # 会写出裸 ID,而契约只给了 `<ID> [<类型>]` 和 `(无)` 两种形态。
        item = "%s [%s]" % (item, state["item_type"] or "feature")
    return "".join(
        line + "\n" for line in [
            "# 回合简报",
            "",
            "- 角色: %s" % me,
            "- 工作项: %s" % (item or "(无)"),
            "- 阶段: %s" % state["phase"],
            "- 测试: %s" % ("GREEN" if green else "RED"),
        ])


def write_brief(root, text):
    """把简报落盘。status 每回合注入给 agent 的东西只活在那一次终端输出里,
    agent 说"我没看到那条决策"时人类无从对质 —— 这个文件就是对质的凭据。"""
    (root / BRIEF_REL).write_text(text, encoding="utf-8")


def cmd_status(root, cfg, args):
    if cfg.get("sync"):
        if git("pull", "--rebase", cwd=root, check=False) is None:
            die("git pull --rebase 失败,无法确认你看到的是最新状态。\n"
                "sync 模式下两个 agent 各有一份工作副本,拉不下来就可能在陈旧的\n"
                "回合上动手。请把这个情况告诉人类,不要继续。")

    me, source = resolve_role(root)
    state = load_state(root)
    phase = state["phase"]
    owner = PHASE_OWNER[phase]

    tampered = state_is_tampered(root)
    green = run_tests(root, cfg)

    role_hint = "写测试,不写实现" if me == "tester" else "写实现,不写测试"
    item_label = state["item"] or "（无,等待认领）"
    if state["item"] and state["item_type"]:
        item_label += "  [%s]" % state["item_type"]

    print("=" * 52)
    print(" 你的角色 : %s  (%s)" % (me, role_hint))
    print(" 角色来源 : %s" % source)
    print(" 当前工作项: %s" % item_label)
    print(" 当前阶段 : %s   → 归属: %s" % (phase, owner))
    print(" 测试状态 : %s   (详见 %s)" % ("GREEN" if green else "RED", TESTLOG_REL))
    print(" 可写路径 : %s" % " ".join(writable_paths(cfg, phase)))
    print(" 已完成项 : %d" % len(state["completed_items"]))
    if state["deadlock_hits"]:
        print(" 曾触发死锁闸: %s" % "、".join(state["deadlock_hits"]))
    print("=" * 52)

    if tampered:
        print()
        print(">>> 警告:%s 被修改过。<<<" % STATE_REL)
        print("协议状态文件由脚本维护,任何人手工修改都是违规的。")
        print("下次 handoff 会拒绝交接并还原它。")

    if cfg["require_setup_verification"] and not state["setup_verified"]:
        print()
        print(">>> 尚未通过开工前校验。<<<")
        print("结对的一方(通常是还没动手的那个)需要先跑:")
        print("  python3 %s verify-setup" % PROG_HINT)
        print("在此之前不能认领工作项。")

    # 轮到自己就写,与后面还打不打印阶段简报无关 —— PLAN 全部完成时
    # 这个函数会提前 return,而契约要求那种情况下简报照写。
    if me == owner:
        write_brief(root, render_brief(me, state, green))

    if plan_all_done(root, cfg):
        print()
        print(">>> %s 里的工作项已全部完成。<<<" % cfg["plan_file"])
        print("请向人类报告项目已完成,不要继续认领新工作项。")
        return 0

    if me != owner:
        print()
        print(">>> 现在不是你的回合。<<<")
        print()
        print("不要修改任何文件。跑 inbox 看对方上一回合做了什么,")
        print("然后向人类报告\"等待 %s 完成 %s 阶段\",并停止。" % (owner, phase))
        print()
        return 0

    print()
    print(">>> 轮到你了。本阶段任务:")
    print()
    print(PHASE_BRIEF[phase] % _brief_vars(cfg, state, phase))
    print()

    # 记忆层召回。status 是协议强制的第一条命令,也是唯一能跨 harness
    # 保证一定被执行的时刻 —— 存了没人读等于没存,所以召回挂在这里。
    mem = memory_brief(root, cfg, state, phase)
    if mem:
        print("=" * 52)
        print(" 你不在场时留下的东西")
        print("=" * 52)
        print(mem)
        print()
    return 0


# --------------------------------------------------------------------------
# claim
# --------------------------------------------------------------------------

def check_item_preconditions(root, cfg, item_id, item_type):
    """认领前的工作项级检查。返回拒绝理由;None 放行。

    verify-setup 已经查过一遍,这里再查是因为**人类可能在那之后动过 PLAN 或
    契约** —— 而这两份都是冻结文件,agent 看不见它们什么时候变的。
    """
    block = next((b for i, _, _, b in _plan_blocks(root, cfg) if i == item_id), "")

    # --- 契约依据:非 cover 的工作项不能建在未经核实的规格上 -----------------
    if item_type != "cover":
        refs = CONTRACT_REF_RE.findall(block)
        sections, dupes = contract_sections(_read(root / cfg["contract_file"]))
        if refs:
            anchor_name = refs[0].strip().strip("`")
            raw, ok = section_provenance(sections.get(anchor_name, ""))
            if anchor_name in dupes:
                return ("拒绝认领 —— 契约里有多个标题都叫「%s」,指向哪一节是歧义的。\n\n"
                        "工作项按标题文本找小节,重名会让它读到另一节的 `依据`。\n"
                        "契约是人类的产物 —— 请交给人类把标题改唯一。" % anchor_name)
            if anchor_name not in sections:
                return ("拒绝认领 —— 契约小节「%s」在 %s 里不存在。\n\n"
                        "现有小节:%s\n\n"
                        "没有契约就没有可断言的东西。多半是 verify-setup 之后"
                        "有人改了标题 —— 契约是人类的产物,请交给人类核对。"
                        % (anchor_name, cfg["contract_file"],
                           "、".join(sorted(sections)) or "(无)"))
            if raw is None:
                return ("拒绝认领 —— 契约小节「%s」没写 `依据`。\n\n"
                        "在小节里加一行 `- 依据: 人类定稿`。\n"
                        "(verify-setup 通过之后契约又被改过才会走到这里 —— "
                        "契约是人类的产物,请交给人类补。)" % anchor_name)
            if not ok:
                return ("拒绝认领 —— 契约小节「%s」的依据是「%s」,不可断言。\n\n"
                        "可断言的依据只有两种:`人类定稿`,或 `考古观察@<sha>`\n"
                        "(agent 真的读过代码、跑过代码之后写下来的)。\n\n"
                        "老文档只能当线索:它写\"返回 null\"而实际代码抛异常时,\n"
                        "tester 会照文档写断言、dev 会以为发现了 bug 去改行为 ——\n"
                        "整条链上每一步都合规,结果是线上炸。\n\n"
                        "正确顺序:先做一个 [cover] 工作项建立事实,人类定稿之后再开这一项。"
                        % (anchor_name, raw or "(没写)"))

    # --- refactor 的安全网 ---------------------------------------------------
    if item_type == "refactor":
        refs = PROTECT_REF_RE.findall(block)
        if not refs:
            return ("拒绝认领 —— [refactor] 必须声明保护它的测试。\n\n"
                    "在 %s 里这个工作项下面加一行:\n"
                    "  - 保护测试: tests/<被重构代码对应的测试目录>\n\n"
                    "重构回合全程是绿的,而绿的测试按定义没抓到任何问题。\n"
                    "那片代码本来就没有测试时,\"绿\"什么都不证明,review-impl\n"
                    "只能凭 diff 猜 —— 这是协议唯一 police 不了的场景。\n\n"
                    "还没有覆盖?先开一个 [cover] 工作项补上。" % cfg["plan_file"])
        target = refs[0].strip().strip("`")
        if not (root / target).exists():
            return ("拒绝认领 —— 保护测试路径不存在:%s\n\n"
                    "路径相对仓库根。写错了改 PLAN(那是人类的事),"
                    "或者先开一个 [cover] 工作项把它建起来。" % target)
        if not matches_any(target, cfg["roles"]["tester"]):
            return ("拒绝认领 —— 保护测试路径 %s 不在 tester 名下(%s)。\n\n"
                    "保护重构的必须是测试。指向实现目录等于没有安全网。"
                    % (target, " ".join(cfg["roles"]["tester"])))
    return None


def cmd_claim(root, cfg, args):
    me, _ = resolve_role(root)
    state = load_state(root)

    if me != "tester":
        die("认领工作项是 tester 的职责,你是 %s。" % me)
    if state["phase"] != "idle":
        die("上一个工作项「%s」还在进行中(阶段 %s),不能认领新的。"
            % (state["item"], state["phase"]))
    if cfg["require_setup_verification"] and not state["setup_verified"]:
        die("尚未通过开工前校验,不能认领工作项。\n"
            "请让结对的另一方先跑:python3 %s verify-setup" % PROG_HINT)

    items = parse_plan(root, cfg)
    if not items:
        die("%s 里没有找到任何工作项。\n"
            "工作项格式必须是:  - [ ] **W1** [bug] — 标题\n"
            "(类型可省略,缺省 feature)" % cfg["plan_file"])

    match = [(i, t, d) for i, t, d, _ in items if i == args.item_id]
    if not match:
        die("%s 里没有工作项 '%s'。\n现有工作项:%s"
            % (cfg["plan_file"], args.item_id,
               ", ".join(i for i, _, _, _ in items)))
    item_id, item_type, done = match[0]
    if done:
        die("工作项 '%s' 已经完成了。请认领一个未完成的。" % item_id)
    if item_type not in ITEM_TYPES:
        die("工作项 '%s' 的类型 '[%s]' 非法。只支持:%s"
            % (item_id, item_type, "、".join(ITEM_TYPES)))

    refusal = check_item_preconditions(root, cfg, args.item_id, item_type)
    if refusal:
        die(refusal)

    if state_is_tampered(root):
        restore_state(root)
        die("你修改了 %s。协议状态由脚本维护,手工修改是违规的。\n"
            "已还原。请重新执行 status 确认真实状态后再认领。" % STATE_REL)

    state["item"] = item_id
    state["item_type"] = item_type
    state["changes_count"] = 0          # 打回计数绑定到工作项
    state["phase"] = flow_of(item_type)["start"]
    # 记下契约此刻的样子。完成时若变了,说明这轮发生过契约变更。
    state["contract_sha"] = blob_sha(root, cfg["contract_file"])
    save_state(root, state)

    # 认领是协议事件,立即提交:留痕,并让状态文件回到"干净",
    # 否则下一次 handoff 的篡改检测会误伤它。
    git("add", "--", STATE_REL, cwd=root)
    git("commit", "-q", "-m",
        "chore(pair): 认领工作项 %s [%s]" % (item_id, item_type), cwd=root)

    print()
    print("[结对协议] 已认领工作项:%s  [%s]" % (item_id, item_type))
    print("  起始阶段: %s  → 归属: %s"
          % (state["phase"], PHASE_OWNER[state["phase"]]))
    if PHASE_OWNER[state["phase"]] != "tester":
        print("  本项从 %s 起步,请告诉人类轮到 %s 了。"
              % (state["phase"], PHASE_OWNER[state["phase"]]))
    print()
    return 0


# --------------------------------------------------------------------------
# 评审证据
# --------------------------------------------------------------------------

# `路径:行号`。评审意见里指认问题的最小形式。不要求后缀 —— Makefile、
# Dockerfile、Go 的可执行入口都没有后缀。真正的把关是下面的"路径必须真实存在"。
LOCATION_RE = re.compile(r"([\w./\-]+):(\d+)")


def _known_path(ref, known):
    """引用的路径是否指向一个真实文件。允许写后缀(`auth.py:42`),但要落在
    路径分隔边界上,免得 `th.py` 匹配到 `auth.py`。"""
    return any(k == ref or k.endswith("/" + ref) for k in known)


def check_review_evidence(root, cfg, phase, verdict, entries, message, args):
    """评审必须带证据。返回拒绝理由;None 表示放行。

    协议里"靠职业操守"占比最高的一处,恰好守着最重要的那道门:脚本此前只校验
    裁决理由非空,而 `approve "看起来不错"` 是非空的。

    Adversarial Review(arXiv:2608.18167)把这个失败模式命名为 false-consensus
    —— agents converge on agreement without sufficient evidence —— 并给出处方:
    异议要少、要结构化、**要有证据支撑**。这里做的就是把"有证据"变成可校验的形状。

    脚本查不了内容,但结构本身就把"看起来不错"挡在门外:它逼你写出具体检查了什么。
    与 --allow-deletion / --no-decision 同一手法 —— 不是放行,是强制留痕。
    """
    if verdict == "approve":
        missing = [name for name, val in (("--checked", args.checked),
                                          ("--uncovered", args.uncovered))
                   if not (val or "").strip()]
        if missing:
            return ("拒绝交接 —— approve 必须交出检查清单,缺少:%s\n\n"
                    "  python3 %s handoff approve \"摘要\" \\\n"
                    "      --checked \"你具体检查了什么\" \\\n"
                    "      --uncovered \"你知道还没被覆盖到的是什么\"\n\n"
                    "示例(rules.md 规则 6 的判例):\n"
                    "  --checked \"hash 函数无特判、cost 取自配置而非常量、"
                    "空密码抛的是契约里写的 ValueError\"\n"
                    "  --uncovered \"超长密码,下轮补测试\"\n\n"
                    "两段都会写进提交记录,对方在 inbox 里必然看到。\n"
                    "确实想不出没覆盖的,`--uncovered \"无\"` —— 那是一句"
                    "被记录在案的明确主张,不是沉默。\n\n"
                    "空手通过是这套协议唯一会致命的失效方式:两个 agent 互相点头,"
                    "红绿全对,而没有任何缺陷被发现。"
                    % ("、".join(missing), PROG_HINT))
        return None

    if verdict != "changes":
        return None

    # 打回:理由或本回合写进 shared_paths 的评审文件里,至少有一处位置引用。
    haystack = [message]
    for xy, path in entries:
        if "D" not in xy and matches_any(path, cfg["shared_paths"]):
            haystack.append(_read(root / path))

    known = set(tracked_files(root)) | {path for _, path in entries}
    refs = [m.group(1) for text in haystack for m in LOCATION_RE.finditer(text)]
    real = [r for r in refs if _known_path(r, known)]

    if not refs:
        return ("拒绝交接 —— 打回必须具体到位置,理由里没有任何 `路径:行号` 引用。\n\n"
                "rules.md 规则 6 的判例:\n"
                "  ✗ \"实现有问题\"\n"
                "  ✓ \"`src/auth.py:42` 对 test@example.com 特判,"
                "换任意其他邮箱就会失败\"\n\n"
                "引用可以写在裁决理由里,也可以写在本回合的 %s 文件里。\n"
                "对方看不到你的对话 —— 指不出位置的意见,它无从下手。"
                % " ".join(cfg["shared_paths"]))

    if not real:
        return ("拒绝交接 —— 你引用的位置指向不存在的文件:%s\n\n"
                "证据要落在真实文件上。请核对路径(相对仓库根),或者直接看 inbox 的 diff。"
                % "、".join(sorted(set(refs))))
    return None


# --------------------------------------------------------------------------
# handoff
# --------------------------------------------------------------------------

def cmd_handoff(root, cfg, args):
    me, _ = resolve_role(root)
    state = load_state(root)
    phase = state["phase"]
    owner = PHASE_OWNER[phase]
    item = state["item"]
    flow = flow_of(state["item_type"])

    # 回合归属先判:idle 时归 tester,dev 在这里应该看到"不是你的回合",
    # 而不是一句它无权执行的"去认领工作项"。
    if me != owner:
        die("现在是 %s 的 %s 回合,不是你(%s)的。不要提交。" % (owner, phase, me))
    if plan_all_done(root, cfg):
        die("%s 里的工作项已全部完成,协议已停止轮转。\n"
            "请向人类报告项目完成。" % cfg["plan_file"])
    if phase == "idle":
        die("还没有认领工作项,没有可交接的回合。先跑:\n"
            "  python3 %s claim <ID>\n工作项列在 %s 里。"
            % (PROG_HINT, cfg["plan_file"]))

    # --- 状态文件篡改检查(先于一切) --------------------------------------
    if state_is_tampered(root):
        restored = restore_state(root)
        die("你修改了 %s。\n\n"
            "协议状态由脚本维护,手工修改它等于伪造回合归属,是严重违规。\n"
            "%s\n"
            "本次交接已拒绝。请重新执行 status 确认真实回合后再继续。"
            % (STATE_REL, "已自动还原为上次提交的版本。" if restored
               else "无法自动还原(该文件尚未被提交过),请交给人类处理。"))

    # --- 解析裁决 ---------------------------------------------------------
    verdict = None
    if phase in REVIEW_PHASES:
        if not args.words or args.words[0] not in ("approve", "changes"):
            die("评审阶段必须给出裁决:\n"
                "  python3 %s handoff changes \"问题清单,至少一处 路径:行号\"\n"
                "  python3 %s handoff approve \"摘要\""
                " --checked \"查了什么\" --uncovered \"还没覆盖什么\""
                % (PROG_HINT, PROG_HINT))
        verdict = args.words[0]
        message = " ".join(args.words[1:]).strip()
        if not message:
            die("裁决必须附理由。禁止空手通过。")
    elif args.words and args.words[0] == "changes" and phase in DISPUTE_PHASES:
        verdict = "changes"
        message = " ".join(args.words[1:]).strip()
        if not message:
            die("提出异议必须附理由:\n"
                "  python3 %s handoff changes \"这条测试哪里和契约矛盾\"" % PROG_HINT)
    elif args.words and args.words[0] == "approve":
        die("approve 只用于评审阶段,当前是 %s 阶段。" % phase)
    else:
        message = " ".join(args.words).strip()
        if not message:
            die("请附一句话说明:python3 %s handoff \"你这回合做了什么\"" % PROG_HINT)

    # 异议必须落到纸面:对方看不到你的对话,只能看到 docs/reviews/ 里的文件。
    is_dispute = verdict == "changes" and phase in DISPUTE_PHASES

    if (phase, verdict) not in flow["transitions"]:
        die("工作项类型 [%s] 的流程里没有 %s 阶段的这个走向。状态可能已损坏。"
            % (state["item_type"], phase))
    target = flow["transitions"][(phase, verdict)]

    entries = changed_entries(root)

    # --- 写权限边界校验 ---------------------------------------------------
    allowed = writable_paths(cfg, phase)
    exempt_from_scope = list(cfg["shared_paths"])
    if memory_on(cfg):
        exempt_from_scope += [cfg["notes_dir"], cfg["decisions_file"]]
    violations = []
    for xy, path in entries:
        if path in PROTOCOL_LOGS or matches_any(path, cfg["ignore_paths"]):
            continue
        hit_frozen = next((f for f in cfg["frozen_paths"]
                           if path_matches(path, f)), None)
        if hit_frozen is not None:
            violations.append((path, "冻结路径 %s 之下,agent 不得修改" % hit_frozen))
            continue
        if not matches_any(path, allowed):
            who = ("本回合是只读评审" if phase in REVIEW_PHASES
                   else "%s 在 %s 阶段" % (me, phase))
            violations.append((path, "越界:%s 只能写 %s" % (who, " ".join(allowed))))
            continue
        # scope:本轮结对圈定的范围。评审目录与记忆层永远豁免 —— 它们是散文,
        # 不是代码,而"要不要扩大范围"必须是人类的显式决定,不是 agent 的顺手。
        if cfg["scope"] and not matches_any(path, exempt_from_scope) \
                and not matches_any(path, cfg["scope"]):
            violations.append((path, "在本轮范围之外。scope = %s\n"
                                     "      要动范围外的代码,这是人类的决定,"
                                     "不是你顺手能做的 —— 写进 %s 说明理由。"
                               % (" ".join(cfg["scope"]),
                                  " ".join(cfg["shared_paths"]))))

    if violations:
        lines = "".join("\n  %s\n      %s" % (p, why) for p, why in violations)
        die("拒绝交接 —— 以下改动越界:%s\n\n"
            "请撤销这些改动后重试。如果你认为规则本身有问题,"
            "写进 docs/reviews/ 并告诉人类。" % lines)

    # --- 测试删除防护 -----------------------------------------------------
    test_paths = cfg["roles"]["tester"]
    deleted = [p for xy, p in entries
               if "D" in xy and matches_any(p, test_paths)]
    if deleted and not args.allow_deletion:
        die("拒绝交接 —— 你删除了已有测试:\n  %s\n\n"
            "测试是规格,删除它等于悄悄缩小验收范围。\n"
            "确有正当理由(比如该用例已被更好的用例取代)就显式声明:\n"
            "  python3 %s handoff \"说明\" --allow-deletion \"删除理由\"\n"
            "理由会写进提交记录,对方在评审时必然看到。"
            % ("\n  ".join(deleted), PROG_HINT))

    # --- 必须真的写了测试(cover 类型全程绿,红绿不变量抓不到空手交接) ----
    if phase in flow["require_new_tests"]:
        touched_tests = [p for xy, p in entries
                         if "D" not in xy and matches_any(p, test_paths)]
        if not touched_tests:
            die("拒绝交接 —— 本项是 [%s] 类型,但你这一回合没有新增或修改任何测试。\n"
                "可写测试路径:%s\n"
                "cover 类型全程是绿的,红绿不变量抓不到空手交接,所以这条单独检查。"
                % (state["item_type"], " ".join(test_paths)))

    # --- 打回之后的修正回合必须真的动了测试 --------------------------------
    # 红绿豁免的本意是"让 tester 能把测试改对"。但 feature 的 spec 本来就没有
    # "必须动测试"这条检查,两者一叠加,tester 可以一个测试都不改就把回合推回去,
    # 而 dev 面对的是一模一样的那条测试 —— 来回到第三次撞死锁闸,白烧两轮。
    if state.get("after_rebound") and phase == "spec" and verdict is None:
        touched = [p for xy, p in entries
                   if "D" not in xy and matches_any(p, cfg["roles"]["tester"])]
        if not touched:
            die("拒绝交接 —— 上一回合把你打回来了,而你没有改动任何测试。\n\n"
                "打回之后的这一回合豁免了 RED 要求,理由是让你能把测试改对 ——\n"
                "不是让你空转一轮把问题原样推回去。\n\n"
                "可写测试路径:%s\n\n"
                "如果你看完之后认为原来的测试是对的、异议不成立,把理由写进 %s,\n"
                "让对方在下一回合面对它 —— 但那也要落到文件上,不能什么都不留。"
                % (" ".join(cfg["roles"]["tester"]), " ".join(cfg["shared_paths"])))

    # --- 异议必须落到纸面 -------------------------------------------------
    if is_dispute:
        written = [p for xy, p in entries
                   if "D" not in xy and matches_any(p, cfg["shared_paths"])]
        if not written:
            die("拒绝交接 —— 你提出了异议,但没有把它写下来。\n\n"
                "对方看不到你的对话,唯一的通信渠道是 %s 里的文件。\n"
                "写清楚:哪条测试、和契约的哪一条矛盾、你认为应该改成什么。\n"
                "然后重新执行本命令。" % " ".join(cfg["shared_paths"]))

    # --- 评审证据 ---------------------------------------------------------
    refusal = check_review_evidence(root, cfg, phase, verdict, entries, message, args)
    if refusal:
        die(refusal)

    # --- 记忆层门禁 -------------------------------------------------------
    # 放在跑测试之前:纸面上的问题不值得先花一遍测试时间。
    refusal = check_memory(root, cfg, state, phase, verdict, target, args)
    if refusal:
        die(refusal)

    # --- 红绿不变量(按工作项类型) ---------------------------------------
    # 异议路径豁免:dev 正是因为测试写错、弄不绿才打回的,拿红绿卡他等于
    # 逼他照着错误的断言写实现。
    green = run_tests(root, cfg)
    # 两处豁免,同一个理由:拿红绿卡住的是修正动作本身。
    #   1. 提异议的那一回合 —— 全豁免。dev 正是因为弄不绿才打回的。
    #   2. 打回之后紧接着的 spec 回合 —— **只豁免 RED**。tester 在按意见修测试,
    #      而 dev 的实现往往已经落地,改对之后整体就是绿的,要求 RED 等于逼它
    #      再造一条假的失败。
    #
    # 第 2 条为什么不能像第 1 条那样整个置空:cover 的 spec 期望的是 GREEN,
    # 而 cover 也有 review-test changes → spec 这条边。整个置空会让一个红着的
    # cover 回合过关,而"全程绿"正是 cover 的全部纪律。
    after_rebound = state.get("after_rebound") and phase == "spec"
    expect = flow["expect"].get(phase)
    if is_dispute or (after_rebound and expect == "RED"):
        expect = None
    if expect == "RED" and green:
        die("%s 阶段结束时测试必须是 RED,现在是 GREEN。\n"
            "你要么没写新用例,要么写了个本来就能通过的用例。\n"
            "失败的测试才是有效的规格。\n"
            "(如果你本来就是在为已有行为补测试,该工作项应该标成 [cover] 类型。)"
            % phase)
    if expect == "GREEN" and not green:
        if state["item_type"] == "cover":
            die("本项是 [cover] 类型,应当全程 GREEN,但测试现在是 RED。\n"
                "你为已有行为写的测试没通过 —— 这说明你发现了一个真实缺陷。\n"
                "这是好事,但不属于 cover 的范围:请告诉人类把它改成 [bug] 类型的\n"
                "工作项,由 dev 来修。看 %s。" % TESTLOG_REL)
        die("%s 阶段结束时测试必须是 GREEN,现在是 RED。\n"
            "看 %s。还没弄绿就不要交接。" % (phase, TESTLOG_REL))

    # --- 死锁保护 ---------------------------------------------------------
    changes_n = state["changes_count"]
    if verdict == "changes":
        changes_n += 1
        if changes_n >= DEADLOCK_LIMIT:
            state["changes_count"] = changes_n
            # 留痕:die 之后状态里若没有记录,人类事后翻不到曾经卡过。
            # 不硬锁 approve —— 打回三次后一方说"我接受"是合理的收敛,
            # 而且它带理由、进提交记录、人类看得见。
            hit = "%s x%d" % (item or "?", changes_n)
            if hit not in state["deadlock_hits"]:
                state["deadlock_hits"].append(hit)
            save_state(root, state)
            git("add", "--", STATE_REL, cwd=root, check=False)
            git("commit", "-q", "-m",
                "chore(pair): 工作项 %s 打回 %d 次,触发死锁闸"
                % (item or "?", changes_n), cwd=root, check=False)
            die("同一工作项已经被打回 %d 次。协议要求此时停止自动轮转。\n"
                "请把双方分歧写清楚,交给人类裁决。不要继续来回。" % changes_n)

    # --- 翻转回合 ---------------------------------------------------------
    finished_item = None
    if target == "DONE":
        finished_item = item
        state["round"] += 1
        if item:
            state["completed_items"].append(item)
            tick_plan_item(root, cfg, item)
        state["item"] = None
        state["item_type"] = None
        state["changes_count"] = 0
        state["contract_sha"] = None
        next_phase = "idle"
    else:
        next_phase = target
        state["changes_count"] = changes_n
    state["phase"] = next_phase
    state["last_actor"] = me
    # 任何打回都算 —— review-test 以"覆盖不足"打回时,tester 要补的那条
    # 回归测试按定义是绿的(修复已经落地)。只认 impl 阶段的异议会漏掉这条入口。
    state["after_rebound"] = (verdict == "changes")
    save_state(root, state)

    # --- 提交 -------------------------------------------------------------
    prefix = ("dispute" if is_dispute
              else COMMIT_PREFIX[phase] + ("/" + verdict if verdict else ""))
    body = "role=%s phase=%s -> %s item=%s type=%s" % (
        me, phase, next_phase, item or "none", state["item_type"] or
        (flow is FEATURE_FLOW and "feature" or "?"))
    if args.allow_deletion:
        body += "\n删除测试(已声明): %s\n  %s" % (args.allow_deletion,
                                                 "\n  ".join(deleted))
    if args.no_decision:
        body += "\n未留决策(已声明): %s" % args.no_decision
    if verdict == "approve":
        body += "\n检查了: %s\n未覆盖: %s" % (args.checked, args.uncovered)

    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "%s: %s" % (prefix, message), "-m", body, cwd=root)

    # 工作项完成时跑一次全量套件。只报告不阻断 —— 范围外的代码这对结对
    # 本来就无权修,阻断等于把它们锁死在一个自己解不开的局面里。
    full_failed = False
    if finished_item and cfg.get("full_test_cmd"):
        full_failed = not run_tests(root, cfg, cmd=cfg["full_test_cmd"],
                                    log_rel=FULL_TESTLOG_REL)

    push_failed = cfg.get("sync") and git("push", cwd=root, check=False) is None

    print()
    print("[结对协议] 已交接。")
    print("  提交: %s" % git("log", "-1", "--oneline", cwd=root).strip())
    print("  下一阶段: %s  → 归属: %s" % (next_phase, PHASE_OWNER[next_phase]))
    if finished_item:
        print("  工作项「%s」已完成并双向通过。" % finished_item)
    print()
    if push_failed:
        # 提交已经落在本地,但对方拉不到 —— 通信只走 git,所以这等于没交接。
        print("!" * 60)
        print("推送失败。提交只在你本地,对方看不到。")
        print("**不要告诉人类\"已交接\"** —— 请报告推送失败,让人类处理\n"
              "(网络、权限,或对方推了新提交需要先 pull)。")
        print("!" * 60)
        print()
        return 2

    if full_failed:
        print("!" * 60)
        print("门禁套件绿,但全量套件红。")
        print("  门禁: %s" % cfg["test_cmd"])
        print("  全量: %s   (详见 %s)" % (cfg["full_test_cmd"], FULL_TESTLOG_REL))
        print()
        print("这个工作项本身按纪律走完了,但范围之外有东西红了。")
        print("**不要告诉人类\"完成\"** —— 报告这件事,由人类决定是扩大范围、")
        print("开一个新工作项,还是接受它。")
        print("!" * 60)
        print()

    if plan_all_done(root, cfg):
        print(">>> %s 里的工作项已全部完成。项目结束。<<<" % cfg["plan_file"])
        print("请向人类报告完成,不要继续轮转。")
    else:
        print("现在请告诉人类:轮到 %s 了。然后停止工作。" % PHASE_OWNER[next_phase])
    print()
    # 与推送失败同一约定:提交落地了,但有一件事人类必须知道才能算完成。
    return 2 if full_failed else 0


# --------------------------------------------------------------------------
# inbox
# --------------------------------------------------------------------------

def cmd_inbox(root, cfg, args):
    n = args.count
    print("=== 最近 %d 次交接 ===============================" % n)
    log = git("log", "-n", str(n), "--format=%h  %s%n      %b", cwd=root, check=False)
    print(log.strip() if log and log.strip() else "(还没有提交)")
    print()
    print("=== 上一回合的完整改动 ===========================")
    show = git("show", "--stat", "--format=%h %s", "HEAD", cwd=root, check=False)
    print(show.strip() if show else "(无)")
    print()
    print("--- diff -----------------------------------------")
    diff = git("show", "--format=", "HEAD", cwd=root, check=False)
    print(diff.rstrip() if diff else "")
    print()
    # 上一回合写给你的散文。只列文件名是不够的 —— 没人会主动去 cat 它,
    # 而对方看不到你的对话,这些文件就是它唯一能对你说话的地方。
    print("=== 对方这一回合写给你的 =========================")
    prose_paths = list(cfg["shared_paths"])
    if memory_on(cfg):
        prose_paths += [cfg["notes_dir"], cfg["decisions_file"]]
    changed = [p for p in ((git("show", "--name-only", "--format=", "HEAD",
                                cwd=root, check=False) or "").split("\n"))
               if p.strip() and matches_any(p.strip(), prose_paths)]
    changed = [p.strip() for p in changed]
    if not changed:
        print("(这一回合没有动过散文文件)")
    budget = 4000
    for rel in changed:
        text = _read(root / rel).strip()
        if not text:
            continue
        if budget <= 0:
            print("\n… 其余文件略,直接读:%s" % " ".join(changed))
            break
        print()
        print("--- %s ---" % rel)
        print(text[:budget] + ("\n…（已截断,完整内容见文件）"
                               if len(text) > budget else ""))
        budget -= len(text)
    print()
    print("=== 全部散文记录(文件清单)=======================")
    found = []
    for shared in prose_paths:
        d = root / shared
        if d.is_dir():
            found += sorted(str(p.relative_to(root)) for p in d.rglob("*")
                            if p.is_file() and not p.name.startswith("."))
        elif (root / shared).is_file():
            found.append(shared)
    print("\n".join(found) if found else "(空)")
    return 0


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

# 健康区间。区间之外不等于错,等于**值得看一眼**。
HEALTH = {
    "打回率": (0.15, 0.50),
    "每工作项回合数": (4, 8),
    "死锁工作项占比": (0.0, 0.10),
}

# 少于这个数的样本,比率没有意义,只报原始计数。
MIN_SAMPLE = 5

REPORT_SEP = "\x1f"


def _handoff_log(root):
    """[(subject, body)],按时间正序。"""
    fmt = "%s" + REPORT_SEP + "%b" + REPORT_SEP + "%x00"
    out = git("log", "--reverse", "--format=" + fmt, cwd=root, check=False) or ""
    rows = []
    for rec in out.split("\x00"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split(REPORT_SEP)
        rows.append((parts[0].strip(), parts[1] if len(parts) > 1 else ""))
    return rows


def _width(text):
    """终端显示宽度。中日韩字符占两列,按字符数补齐会把表格排歪。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text, width):
    return text + " " * max(0, width - _width(text))


def _fmt_rate(hit, total):
    return "—" if not total else "%.0f%% (%d/%d)" % (100.0 * hit / total, hit, total)


def _flag(name, value, sample_ok=True):
    """区间判定。样本不足时不下结论 —— 三次评审算出的打回率没有意义。"""
    if value is None or not sample_ok:
        return "样本不足" if not sample_ok else "—"
    lo, hi = HEALTH[name]
    if value < lo:
        return "!! 偏低"
    if value > hi:
        return "!  偏高"
    return "ok"


def cmd_report(root, cfg, args):
    """只读的协议健康度报告。纯读 git log,不碰状态。

    存在的理由只有一条:**"两个 agent 互相点头"在此之前不可观测。**
    脚本能强制评审带证据(结构),强制不了评审有内容。打回率长期接近 0 是
    那件事唯一的量化证据 —— 而这套协议存在的全部理由就是防它。

    区间之外不等于错,等于值得看一眼。
    """
    rows = _handoff_log(root)
    state = load_state(root)

    reviews = changes = disputes = 0
    claimed = deadlocks = no_decision = 0
    rounds_by_item = {}

    for subject, body in rows:
        prefix = subject.split(":", 1)[0].strip()
        if prefix.startswith("review("):
            reviews += 1
            if prefix.endswith("/changes"):
                changes += 1
        elif prefix == "dispute":
            disputes += 1
        if subject.startswith("chore(pair): 认领工作项"):
            claimed += 1
        if "触发死锁闸" in subject:
            deadlocks += 1
        if "未留决策(已声明)" in body:
            no_decision += 1
        m = re.search(r"item=(\S+)", body)
        if m and m.group(1) != "none":
            rounds_by_item[m.group(1)] = rounds_by_item.get(m.group(1), 0) + 1

    done = len(state["completed_items"])
    decisions = len(parse_decisions(_read(root / cfg["decisions_file"]))) \
        if memory_on(cfg) else 0
    avg_rounds = (sum(rounds_by_item.values()) / float(len(rounds_by_item))
                  if rounds_by_item else None)
    rate = (changes / float(reviews)) if reviews else None
    dl_rate = (deadlocks / float(claimed)) if claimed else None

    print("=" * 62)
    print(" 结对健康度  —  %s" % root)
    print("=" * 62)
    print(" 已完成工作项 : %d        进行中: %s"
          % (done, state["item"] or "(无)"))
    print(" 交接提交     : %d        认领: %d"
          % (sum(rounds_by_item.values()), claimed))
    print("-" * 62)

    def row(name, value, verdict):
        print(" %s %s %s" % (_pad(name, 20), _pad(value, 18), verdict))

    row("指标", "值", "判定")
    print("-" * 62)
    row("打回率", _fmt_rate(changes, reviews),
        _flag("打回率", rate, reviews >= MIN_SAMPLE))
    row("每工作项回合数", "—" if avg_rounds is None else "%.1f" % avg_rounds,
        _flag("每工作项回合数", avg_rounds, bool(rounds_by_item)))
    row("死锁工作项占比", _fmt_rate(deadlocks, claimed),
        _flag("死锁工作项占比", dl_rate, claimed >= MIN_SAMPLE))
    row("测试异议", "%d 次" % disputes, "—")
    row("决策/完成项", "%d / %d" % (decisions, done),
        "!! 记忆层空转" if done >= MIN_SAMPLE and not decisions else "—")
    row("--no-decision", _fmt_rate(no_decision, done),
        "!  偏高" if done and no_decision > done / 2.0 else "—")
    print("=" * 62)
    print()

    if reviews < MIN_SAMPLE:
        print("  评审样本只有 %d 次,比率还说明不了任何事。至少跑到 %d 次再看。"
              % (reviews, MIN_SAMPLE))
        print()
        return 0

    if rate is not None and rate < HEALTH["打回率"][0]:
        print("  >>> 打回率偏低。<<<")
        print()
        print("  这是这套协议最主要的失败模式:两个 agent 互相点头,红绿全对,")
        print("  流程全走完,而没有任何缺陷被发现。脚本能强制 approve 带上")
        print("  --checked/--uncovered,强制不了它有内容。")
        print()
        print("  读几条 approve 的理由:")
        print("    python3 %s inbox 10" % PROG_HINT)
        print()
        print("  常见成因:工作项切得太大,评审者没能力细看;或者契约太模糊,")
        print("  没有可争的东西。见 docs/troubleshooting.md。")
        print()
    return 0


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------

ACTIVATOR = """# 本仓库是双 AI agent 结对开发项目

**在做任何事之前:**

1. 激活 `pair-protocol` 技能(位于 `.agents/skills/pair-protocol/`)。
   如果你的工具不自动激活技能,直接读
   `.agents/skills/pair-protocol/SKILL.md` 并严格遵守。
2. 运行 `python3 .agents/skills/pair-protocol/scripts/pair.py status`,
   确认你的角色和当前回合。

在这两步完成之前,**不要读代码、不要修改任何文件**。

你不是单独在这个项目上工作。另一个 agent 正在负责你不负责的那一半,
擅自动手会破坏它的工作。
"""

CLAUDE_MD = """@AGENTS.md

## Claude Code 专用

- `pair-protocol` 技能已通过 `.claude/skills/pair-protocol` 软链接接入,
  也可以直接 `/pair-protocol` 调用。
- 不要用 subagent 代跑结对回合。回合状态在 `.pair/state.json`,
  必须由主会话执行 `status` 和 `handoff`。
"""

CURSOR_MDC = """---
description: 双 agent 结对编程协议 —— 开工前必读
alwaysApply: true
---

本仓库是双 AI agent 结对开发项目。

开工前必须:(1) 激活 `pair-protocol` 技能,或直接读
`.agents/skills/pair-protocol/SKILL.md`;(2) 运行
`python3 .agents/skills/pair-protocol/scripts/pair.py status` 确认角色和回合。
在此之前不要修改任何文件。
"""

ENTRY_MARK_BEGIN = "<!-- pair-protocol:begin -->"
ENTRY_MARK_END = "<!-- pair-protocol:end -->"

# `.cursor/rules/*.mdc` 这类文件的 YAML frontmatter **必须在第一个字节**,
# 前面多一行 HTML 注释就整块失效(alwaysApply 不再生效,而那正是它存在的理由)。
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def _split_frontmatter(text):
    m = _FRONTMATTER_RE.match(text)
    return (m.group(0), text[m.end():]) if m else ("", text)

ENTRY_FILES = {
    "AGENTS.md": ACTIVATOR,
    "GEMINI.md": ACTIVATOR,
    "CONVENTIONS.md": ACTIVATOR,
    ".clinerules": ACTIVATOR,
    ".windsurfrules": ACTIVATOR,
    ".github/copilot-instructions.md": ACTIVATOR,
    "CLAUDE.md": CLAUDE_MD,
    ".cursor/rules/pair.mdc": CURSOR_MDC,
}

# (探测文件, 测试命令)
STACK_PROBES = [
    ("go.mod", "go test ./..."),
    ("Cargo.toml", "cargo test"),
    ("package.json", "npm test"),
    ("pyproject.toml", "python3 -m pytest"),
    ("setup.py", "python3 -m pytest"),
    ("pom.xml", "mvn -q test"),
    ("build.gradle", "gradle test"),
]

PLAN_SKELETON = """# 项目规划（冻结 — agent 只读）

> 由人类维护。工作项完成时由脚本勾选,那是脚本的权限,不是 agent 的。
>
> 粒度决定成败:每个工作项要小到一个回合写三五个用例就覆盖完。

## 目标

<!-- 一段话说明这轮结对要达成什么 -->

## 工作项

格式必须是 `- [ ] **ID** [类型] — 标题`,`pair.py claim` 靠它识别。
类型可省略(缺省 feature),可选:feature / bug / cover / refactor。

- [ ] **W1** [feature] — <标题>
  - 验收标准:<可观测的、能写成断言的条件>
  - 对应契约:`docs/CONTRACT.md` → <小节名>
"""

CONTRACT_SKELETON = """# 接口契约（冻结 — agent 只读，变更需双方同意后由人类修改）

> **这是整套机制的承重墙。**
>
> 两个 agent 从不交谈,只通过这份契约对齐。契约含糊 → tester 测
> `login() -> token`,dev 写 `authenticate() -> Session`,两边各自都"对",
> 合起来是废的。这是唯一会让整个项目失败的方式。
>
> 规则:**没写进这份文件的东西,tester 不许断言。**
>
> PLAN 里每个工作项都要用 `对应契约:\\`docs/CONTRACT.md\\` → 小节名`
> 指向这里的一个 `##` 小节,verify-setup 会检查。

## <小节名>

- 依据: 人类定稿

<!-- `依据` 是必填的,verify-setup 会查。它记的是"这一节凭什么可信":
     人类定稿          人类逐条确认过。新项目默认就是这个
     考古观察@<sha>    agent 读过代码、跑过代码之后写下来的现状
     已有文档 <路径>(待核实)   从老文档抄来的线索

     **只有前两者可以被 tester 断言。** 存量项目老文档的头号病症是过时:
     它写"返回 null"而实际代码抛异常时,tester 会照它写断言、dev 会以为
     发现了 bug 去改行为,整条链每一步都合规,结果是线上炸。
     待核实的小节只能由 [cover] 工作项去建立事实,再由人类定稿。 -->

### `函数名(参数: 类型) -> 返回类型`

**行为** <正常路径下做什么>

**参数约束**

| 参数 | 类型 | 约束 |
|---|---|---|
|  |  |  |

**返回** <精确到字段和类型>

**错误**

| 条件 | 抛出 |
|---|---|
|  |  |

**边界情况**
<!-- 空输入、超长输入、并发、null。没在这里写明的边界,tester 不能凭空假设。 -->
"""

DECISIONS_SKELETON = """# 决策记录（追加式 — 只能往后加，不能改已有条目）

> 两个 agent 不共享对话，也不共享各自厂商的记忆。这份文件是它们唯一
> 累积起来的共同结论，`pair.py status` 会在相关回合把它读给双方听。
>
> **只记事实和裁决，不记推理过程。** 共享推理会让两边想到一块去，而互相
> 点头正是这套机制要防的事 —— 所以下面故意没有"分析"字段。
>
> 强制写入的时刻只有三个:同一工作项第二次被打回、契约在工作项期间被改过、
> 工作项完成时笔记里还有没沉淀的东西。其余时候想写就写。
>
> 格式如下，四个字段缺一不可，单条不得超过 1500 字符（超了 handoff 会拒绝
> —— 这条结论此后每次 status 都会被读一遍，长了就没人读）:

    ## W1 — 用毫秒时间戳而不是 ISO 字符串做排序键

    - 理由: ISO 字符串在跨时区输入下排序结果和真实先后不一致，
      W1 的验收标准直接依赖排序
    - 已否决: 存 ISO 再解析后排序 —— 每次读都要解析，且解析失败没有兜底路径
    - 影响路径: `src/timeline.py`, `tests/test_timeline.py`

`影响路径` 是检索键:今后谁要动这些路径，`status` 会自动把这条结论摆到他面前。
所以路径要写准，写全。

---

"""


# pair.py 本身是 Python,每次 status/handoff 跑测试都会生成字节码。
# 不忽略的话,它会落在**对方**的路径下,让两个角色互相把对方卡在越界上。
# 这与目标项目用什么语言无关。
GITIGNORE_LINES = [".pair/.last-test.log", ".pair/.last-full-test.log",
                   ".pair/whoami",
                   "__pycache__/", "*.pyc"]


def _detect_stack(root):
    for probe, cmd in STACK_PROBES:
        if (root / probe).exists():
            return cmd, probe
    return "", None


def _detect_roles(root):
    """返回 (roles, 说明)。优先目录切分,其次同目录 glob(用负模式避免重叠)。"""
    files = tracked_files(root)

    for tdir, sdir in (("tests", "src"), ("test", "src"),
                       ("spec", "lib"), ("src/test", "src/main")):
        if (root / tdir).is_dir():
            src = sdir if (root / sdir).is_dir() else "src"
            return ({"tester": [tdir], "dev": [src]},
                    "目录切分:%s / %s" % (tdir, src))

    if any(f.endswith("_test.go") for f in files):
        return ({"tester": ["**/*_test.go"],
                 "dev": ["**/*.go", "!**/*_test.go"]},
                "Go 同目录布局(用负模式排除测试文件)")

    for suffix in (".test.ts", ".test.js", ".spec.ts", ".spec.js"):
        if any(f.endswith(suffix) for f in files):
            stem = suffix.rsplit(".", 1)[0]          # .test / .spec
            return ({"tester": ["**/*%s.*" % stem],
                     "dev": ["src/**", "!**/*%s.*" % stem]},
                    "JS/TS 同目录布局(%s.*)" % stem)

    return ({"tester": ["tests"], "dev": ["src"]},
            "未识别布局,填了默认值 —— 请人类核对")


def merge_entry(root, rel, content):
    """把协议激活段落幂等地并进入口文件。返回 'written' / 'updated' / 'inserted' / None。

    曾经这里是"文件已存在就跳过" —— 于是任何已经有 CLAUDE.md / AGENTS.md 的
    仓库(也就是所有现有项目)接入之后,agent 根本读不到激活指令,而
    verify-setup 只查文件存在,会一路放行。接入"成功"了,协议却从未生效。

    **前置插入而不是追加**:协议的前提是"跑 status 之前不许碰任何文件",
    这句话埋在一份三百行 CLAUDE.md 的末尾就不成立了。人类可以把整个标记块
    挪到别处,挪走之后重跑 init 仍然就地更新,不会重复插入。
    """
    c_fm, c_body = _split_frontmatter(content)
    block = "%s\n%s\n%s\n" % (ENTRY_MARK_BEGIN, c_body.strip(), ENTRY_MARK_END)
    p = root / rel
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(c_fm + block, encoding="utf-8")
        return "written"

    old = p.read_text(encoding="utf-8")
    i, j = old.find(ENTRY_MARK_BEGIN), old.find(ENTRY_MARK_END)
    if i >= 0 and j > i:
        merged = old[:i] + block.rstrip("\n") + old[j + len(ENTRY_MARK_END):]
        if merged == old:
            return None
        p.write_text(merged, encoding="utf-8")
        return "updated"

    # 已有文件自己的 frontmatter 优先保留 —— 我们不改写别人的 YAML,
    # 只把协议段落插到它后面(仍然在正文最前)。
    o_fm, o_body = _split_frontmatter(old)
    p.write_text((o_fm or c_fm) + block + "\n" + o_body, encoding="utf-8")
    return "inserted"


def cmd_init(root, cfg, args):
    print("=== 结对协议初始化:%s ===" % root)
    existing = load_config(root, required=False)

    # --- 探测 -------------------------------------------------------------
    if existing and existing.get("test_cmd"):
        test_cmd, probe = existing["test_cmd"], "已有 config"
    else:
        test_cmd, probe = _detect_stack(root)
    roles, roles_why = (existing["roles"], "已有 config") if existing \
        else _detect_roles(root)

    print("  测试命令: %s   (%s)" % (test_cmd or "（未探测到,需人类填写）",
                                     probe or "无匹配"))
    print("  角色路径: tester=%s  dev=%s   (%s)"
          % (roles["tester"], roles["dev"], roles_why))

    if not test_cmd:
        die("探测不到测试命令。请先手工创建 %s 并填入 test_cmd,再重跑 init。\n"
            "格式见 INSTALL.md。" % CONFIG_REL)

    # --- 基线检查(在写任何文件之前,失败就不留残骸) ----------------------
    probe_cfg = {"test_cmd": test_cmd}
    print("  基线检查: 正在跑 %s ..." % test_cmd)
    if not run_tests(root, probe_cfg):
        die("基线不是全绿,拒绝初始化。\n\n"
            "impl 阶段\"测试必须 GREEN\"这条不变量整个押在基线全绿上。基线本来就红,\n"
            "协议要么直接卡死,要么那条不变量形同虚设 —— 两种都比不接入更糟。\n\n"
            "两条正当出路:\n\n"
            "  1. 把现有测试修绿,再重跑 init。(推荐)\n\n"
            "  2. 存量项目老套件红着、或者慢到没法每回合跑:把 test_cmd **收窄**\n"
            "     到本轮真正要动的范围,把全量套件放进 full_test_cmd。\n"
            "     手工写 %s:\n\n"
            "       {\n"
            "         \"test_cmd\": \"pytest tests/billing\",     // 门禁,必须绿\n"
            "         \"full_test_cmd\": \"pytest\"              // 只报告,不阻断\n"
            "       }\n\n"
            "     然后在 docs/reviews/baseline.md 写明:放弃了哪些用例、为什么。\n"
            "     **这不是把\"绿\"放宽,是缩小它的范围并留痕。**\n\n"
            "失败详情见 %s" % (CONFIG_REL, TESTLOG_REL))
    print("  基线检查: GREEN")

    # --- 写文件(幂等) ----------------------------------------------------
    written, skipped = [], []

    def put(rel, content):
        p = root / rel
        if p.exists():
            skipped.append(rel)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        written.append(rel)

    put(CONFIG_REL, json.dumps({
        "test_cmd": test_cmd,
        "roles": roles,
        "full_test_cmd": None,
        "shared_paths": ["docs/reviews"],
        "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md",
                         ".agents", ".claude", ".pair"],
        "ignore_paths": [],
        "scope": [],
        "plan_file": "docs/PLAN.md",
        "contract_file": "docs/CONTRACT.md",
        "sync": False,
        "require_setup_verification": True,
        "notes_dir": "docs/notes",
        "decisions_file": "docs/DECISIONS.md",
        "memory": True,
    }, ensure_ascii=False, indent=2) + "\n")
    put(STATE_REL, json.dumps(DEFAULT_STATE, indent=2) + "\n")
    put("docs/PLAN.md", PLAN_SKELETON)
    put("docs/CONTRACT.md", CONTRACT_SKELETON)
    put("docs/reviews/.gitkeep", "")
    put("docs/notes/.gitkeep", "")
    put("docs/DECISIONS.md", DECISIONS_SKELETON)
    for rel, content in ENTRY_FILES.items():
        how = merge_entry(root, rel, content)
        if how == "written":
            written.append(rel)
        elif how == "inserted":
            written.append("%s(已有文件,协议段落插入到开头)" % rel)
        elif how == "updated":
            written.append("%s(更新了协议段落)" % rel)
        else:
            skipped.append(rel)

    gi = root / ".gitignore"
    have = gi.read_text(encoding="utf-8") if gi.exists() else ""
    add = [ln for ln in GITIGNORE_LINES if ln not in have]
    if add:
        gi.write_text((have + ("\n" if have and not have.endswith("\n") else "")
                       + "\n".join(add) + "\n"), encoding="utf-8")
        written.append(".gitignore(追加 %d 行)" % len(add))

    for rel in written:
        print("  + %s" % rel)
    for rel in skipped:
        print("  = %s（已存在,跳过）" % rel)

    print()
    print("[结对协议] 初始化完成。接下来由人类做三件事:")
    print("  1. 填写 docs/PLAN.md 的工作项(格式:- [ ] **W1** [feature] — 标题)")
    print("  2. 填写 docs/CONTRACT.md —— 这是承重墙,别偷懒")
    print("  3. 提交,然后让结对的一方跑:")
    print("       python3 %s verify-setup" % PROG_HINT)
    print()
    return 0


# --------------------------------------------------------------------------
# verify-setup
# --------------------------------------------------------------------------

# re.M 是必须的:工作项块是多行的,`对应契约` 后面还可能有 `保护测试`、
# `验收标准` 等行。少了它,`$` 只在整块末尾匹配 —— 于是"对应契约不是最后一行"
# 的工作项会被误报成"没有指向契约"。
CONTRACT_REF_RE = re.compile(r"对应契约[::]\s*.*?[→>]\s*(.+?)\s*$", re.M)
PROTECT_REF_RE = re.compile(r"保护测试[::]\s*(.+?)\s*$", re.M)

# 契约小节的证据等级。存量项目老文档的头号病症是**过时**,而它的错误方式极其
# 危险:README 写"找不到返回 null",实际代码抛异常 → tester 照文档写断言 → 红
# → dev 以为发现 bug → 改了行为 → 线上炸。这条链上每一步都符合协议纪律,
# 红绿全对,评审也挑不出毛病。
#
# 所以老文档只能当线索,不能当断言依据。断言依据只有两种:人类逐条定稿过,
# 或者 agent 真的读过代码、跑过代码之后写下来的。
PROVENANCE_RE = re.compile(r"^\s*[-*]\s*依据[::]\s*(.+?)\s*$", re.M)
ASSERTABLE_PROVENANCE = ("人类定稿", "考古观察")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_LEVELLED_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)


_FENCE_RE = re.compile(r"^([ \t]*)(```+|~~~+).*?^\1\2[^\n]*$", re.M | re.S)


def _blank_fenced_blocks(text):
    """把 ``` 围栏里的内容换成等量空行。

    契约里放 markdown 示例是完全正常的事(格式类规格就该用示例锚定),
    而示例里的 `# 标题` 不是契约的小节。不剔掉它们,一份带示例的契约会被
    判成"小节重名",而且偏移量还会错位 —— 所以用等量空行替换而不是删除。
    """
    def blank(m):
        return "\n" * m.group(0).count("\n")
    return _FENCE_RE.sub(blank, text)


def contract_sections(text):
    """返回 ({小节名: 自身正文}, {重名的小节名})。

    **正文只取到下一个标题为止,不含子小节。** 取全了会让父小节"继承"子小节的
    `依据` —— 一个没人背书的 `##` 会因为它下面某个 `###` 写了依据而被放行。

    **重名单独报出来。** 字典按标题文本建键,同一个 `### 函数签名` 在两个不同的
    `##` 下各出现一次时后者会覆盖前者,于是工作项读到的是另一节的依据 ——
    顺序反过来就是错误放行。歧义不能靠"取第一个"糊过去,要让人类改标题。
    """
    text = _blank_fenced_blocks(text)
    heads = list(_LEVELLED_HEADING_RE.finditer(text))
    out, dupes = {}, set()
    for i, m in enumerate(heads):
        name = m.group(2).strip().strip("`")
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        if name in out:
            dupes.add(name)
        out[name] = text[m.end():end]
    return out, dupes


def section_provenance(body):
    """小节的 `- 依据: …`。返回 (原文, 是否可被断言);没写返回 (None, False)。"""
    m = PROVENANCE_RE.search(body or "")
    if not m:
        return None, False
    raw = m.group(1).strip()
    return raw, any(raw.startswith(k) for k in ASSERTABLE_PROVENANCE)


def _plan_blocks(root, cfg):
    """[(id, type, done, 该工作项的文本块)]"""
    p = root / cfg["plan_file"]
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    marks = [(n, ITEM_RE.match(ln)) for n, ln in enumerate(lines)]
    marks = [(n, m) for n, m in marks if m]
    out = []
    for idx, (n, m) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        out.append((m.group("id").strip(), m.group("typename") or "feature",
                    m.group("mark") in "xX", "\n".join(lines[n:end])))
    return out


def cmd_verify_setup(root, cfg, args):
    fails, warns = [], []

    def bad(msg):
        fails.append(msg)

    def warn(msg):
        warns.append(msg)

    print("=== 开工前校验:%s ===" % root)

    # --- 角色路径 ---------------------------------------------------------
    for r in ROLES:
        if not cfg["roles"].get(r):
            bad("roles.%s 为空 —— 该角色无处可写" % r)

    files = tracked_files(root)
    both = [f for f in files
            if matches_any(f, cfg["roles"]["tester"])
            and matches_any(f, cfg["roles"]["dev"])]
    if both:
        bad("以下文件同时属于两个角色(边界重叠,零冲突保证失效):\n      %s%s"
            % ("\n      ".join(both[:10]),
               "\n      … 共 %d 个" % len(both) if len(both) > 10 else ""))

    for r in ROLES:
        owned = [f for f in files if matches_any(f, cfg["roles"][r])]
        if files and not owned:
            warn("roles.%s 的模式没有匹配到任何已跟踪文件:%s"
                 % (r, cfg["roles"][r]))

    for r in ROLES:
        clash = [p for p in cfg["roles"][r]
                 if not p.startswith("!")
                 and any(path_matches(p.rstrip("/*"), f)
                         or path_matches(f, p) for f in cfg["frozen_paths"])]
        if clash:
            bad("roles.%s 的 %s 与 frozen_paths 冲突 —— 该角色永远无法提交"
                % (r, clash))

    # --- 测试命令与基线 ---------------------------------------------------
    if not cfg.get("test_cmd"):
        bad("未配置 test_cmd")
    elif not run_tests(root, cfg):
        bad("基线不是全绿。impl 阶段的 GREEN 要求依赖基线全绿,\n"
            "      现在协议会卡死。详见 %s" % TESTLOG_REL)

    # --- scope --------------------------------------------------------------
    if cfg["scope"]:
        in_scope = [f for f in files if matches_any(f, cfg["scope"])]
        if not in_scope:
            warn("scope 没有匹配到任何已跟踪文件:%s" % cfg["scope"])
        for r in ROLES:
            owned = [f for f in files if matches_any(f, cfg["roles"][r])]
            if owned and not [f for f in owned if matches_any(f, cfg["scope"])]:
                bad("scope 把 roles.%s 的文件全排除了 —— 该角色永远无法提交任何改动。"
                    "\n      scope=%s  roles.%s=%s"
                    % (r, cfg["scope"], r, cfg["roles"][r]))

    # --- 全量套件(只报告)---------------------------------------------------
    if cfg.get("full_test_cmd"):
        if not run_tests(root, cfg, cmd=cfg["full_test_cmd"],
                         log_rel=FULL_TESTLOG_REL):
            warn("全量套件是红的:%s\n"
                 "      这本身不阻断(门禁是收窄过的 test_cmd),但请确认人类知道\n"
                 "      放弃了哪些用例、为什么。详见 %s"
                 % (cfg["full_test_cmd"], FULL_TESTLOG_REL))

    # --- PLAN -------------------------------------------------------------
    blocks = _plan_blocks(root, cfg)
    if not blocks:
        bad("%s 里没有合法工作项。格式:- [ ] **W1** [feature] — 标题"
            % cfg["plan_file"])
    pending = [b for b in blocks if not b[2]]
    if blocks and not pending:
        warn("%s 里所有工作项都已完成,没有可做的事" % cfg["plan_file"])
    for item_id, typ, _, _ in blocks:
        if typ not in ITEM_TYPES:
            bad("工作项 '%s' 的类型 '[%s]' 非法。只支持:%s"
                % (item_id, typ, "、".join(ITEM_TYPES)))

    # --- CONTRACT 覆盖度 --------------------------------------------------
    cpath = root / cfg["contract_file"]
    if not cpath.exists():
        bad("找不到 %s" % cfg["contract_file"])
    else:
        text = cpath.read_text(encoding="utf-8")
        sections, dupes = contract_sections(text)
        for name in sorted(dupes):
            bad("契约里有多个标题都叫「%s」。工作项按标题文本指向小节,\n"
                "      重名会让它读到另一节的 `依据` —— 请把标题改得唯一。" % name)
        for item_id, typ, _, block in pending:
            refs = CONTRACT_REF_RE.findall(block)
            if not refs:
                # cover 的活就是把还没有契约的行为变成事实,允许它指向尚不存在的小节
                if typ == "cover":
                    continue
                bad("工作项 '%s' 没有指向契约。在它下面加一行:\n"
                    "      - 对应契约:`%s` → <小节名>"
                    % (item_id, cfg["contract_file"]))
                continue
            anchor = refs[0].strip().strip("`")
            if anchor in dupes:
                continue          # 上面已经单独报过歧义,不重复刷屏
            if anchor not in sections:
                if typ == "cover":
                    continue
                bad("工作项 '%s' 指向的契约小节 '%s' 在 %s 里不存在。\n"
                    "      现有小节:%s"
                    % (item_id, anchor, cfg["contract_file"],
                       "、".join(sorted(sections)) or "(无)"))
                continue
            raw, ok = section_provenance(sections[anchor])
            if raw is None:
                bad("契约小节 '%s' 没写 `依据`。在小节里加一行:\n"
                    "      - 依据: 人类定稿\n"
                    "      可选值:`人类定稿` / `考古观察@<sha>` / "
                    "`已有文档 <路径>(待核实)`\n"
                    "      前两者可以被 tester 断言,第三者不行 —— "
                    "存量项目的老文档常常是过时的。" % anchor)
            elif not ok and typ != "cover":
                # 这是**顺序**问题,不是配置错误:人类完全可以把完整路线图一次
                # 写进 PLAN,由前面的 [cover] 项把契约做实。真正的闸在 claim ——
                # 那时才是"现在就要动这一项"。在这里 fail 等于禁止提前规划。
                warn("工作项 '%s' [%s] 指向的契约小节 '%s' 依据是「%s」,不可断言。\n"
                    "      tester 不能拿一份未经核实的规格写断言 —— 老文档说"
                    "\"返回 null\"、\n"
                    "      实际代码抛异常,这条链上每一步都合规,结果是线上炸。\n\n"
                     "      正确顺序:先开一个 [cover] 工作项建立事实(特征测试 + "
                     "契约草案),\n"
                     "      人类定稿之后这一项才能 claim。现在只是提醒,不阻断。"
                     % (item_id, typ, anchor, raw))

    # --- refactor 的安全网 --------------------------------------------------
    for item_id, typ, _, block in pending:
        if typ != "refactor":
            continue
        # 同样是顺序问题:保护它的测试很可能正是前面某个 [cover] 项要建的。
        # 硬闸在 claim,这里只提醒。
        refs = PROTECT_REF_RE.findall(block)
        if not refs:
            warn("工作项 '%s' [refactor] 没声明保护它的测试。在它下面加一行:\n"
                 "      - 保护测试: tests/<对应的测试目录>\n"
                 "      重构全程是绿的,而绿的测试按定义没抓到问题 —— 那片代码\n"
                 "      本来就没测试时,\"绿\"什么都不证明。claim 时会硬拦。" % item_id)
            continue
        target = refs[0].strip().strip("`")
        if not (root / target).exists():
            warn("工作项 '%s' 的保护测试路径还不存在:%s(claim 时会硬拦)"
                 % (item_id, target))
        elif not matches_any(target, cfg["roles"]["tester"]):
            bad("工作项 '%s' 的保护测试路径 %s 不在 tester 名下(%s)——\n"
                "      保护重构的必须是测试。指向实现目录等于没有安全网。"
                % (item_id, target, " ".join(cfg["roles"]["tester"])))

    # --- 记忆层路径自洽 ---------------------------------------------------
    if memory_on(cfg):
        for label, target in (("notes_dir", cfg["notes_dir"]),
                              ("decisions_file", cfg["decisions_file"])):
            for r in ROLES:
                if matches_any(target, cfg["roles"][r]):
                    bad("%s(%s)落在 roles.%s 之下 —— 记忆层必须两个角色都能写,"
                        "\n      被角色路径圈进去就变成单方私有的了"
                        % (label, target, r))
            hit = next((f for f in cfg["frozen_paths"]
                        if path_matches(target, f)), None)
            if hit:
                bad("%s(%s)落在冻结路径 %s 之下 —— agent 永远写不了它"
                    % (label, target, hit))
        if matches_any(cfg["notes_dir"], cfg["shared_paths"]) or \
                matches_any(cfg["decisions_file"], cfg["shared_paths"]):
            bad("记忆层路径落在 shared_paths 之下。这会让"
                "\n      「异议必须写下来」那条检查被随手写的笔记满足,"
                "\n      等于静默削掉一条现有防护。请把它们配成互不包含的路径。")

    # --- 入口文件与技能 ---------------------------------------------------
    if not (root / ".agents/skills/pair-protocol/SKILL.md").exists():
        bad("找不到 .agents/skills/pair-protocol/SKILL.md")
    # 只查文件在不在是不够的:现有项目本来就有 CLAUDE.md,里面却可能一个字
    # 都没提结对协议 —— 那种情况下接入"成功"了,agent 却从不知道自己在结对。
    for f in ("AGENTS.md", "CLAUDE.md"):
        fp = root / f
        if not fp.exists():
            warn("缺少入口文件:%s —— 对应工具的 agent 不会知道这是结对项目" % f)
        elif ENTRY_MARK_BEGIN not in fp.read_text(encoding="utf-8"):
            warn("%s 里没有协议激活段落(%s)。重跑 init 会把它插到文件开头;\n"
                 "      如果你是有意自己写的激活说明,忽略这条。"
                 % (f, ENTRY_MARK_BEGIN))

    # --- 报告 -------------------------------------------------------------
    print()
    for w in warns:
        print("  [警告] %s" % w)
    for f in fails:
        print("  [失败] %s" % f)

    if fails:
        print()
        die("校验未通过:%d 项失败。这些都需要人类修改配置或 PLAN/CONTRACT,\n"
            "你(agent)不能自己改冻结文件。请把上面的清单交给人类。" % len(fails))

    state = load_state(root)
    if state_is_tampered(root):
        restore_state(root)
        die("你修改了 %s,已还原。请重新执行 verify-setup。" % STATE_REL)

    print()
    print("  脚本能查的都通过了%s。"
          % ("（有 %d 条警告）" % len(warns) if warns else ""))

    # --- 契约歧义审查:这一步不能只靠 prose 要求 ---------------------------
    # 脚本查不了歧义,但可以强制"你必须交出一份审查结论"。没有它就不放行 ——
    # 否则这道最关键的门禁会退化成一句可以无视的建议。
    report = root / SETUP_REPORT_REL
    text = report.read_text(encoding="utf-8").strip() if report.exists() else ""
    if len(text) < MIN_SETUP_REPORT_CHARS:
        print()
        print("=" * 60)
        print(" 还差最后一步 —— 只有你能做的那一步。")
        print("=" * 60)
        print("""
 通读 %s,把你认为**有歧义的条款**写进
 %s。

 脚本能查格式和覆盖度,查不了歧义。而契约歧义是这套机制唯一会致命的
 失败模式 —— tester 测 `login() -> token`、dev 写 `authenticate() -> Session`,
 两边各自都"对",合起来是废的。

 逐条问自己:
   - 每个函数的返回值,类型和字段是否精确到能写断言?
   - 错误条件是否穷举?抛什么、什么时候抛,是否明确?
   - 边界情况(空、超长、null、并发)是否写明?没写明的,tester 不许假设
   - 有没有哪句话可以有两种合理解读?

 有歧义就写下来,交给人类在开工前定稿。没有就明确写"无歧义",并说明你
 逐条核对过哪些 —— 空泛的一句"看过了没问题"不算。

 写完后重新执行 verify-setup。在交出这份结论之前,校验不会通过,
 也不能认领工作项。
""" % (cfg["contract_file"], SETUP_REPORT_REL))
        die("尚未交出契约审查结论(%s 缺失或过短,至少 %d 字)。\n"
            "这是本步骤存在的主要理由,不能跳过。"
            % (SETUP_REPORT_REL, MIN_SETUP_REPORT_CHARS))

    # 本命令对外的承诺是"只读校验"。此处只提交它自己产生的东西:
    # 状态位与那份契约审查结论。曾经这里是 `git add -A` —— 那会把工作区里
    # 任何东西一并提交进基线,包括结对开始前就被写好的实现,而那恰好会让
    # spec 阶段的 RED 要求失效(测试一上来就是绿的)。
    state["setup_verified"] = True
    save_state(root, state)
    to_add = [STATE_REL, SETUP_REPORT_REL] + [
        p for _, p in changed_entries(root) if matches_any(p, cfg["shared_paths"])]
    git("add", "--", *sorted(set(to_add)), cwd=root)
    git("commit", "-q", "-m", "chore(pair): 通过开工前校验,含契约审查结论", cwd=root)

    stray = [p for xy, p in changed_entries(root)
             if "D" not in xy and not matches_any(p, cfg["ignore_paths"])
             and any(matches_any(p, cfg["roles"][r]) for r in ROLES)]
    if stray:
        print()
        print("  [警告] 工作区里有未提交的代码改动,**没有**被本次提交带上:")
        for p_ in stray[:10]:
            print("      %s" % p_)
        print("  开工前就存在的实现会让 spec 阶段的 RED 要求失效。"
              "请交给人类确认这些是不是该在的。")

    print()
    print("  契约审查结论已收到(%s,%d 字)。" % (SETUP_REPORT_REL, len(text)))
    print("  开工前校验全部通过,现在可以认领工作项了。")
    print()
    return 0


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pair.py", description="双 agent 结对编程协议执行层")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化本仓库(结对开始之前跑)")
    sub.add_parser("verify-setup", help="开工前只读校验,由结对的另一方跑")
    sub.add_parser("status", help="我是谁 / 轮到谁 / 红绿 / 该干什么")

    p_claim = sub.add_parser("claim", help="认领 PLAN 里的一个工作项")
    p_claim.add_argument("item_id")

    p_ho = sub.add_parser("handoff", help="校验 → 提交 → 翻转回合")
    p_ho.add_argument("words", nargs="*")
    p_ho.add_argument("--allow-deletion", metavar="理由", default=None,
                      help="显式声明本次删除了测试,并给出理由")
    p_ho.add_argument("--no-decision", metavar="理由", default=None,
                      help="显式声明本工作项的笔记没有值得沉淀成决策的内容")
    p_ho.add_argument("--checked", metavar="内容", default=None,
                      help="approve 必填:你具体检查了什么")
    p_ho.add_argument("--uncovered", metavar="内容", default=None,
                      help="approve 必填:你知道还没被覆盖到的是什么(没有就写\"无\")")

    sub.add_parser("report", help="协议健康度:打回率等指标,只读")
    p_in = sub.add_parser("inbox", help="对方上一回合做了什么")
    p_in.add_argument("count", nargs="?", type=int, default=1)

    args = ap.parse_args(argv)
    root = repo_root()
    cfg = load_config(root, required=(args.cmd != "init"))
    return {
        "init": cmd_init,
        "verify-setup": cmd_verify_setup,
        "status": cmd_status,
        "claim": cmd_claim,
        "handoff": cmd_handoff,
        "inbox": cmd_inbox,
        "report": cmd_report,
    }[args.cmd](root, cfg, args)


if __name__ == "__main__":
    sys.exit(main())
