#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双 AI agent 结对编程协议 —— 执行层。

单文件,仅依赖 Python 3 标准库。用法:

    python3 pair.py init [目标目录]     # 初始化(结对开始之前跑)
    python3 pair.py verify-setup        # 另一方开工前的只读校验
    python3 pair.py status
    python3 pair.py claim W1
    python3 pair.py handoff "说明"
    python3 pair.py handoff approve "理由"
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

STATE_REL = ".pair/state.json"
CONFIG_REL = ".pair/config.json"
TESTLOG_REL = ".pair/.last-test.log"
WHOAMI_REL = ".pair/whoami"
SETUP_REPORT_REL = "docs/reviews/setup-verification.md"
# 契约审查结论的最小长度。门槛不高,但足以挡住空文件和一句话敷衍。
MIN_SETUP_REPORT_CHARS = 120

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
    cfg.setdefault("plan_file", "docs/PLAN.md")
    cfg.setdefault("contract_file", "docs/CONTRACT.md")
    cfg.setdefault("sync", False)
    cfg.setdefault("require_setup_verification", True)
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
    """按角色 + 阶段计算可写路径。评审阶段只读:仅允许写评审记录。"""
    shared = list(cfg["shared_paths"])
    if phase in REVIEW_PHASES or phase == "idle":
        return shared
    return list(cfg["roles"][PHASE_OWNER[phase]]) + shared


def run_tests(root, cfg):
    cmd = os.environ.get("PAIR_TEST_CMD") or cfg.get("test_cmd")
    if not cmd:
        die("未配置 test_cmd。请编辑 %s 填入本项目的测试命令。" % CONFIG_REL)
    log = root / TESTLOG_REL
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
%(redgreen)s
  完成后: python3 %(prog)s handoff "一句话说明这个用例在验证什么\"""",

    "impl": """  写实现。

  硬约束:
    - 只能写:%(paths)s
    - 禁止修改或删除任何测试。认为测试写错了 -> 写异议到 docs/reviews/,
      用 handoff changes "理由" 打回,由测试方修
    - 禁止针对测试输入硬编码返回值来蒙混过关
%(redgreen)s
  完成后: python3 %(prog)s handoff "一句话说明你怎么实现的\"""",

    "review-impl": """  审查对方的实现。跑 inbox 看 diff。

  重点查:
    - 有没有针对测试输入特判/硬编码
    - 有没有偏离 %(contract)s
    - 有没有明显未覆盖的边界情况

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  必须给出裁决,禁止只说"看起来不错":
    通过 -> python3 %(prog)s handoff approve "理由"
    打回 -> python3 %(prog)s handoff changes "具体到行的问题清单\"""",

    "review-test": """  审查对方的测试。跑 inbox 看 diff。

  重点查:
    - 有没有断言私有实现细节,导致测试变成变更探测器
    - 覆盖是否够(边界值、错误路径)
    - %(cover_hint)s

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  必须给出裁决,禁止只说"看起来不错":
    通过 -> python3 %(prog)s handoff approve "理由"
    打回 -> python3 %(prog)s handoff changes "具体问题清单\"""",
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
    return {
        "plan": cfg["plan_file"],
        "contract": cfg["contract_file"],
        "paths": " ".join(writable_paths(cfg, phase)),
        "prog": PROG_HINT,
        "redgreen": rg,
        "cover_hint": ("这条测试真的能发现回归吗(cover 类型的核心问题)"
                       if state["item_type"] == "cover"
                       else "用例是否真的对应 PLAN 里的工作项"),
    }


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
    return 0


# --------------------------------------------------------------------------
# claim
# --------------------------------------------------------------------------

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

    if state_is_tampered(root):
        restore_state(root)
        die("你修改了 %s。协议状态由脚本维护,手工修改是违规的。\n"
            "已还原。请重新执行 status 确认真实状态后再认领。" % STATE_REL)

    state["item"] = item_id
    state["item_type"] = item_type
    state["changes_count"] = 0          # 打回计数绑定到工作项
    state["phase"] = flow_of(item_type)["start"]
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
                "  python3 %s handoff approve \"理由\"\n"
                "  python3 %s handoff changes \"问题清单\"" % (PROG_HINT, PROG_HINT))
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

    entries = changed_entries(root)

    # --- 写权限边界校验 ---------------------------------------------------
    allowed = writable_paths(cfg, phase)
    violations = []
    for xy, path in entries:
        if path == TESTLOG_REL or matches_any(path, cfg["ignore_paths"]):
            continue
        hit_frozen = next((f for f in cfg["frozen_paths"]
                           if path_matches(path, f)), None)
        if hit_frozen is not None:
            violations.append((path, "冻结路径 %s 之下,agent 不得修改" % hit_frozen))
            continue
        if not matches_any(path, allowed):
            scope = ("本回合是只读评审" if phase in REVIEW_PHASES
                     else "%s 在 %s 阶段" % (me, phase))
            violations.append((path, "越界:%s 只能写 %s" % (scope, " ".join(allowed))))

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

    # --- 异议必须落到纸面 -------------------------------------------------
    if is_dispute:
        written = [p for xy, p in entries
                   if "D" not in xy and matches_any(p, cfg["shared_paths"])]
        if not written:
            die("拒绝交接 —— 你提出了异议,但没有把它写下来。\n\n"
                "对方看不到你的对话,唯一的通信渠道是 %s 里的文件。\n"
                "写清楚:哪条测试、和契约的哪一条矛盾、你认为应该改成什么。\n"
                "然后重新执行本命令。" % " ".join(cfg["shared_paths"]))

    # --- 红绿不变量(按工作项类型) ---------------------------------------
    # 异议路径豁免:dev 正是因为测试写错、弄不绿才打回的,拿红绿卡他等于
    # 逼他照着错误的断言写实现。
    green = run_tests(root, cfg)
    expect = None if is_dispute else flow["expect"].get(phase)
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
    target = flow["transitions"][(phase, verdict)]
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
        next_phase = "idle"
    else:
        next_phase = target
        state["changes_count"] = changes_n
    state["phase"] = next_phase
    state["last_actor"] = me
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

    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "%s: %s" % (prefix, message), "-m", body, cwd=root)

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

    if plan_all_done(root, cfg):
        print(">>> %s 里的工作项已全部完成。项目结束。<<<" % cfg["plan_file"])
        print("请向人类报告完成,不要继续轮转。")
    else:
        print("现在请告诉人类:轮到 %s 了。然后停止工作。" % PHASE_OWNER[next_phase])
    print()
    return 0


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
    print("=== 评审记录 =====================================")
    found = []
    for shared in cfg["shared_paths"]:
        d = root / shared
        if d.is_dir():
            found += sorted(str(p.relative_to(root)) for p in d.rglob("*")
                            if p.is_file() and not p.name.startswith("."))
    print("\n".join(found) if found else "(空)")
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

GITIGNORE_LINES = [".pair/.last-test.log", ".pair/whoami"]


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
            "impl 阶段\"测试必须 GREEN\"这条不变量依赖基线全绿,否则协议会卡死,\n"
            "或者那条不变量形同虚设。请先把现有测试修绿,再重跑 init。\n\n"
            "失败详情见 %s" % TESTLOG_REL)
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
        "shared_paths": ["docs/reviews"],
        "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md",
                         ".agents", ".claude", ".pair"],
        "ignore_paths": [],
        "plan_file": "docs/PLAN.md",
        "contract_file": "docs/CONTRACT.md",
        "sync": False,
        "require_setup_verification": True,
    }, ensure_ascii=False, indent=2) + "\n")
    put(STATE_REL, json.dumps(DEFAULT_STATE, indent=2) + "\n")
    put("docs/PLAN.md", PLAN_SKELETON)
    put("docs/CONTRACT.md", CONTRACT_SKELETON)
    put("docs/reviews/.gitkeep", "")
    for rel, content in ENTRY_FILES.items():
        put(rel, content)

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

CONTRACT_REF_RE = re.compile(r"对应契约[::]\s*.*?[→>]\s*(.+?)\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)


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
        headings = {h.strip().strip("`") for h in HEADING_RE.findall(text)}
        for item_id, _, _, block in pending:
            refs = CONTRACT_REF_RE.findall(block)
            if not refs:
                bad("工作项 '%s' 没有指向契约。在它下面加一行:\n"
                    "      - 对应契约:`%s` → <小节名>"
                    % (item_id, cfg["contract_file"]))
                continue
            anchor = refs[0].strip().strip("`")
            if anchor not in headings:
                bad("工作项 '%s' 指向的契约小节 '%s' 在 %s 里不存在。\n"
                    "      现有小节:%s"
                    % (item_id, anchor, cfg["contract_file"],
                       "、".join(sorted(headings)) or "(无)"))

    # --- 入口文件与技能 ---------------------------------------------------
    if not (root / ".agents/skills/pair-protocol/SKILL.md").exists():
        bad("找不到 .agents/skills/pair-protocol/SKILL.md")
    missing = [f for f in ("AGENTS.md", "CLAUDE.md") if not (root / f).exists()]
    if missing:
        warn("缺少入口文件:%s —— 对应工具的 agent 不会知道这是结对项目"
             % "、".join(missing))

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

    state["setup_verified"] = True
    save_state(root, state)
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "chore(pair): 通过开工前校验,含契约审查结论", cwd=root)

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
    }[args.cmd](root, cfg, args)


if __name__ == "__main__":
    sys.exit(main())
