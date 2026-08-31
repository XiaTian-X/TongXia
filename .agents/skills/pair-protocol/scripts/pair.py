#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双 AI agent 结对编程协议 —— 执行层。

单文件,仅依赖 Python 3 标准库。用法:

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

# 阶段 -> 负责角色。回合严格按此顺序轮转。
PHASE_OWNER = {
    "spec": "tester",
    "impl": "dev",
    "review-impl": "tester",
    "review-test": "dev",
}
REVIEW_PHASES = ("review-impl", "review-test")

# (当前阶段, 裁决) -> (下一阶段, 附注)
TRANSITIONS = {
    ("spec", None): ("impl", None),
    ("impl", None): ("review-impl", None),
    ("review-impl", "approve"): ("review-test", None),
    ("review-impl", "changes"): ("impl", None),
    ("review-test", "approve"): ("spec", "item-done"),
    ("review-test", "changes"): ("spec", None),
}

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

DEFAULT_STATE = {
    "round": 0,
    "phase": "spec",
    "item": None,
    "last_actor": None,
    "changes_count": 0,
    "completed_items": [],
}

# `- [ ] **W1** — 标题`
ITEM_RE = re.compile(r"^(?P<pre>\s*-\s*\[)(?P<mark>[ xX])(?P<mid>\]\s*\*\*)(?P<id>[^*]+)(?P<post>\*\*.*)$")


# --------------------------------------------------------------------------
# 基础设施
# --------------------------------------------------------------------------

def die(msg, code=1):
    sys.stderr.write("\n[结对协议] %s\n\n" % msg)
    sys.exit(code)


def git(*args, cwd=None, check=True):
    """跑 git,返回 stdout(str)。check=False 时失败返回 None。"""
    proc = subprocess.run(
        ("git",) + args,
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        if check:
            die("git %s 失败:\n%s" % (" ".join(args), proc.stderr.decode("utf-8", "replace")))
        return None
    return proc.stdout.decode("utf-8", "replace")


def repo_root():
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        die("这里不是 git 仓库。结对协议依赖 git 做交接。")
    return Path(proc.stdout.decode("utf-8").strip())


def load_config(root):
    p = root / CONFIG_REL
    if not p.exists():
        die("找不到 %s。本仓库尚未初始化结对协议。" % CONFIG_REL)
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die("%s 不是合法 JSON:%s" % (CONFIG_REL, e))
    cfg.setdefault("roles", {"tester": ["tests"], "dev": ["src"]})
    cfg.setdefault("shared_paths", ["docs/reviews"])
    cfg.setdefault("frozen_paths", [])
    cfg.setdefault("plan_file", "docs/PLAN.md")
    cfg.setdefault("sync", False)
    # 状态文件永远冻结,不允许配置放开
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
    return merged


def save_state(root, state):
    p = root / STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# 角色解析 —— 多来源降级,兼容 CLI / GUI / 云端 harness
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
    """返回 (role, source)。"""
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
    """返回 [(xy, path)]。用 -z 输出,彻底绕开路径转义问题(中文/空格文件名)。"""
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=root)
    parts = out.split("\0")
    entries = []
    i = 0
    while i < len(parts):
        rec = parts[i]
        if not rec:
            i += 1
            continue
        xy, path = rec[:2], rec[3:]
        entries.append((xy, path))
        # 重命名/复制会多跟一个来源路径字段
        if "R" in xy or "C" in xy:
            i += 2
        else:
            i += 1
    return entries


def under(path, prefix):
    """path 是否等于 prefix 或位于 prefix 之下。纯路径比较,不碰文件系统。"""
    p = PurePosixPath(path)
    q = PurePosixPath(prefix)
    return p == q or q in p.parents


def writable_paths(cfg, phase):
    """按角色 + 阶段计算可写路径。评审阶段只读:仅允许写评审记录。"""
    shared = list(cfg["shared_paths"])
    if phase in REVIEW_PHASES:
        return shared
    return list(cfg["roles"][PHASE_OWNER[phase]]) + shared


def run_tests(root, cfg):
    cmd = os.environ.get("PAIR_TEST_CMD") or cfg.get("test_cmd")
    if not cmd:
        die("未配置 test_cmd。请编辑 %s 填入本项目的测试命令。" % CONFIG_REL)
    log = root / TESTLOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as f:
        rc = subprocess.call(cmd, shell=True, cwd=str(root), stdout=f, stderr=subprocess.STDOUT)
    return rc == 0


def state_is_tampered(root):
    """state.json 在工作区里被改动过 = agent 动了它。脚本只在提交前一刻写它。"""
    return any(p == STATE_REL for _, p in changed_entries(root))


def restore_state(root):
    if git("checkout", "HEAD", "--", STATE_REL, cwd=root, check=False) is None:
        # 尚未被提交过(首次初始化),没有可还原的版本
        return False
    return True


# --------------------------------------------------------------------------
# PLAN.md
# --------------------------------------------------------------------------

def parse_plan(root, cfg):
    """返回 [(id, done, lineno)]。PLAN 不存在时返回 []。"""
    p = root / cfg["plan_file"]
    if not p.exists():
        return []
    items = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        m = ITEM_RE.match(line)
        if m:
            items.append((m.group("id").strip(), m.group("mark") in "xX", n))
    return items


def tick_plan_item(root, cfg, item_id):
    """把 PLAN.md 里对应工作项勾成 [x]。脚本可以改冻结文件,agent 不可以。"""
    p = root / cfg["plan_file"]
    if not p.exists():
        return False
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    for n, line in enumerate(lines):
        m = ITEM_RE.match(line.rstrip("\n"))
        if m and m.group("id").strip() == item_id:
            nl = "\n" if line.endswith("\n") else ""
            lines[n] = (m.group("pre") + "x" + m.group("mid")
                        + m.group("id") + m.group("post") + nl)
            p.write_text("".join(lines), encoding="utf-8")
            return True
    return False


def plan_all_done(root, cfg):
    items = parse_plan(root, cfg)
    return bool(items) and all(done for _, done, _ in items)


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

PHASE_BRIEF = {
    "spec": """  从 %(plan)s 认领下一个工作项(python3 %(prog)s claim <ID>),
  按 docs/CONTRACT.md 的接口签名写出【会失败】的测试。
  只写一个或一组紧密相关的用例,不要一次砸一堆。

  硬约束:
    - 只能写:%(paths)s
    - 只断言 CONTRACT 里的可观测行为,禁止断言私有方法名/调用次数
    - 交接前测试必须是 RED。绿着交接会被拒绝。
    - 不许删除已有测试。确需删除要显式带 --allow-deletion "理由"。

  完成后: python3 %(prog)s handoff "一句话说明这个用例在验证什么\"""",

    "impl": """  读新增的失败用例,写出让它变绿的最小实现。

  硬约束:
    - 只能写:%(paths)s
    - 禁止修改或删除任何测试。认为测试写错了 -> 写异议到 docs/reviews/,
      用 handoff changes "理由" 打回,由测试方修
    - 禁止针对测试输入硬编码返回值来蒙混过关
    - 交接前测试必须 GREEN

  完成后: python3 %(prog)s handoff "一句话说明你怎么实现的\"""",

    "review-impl": """  审查对方的实现。跑 inbox 看 diff。

  重点查:
    - 有没有针对测试输入特判/硬编码
    - 有没有偏离 docs/CONTRACT.md
    - 有没有明显未覆盖的边界情况(记下来,下个 spec 回合补测试)

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  必须给出裁决,禁止只说"看起来不错":
    通过 -> python3 %(prog)s handoff approve "理由"
    打回 -> python3 %(prog)s handoff changes "具体到行的问题清单\"""",

    "review-test": """  审查对方的测试。跑 inbox 看 diff。

  重点查:
    - 有没有断言私有实现细节,导致测试变成变更探测器
    - 覆盖是否够(边界值、错误路径)
    - 用例是否真的对应 PLAN 里的工作项

  【本回合只读】只能写:%(paths)s
  夹带任何代码改动都会被拒绝。

  必须给出裁决,禁止只说"看起来不错":
    通过 -> python3 %(prog)s handoff approve "理由"
    打回 -> python3 %(prog)s handoff changes "具体问题清单\"""",
}


def cmd_status(root, cfg, args):
    if cfg.get("sync"):
        git("pull", "--rebase", cwd=root, check=False)

    me, source = resolve_role(root)
    state = load_state(root)
    phase = state["phase"]
    owner = PHASE_OWNER[phase]

    tampered = state_is_tampered(root)
    green = run_tests(root, cfg)

    role_hint = "写测试,不写实现" if me == "tester" else "写实现,不写测试"
    print("=" * 52)
    print(" 你的角色 : %s  (%s)" % (me, role_hint))
    print(" 角色来源 : %s" % source)
    print(" 当前工作项: %s" % (state["item"] or "（无,等待认领）"))
    print(" 当前阶段 : %s   → 归属: %s" % (phase, owner))
    print(" 测试状态 : %s   (详见 %s)" % ("GREEN" if green else "RED", TESTLOG_REL))
    print(" 可写路径 : %s" % " ".join(writable_paths(cfg, phase)))
    print(" 已完成项 : %d" % len(state["completed_items"]))
    print("=" * 52)

    if tampered:
        print()
        print(">>> 警告:%s 被修改过。<<<" % STATE_REL)
        print("协议状态文件由脚本维护,任何人手工修改都是违规的。")
        print("下次 handoff 会拒绝交接并还原它。")

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
    print(PHASE_BRIEF[phase] % {
        "plan": cfg["plan_file"],
        "paths": " ".join(writable_paths(cfg, phase)),
        "prog": PROG_HINT,
    })
    print()
    return 0


# --------------------------------------------------------------------------
# claim
# --------------------------------------------------------------------------

def cmd_claim(root, cfg, args):
    me, _ = resolve_role(root)
    state = load_state(root)

    if state["phase"] != "spec":
        die("只能在 spec 阶段认领工作项,当前阶段是 %s。" % state["phase"])
    if me != "tester":
        die("认领工作项是 tester 的职责,你是 %s。" % me)

    items = parse_plan(root, cfg)
    if not items:
        die("%s 里没有找到任何工作项。\n"
            "工作项格式必须是:  - [ ] **W1** — 标题" % cfg["plan_file"])

    ids = [i for i, _, _ in items]
    if args.item_id not in ids:
        die("%s 里没有工作项 '%s'。\n现有工作项:%s"
            % (cfg["plan_file"], args.item_id, ", ".join(ids) or "(无)"))
    for i, done, _ in items:
        if i == args.item_id and done:
            die("工作项 '%s' 已经完成了。请认领一个未完成的。" % args.item_id)

    if state["item"] and state["item"] != args.item_id:
        die("当前已认领工作项 '%s' 且尚未完成,不能中途改领 '%s'。"
            % (state["item"], args.item_id))

    if state_is_tampered(root):
        restore_state(root)
        die("你修改了 %s。协议状态由脚本维护,手工修改是违规的。\n"
            "已还原。请重新执行 status 确认真实状态后再认领。" % STATE_REL)

    state["item"] = args.item_id
    state["changes_count"] = 0  # 打回计数绑定到工作项
    save_state(root, state)

    # 认领是一个协议事件,立即提交:既留痕,也让状态文件回到"干净"状态,
    # 否则下一次 handoff 的篡改检测会误伤它。
    git("add", "--", STATE_REL, cwd=root)
    git("commit", "-q", "-m", "chore(pair): 认领工作项 %s" % args.item_id, cwd=root)

    print()
    print("[结对协议] 已认领工作项:%s" % args.item_id)
    print("现在按 docs/CONTRACT.md 写出会失败的测试。")
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

    if me != owner:
        die("现在是 %s 的 %s 回合,不是你(%s)的。不要提交。" % (owner, phase, me))

    if plan_all_done(root, cfg):
        die("%s 里的工作项已全部完成,协议已停止轮转。\n"
            "请向人类报告项目完成。" % cfg["plan_file"])

    # --- 状态文件篡改检查(最优先,先于一切) -----------------------------
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
        if len(args.words) < 1 or args.words[0] not in ("approve", "changes"):
            die("评审阶段必须给出裁决:\n"
                "  python3 %s handoff approve \"理由\"\n"
                "  python3 %s handoff changes \"问题清单\"" % (PROG_HINT, PROG_HINT))
        verdict = args.words[0]
        message = " ".join(args.words[1:]).strip()
        if not message:
            die("裁决必须附理由。禁止空手通过。")
    else:
        message = " ".join(args.words).strip()
        if not message:
            die("请附一句话说明:python3 %s handoff \"你这回合做了什么\"" % PROG_HINT)

    # --- spec 阶段必须已认领工作项 ---------------------------------------
    if phase == "spec" and not item:
        die("还没有认领工作项。先跑:\n"
            "  python3 %s claim <ID>\n"
            "工作项列在 %s 里。" % (PROG_HINT, cfg["plan_file"]))

    entries = changed_entries(root)

    # --- 写权限边界校验 ---------------------------------------------------
    allowed = writable_paths(cfg, phase)
    frozen = cfg["frozen_paths"]
    violations = []
    for xy, path in entries:
        if path == TESTLOG_REL:
            continue
        hit_frozen = next((f for f in frozen if under(path, f)), None)
        if hit_frozen is not None:
            violations.append((path, "冻结路径 %s 之下,agent 不得修改" % hit_frozen))
            continue
        if not any(under(path, a) for a in allowed):
            scope = "本回合是只读评审" if phase in REVIEW_PHASES else "%s 在 %s 阶段" % (me, phase)
            violations.append((path, "越界:%s 只能写 %s" % (scope, " ".join(allowed))))

    if violations:
        lines = "".join("\n  %s\n      %s" % (p, why) for p, why in violations)
        die("拒绝交接 —— 以下改动越界:%s\n\n"
            "请撤销这些改动后重试。如果你认为规则本身有问题,"
            "写进 docs/reviews/ 并告诉人类。" % lines)

    # --- 测试删除防护 -----------------------------------------------------
    test_paths = cfg["roles"]["tester"]
    deleted = [p for xy, p in entries
               if "D" in xy and any(under(p, t) for t in test_paths)]
    if deleted and not args.allow_deletion:
        die("拒绝交接 —— 你删除了已有测试:\n  %s\n\n"
            "测试是规格,删除它等于悄悄缩小验收范围。\n"
            "确有正当理由(比如该用例已被更好的用例取代)就显式声明:\n"
            "  python3 %s handoff \"说明\" --allow-deletion \"删除理由\"\n"
            "理由会写进提交记录,对方在评审时必然看到。"
            % ("\n  ".join(deleted), PROG_HINT))

    # --- 红绿不变量 -------------------------------------------------------
    green = run_tests(root, cfg)
    if phase == "spec" and green:
        die("spec 阶段结束时测试必须是 RED,现在是 GREEN。\n"
            "你要么没写新用例,要么写了个本来就能通过的用例。\n"
            "失败的测试才是有效的规格。")
    if phase == "impl" and not green:
        die("impl 阶段结束时测试必须是 GREEN,现在是 RED。\n"
            "看 %s。还没弄绿就不要交接。" % TESTLOG_REL)
    if phase in REVIEW_PHASES and not green:
        die("评审阶段测试不该是 RED。有人破坏了主干,先修好。")

    # --- 死锁保护 ---------------------------------------------------------
    changes_n = state["changes_count"]
    if verdict == "changes":
        changes_n += 1
        if changes_n >= DEADLOCK_LIMIT:
            state["changes_count"] = changes_n
            save_state(root, state)
            git("add", "--", STATE_REL, cwd=root, check=False)
            git("commit", "-q", "-m",
                "chore(pair): 工作项 %s 打回 %d 次,触发死锁闸" % (item or "?", changes_n),
                cwd=root, check=False)
            die("同一工作项已经被打回 %d 次。协议要求此时停止自动轮转。\n"
                "请把双方分歧写清楚,交给人类裁决。不要继续来回。" % changes_n)

    # --- 翻转回合 ---------------------------------------------------------
    next_phase, note = TRANSITIONS[(phase, verdict)]
    finished_item = None
    if note == "item-done":
        finished_item = item
        state["round"] += 1
        if item:
            state["completed_items"].append(item)
            tick_plan_item(root, cfg, item)
        state["item"] = None
        state["changes_count"] = 0
    else:
        state["changes_count"] = changes_n
    state["phase"] = next_phase
    state["last_actor"] = me
    save_state(root, state)

    # --- 提交 -------------------------------------------------------------
    prefix = COMMIT_PREFIX[phase] + ("/" + verdict if verdict else "")
    body = "role=%s phase=%s -> %s item=%s" % (me, phase, next_phase, item or "none")
    if args.allow_deletion:
        body += "\n删除测试(已声明): %s\n  %s" % (args.allow_deletion, "\n  ".join(deleted))

    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "%s: %s" % (prefix, message), "-m", body, cwd=root)

    if cfg.get("sync"):
        git("push", cwd=root, check=False)

    all_done = plan_all_done(root, cfg)
    print()
    print("[结对协议] 已交接。")
    print("  提交: %s" % git("log", "-1", "--oneline", cwd=root).strip())
    print("  下一阶段: %s  → 归属: %s" % (next_phase, PHASE_OWNER[next_phase]))
    if finished_item:
        print("  工作项「%s」已完成并双向通过。" % finished_item)
    print()
    if all_done:
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

PROG_HINT = ".agents/skills/pair-protocol/scripts/pair.py"


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pair.py", description="双 agent 结对编程协议执行层")
    sub = ap.add_subparsers(dest="cmd", required=True)

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
    cfg = load_config(root)
    return {
        "status": cmd_status,
        "claim": cmd_claim,
        "handoff": cmd_handoff,
        "inbox": cmd_inbox,
    }[args.cmd](root, cfg, args)


if __name__ == "__main__":
    sys.exit(main())
