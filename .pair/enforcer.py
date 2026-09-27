#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双 AI agent 结对编程协议 —— 执行层。

单文件,仅依赖 Python 3 标准库。用法:

    python3 pair.py init [目标目录]     # 初始化(结对开始之前跑)
    python3 pair.py verify-setup --drafter self|other  # 另一方开工前的只读校验
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
    "review-naming",       # 评审目录顶层 .md 的名字要对上某个工作项
    "dispute-evidence",    # impl 阶段的 changes 必须写进 shared_paths
    "review-evidence",     # approve 要检查清单,changes 要 路径:行号 引用
    "archaeology-sha",     # 依据: 考古观察@<sha> 的 sha 必须真实存在
    "document-shape",      # 异议/契约变更/基线说明的必含小节,见下面的子项
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
    "dispute-shape",         # document-shape 的子项:异议必须存在且有三小节
    "contract-change-shape", # document-shape 的子项:契约变更四小节(按文件名触发)
    "baseline-shape",        # document-shape 的子项:基线说明两小节
    "setup-report-coverage", # 契约审查结论必须逐节点名 + 声明作者身份
    "doc-reason",            # 改了规范性文档就必须给理由
    "roadmap-basis",         # 路线图有改写时,依据必须指向一份真实产物
    "contract-change-basis", # 改承重文件时,声明必须指向一份真实产物
    "contract-change-now",   # 带声明的那次交接必须当场留决策(不是等到 DONE)
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
# 第五轮起契约审查结论**按角色分开**。两个角色写同一个固定名,第三轮真的整份
# 覆盖过一次(`2ff494f`)。上面那个旧的单一路径只剩回落用途:解析不出角色、
# 或自己的角色文件还没写时才读它,并且要说出来。
SETUP_REPORT_ROLE_FMT = "docs/reviews/setup-verification-%s.md"
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

# --- 评审目录里的文档 ---------------------------------------------------
# 命名的用处是让人和脚本都找得到:一份评审记录属于哪个工作项,从文件名就该看出来。
# 但规范只管**前缀**,不管后半截 —— 上一轮真实运行里 tester 写过一份
# `W1-spec-blocked.md`(不是裁决,是"我被协议卡住了"的求裁文书),那完全正当,
# 规范不该把它拒掉。
REVIEW_FIXED_NAMES = ("setup-verification.md", "baseline.md",
                      PurePosixPath(SETUP_REPORT_ROLE_FMT % "tester").name,
                      PurePosixPath(SETUP_REPORT_ROLE_FMT % "dev").name)
# `contract-change-<ID>.md`。前缀在前、ID 在后,与 improvements.md 的 P1-3 一致。
REVIEW_ID_PREFIXES = ("contract-change-",)

# 三份有必含小节的文档。三处的共同点:rules.md 早就写明了要素,却零强制。
DISPUTE_SECTIONS = ("哪条用例", "和契约的哪一条矛盾", "应该改成什么")
CONTRACT_CHANGE_SECTIONS = ("现在的契约是什么", "为什么不行",
                            "提议改成什么", "影响哪些测试和实现")
BASELINE_SECTIONS = ("放弃了哪些用例", "为什么")
BASELINE_REL = "docs/reviews/baseline.md"
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
    # **按角色**记下"这个角色上次通过开工前校验时,读的是哪一份契约"(W13)。
    # 与上面的 contract_sha 是两回事:那个按工作项记、取 HEAD 的 blob,给完成时
    # 的 contract-change-note 用;这个按角色记、取**工作区内容**,给 claim 用 ——
    # 人类改了契约还没提交是常态,HEAD 口径看不见它。老状态里没有这个键 =
    # 不知道上次校验的是哪一份,claim 要求重跑。
    "setup_verified_contract": {},
    # 上一次交接是不是一次**打回**(异议或评审 changes)。打回之后回到 spec 时,
    # dev 的实现往往已经随之前的交接落地了 —— tester 按打回意见改完测试,
    # 套件整体就是绿的,而 feature 的 spec 要求 RED。不记这一笔,
    # "打回 → 修正"这条路会在下一回合把自己卡死。
    "after_rebound": False,
    # W17:只涉及测试的打回走捷径要的两笔。`rebound_from` 是上一次打回来自哪一阶段;
    # `reviewed_contract` 是 review-impl approve 那一刻契约的**工作区内容** sha
    # (W13 口径)—— 实现是在那一刻被审过的。老状态里没有这两个键 = 不走捷径。
    "rebound_from": None,
    "reviewed_contract": None,
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


# 角色来自环境变量时的来源说明。status 的表头打它,W22 的警告靠它区分来源 —— 一个常量,不写两遍字面。
ROLE_FROM_ENV = "PAIR_ROLE 环境变量"


def try_resolve_role(root):
    """同 `resolve_role`,但**什么都没配**时返回 `(None, None)`,不停下。

    值配错了(`PAIR_ROLE` 或 `.pair/whoami` 不是 tester/dev)照样停 ——
    那是配置错误,不是"还没配"。`verify-setup` 是新项目接入后的第一条命令,
    那时角色可以还没配,它要能回落而不是被卡死。
    """
    env = os.environ.get("PAIR_ROLE", "").strip()
    if env:
        if env not in ROLES:
            die("PAIR_ROLE='%s' 无效,只能是 tester 或 dev。" % env)
        return env, ROLE_FROM_ENV

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

    return None, None


def resolve_role(root):
    role, source = try_resolve_role(root)
    if role is None:
        die(ROLE_HELP)
    return role, source


# --------------------------------------------------------------------------
# git 工作区
# --------------------------------------------------------------------------

def changed_entries(root):
    """[(xy, path)]。用 -z 输出,绕开中文/空格路径的转义问题。"""
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", cwd=root)
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


JUDGE_REL = ".pair/enforcer.py"


def judge_pair(root):
    """(裁判副本, 正本) —— 副本或正本缺一就返回 (None, None)。

    正本走 `PROG_HINT` 那个固定路径,**绝不能用 `__file__`**:本轮的真实
    部署方式就是跑副本,那时 `__file__` 指向副本自己 —— 拿它去比是自己跟
    自己比,恒真,而且恰好在最该生效的场景下失效。
    """
    copy, src = root / JUDGE_REL, root / PROG_HINT
    if not copy.exists() or not src.exists():
        return None, None
    return copy, src


def judge_in_sync(root):
    """副本是否逐字节等于正本。副本不存在时算同步(默认用法没有副本)。

    **必须逐字节。** 比注册表、比符号集合、比 strip 之后的文本都不行 ——
    上一轮真实发生过的漂移里 `ENFORCEMENTS` 与 `HANDOFF_INVARIANTS` 两边
    差集都是空的,而两个文件差 122 行、整节孤儿清单不在裁判里。
    那种判据长得像检测器,实际恒真。
    """
    copy, src = judge_pair(root)
    return copy is None or copy.read_bytes() == src.read_bytes()


def repin_judge(root):
    """把正本复制成副本,返回新的 blob sha;没有副本时返回 None。

    调用点必须落在**写权限边界校验之后、`git add -A` 之前**:落在校验之前
    会被自己的冻结判定拦住,落在 `git add -A` 之后则重钉过的副本留在工作区
    没进提交 —— 下一个回合对方被冻结判定拦住,而那个改动不是它做的,
    撤销又会把重钉一起撤掉,它没有出路。
    """
    copy, src = judge_pair(root)
    if copy is None:
        return None                     # 没有副本 —— 什么都没发生
    copy.write_bytes(src.read_bytes())
    out = git("hash-object", PROG_HINT, cwd=root, check=False)
    # 到这一行副本**已经改写**。所以返回的是"重钉发生过"这个事实,不是
    # "取到了 sha":取不到就返回空串,调用方照样留痕。
    #
    # 两条看起来更严的路都比这条差:
    #   - 取不到就什么都不写 —— 那是"动作发生了、记录没有",正是 W10 要
    #     消灭的那一类失效(上一轮的漂移整轮没被发现,就因为它不让任何
    #     东西变红)。
    #   - 取不到就让整次交接失败 —— `die` 会把已经改写的副本留在工作区
    #     没进提交,下一个回合对方被冻结判定拦住,而拒绝文案让它"撤销这些
    #     改动",撤销就把重钉撤掉。这不是推演:`35136c4` 实测发生过一次。
    #
    # 副本同步是本工作项要守的不变量,记录的完整性次之 —— 所以宁可 sha
    # 缺一格,也不让副本停在半路。
    return (out or "").strip()


# 清单超过这个条数就截断 —— 列全会刷屏,人就不看了。
PATH_LISTING_LIMIT = 10


def is_orphan(path, cfg):
    """不属于任何角色、也不在共享/冻结/ignore_paths/记忆层里的已跟踪文件。

    **记忆层必须排除。** 它被挡在角色/冻结/共享之外不是配置疏忽,是
    cmd_verify_setup 的「记忆层路径自洽」那段自己强制的 —— 三种归法都会
    bad()。不排除,这条警告就没有任何一种消除方式,而一个结构上不可能清零的
    警告几次之后就没人看了。
    """
    if any(matches_any(path, cfg["roles"][r]) for r in ROLES):
        return False
    if matches_any(path, cfg["shared_paths"]):
        return False
    if matches_any(path, cfg["ignore_paths"]):
        return False
    if any(path_matches(path, f) for f in cfg["frozen_paths"]):
        return False
    if memory_on(cfg) and (path_matches(path, cfg["notes_dir"])
                           or path_matches(path, cfg["decisions_file"])):
        return False
    return True


def render_path_listing(head, paths, limit=PATH_LISTING_LIMIT):
    """`<首行>` + 逐行路径,超过 limit 只列前 limit 行再补**剩余**数。

    补的是剩余数不是总数:总数已经在首行里,再报一次说不出"还有多少没看到"。
    """
    lines = [head] + ["      %s" % p for p in paths[:limit]]
    if len(paths) > limit:
        lines.append("      … 还有 %d 个没列出" % (len(paths) - limit))
    return "\n".join(lines)


def combining_in_new_lines(root, cfg, entries):
    """评审目录与记忆层里**本回合新增的行**中的组合符(W37):[(路径, 行号, ["U+XXXX", ...])]。

    第十九轮把"文档里写码位用 `U+XXXX` 文字,也不嵌字符本身"写进了 `rules.md`;第二十轮两个会话在五份文档里
    嵌了 26 个裸组合符,谁都没发现 —— 写出来的就是它想写的,看不出问题。规则放在会话不去读的地方,而这件事脚本能判。
    只看新增行:未跟踪的文件是全部行,已跟踪的取相对 HEAD 的新增行。旧行不是这一回合写的,提示了也不该由这一回合改。
    测试与实现不管(测试另有 `chr(0x...)` 常量与 NFC 不动点护栏)。
    """
    docs = list(cfg["shared_paths"])
    if memory_on(cfg):
        docs += [cfg["notes_dir"], cfg["decisions_file"]]
    hits = []
    for xy, path in entries:
        if "D" in xy or not matches_any(path, docs) or not (root / path).is_file():
            continue
        if xy == "??":
            text = (root / path).read_text(encoding="utf-8", errors="replace")
            added = list(enumerate(text.splitlines(), 1))
        else:
            added, n = [], 0
            diff = git("diff", "-U0", "HEAD", "--", path, cwd=root, check=False) or ""
            for line in diff.splitlines():
                m = re.match(r"@@ -\S+ \+(\d+)", line)
                if m:
                    n = int(m.group(1))
                elif line.startswith("+") and not line.startswith("+++"):
                    added.append((n, line[1:]))
                    n += 1
        for lineno, line in added:
            marks = ["U+%04X" % ord(c) for c in line if unicodedata.category(c).startswith("M")]
            if marks:
                hits.append((path, lineno, marks))
    return hits


def os_files_left(entries, cfg):
    """这一回合要当它不存在的系统文件:**未跟踪**、文件名在 `OS_FILES` 里、**不在孤儿位置**(W35)。

    W31 只管被拒的那一种(孤儿位置,给出 `.gitignore` 出口)。落在某个角色路径下的,原先不会被拒,
    而是随 `git add -A` 被提交进仓库 —— 仓库里多一个谁都没写过的文件。只是不提交还不够:它留在工作区,
    下一回合就在对方的 `changed_entries` 里,不在对方的路径下,**对方的交接被写权限边界拒绝**
    (W35 的开工前审查 ⑩)。所以这类文件既不进提交、也不参与写权限边界的判定,不论谁的回合。
    已跟踪的不管:那是人类早先提交的。
    """
    return [p for xy, p in entries
            if xy == "??" and PurePosixPath(p).name in OS_FILES and not is_orphan(p, cfg)]


def _orphan_note(path, cfg):
    """越界文案里一个文件那一段的补充说明。

    操作系统写的文件(W31)单独说:它不是任何人改的,出口是人类把它加进 `.gitignore`,
    不是"划归到某个角色"。已接入、`.gitignore` 还没跟上 `GITIGNORE_LINES` 的项目会撞上 ——
    第十五轮 tester 的第一次交接就是这么被拦的,文案只让它去找人类,而新用户不知道这个文件是什么。
    **拒绝本身不变**;认的是文件名,`docs/.DS_Store` 也算。
    """
    if PurePosixPath(path).name in OS_FILES:
        return ("\n      这是操作系统写的文件(有人用文件管理器看过这个目录),不是谁改的。"
                "\n      请人类把它加进 .gitignore —— init 写的 .gitignore 已含这一行。")
    if is_orphan(path, cfg):
        return "\n      这个文件不属于任何角色,需要人类划归。"
    return ""


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


def review_append_paths(cfg, phase):
    """评审阶段执行者名下、**只能追加**的路径(`review_append_paths`,W16)。

    **不并进 `writable_paths`。** 那里评审与 idle 返回的是 `shared_paths`,而
    `shared_paths` 另有语义(任何阶段都可写、异议举证认它)。这批路径只在评审阶段、
    只对阶段执行者放开,而且放开的不是"可写",是"只追加" —— 在写权限边界里单独判。
    """
    if phase not in REVIEW_PHASES:
        return []
    return list((cfg.get("review_append_paths") or {}).get(PHASE_OWNER[phase], []))


def writable_display(cfg, phase, role=None):
    """`status` 与简报里"可写路径"那一行:只追加的路径标出来,免得被读成可写。

    `role` 是执行命令的角色(W25)。它不是这个阶段的执行者时,只给共享路径与记忆层 ——
    归属方的角色路径、评审阶段执行者名下的只追加路径,它一个都写不了。第九轮 tester 在
    impl 阶段看到的是 dev 的 `src …`,同一屏又写着"现在不是你的回合"。
    不传 `role` 就按阶段执行者算:简报只写给执行者(`cmd_status` 里 `me == owner` 才落盘)。

    **只改显示。** 写权限边界在 `handoff` 里另算,一直是对的;这里借 `writable_paths`
    的 idle 分支取"任何阶段都能写的那部分",不另起一套,免得显示与判定漂开。
    """
    if role is not None and role != PHASE_OWNER[phase]:
        return " ".join(writable_paths(cfg, "idle"))
    parts = list(writable_paths(cfg, phase))
    parts += ["%s(只追加)" % p for p in review_append_paths(cfg, phase)]
    return " ".join(parts)


def append_only_violation(root, path):
    """这份只追加路径本回合的改动是不是"只追加"。返回拒绝理由;None 放行。

    **"追加" = 相对 HEAD 没有删除行**,不是"加在末尾":`MUTATIONS` 的新条目必须插在
    收尾的 `]` 之前。删掉整个文件、改名,都有删除行。

    **必须已在 HEAD 里。** `has_rewrite` 对未跟踪文件的删除行数是 0,会把新建当成
    纯追加 —— 那等于评审回合能新写一整个测试文件。
    """
    if not blob_sha(root, path):
        return ("评审回合只能往已提交的文件追加,这份文件不在 HEAD 里 —— "
                "新建不算追加")
    if has_rewrite(root, path):
        return "评审回合只能往它追加,不能改或删已有行"
    return None


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


def worktree_sha(root, path):
    """工作区里这份文件内容的 blob sha;读不到返回 None。

    和 `blob_sha` 的区别:那个取 HEAD 里的,这个取工作区里的。W13 的记录端与
    比对端**都**用这一个 —— 两端口径不同会把整轮锁死(一端记 HEAD、一端比工作区,
    人类留一个未提交的契约改动,claim 就永久拒绝,重跑校验也解不开)。
    """
    if not (root / path).is_file():
        return None
    out = git("hash-object", "--", path, cwd=root, check=False)
    return out.strip() if out else None


def stale_verification(root, cfg, state, role):
    """这个角色上次通过开工前校验时读的契约,是不是现在工作区里这一份。
    返回拒绝理由;None 表示是同一份。**现场算,不写状态**:唯一能发现的时机是
    claim 的拒绝路径(那是 die),status 是只读的,whose-turn 承诺始终 exit 0。
    """
    rel = cfg["contract_file"]
    now = worktree_sha(root, rel)
    if now is None:
        return ("读不到 %s(被删或改名?)。契约是两边对齐的唯一依据,读不到就说不清\n"
                "你校验过的是哪一份。先让人类恢复它,再重跑:\n"
                "  python3 %s verify-setup --drafter self|other" % (rel, PROG_HINT))
    seen = (state.get("setup_verified_contract") or {}).get(role)
    if seen == now:
        return None
    why = ("状态里没有 %s 上次校验时读的是哪一份契约 —— 存量项目升级上来就是这样,\n"
           "\"不知道校验的是哪一份\"和\"校验的是另一份\"风险一样" % role
           if seen is None else
           "%s 在 %s 上次通过开工前校验之后变过(比的是工作区内容,\n"
           "人类还没提交的改动也算)" % (rel, role))
    return ("%s。\n\n"
            "每个角色各记一份,**只有 %s 自己重跑才能解锁** —— 照契约写断言的是 tester、\n"
            "写实现的是 dev,任何一方读的若是旧契约,两边就会各自\"对\"、合起来是废的。\n"
            "%s 重跑:\n"
            "  PAIR_ROLE=%s python3 %s verify-setup --drafter self|other"
            % (why, role, role, role, PROG_HINT))


def rebound_shortcut(root, cfg, state, green, changed_named_frozen):
    """review-test 打回之后的 spec 回合,能不能跳过 impl 与 review-impl 直接进 review-test(W17)。

    走捷径时,实现在 review-impl approve 之后没有任何人能改过:review-test 只读,
    spec 只能写测试与 `shared_paths`。能让"已审过的实现"失去依据的只有承重文件,
    所以两个来源都排除 —— 这一回合实际改的(按改动判,不按旗标判),与 review-impl
    approve 之后被提交的(比那一刻记下的契约工作区 sha)。规划文件不改变契约 sha,
    只能靠前一条管。

    **没有记录一律不走**:老状态没有 `rebound_from` / `reviewed_contract`,
    不猜。`None == sha` 本来就不成立,不另写一句判空。

    **不另判"是不是 spec、有没有裁决"。** `rebound_from` 只在打回那一次写成
    "review-test"、下一次交接就清掉,而 review-test 打回之后的下一次交接只能是
    spec 回合 —— 另判一遍是拆掉也没有用例能红的防护(W14 付过这个代价)。
    """
    if not green:
        return False
    if state.get("rebound_from") != "review-test":
        return False
    if changed_named_frozen:
        return False
    return state.get("reviewed_contract") == worktree_sha(root, cfg["contract_file"])


def phase_owner(root, cfg, state):
    """当前阶段归谁。只有 idle 有一处例外(W19)。

    `claim` 要求两个角色的开工前校验都作数之后,dev 那一份过期时**唯一能解锁的是 dev**,
    而 idle 的归属写死是 tester —— 驱动器会反复调度 tester、tester 反复被拒。所以:
    tester 那一份作数、dev 那一份不作数 → 归 dev;tester 不作数 → 照旧 tester
    (先让认领的一方读新契约);都作数 → tester。`whose-turn` 与 `status` 共用这一个判定。

    **不另判 `setup_verified`**:tester 那一份作数就意味着它校验过,
    另判一遍是拆掉也没有用例能红的防护。
    """
    phase = state["phase"]
    if phase == "idle" and cfg["require_setup_verification"]:
        if (stale_verification(root, cfg, state, "tester") is None
                and stale_verification(root, cfg, state, "dev")):
            return "dev"
    return PHASE_OWNER[phase]


IDLE_REVERIFY_BRIEF = """  当前没有进行中的工作项,但**你那一份开工前校验不作数了** —— 契约在你上次校验之后变过,
  或者你从没校验过。tester 认领会被拒,而只有你自己重跑才能解锁:

    PAIR_ROLE=dev python3 %(prog)s verify-setup --drafter self|other

  先通读契约里变了的那几节,往 docs/reviews/setup-verification-dev.md **末尾追加**
  一段补记(评审记录只能追加),再跑上面这条。"""


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


def no_decision_is_read(root, cfg, state, target):
    """这一回合晋升闸会不会**读到** `--no-decision`(W14:声明只在生效时留痕)。

    就是晋升闸的条件去掉 `not args.no_decision` 那一项:完成交接、笔记够长、
    本工作项还没有同 id 的决策。与 `check_memory` 里那一行同一个判据 ——
    那一行是变异锚点,不改写它,在这里另算一遍。必须在完成交接把 item 置空
    **之前**调用。
    """
    if not memory_on(cfg) or target != "DONE":
        return False
    item = state["item"]
    note = _read(notes_path(root, cfg, item)).strip()
    settled = [e for e in parse_decisions(_read(root / cfg["decisions_file"]))
               if e[0] == item]
    return len(note) >= MIN_NOTE_PROMOTE_CHARS and not settled


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
    settled = [e for e in parse_decisions(_read(root / dfile)) if e[0] == item]

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
                and cur_sha != state["contract_sha"] and not settled):
            return ("拒绝交接 —— %s 在这个工作项期间被改过,但 %s 里没有对应记录。\n\n"
                    "契约变更是重新推导代价最高的事:今后每个新回合都会拿改过的\n"
                    "契约当作理所当然,而改它的理由谁都看不到了。\n\n"
                    "追加一条 `## %s — …`,写清楚原来是什么、为什么不行、改成了什么。\n\n"
                    "%s" % (cfg["contract_file"], dfile, item,
                            DECISION_FORMAT_HINT))

        # --- 晋升 gate:笔记要随工作项一起沉底,给它一次留下的机会 -------
        note = _read(notes_path(root, cfg, item)).strip()
        if len(note) >= MIN_NOTE_PROMOTE_CHARS and not settled and not args.no_decision:
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
    - 禁止修改或删除任何测试。认为测试写错了 -> 写异议到 %(review_file)s
      (三个小节:哪条用例 / 和契约的哪一条矛盾 / 应该改成什么),
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

  【裁决必须带证据】先找问题,再决定通过与否。该挑的问题要真挑出来:
  敷衍的"看起来不错"会让两份努力合起来仍是废的。通过 -> 交出你具体查过
  哪些地方、为什么认为那里没问题;打回 -> 指到路径:行号。为了显得没在
  点头而制造一次打回,同样失真。

  详情写进:%(review_file)s
  (评审目录里的文件名要能对上工作项。模板见 references/documents.md)
  两个 flag 里的话要自己站得住,别写成"详见那个文件" —— 它们进提交正文,
  对方在 inbox 里必然看到,而文件要它主动去开。

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

  【裁决必须带证据】先找问题,再决定通过与否。该挑的问题要真挑出来:
  敷衍的"看起来不错"会让两份努力合起来仍是废的。通过 -> 交出你具体查过
  哪些地方、为什么认为那里没问题;打回 -> 指到路径:行号。为了显得没在
  点头而制造一次打回,同样失真。

  详情写进:%(review_file)s
  (评审目录里的文件名要能对上工作项。模板见 references/documents.md)
  两个 flag 里的话要自己站得住,别写成"详见那个文件" —— 它们进提交正文,
  对方在 inbox 里必然看到,而文件要它主动去开。

    打回 -> python3 %(prog)s handoff changes "问题清单,至少一处 路径:行号"
    通过 -> python3 %(prog)s handoff approve "摘要"
                --checked "你具体检查了什么" --uncovered "还没覆盖到什么\"""",
}


def review_file_for(cfg, state, phase):
    """这一回合该写哪个评审文件。**能生成的就别校验** ——
    命名规则的信息 state 里全有,直接告诉它,拒绝分支自然没人撞。"""
    item = state["item"]
    if not item or phase not in REVIEW_PHASES + DISPUTE_PHASES:
        return ""
    base = cfg["shared_paths"][0]
    if phase in DISPUTE_PHASES:
        return "%s/%s-dispute.md" % (base, item)
    n = state["changes_count"]
    return "%s/%s-%s%s.md" % (base, item, phase, "" if not n else "-%d" % (n + 1))


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
        "paths": writable_display(cfg, phase),
        "prog": PROG_HINT,
        "redgreen": rg,
        "notes": notes,
        "cover_hint": ("这条测试真的能发现回归吗(cover 类型的核心问题)"
                       if state["item_type"] == "cover"
                       else "用例是否真的对应 PLAN 里的工作项"),
        "review_file": review_file_for(cfg, state, phase),
    }


def render_brief(me, state, green, mem=""):
    """回合简报的正文。

    标题行 + 空行 + 四个 `- 字段: 值`(半角冒号加一个空格),末尾一个换行。
    字段顺序固定:角色 / 工作项 / 阶段 / 测试。工作项为空时写 `(无)`,
    类型为空时按 feature 算。测试只有 GREEN / RED 两个取值。

    `mem` 是 `memory_brief` 的返回值 —— **调用方算好了传进来,这里不自己算**。
    契约的「不做」要求简报与终端来自同一次取值:两处各算一遍,就有了两个
    可能不一致的答案,而这一节的全部意义是"可对质"。空串表示这一次终端
    没有注入记忆块,那时记忆段落连同它前面那个空行一起省略。

    格式是逐字节钉死的 —— 它是给人类事后对质用的凭据,不是终端输出的副本。
    """
    item = state["item"]
    if item:
        # 类型为空时按 feature 算 —— flow_of(None) 就是这么解释的,协议其余
        # 部分一律跟着它走。不这样写,v0 迁移过来的状态(没有 item_type 这个键)
        # 会写出裸 ID,而契约只给了 `<ID> [<类型>]` 和 `(无)` 两种形态。
        item = "%s [%s]" % (item, state["item_type"] or "feature")
    head = "".join(
        line + "\n" for line in [
            "# 回合简报",
            "",
            "- 角色: %s" % me,
            "- 工作项: %s" % (item or "(无)"),
            "- 阶段: %s" % state["phase"],
            "- 测试: %s" % ("GREEN" if green else "RED"),
        ])
    # 终端把记忆块包在两条 `=` 分隔线和一行标题里;简报只要内容本身。
    return head + ("\n" + mem.rstrip("\n") + "\n" if mem else "")


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
    owner = phase_owner(root, cfg, state)

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
    print(" 可写路径 : %s" % writable_display(cfg, phase, me))
    print(" 已完成项 : %d" % len(state["completed_items"]))
    if state["deadlock_hits"]:
        print(" 曾触发死锁闸: %s" % "、".join(state["deadlock_hits"]))
    print("=" * 52)

    # 共用一个目录时角色要来自 PAIR_ROLE(W22)。`.pair/whoami` 只有一个文件、同一目录里只有一个分支,
    # 两边会读成同一个角色,而谁都不会被拒绝。只警告不拒绝:sync 为假也可能只有一个 agent 在这个目录里。
    # 必须打在"不是你的回合"那一支之前 —— 那一支提前结束。
    if not cfg.get("sync") and source != ROLE_FROM_ENV:
        print()
        print(">>> 警告:你的角色来自 %s,而两个 agent 共用这个目录(sync 为假)。<<<" % source)
        print("它在同一个目录里只有一份,两个 agent 会读成同一个角色,谁都不会被拒绝。")
        print("每条协议命令都带上前缀:")
        print("  PAIR_ROLE=%s python3 %s <命令>" % (me, PROG_HINT))
        print("(只有一个 agent 在这个目录里工作时,这条可以忽略。)")

    if tampered:
        print()
        print(">>> 警告:%s 被修改过。<<<" % STATE_REL)
        print("协议状态文件由脚本维护,任何人手工修改都是违规的。")
        print("下次 handoff 会拒绝交接并还原它。")

    if cfg["require_setup_verification"] and not state["setup_verified"]:
        print()
        print(">>> 尚未通过开工前校验。<<<")
        print("结对的一方(通常是还没动手的那个)需要先跑:")
        print("  python3 %s verify-setup --drafter self|other" % PROG_HINT)
        print("在此之前不能认领工作项。")
    elif cfg["require_setup_verification"]:
        stale = stale_verification(root, cfg, state, me)
        if stale:
            print()
            print(">>> 提示:你上次的开工前校验已经不作数了(不阻断本命令)。<<<")
            for line in stale.split("\n"):
                print("  " + line if line else "")

    # 记忆块**只算这一次**,简报与终端共用它 —— 契约的「不做」要求两处来自
    # 同一次取值。而且只在终端真的会打印它的那条路径上算:PLAN 全部完成时
    # status 提前收尾,终端不打印记忆注入,简报也就没有记忆段落
    #(「同一次取值」优先于「轮到自己就写」)。
    all_done = plan_all_done(root, cfg)
    mem = ("" if all_done or me != owner
           else memory_brief(root, cfg, state, phase))

    # 轮到自己就写,与后面还打不打印阶段简报无关 —— PLAN 全部完成时
    # 这个函数会提前 return,而契约要求那种情况下简报照写(只是没有记忆段落)。
    if me == owner:
        try:
            write_brief(root, render_brief(me, state, green, mem))
        except OSError as exc:
            # 只兜 OSError(契约「边界」)。简报是可观测性、不是门禁:它写不出来
            # 该报告,但不该连累 status —— status 是每回合的第一条命令,它挂了
            # 整个回合就开不了工。try 只裹住写这一下,后面的记忆注入不受影响。
            # 换行压掉:契约要求标准输出**恰好多一行**。
            print("[简报] 写不出 %s:%s(不影响本回合)"
                  % (BRIEF_REL, str(exc).replace("\n", " ")))

    if all_done:
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
    if phase == "idle" and owner == "dev":
        print(IDLE_REVERIFY_BRIEF % {"prog": PROG_HINT})
    else:
        print(PHASE_BRIEF[phase] % _brief_vars(cfg, state, phase))
    if phase != "idle":
        print(scratch_hint(phase))
    print()

    # 记忆层召回。status 是协议强制的第一条命令,也是唯一能跨 harness
    # 保证一定被执行的时刻 —— 存了没人读等于没存,所以召回挂在这里。
    # `mem` 在上面已经算过,简报用的是同一份。
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
            "请让结对的另一方先跑:python3 %s verify-setup --drafter self|other"
            % PROG_HINT)

    # --- 契约变了,之前的校验作废(W13)---------------------------------------
    # 只作用于 claim:工作项中途契约变了不挡交接(本轮每一项都要改契约),
    # whose-turn 也不因此输出 stop。门禁没开时这一条不存在。
    if cfg["require_setup_verification"]:
        stales = [s for s in (stale_verification(root, cfg, state, r) for r in ROLES) if s]
        if stales:
            die("拒绝认领 —— " + "\n\n".join(stales))

    # --- 裁判副本必须与正本一致 -------------------------------------------
    # 校验放在 claim 不放在 handoff:工作项进行中 dev 正在改正本,两者本来
    # 就该不等 —— 放在 handoff 会让 dev 每一次实现都被自己拦住。
    if not judge_in_sync(root):
        die("拒绝认领 —— 裁判副本和正本不一致。\n\n"
            "  副本(实际在执行的):%s\n"
            "  正本(工作产物)    :%s\n\n"
            "副本落后时,协议是拿一个旧版本在判你 —— 上一轮真实发生过:\n"
            "两个文件差 122 行,整节孤儿清单在副本里根本不存在,而整轮没人发现,\n"
            "因为少一条警告不会让任何东西变红。\n\n"
            "重钉:\n"
            "  cp %s %s\n\n"
            "重钉之前先确认正本是绿的 —— 钉上去的那一份马上就要当裁判。"
            % (JUDGE_REL, PROG_HINT, PROG_HINT, JUDGE_REL))

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


ROADMAP_REL = "docs/improvements.md"


def normative_docs(cfg, entries):
    """本回合改动里的**规范性文档**。

    闭合定义:所有 `.md`,减去记忆层(`notes_dir` / `decisions_file`)与评审
    目录(`shared_paths`)。**不是枚举** —— 新加的 `.md` 默认落在范围内,
    而不是默认漏掉;第一版写成枚举,实算漏掉 13 份,其中包括 `AGENTS.md`、
    `CLAUDE.md` 这批告诉每个 agent"这是结对项目"的入口文件。

    **判据取本回合改动那一批(含未跟踪),不是 `git ls-files`。** 照后者判,
    本回合新写一份规范性文档就完全逃过这条要求,而新增文档恰恰最该说明为什么。
    调用方传进来的 `entries` 是 `handoff` 开头抓的那一批 —— 也就是
    `tick_plan_item` 写 `PLAN.md` **之前**,所以脚本自己的勾选不会被算进来。
    """
    out = []
    for _, path in entries:
        if not path.endswith(".md"):
            continue
        # 两个操作数的顺序是**故意**和写权限边界那一处相反的:变异点
        # 「拆掉 ignore_paths」与「拆掉协议日志的边界豁免」锚的是那一行的
        # 字面片段(mutation_check.py,tester 独占路径),这里照抄会让锚点
        # 命中两处、`test_变异点仍能匹配到源码` 直接红,而我改不了那个文件。
        if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:
            continue
        if matches_any(path, cfg["shared_paths"]):
            continue
        if memory_on(cfg) and (path_matches(path, cfg["notes_dir"])
                               or path_matches(path, cfg["decisions_file"])):
            continue
        out.append(path)
    return sorted(set(out))


def has_rewrite(root, path):
    """这个文件本回合相对 HEAD 有没有删除行(有=改写,无=纯追加)。

    **必须比 `HEAD`。** 不带参数的 `git diff` 只看未暂存的改动 —— agent 只要
    在 `handoff` 之前先 `git add` 自己那几个文件,删除行数就变成 0,
    `--basis` 直接绕过。未跟踪的新文件在 `HEAD` 里没有对应物,删除行数为 0,
    按纯追加处理,这是对的。
    """
    stat = git("diff", "--numstat", "HEAD", "--", path,
               cwd=root, check=False) or ""
    for line in stat.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[1].isdigit() and int(cols[1]) > 0:
            return True
    return False


def basis_points_at_file(root, text, entries):
    """`--basis` 里有没有一个指向真实文件的路径。

    三条都来自契约,少一条实现方就只能猜:
    - **抽取**按空白切开、逐个候选去问,**至少命中一个就算合格**(包含匹配,
      不是整串匹配)—— "见 X 的第二节"是人会自然写出来的形式;
    - **行号后缀**先剥掉再问,剥不出就按原样问;
    - **`known` 含本回合改动** —— 依据往往就是这一回合刚写的那份评审记录,
      只用 `tracked_files` 会让第一个真实用例就被拒。

    抽取这一步不能复用 `LOCATION_RE`:它的正则要求带行号,而依据通常是
    一份文档的路径、不带行号,拿它抽会一个都抽不出来。
    """
    known = set(tracked_files(root)) | {p for _, p in entries}
    for token in (text or "").split():
        stripped = re.sub(r":\d+$", "", token)
        if _known_path(token, known) or _known_path(stripped, known):
            return True
    return False


def _review_top_level(cfg, path):
    """这个路径是不是评审目录的**顶层 .md**。

    子目录(`docs/reviews/W1/x.md`)、附件、以及点开头的文件(`.gitkeep`)
    一律不管 —— 命名规则的用处是让人找得到评审记录,不是管辖整个目录。
    """
    name = PurePosixPath(path).name
    if not name.endswith(".md") or name.startswith("."):
        return False
    parent = str(PurePosixPath(path).parent)
    return any(parent == str(PurePosixPath(sp)) for sp in cfg["shared_paths"])


def review_rewrite_violation(root, cfg, path):
    """这份改动是不是在**改写**一份已提交的评审记录。返回拒绝理由;None 放行(W18)。

    评审记录是双方共识的凭据,和 `DECISIONS.md` 同级 —— 那边改写会被拒,这边一直不会。
    W14、W15 的第二次 review-impl 各把上一版整份改写,而简报其实一直给着正确的名字
    (`review_file_for` 在打回过之后算的是 `-2`),缺的只是写侧这一道。

    范围与命名检查同一个:评审目录的**顶层 `.md`**。判据与 `--basis` 判改写同口径:
    相对 HEAD 有删除行。删除整份、改名(W16 起改名拆成删除 + 新增)都有删除行。

    **两处措辞是故意跟既有变异锚点岔开的**:`blob_sha(...) is None` 与
    `not has_rewrite(...)` —— W16 的两个锚点是 `if not blob_sha(root, path):` 与
    `if has_rewrite(root, path):`,照抄会让那两个锚点各匹配两处,
    `test_变异点仍能匹配到源码` 当场红。
    """
    if not _review_top_level(cfg, path):
        return None
    if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:
        return None
    if blob_sha(root, path) is None:
        return None
    if not has_rewrite(root, path):
        return None
    return "评审记录只能追加:这份文件已经提交过,不能改或删它已有的行"


def review_rewrite_hint(cfg, state, phase):
    """改写评审记录被拒时,告诉它本回合该写哪个文件、以及不要撤销别人的东西。"""
    name = review_file_for(cfg, state, phase)
    where = "本回合该写的是 %s" % name if name else "要另写就新建一份文件"
    return "%s。\n      如果这份改动不是你做的,不要撤销,也不要改名 —— 告诉人类。" % where


def check_review_names(root, cfg, entries, item_ids):
    """评审记录的文件名要能对上某个工作项。返回拒绝理由;None 放行。

    **对的是 PLAN 里的全部工作项 ID,不是当前这个。** 只认当前 item 会造成
    两种误伤:人类在 `docs/reviews/` 放了文件却没提交(协议正是这么要求人类
    介入的),以及上一个工作项遗留在工作区里的评审文件 —— 两种情况下 agent
    的唯一出路都是改名或删掉**不是它写的东西**,而那两件事它都不该做。
    """
    bad = []
    for xy, path in entries:
        if "D" in xy or path in PROTOCOL_LOGS or matches_any(path, cfg["ignore_paths"]):
            continue
        if not _review_top_level(cfg, path):
            continue
        name = PurePosixPath(path).name
        if name in REVIEW_FIXED_NAMES:
            continue
        stem = name
        for pre in REVIEW_ID_PREFIXES:
            if name.startswith(pre):
                stem = name[len(pre):]
                break
        # `W1.md` 和 `W1-review-impl.md` 都算数,但 `W11-x.md` 不能在 W1 的回合蒙混
        if any(stem == i + ".md" or stem.startswith(i + "-") for i in item_ids):
            continue
        bad.append(path)

    if not bad:
        return None
    return ("拒绝交接 —— 评审目录里这些文件的名字对不上任何工作项:\n  %s\n\n"
            "规范:`<工作项ID>-<随便什么>.md`,或者 `<工作项ID>.md`。\n"
            "固定名 %s 和 `contract-change-<工作项ID>.md` 也可以。\n"
            "PLAN 里现有的工作项:%s\n\n"
            "**如果这个文件不是你写的,不要改名、不要删,告诉人类。**\n"
            "人类在结对期间往这里放文件却没提交,就会变成这样 —— "
            "见 INSTALL.md 的「人类介入的纪律」。"
            % ("\n  ".join(bad), "、".join(REVIEW_FIXED_NAMES),
               "、".join(item_ids) or "(无)"))


def missing_sections(text, sections, min_chars=MIN_NOTE_SECTION_CHARS):
    """文本里缺了哪些必需小节。从 missing_note_sections 里解出来的纯函数版 ——
    同一段逻辑此前只有笔记在用,现在异议、契约变更请求、基线说明都要用。"""
    missing = []
    for name in sections:
        m = re.search(r"^#{2,}\s*%s\s*$" % re.escape(name), text, re.M)
        if not m:
            missing.append("缺少小节 `## %s`" % name)
            continue
        rest = text[m.end():]
        nxt = re.search(r"^#{1,6}\s", rest, re.M)
        body = (rest[:nxt.start()] if nxt else rest).strip()
        if len(body) < min_chars:
            missing.append("`## %s` 正文太短(%d 字,至少 %d)"
                           % (name, len(body), min_chars))
    return missing


ARCHAEOLOGY_SHA_RE = re.compile(r"依据[::]\s*考古观察@([0-9a-fA-F]{4,40})")


def check_archaeology_shas(root, cfg, entries):
    """`依据: 考古观察@<sha>` 里的 sha 必须指向真实的 commit。

    `cover` 回合起草的契约草案会**变成契约本身** —— 它是下游影响最大的一份
    agent 产出。而 `考古观察@<sha>` 是三档依据里唯一**可被脚本校验**的那档:
    sha 存不存在,git 说了算。不查的话,写一个编的 sha 和写"人类定稿"
    一样容易,那这一档就只是个好听的标签。
    """
    bad = []
    for xy, path in entries:
        if "D" in xy or not matches_any(path, cfg["shared_paths"]):
            continue
        for sha in ARCHAEOLOGY_SHA_RE.findall(_read(root / path)):
            if git("cat-file", "-e", sha + "^{commit}", cwd=root, check=False) is None:
                bad.append((path, sha))
    if not bad:
        return None
    return ("拒绝交接 —— `考古观察@<sha>` 里的 sha 在本仓库找不到:\n%s\n\n"
            "`考古观察` 是三档依据里唯一可被脚本校验的那一档,靠的就是这个 sha。\n"
            "它记的是「我读的是哪个版本的代码」 —— 编一个 sha,这一档就只剩标签。\n"
            "用 `git rev-parse --short HEAD` 取当前的。"
            % "\n".join("  %s → %s" % (p, sha) for p, sha in bad))


def check_shaped_documents(root, cfg, entries, state, phase, verdict):
    """异议 / 契约变更请求 / 基线说明:有必含小节的那三份。返回拒绝理由。

    三处的共同点是 rules.md 早就写明了要素、却零强制 —— 而它们各自守着的东西
    都不轻:异议是**全协议唯一豁免红绿不变量**的入口;契约变更会改动那份
    "唯一会致命"的文件;基线说明是门禁范围被缩小的唯一留痕。
    """
    item = state["item"]
    written = {PurePosixPath(p).name: p for xy, p in entries
               if "D" not in xy and _review_top_level(cfg, p)}

    # 归人类的那份要多给一条出路。命名检查(check_review_names)已经踩过这个
    # 教训并写进了 docstring:只按当前回合判,会把人类留在工作区里的文件算到
    # agent 头上,而它的唯一出路就变成改名或删掉**不是它写的东西**。
    # `baseline.md` 是总表里唯一归人类的那份,同一条出路必须给它。
    NOT_YOURS = ("\n\n**如果这个文件不是你写的,不要改、不要删,告诉人类。**\n"
                 "%s 归人类写。人类在结对期间往评审目录放文件却没提交,\n"
                 "就会变成这样 —— 见 INSTALL.md 的「人类介入的纪律」。")

    def shape(name, sections, why, human_owned=False):
        rel = written.get(name)
        if rel is None:
            return None
        miss = missing_sections(_read(root / rel), sections)
        if not miss:
            return None
        return ("拒绝交接 —— %s 缺少必需的小节:\n  - %s\n\n"
                "需要这几节,每节正文至少 %d 字:\n%s\n\n%s%s"
                % (rel, "\n  - ".join(miss), MIN_NOTE_SECTION_CHARS,
                   "\n".join("  ## " + x for x in sections), why,
                   (NOT_YOURS % name) if human_owned else ""))

    # 异议:dev 在 impl 阶段打回测试。规则 2 早就写了三要素,却零强制。
    # 这里**要求文件必须存在**,不是"写了才查形状" —— 因为 verdict + phase
    # 这个信号是现成的,而按文件名触发的检查,开关在被约束者手里。
    # 不变量 9 只要求"写了 shared_paths 下的某个文件",这一条把它变具体。
    if item and verdict == "changes" and phase in DISPUTE_PHASES:
        name = "%s-dispute.md" % item
        if name not in written:
            return ("拒绝交接 —— 提异议要写进 %s/%s。\n\n"
                    "需要三个小节(rules.md 规则 2 的三要素),每节至少 %d 字:\n"
                    "%s\n\n"
                    "这条路径**豁免红绿不变量** —— 全协议只有它豁免。\n"
                    "换来的代价就是把话说清楚:对方看不到你的对话,\n"
                    "指不出是哪条用例、和契约的哪一条矛盾,它无从下手。"
                    % (cfg["shared_paths"][0], name, MIN_NOTE_SECTION_CHARS,
                       "\n".join("  ## " + x for x in DISPUTE_SECTIONS)))
        r = shape(name, DISPUTE_SECTIONS,
                  "这条路径豁免红绿不变量 —— 全协议只有它豁免。"
                  "换来的代价就是把话说清楚。")
        if r:
            return r

    # 契约变更请求:按文件名触发。脚本无从知道"这个回合是一次契约变更请求",
    # 所以这条是"你用了这个名字就得守这个形状",不是"契约变更必须走这个形状"。
    if item:
        r = shape("contract-change-%s.md" % item, CONTRACT_CHANGE_SECTIONS,
                  "契约漂移是这套机制唯一会致命的失败模式。"
                  "人类要拿这份材料去改那份文件,四要素缺一都不够。")
        if r:
            return r

    r = shape("baseline.md", BASELINE_SECTIONS,
              "门禁套件被收窄之后,这份是「放弃了什么」的唯一留痕。",
              human_owned=True)
    if r:
        return r
    return None


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
    # W35:落在孤儿位置以外的未跟踪系统文件,这一回合当它不存在 —— 不进写权限边界、不进提交。
    # 下面每一道判定看的都是 `entries`,所以在这里一次拿掉,不在每道判定里各写一遍。
    left_os = os_files_left(entries, cfg)
    entries = [(xy, p) for xy, p in entries if p not in left_os]
    # W37:提交前算好(提交之后就没有"相对 HEAD 的新增行"了),交接成功后再打印。
    combining = combining_in_new_lines(root, cfg, entries)

    # --- 写权限边界校验 ---------------------------------------------------
    allowed = writable_paths(cfg, phase)
    appendable = review_append_paths(cfg, phase)
    exempt_from_scope = list(cfg["shared_paths"])
    if memory_on(cfg):
        exempt_from_scope += [cfg["notes_dir"], cfg["decisions_file"]]
    # 冻结豁免:**只认 `plan_file` 与 `contract_file` 这两个配置键**,
    # 不是"带了旗标就能改冻结路径" —— `frozen_paths` 里还有 `.pair`,
    # 而 `.pair/enforcer.py` 是裁判,一个旗标能改判官,这条防护就整个塌了。
    # `continue` 落在循环最前面,所以跳过的是**三道**判定(冻结、越界、scope):
    # 只跳冻结那一道的话,下一行就是越界 —— 这两份文件不在任何角色路径里,
    # 五个阶段全部不在 allowed 中,拒绝理由只会从"冻结"换成"越界"。
    named_frozen = {cfg["plan_file"], cfg["contract_file"]}
    violations = []
    for xy, path in entries:
        if path in named_frozen and args.contract_change:
            continue
        if path in PROTOCOL_LOGS or matches_any(path, cfg["ignore_paths"]):
            continue
        hit_frozen = next((f for f in cfg["frozen_paths"]
                           if path_matches(path, f)), None)
        if hit_frozen is not None:
            violations.append((path, "冻结路径 %s 之下,agent 不得修改" % hit_frozen))
            continue
        # 只追加路径(W16):不进 allowed,在这里单独判,判完就不再走越界那一道。
        if matches_any(path, appendable):
            why = append_only_violation(root, path)
            if why:
                violations.append((path, why))
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

    for xy, path in entries:
        rewrite = review_rewrite_violation(root, cfg, path)
        if rewrite:
            violations.append((path, rewrite + "。" + review_rewrite_hint(cfg, state, phase)))

    # 孤儿要单独说。开工前的警告和真正撞上的时刻隔着几十个回合,而撞上的那个
    # 文件多半是人类刚改的 —— 让 agent"撤销这些改动"就会撤销掉不是它写的东西。
    # 只在中间加一句提示不够:末尾留着一句相反的指令,agent 照样照后者做,
    # 所以末尾那句要跟着变。
    #
    # 下面两行之间不能插东西:变异点「拆掉写权限边界」锚的就是 `if violations:`
    # 紧跟 `lines =`(mutation_check.py 的 MUTATIONS,在 tester 路径下,我改不了)。
    # 孤儿的计算因此排在 lines 之后,不是它逻辑上该在的位置。
    if violations:
        lines = "".join(
            "\n  %s\n      %s%s"
            % (p, why, _orphan_note(p, cfg))
            for p, why in violations)
        orphaned = [p for p, _ in violations if is_orphan(p, cfg)]
        if orphaned:
            tail = ("其中 %d 个不属于任何角色 —— 那多半不是你改的。\n"
                    "**先找人类划归,不要直接撤销。** 其余越界的改动请撤销后重试。"
                    % len(orphaned))
        else:
            tail = "请撤销这些改动后重试。"
        die("拒绝交接 —— 以下改动越界:%s\n\n%s如果你认为规则本身有问题,"
            "写进 docs/reviews/ 并告诉人类。" % (lines, tail + ""))

    # --- 契约/计划的变更要带声明,并且当场留决策 ---------------------------
    changed_named_frozen = sorted({p for _, p in entries if p in named_frozen})
    if changed_named_frozen and args.contract_change:
        # 校验强度取高的那一档,和 `--basis` 同一条判据:只要求非空的话,
        # 它和 `--doc-reason` 效果完全一样,叠在一起只是多打一行字。
        if not basis_points_at_file(root, args.contract_change, entries):
            die("拒绝交接 —— `--contract-change` 里没有指向真实文件的路径,\n"
                "所以它只是一句话,对方无从核对。\n\n"
                "  你写的: %s\n"
                "  改动的: %s\n\n"
                "写一份**产物**的路径(本回合的决策记录、评审记录这类);\n"
                "可以写在句子里,也可以带行号。"
                % (args.contract_change, "、".join(changed_named_frozen)))
        # 这是一条**新检查,不是复用**:既有那条(契约在工作项期间变过就必须
        # 留决策)的触发点是 `target == "DONE"`,拿 `claim` 时记下的
        # contract_sha 比对 —— 它抓的是"完成时发现契约变过",抓不到
        # 改动发生的那一刻。两条并存、互不替代。
        fresh = [e for e in new_decision_entries(root, cfg) if e[0] == item]
        if not fresh:
            die("拒绝交接 —— 你改了 %s,但本回合没有留下决策。\n\n"
                "承重文件的改动是重新推导代价最高的事:今后每个回合都会拿改过的\n"
                "版本当作理所当然,而改它的理由谁都看不到了。\n\n"
                "在 %s 里追加一条 `## %s — …`,写清楚原来是什么、为什么不行、\n"
                "改成了什么。\n\n%s"
                % ("、".join(changed_named_frozen), cfg["decisions_file"],
                   item, DECISION_FORMAT_HINT))

    # --- 文档改动要带理由 -------------------------------------------------
    # 用的是 `entries`(handoff 开头抓的那一批),不是提交内容:完成工作项时
    # 脚本自己去 PLAN.md 勾选,那次写入发生在这之后 —— 按提交判会让每一次
    # 完成工作项的交接都被要求 --doc-reason,而那个改动不是 agent 做的。
    touched_docs = normative_docs(cfg, entries)
    # 判空要剥空白,和同一份文件里 --checked / --uncovered 的判据一致:
    # 实测 `--doc-reason "   "` 退出码 0,而 git 会剥掉尾随空白 ——
    # 提交正文那一行渲染成「文档改动理由:」后面什么都没有,
    # 放行了,而且留下的痕和没写一模一样。契约要的是强制留痕。
    if touched_docs and not (args.doc_reason or "").strip():
        die("拒绝交接 —— 本回合改了规范性文档,但没说为什么:\n  %s\n\n"
            "归属其实已经有了(提交正文里那行 `role=… phase=… item=…` 由脚本\n"
            "写入,可靠),缺的是**理由与文档的绑定**:一次交接可能改了实现\n"
            "加三份文档,而说明只有提交标题那一句。\n\n"
            "  python3 %s handoff \"说明\" --doc-reason \"为什么改这些文档\"\n\n"
            "笔记与评审记录豁免 —— 它们本身就是理由。\n"
            "理由会写进提交正文,不校验写得好不好,那靠对方评审。"
            % ("\n  ".join(touched_docs), PROG_HINT))

    # --- 路线图的改写要有依据 ---------------------------------------------
    # 只作用于路线图,而且只在**有改写**时:新条目往往是审查中发现的待办,
    # 一刀切会让"记录一个发现"也要走重流程,路线图就变成不能记录发现的死文档。
    if ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):
        if not args.basis:
            die("拒绝交接 —— 你改写了 %s(有删除行),这要给依据。\n\n"
                "纯追加(只新增、不删行)不需要 —— 记录一个发现应当是轻的。\n"
                "但**改写**动的是别人已经读过的结论,要说清楚凭什么。\n\n"
                "  python3 %s handoff \"说明\" --doc-reason \"…\" "
                "--basis \"docs/reviews/…\"\n\n"
                "依据要指向一个仓库里真实存在的路径(评审记录、决策记录这类\n"
                "**产物**),不是一句散文 —— 那样对方才能点开核对。"
                % (ROADMAP_REL, PROG_HINT))
        if not basis_points_at_file(root, args.basis, entries):
            die("拒绝交接 —— `--basis` 里没有指向真实文件的路径,\n"
                "所以它和 `--doc-reason` 一样只是一句话,对方无从核对。\n\n"
                "  你写的: %s\n"
                "  改写的: %s\n\n"
                "写一份**产物**的路径,例如本回合的评审记录或决策记录;\n"
                "可以写在句子里(\"见 X 的第二节\"),也可以带行号(\"X:12\")。"
                % (args.basis, ROADMAP_REL))

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

    # --- 评审目录的命名 ---------------------------------------------------
    refusal = check_review_names(
        root, cfg, entries, [i for i, _, _, _ in parse_plan(root, cfg)])
    if refusal:
        die(refusal)

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

    # --- 考古观察的 sha 必须是真的 ------------------------------------------
    refusal = check_archaeology_shas(root, cfg, entries)
    if refusal:
        die(refusal)

    # --- 三份有必含小节的文档 ----------------------------------------------
    # 放在评审证据之后:一个什么都没写的回合该先收到"你没写下来",
    # 而不是"小节缺了"。顺序即语义。
    refusal = check_shaped_documents(root, cfg, entries, state, phase, verdict)
    if refusal:
        die(refusal)

    # --- 记忆层门禁 -------------------------------------------------------
    # 放在跑测试之前:纸面上的问题不值得先花一遍测试时间。
    refusal = check_memory(root, cfg, state, phase, verdict, target, args)
    if refusal:
        die(refusal)
    # 趁工作项状态还没被下面的完成交接清空,记下晋升闸有没有读到 --no-decision。
    no_decision_read = no_decision_is_read(root, cfg, state, target)

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

    # --- 只涉及测试的打回不再经过 impl(W17)-----------------------------------
    if target == "impl" and rebound_shortcut(root, cfg, state, green, changed_named_frozen):
        target = "review-test"

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
    state["rebound_from"] = phase if verdict == "changes" else None
    if phase == "review-impl" and verdict == "approve":
        state["reviewed_contract"] = worktree_sha(root, cfg["contract_file"])
    save_state(root, state)

    # --- 裁判副本重钉 -----------------------------------------------------
    # 只在 DONE 且全绿时。"全绿"就是证据 —— 那是这个协议唯一信任的东西,
    # 不另造一套。位置钉两头:在写权限边界校验之后(否则被自己的冻结判定
    # 拦住),且在 `git add -A` 之前(否则重钉过的副本留在工作区没进提交)。
    repinned = repin_judge(root) if (target == "DONE" and green) else None

    # --- 提交 -------------------------------------------------------------
    prefix = ("dispute" if is_dispute
              else COMMIT_PREFIX[phase] + ("/" + verdict if verdict else ""))
    body = "role=%s phase=%s -> %s item=%s type=%s" % (
        me, phase, next_phase, item or "none", state["item_type"] or
        (flow is FEATURE_FLOW and "feature" or "?"))
    # 声明只在**生效**时写进正文(W14):"生效"= 这一回合真有检查读到了它,
    # 不是"处在它该出现的阶段"。不生效时不写、不进统计,但也**不拒绝** ——
    # 要治的是统计被污染,不是用法不整洁。判据一律用 handoff 开头抓的那批
    # 改动(entries),不用提交内容:完成时 tick_plan_item 会改 PLAN.md。
    if args.allow_deletion and deleted:
        body += "\n删除测试(已声明): %s\n  %s" % (args.allow_deletion,
                                                 "\n  ".join(deleted))
    if args.no_decision and no_decision_read:
        body += "\n未留决策(已声明): %s" % args.no_decision
    if args.doc_reason and touched_docs:
        body += "\n文档改动理由: %s" % args.doc_reason
    if args.basis and ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):
        body += "\n改写依据: %s" % args.basis
    if args.contract_change and changed_named_frozen:
        body += "\n契约变更(已声明): %s" % args.contract_change
    # 空转判定(W14):每一次从 impl 出发、且不是异议的交接都写,值为是/否 ——
    # 只在空转时才写的话,report 分不出"没空转"和"那时还没有这一行"。
    # 空转 = 本回合的改动里,既没有落在执行者角色路径下的,也没有带
    # --contract-change 生效的承重文件改动(W9 合法化的那类交付不算开销)。
    if phase == "impl" and not is_dispute:
        idle = not (any(matches_any(p, cfg["roles"][me]) for _, p in entries)
                    or (args.contract_change and changed_named_frozen))
        body += "\n%s: %s" % (IDLE_JUDGMENT, "是" if idle else "否")
    if verdict == "approve":
        body += "\n检查了: %s\n未覆盖: %s" % (args.checked, args.uncovered)
    # `is not None` 而不是真值判断:空串表示"重钉发生了但 sha 没取到",
    # 那一行更要写,不能被 falsy 吞掉。
    if repinned is not None:
        body += "\n裁判副本已重钉: %s -> %s (%s)" % (
            PROG_HINT, JUDGE_REL, repinned or "sha 取失败")

    git("add", "-A", cwd=root)
    if left_os:
        # 退回未暂存:它们留在工作区,不删 —— 不是 agent 写的,删不删是人类的事。
        git("reset", "-q", "--", *left_os, cwd=root)
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
    if left_os:
        print()
        print("  以下是操作系统写的文件(有人用文件管理器看过这个目录),没有提交、留在工作区:")
        for p_ in left_os:
            print("      %s" % p_)
        print("  请人类把它们加进 .gitignore —— init 写的 .gitignore 已含这几行。")
    if combining:
        print()
        print("  评审或笔记里本回合新写的行嵌着组合符(字符本身,不是文字),读的人看不出来:")
        for p_, n_, marks in combining:
            print("      %s:%d  %s" % (p_, n_, " ".join(marks)))
        print("  文档里提到码位请写成 U+XXXX 这样的文字(不写转义,也不嵌字符本身)。"
              "这只是提示,交接已经完成。")
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
# whose-turn
# --------------------------------------------------------------------------

def cmd_whose_turn(root, cfg, args):
    """一行机器可读的输出:接下来该谁,或者为什么该停。

    存在的理由是**让驱动器里没有协议逻辑**。自动驱动两个 agent 时,
    "现在轮到谁""要不要停下来交给人类"都是协议判断 —— 让驱动脚本自己去读
    state.json 猜,它就成了协议的第二个实现;两份判定迟早不一致,门禁看着
    还在、实际拦不住。所以判断留在这里,驱动器只认这一行输出。

    **不跑测试。** 它会被循环调用,而 status 已经负责跑测试了。

    输出:
        turn tester | turn dev        接下来轮到谁
        stop <理由>                   该停下来交给人类
    退出码始终 0 —— 它是查询,不是门禁。
    """
    state = load_state(root)

    if cfg["require_setup_verification"] and not state["setup_verified"]:
        print("stop 尚未通过开工前校验,需要结对的一方先跑 verify-setup")
        return 0
    if plan_all_done(root, cfg):
        print("stop %s 里的工作项已全部完成" % cfg["plan_file"])
        return 0
    if state["changes_count"] >= DEADLOCK_LIMIT:
        print("stop 工作项 %s 已被打回 %d 次,协议要求交给人类裁决"
              % (state["item"], state["changes_count"]))
        return 0
    if state_is_tampered(root):
        print("stop %s 被改动过,先跑 status 确认真实状态" % STATE_REL)
        return 0

    print("turn %s" % phase_owner(root, cfg, state))
    return 0


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

# 健康区间。区间之外不等于错,等于**值得看一眼**。
HEALTH = {
    "打回率": (0.15, 0.50),
    "死锁工作项占比": (0.0, 0.10),
}

# 少于这个数的样本,比率没有意义,只报原始计数。
MIN_SAMPLE = 5

REPORT_SEP = "\x1f"
# impl 交接写进提交正文的那一行的前缀,handoff 写、report 读 —— 同一个常量。
IDLE_JUDGMENT = "空转判定"


# report 只认协议写进提交里的那几行(W21)。正文里还有评审旗标的值、人类手写的散文 ——
# 在整段正文里找子串,顺带提到一句就被算进去:`0aea588`(路线图散文里的 `item=`)被算成交接,
# `136cabd`(评审 `--checked` 里的 `phase=… -> idle`)被算成完成。**必须在行首、必须是完整形状。**
# 组:1 = 来源阶段,2 = 去向,3 = 工作项。与 handoff 里 `body = "role=%s phase=%s -> %s item=%s type=%s"` 同形。
PROTOCOL_LINE_RE = re.compile(r"^role=\S+ phase=(\S+) -> (\S+) item=(\S+) type=", re.M)
NO_DECISION_LINE_RE = re.compile(r"^未留决策\(已声明\): ", re.M)
CONTRACT_CHANGE_LINE_RE = re.compile(r"^契约变更\(已声明\): ", re.M)
# 主题的后半句是执行者写的自由文本,只认 handoff 触发死锁闸时生成的那个完整主题。
DEADLOCK_SUBJECT_RE = re.compile(r"^chore\(pair\): 工作项 \S+ 打回 \d+ 次,触发死锁闸$")


def _handoff_log(root, since=None):
    """[(subject, body)],按时间正序。`since` 是起点提交的 sha 时只读 `<since>..HEAD`(W20)。"""
    fmt = "%s" + REPORT_SEP + "%b" + REPORT_SEP + "%x00"
    span = ("%s..HEAD" % since,) if since else ()
    out = git("log", "--reverse", "--format=" + fmt, *span, cwd=root, check=False) or ""
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

    它补的是一个观测缺口:**"交付会不会在悄悄变废"在此之前无法量化。**
    脚本能强制评审带证据(结构),强制不了评审有内容。评审样本足够时,
    打回率长期接近 0 是这件事唯一的量化证据。防点头是保障交付的手段,
    不是协议存在的全部目的;report 盯的是手段层有没有在空转 —— 打回率只是其中一项。

    区间之外不等于错,等于值得看一眼。
    """
    # 起点(W20):只认**提交**。`^{commit}` 让树、blob 这类合法对象也被拒 ——
    # `<tree>..HEAD` 不成立,git 会报错,而 check=False 会把它吞成"区间为空"。
    since = None
    if args.since is not None:
        since = (git("rev-parse", "--verify", "-q", args.since + "^{commit}",
                     cwd=root, check=False) or "").strip() or None
        if since is None:
            die("report --since %s:这不是本仓库里的一个提交。\n"
                "起点要能解析成提交:sha、分支名、HEAD~3 这类。" % args.since)
        # 旁支上的提交也能解析成提交,但 `<它>..HEAD` 是两条分支的差集,不是"它之后" ——
        # 退出 0、看起来合理的一张表,正是这个参数要消灭的静默偏差。
        if git("merge-base", "--is-ancestor", since, "HEAD", cwd=root, check=False) is None:
            die("report --since %s:这个提交不在当前分支的历史上(不是 HEAD 的祖先)。\n"
                "拿它当起点,统计的会是两条分支的差集,而不是\"它之后\"。\n"
                "换一个当前分支历史上的提交。" % args.since)
    rows = _handoff_log(root, since)
    state = load_state(root)

    reviews = changes = disputes = 0
    claimed = deadlocks = no_decision = contract_changes = 0
    idle_rounds = unjudged = 0          # W14:空转的 impl 回合 / 没有判定行的 impl 回合
    finished = 0                        # W20:区间里把工作项推进到完成的交接
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
        if DEADLOCK_SUBJECT_RE.match(subject):
            deadlocks += 1
        if NO_DECISION_LINE_RE.search(body):
            no_decision += 1
        if CONTRACT_CHANGE_LINE_RE.search(body):
            contract_changes += 1
        m = PROTOCOL_LINE_RE.search(body)
        if m and m.group(3) != "none":
            rounds_by_item[m.group(3)] = rounds_by_item.get(m.group(3), 0) + 1
            # 只在表头计入的提交里数,两数之和才恒等于「交接提交」。
            # **空转只认那一行**,不在这里再按阶段过滤:写不写判定行是 handoff 的
            # 职责(只写在 impl、非异议的交接上)。两边各过滤一遍的话,拆掉任何
            # 一边都没有用例看得见 —— 冗余的防护等于没有可测的防护。
            if m.group(2) == "idle":
                finished += 1
            j = re.search(r"^%s: (是|否)$" % IDLE_JUDGMENT, body, re.M)
            if j and j.group(1) == "是":
                idle_rounds += 1
            elif j is None and m.group(1) == "impl" and prefix != "dispute":
                unjudged += 1           # 没有判定行的 impl 交接不猜,单独计

    done = len(state["completed_items"])
    decisions = len(parse_decisions(_read(root / cfg["decisions_file"]))) \
        if memory_on(cfg) else 0
    rate = (changes / float(reviews)) if reviews else None
    dl_rate = (deadlocks / float(claimed)) if claimed else None

    print("=" * 62)
    print(" 结对健康度  —  %s" % root)
    print("=" * 62)
    print(" 已完成工作项 : %d        进行中: %s"
          % (done, state["item"] or "(无)"))
    print(" 交接提交     : %d        认领: %d"
          % (sum(rounds_by_item.values()), claimed))
    if since:
        print(" 起点         : %s(只作用于从提交里数的行;已完成工作项、进行中、"
              "决策/完成项照读状态)" % since[:12])
    print("-" * 62)

    def row(name, value, verdict):
        print(" %s %s %s" % (_pad(name, 20), _pad(value, 18), verdict))

    row("指标", "值", "判定")
    print("-" * 62)
    row("打回率", _fmt_rate(changes, reviews),
        _flag("打回率", rate, reviews >= MIN_SAMPLE))
    # 「每工作项回合数」删掉了:它把推进交付的回合与协议开销的回合混在同一个
    # 分母里,第四轮显示 7.9 ok 而其中有空转 —— 会给出错误诊断的指标比没有更糟。
    # 三个绝对计数,不设健康区间:样本还不足以说什么算正常,先让它可观测。
    handoffs = sum(rounds_by_item.values())
    row("推进交付的回合", "%d" % (handoffs - idle_rounds), "—")
    row("协议开销的回合", "%d" % idle_rounds, "—")
    row("未判定的 impl 回合", "%d" % unjudged, "—")
    row("死锁工作项占比", _fmt_rate(deadlocks, claimed),
        _flag("死锁工作项占比", dl_rate, claimed >= MIN_SAMPLE))
    row("测试异议", "%d 次" % disputes, "—")
    row("决策/完成项", "%d / %d" % (decisions, done),
        "!! 记忆层空转" if done >= MIN_SAMPLE and not decisions else "—")
    # 两条声明比率的分母跟着起点走(W20):分子只数区间里的声明,分母若仍读状态里的
    # 全部历史完成数,区间里完成 1 项、带 1 次生效声明会显示 50% (1/2)。
    per_done = finished if since else done
    row("--no-decision", _fmt_rate(no_decision, per_done),
        "!  偏高" if per_done and no_decision > per_done / 2.0 else "—")
    # 承重文件不再冻结,换来的是"改了必有人知道"。频率是这笔交易唯一的
    # 观测量:弱版本对"两个 agent 合谋改契约去迁就实现"的防护弱于双方签字,
    # 异常了就该收紧。
    row("--contract-change", _fmt_rate(contract_changes, per_done),
        "!  偏高" if per_done and contract_changes > per_done else "—")
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
        print("  这是手段层最该警惕的失效模式:两个 agent 互相点头,红绿全对,")
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
- 一个角色的回合由这个角色自己的会话从头跑到尾(`status`、`handoff` 都是),
  不要转手给别的 agent 或会话去跑 —— 回合状态在 `.pair/state.json`,
  转手之后谁做的、做到哪一步就对不上了。**你本身就是这个角色唯一的会话时
  (不论你是怎么被启动的,包括被派出来的 subagent),这条不针对你。**
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
> **只记事实和裁决，不记推理过程。** 记忆层是让下一回合不必从零重新推导，
> 不是让两边想到一块去 —— 共享推理会让两份产出趋同，合起来少一道验收。
> 所以下面故意没有"分析"字段。
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
# `.pair/scratch/`(W23):验证用的副本与临时脚本放这里。被 git 忽略的文件不出现在 git status 里,
# 写权限边界、提交、verify-setup 的"未提交的代码改动"都看不见它们 —— 不需要为它另写判定。
# 操作系统写的文件(W31):有人用 Finder / 资源管理器看过项目目录,它们就会出现;不属于任何角色,
# 第十五轮 macOS 的 `.DS_Store` 因此挡住了第一次交接,而那时 GITIGNORE_LINES 里没有它。
# **名单只写在这一处**(W34),GITIGNORE_LINES 末行引用它;写权限边界认系统文件、handoff 不提交它们,都读这一处。
# 曾经是从 GITIGNORE_LINES 里按"不含 / 也不含 *"筛出来的 —— 按形状猜语义,今后加一个 `.env` 就会被说成"操作系统写的"。
OS_FILES = (".DS_Store", "Thumbs.db", "desktop.ini")
GITIGNORE_LINES = [".pair/.last-test.log", ".pair/.last-full-test.log",
                   ".pair/whoami", ".pair/turns/", BRIEF_REL,
                   "__pycache__/", "*.pyc", ".pair/scratch/",
                   *OS_FILES]


def scratch_hint(phase):
    """工作阶段的简报末尾那一句:验证用的副本放哪(W30)。

    W23 给了 `.pair/scratch/`,却只写在 `rules.md` 的一个小节里;四轮独立运行它一次都没被用上 ——
    会话每回合必读的是这份简报,而工具的系统提示在会话一启动就说"临时文件放你自己的 scratchpad"。
    路径**取自 `GITIGNORE_LINES` 里那一行**,不另写字面:提示替机制做预告,两者就得同源(W27 的决策)。
    评审阶段同一屏写着"本回合只读",所以要顺带说清它被 git 忽略、写在里面不算写。
    """
    scratch = next(l for l in GITIGNORE_LINES if l.startswith(".pair/scratch"))
    ro = ("它被 git 忽略,写在里面不算本回合的改动。"
          if phase in REVIEW_PHASES else "它被 git 忽略,不进提交、不算越界。")
    return ("  需要写临时副本或脚本做验证(故意改坏实现、另写参考实现)时,放 %s ——\n"
            "  %s能不写文件就不写:很多验证在一条命令里换掉函数就能跑完。"
            % (scratch, ro))


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
    print("       python3 %s verify-setup --drafter self|other" % PROG_HINT)
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


def _normalize(text):
    """NFKC 归一 + 折叠空白。

    小节名常常是整个函数签名(骨架的标题模板就是
    `函数名(参数: 类型) -> 返回类型`),而全角/半角冒号、多一个空格,
    在两份不同的人写的文档里几乎必然出现。不归一就等于抽签。
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


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


def setup_report_paths(root):
    """(读哪一份, 该让人写哪一份, 回落说明或 None)。

    **角色文件优先,缺失才回落到旧的单一路径。不读并集** —— 读并集的话,
    一个角色可以交一句废话、靠另一份把字数与小节名凑满。
    角色走既有的解析顺序(PAIR_ROLE → .pair/whoami → 分支),不是 --drafter:
    后者说的是"审查者有没有参与起草",和"你是哪个 agent"是两个轴。
    """
    me, _ = try_resolve_role(root)
    if me is None:
        return SETUP_REPORT_REL, SETUP_REPORT_REL, (
            "解析不出你的角色(PAIR_ROLE、%s、pair/<角色> 分支都没有),"
            "结论读的是两个角色共用的旧位置 %s。配好角色之后请改用 %s。"
            % (WHOAMI_REL, SETUP_REPORT_REL, SETUP_REPORT_ROLE_FMT % "<角色>"))
    mine = SETUP_REPORT_ROLE_FMT % me
    if (root / mine).exists():
        return mine, mine, None
    return SETUP_REPORT_REL, mine, (
        "%s 不存在,回落到旧的共享位置 %s。它是两个角色共用的,"
        "第三轮在这里整份覆盖过对方的结论 —— 建议改名为 %s(本命令不替你搬)。"
        % (mine, SETUP_REPORT_REL, mine))


def index_has_diff(root, paths):
    """`paths` 这批路径在索引里相对 HEAD 有没有差异。

    **只看这一批,与工作区其余部分无关。** 拿"工作区干净"当判据是错的:
    `src/` 下一份未跟踪的偷跑实现会让工作区永远不干净 → 照样去提交 →
    照样空提交 → 照样 exit 1,缺陷原样保留。
    """
    proc = subprocess.run(("git", "diff", "--cached", "--quiet", "--") + tuple(paths),
                          cwd=root, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    return proc.returncode != 0


def staged_paths(root, paths):
    """`paths` 里在索引中相对 HEAD **真有差异**的那些 —— `verify-setup` 提交的就是这一批。

    和 `index_has_diff` 判的是同一个集合:它非空,那个函数才会是真。

    **不能直接把 `paths` 全交给 `git commit --`。** 带路径的提交要求每个路径 git
    都认得(在索引或 HEAD 里)。`shared_paths` 下暂存为新增、随后又从工作区删掉的
    文件(porcelain `AD`),被前面那次 `git add` 拿出索引之后就谁都不认得了,
    提交报 pathspec 不匹配、整条命令 exit 1 —— 而状态位已经写进工作区。

    `-z` 切开:中文路径不带 `-z` 会被 `core.quotepath` 转义,转义后的名字
    交回给 git 当路径是对不上的。
    """
    out = git("diff", "--cached", "--name-only", "-z", "--", *paths, cwd=root)
    return [p for p in out.split("\0") if p]


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

    # --- 路径归属的可见性 --------------------------------------------------
    # 这两个缺口原本只在第 N 个回合突然发作:孤儿是"两个 agent 都写不了",
    # ignore_paths 是"任何角色任何阶段都能写"。两者都不是错误配置 ——
    # 前者要人类划归,后者本来就是副产物该有的待遇 —— 但都必须是人类
    # **看得见的决定**,不能藏在配置里。所以是 warn,不是 bad。
    orphans = [f for f in files if is_orphan(f, cfg)]
    if orphans:
        warn(render_path_listing(
            "%d 个孤儿:不属于任何角色,也不在共享/冻结/ignore_paths/记忆层里。\n"
            "      两个 agent 都写不了它们,而这件事在开工时没有任何地方说过 ——\n"
            "      前两轮三次卡顿全出自这里。请人类划归到某个角色或冻结:"
            % len(orphans), orphans))

    ignored = [f for f in files if matches_any(f, cfg["ignore_paths"])]
    if ignored:
        warn(render_path_listing(
            "%d 个文件不受边界保护:命中 ignore_paths,任何角色、任何阶段都能写。\n"
            "      这是它的用途(副产物就该这样),但哪些文件已经不受保护\n"
            "      必须是人类看得见的决定,不是藏在配置里的一行:"
            % len(ignored), ignored))

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

    # --- 收窄了门禁套件,就得说清楚放弃了什么 --------------------------------
    # 配了 full_test_cmd = 门禁套件被收窄过 = 红绿不变量的覆盖面被缩小了。
    # 那份说明是"缩小到哪里、放弃了什么"的唯一留痕,没有它,以后没人知道
    # 当年绿的到底是哪一半。
    if cfg.get("full_test_cmd") and not (root / BASELINE_REL).exists():
        warn("配了 full_test_cmd(门禁套件被收窄过),但没有 %s。\n"
             "      写两节:`## 放弃了哪些用例` / `## 为什么`。\n"
             "      这是门禁范围被缩小的唯一留痕。" % BASELINE_REL)

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

    # --- 契约审查结论读哪一份 ----------------------------------------------
    # 放在打印警告之前:回落警告要计进下面那个"有 N 条警告"。
    # 第一版放在摘要之后、直接 print,于是摘要写"有 3 条"而眼前是 4 条 ——
    # 一个会说错的计数,正是第五轮要修的那一类仪器。
    report_rel, target_rel, fallback_why = setup_report_paths(root)
    report = root / report_rel
    text = report.read_text(encoding="utf-8").strip() if report.exists() else ""
    # 回落时要说出来 —— 判据是"这条警告出现了"。只在回落的那份真存在时才说:
    # 两份都没有时走下面"还差最后一步"的指引,在那之前再报一条回落是噪音。
    if fallback_why and report.exists():
        warn(fallback_why)

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
    if len(text) < MIN_SETUP_REPORT_CHARS:
        print()
        print("=" * 60)
        print(" 还差最后一步 —— 只有你能做的那一步。")
        print("=" * 60)
        print("""
 通读 %s,把你认为**有歧义的条款**写进
 %s。%s

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

 结论里**逐节点名** —— 每个被工作项引用的小节都要在结论里出现过,
 泛泛一句"看过了没问题"正是这道门要挡的东西。

 写完后带上起草人声明重新执行(二选一,声明会写进提交正文):

   python3 %s verify-setup --drafter other   # 我没参与契约起草
   python3 %s verify-setup --drafter self    # 我参与了,结论证明力打折

 在交出这份结论之前,校验不会通过,也不能认领工作项。
""" % (cfg["contract_file"], target_rel,
       "" if target_rel == SETUP_REPORT_REL else
       "\n (结论按角色分开存放。旧的共享位置 %s 仍然认,但会打警告 ——\n"
       "  它是两个角色共用的,第三轮在那里整份覆盖过对方的结论。)" % SETUP_REPORT_REL,
       PROG_HINT, PROG_HINT))
        die("尚未交出契约审查结论(%s 缺失或过短,至少 %d 字)。\n"
            "这是本步骤存在的主要理由,不能跳过。"
            % (report_rel if report.exists() else target_rel,
               MIN_SETUP_REPORT_CHARS))

    # --- 结论必须逐节点名 ---------------------------------------------------
    # 长度是地板,不是门。一段泛泛而谈轻松过 120 字,而这道门守着协议自称
    # **唯一会致命**的失败模式。要点名十个小节,就得逐个读过去。
    #
    # 能力边界要说清楚:它只保证**覆盖面**,不保证消歧。
    # 最优敷衍解仍然是「以下小节均无歧义:A、B、C」。
    # architecture.md 里「契约不含糊 | ❌ 只有人类」那一行因此原样留着。
    #
    # 结论侧先剥掉围栏 —— 否则把整份 CONTRACT.md 粘进一个 ``` 里,
    # 所有小节名瞬间"全被点名",而那正是这条检查要消灭的东西的加强版。
    naked = _normalize(_blank_fenced_blocks(text))
    unnamed = []
    for item_id, typ, _, block in pending:
        refs = CONTRACT_REF_RE.findall(block)
        if not refs:
            continue
        anchor_name = refs[0].strip().strip("`")
        if anchor_name in dupes or anchor_name not in sections:
            continue            # 上面已经单独报过,这里再报是纯噪音
        if _normalize(anchor_name) not in naked:
            unnamed.append((item_id, anchor_name))
    if unnamed:
        die("契约审查结论里没有点到这些小节:\n%s\n\n"
            "结论要逐节过 —— 泛泛一句「看过了没问题」正是这道门要挡的东西。\n"
            "每一节都问:返回值精确到能写断言吗?错误条件穷举了吗?\n"
            "边界(空、超长、null、并发)写明了吗?有没有两种合理解读?\n\n"
            "(注意:把契约整段粘进 ``` 围栏不算点名 —— 围栏内容会被剥掉。)"
            % "\n".join("  工作项 %s → 「%s」" % (i, a) for i, a in unnamed))

    # --- 起草人自审要说出来 --------------------------------------------------
    # 上一轮真实运行里那份结论开头自己写着"审查者:起草人本人,证明力打折"。
    # 那是用真实运行换回来的观察 —— 把它从自觉变成必答一项。
    #
    # **用参数,不在结论里搜关键词。** 这里适用 ADR-014 的同一条理由,而且
    # 关键词版实测两头落空:「本结论作者未介入契约的编写」这种正确说法被拒,
    # 正文里随便一个「参与」(哪怕说的是参与实现)却能放行。参数是结构。
    # 声明进提交正文,读结论的人在 inbox 里必然看到 —— 和 --allow-deletion
    # / --no-decision 同一手法:不是放行,是强制留痕。
    if args.drafter is None:
        die("还要声明你有没有参与过这份契约的起草,二选一:\n\n"
            "  python3 %s verify-setup --drafter other   # 我没参与起草\n"
            "  python3 %s verify-setup --drafter self    # 我参与了,结论证明力打折\n\n"
            "为什么要问:起草人审自己写的东西看不见自己的盲区。\n"
            "这道门守的是唯一会致命的失败模式,读结论的人有权知道谁写的。\n"
            "声明会写进提交正文,不用你在结论里另写一句。"
            % (PROG_HINT, PROG_HINT))

    # 本命令对外的承诺是"只读校验"。此处只提交它自己产生的东西:
    # 状态位与那份契约审查结论。曾经这里是 `git add -A` —— 那会把工作区里
    # 任何东西一并提交进基线,包括结对开始前就被写好的实现,而那恰好会让
    # spec 阶段的 RED 要求失效(测试一上来就是绿的)。
    # 这份结论也不能改写(W18)。**拒绝必须在写状态之前** —— 放在 save_state 之后
    # 就是 W12、W15 两次治过的"状态对、退出码错",而且这回状态位还留在工作区,
    # 下一次交接会判它篡改。
    rewrite = review_rewrite_violation(root, cfg, report_rel)
    if rewrite:
        die(rewrite + "。\n\n"
            "%s 是上一次校验留下的凭据,契约变了就往它**末尾追加**一段补记,\n"
            "不要覆盖(W13 起两个角色都是这么做的)。\n\n"
            "如果这份改动不是你做的,不要撤销 —— 告诉人类。" % report_rel)
    state["setup_verified"] = True
    # 按角色记下这次校验的是哪一份契约(工作区内容)。先复制再写:load_state
    # 是浅拷贝,直接往默认值里的 dict 写会改到 DEFAULT_STATE 本身。
    # 解析不出角色时(W12 的回落路径)记不了 —— 那个角色认领时会被要求重跑。
    who, _ = try_resolve_role(root)
    if who:
        rec = dict(state.get("setup_verified_contract") or {})
        rec[who] = worktree_sha(root, cfg["contract_file"])
        state["setup_verified_contract"] = rec
    save_state(root, state)
    to_add = [STATE_REL, report_rel] + [
        p for _, p in changed_entries(root) if matches_any(p, cfg["shared_paths"])]
    git("add", "--", *sorted(set(to_add)), cwd=root)
    drafter_line = ("起草人自审: 是 —— 审查者参与过契约起草,本结论证明力打折"
                    if args.drafter == "self"
                    else "起草人自审: 否 —— 审查者未参与契约起草")
    # 三类都没变时 git 会拒绝空提交,整条命令 exit 1 —— 状态位上面已经存好,
    # 状态是对的、退出码是错的,而调用方只看退出码。所以先问索引。
    # 只改"索引里没有差异"这一种情形,有差异时一个字不变。
    if index_has_diff(root, sorted(set(to_add))):
        # 提交也只带这一批:不带路径的 commit 提交的是整个索引,有人事先
        # `git add` 的实现会跟着结论进开工基线。索引里的其他东西原样留着。
        staged = staged_paths(root, sorted(set(to_add)))
        git("commit", "-q", "-m", "chore(pair): 通过开工前校验,含契约审查结论",
            "-m", drafter_line, "--", *staged, cwd=root)
    else:
        print()
        print("  没有需要提交的改动 —— 状态位与结论都和上次提交时一样,"
              "本次不产生提交。")

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

    # W27:结尾那句要看另一方。认领要**两个**角色的校验都作数(W19),只看自己这一份
    # 就会在一半的情况下说错 —— 第十一轮 tester 看到"现在可以认领",紧接着 claim 被拒。
    # 判定与 claim 用同一个 stale_verification,不另算(与 W25 同一个理由)。
    # 解析不出角色时记不了自己这一份,也就说不清谁是"另一方",照旧。
    waiting = None
    if cfg["require_setup_verification"] and who:
        other = [r for r in ROLES if r != who][0]
        if stale_verification(root, cfg, state, other):
            waiting = other

    print()
    print("  契约审查结论已收到(%s,%d 字)。" % (report_rel, len(text)))
    print("  %s" % drafter_line)
    if waiting:
        print("  开工前校验全部通过 —— 这是 %s 这一份。%s 的校验还不作数,"
              "认领要等它自己重跑:" % (who, waiting))
        print("    PAIR_ROLE=%s python3 %s verify-setup --drafter self|other"
              % (waiting, PROG_HINT))
    else:
        print("  开工前校验全部通过,现在可以认领工作项了。")
    print()
    return 0


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pair.py", description="双 agent 结对编程协议执行层")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化本仓库(结对开始之前跑)")
    p_vs = sub.add_parser("verify-setup", help="开工前只读校验,由结对的另一方跑")
    p_vs.add_argument("--drafter", choices=("self", "other"), default=None,
                      help="你有没有参与这份契约的起草:self=参与过(结论证明力打折)"
                           " / other=没参与。声明会写进提交正文")
    sub.add_parser("status", help="我是谁 / 轮到谁 / 红绿 / 该干什么")

    p_claim = sub.add_parser("claim", help="认领 PLAN 里的一个工作项")
    p_claim.add_argument("item_id")

    p_ho = sub.add_parser("handoff", help="校验 → 提交 → 翻转回合")
    p_ho.add_argument("words", nargs="*")
    p_ho.add_argument("--allow-deletion", metavar="理由", default=None,
                      help="显式声明本次删除了测试,并给出理由")
    p_ho.add_argument("--no-decision", metavar="理由", default=None,
                      help="显式声明本工作项的笔记没有值得沉淀成决策的内容")
    p_ho.add_argument("--doc-reason", metavar="理由", default=None,
                      help="本回合改了规范性文档时必填:为什么改")
    p_ho.add_argument("--basis", metavar="依据", default=None,
                      help="改写路线图(有删除行)时必填:指向一份真实产物的路径")
    p_ho.add_argument("--contract-change", metavar="依据", default=None,
                      help="改 PLAN/CONTRACT 时必填:指向一份真实产物的路径")
    p_ho.add_argument("--checked", metavar="内容", default=None,
                      help="approve 必填:你具体检查了什么")
    p_ho.add_argument("--uncovered", metavar="内容", default=None,
                      help="approve 必填:你知道还没被覆盖到的是什么(没有就写\"无\")")

    sub.add_parser("whose-turn", help="一行输出:接下来该谁,或为什么该停")
    p_rep = sub.add_parser("report", help="协议健康度:打回率等指标,只读")
    p_rep.add_argument("--since", metavar="<rev>",
                       help="只统计这个提交之后的交接(<rev>..HEAD)")
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
        "whose-turn": cmd_whose_turn,
    }[args.cmd](root, cfg, args)


if __name__ == "__main__":
    sys.exit(main())
