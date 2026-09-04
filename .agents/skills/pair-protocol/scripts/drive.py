#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动驱动两个结对 agent —— 把"人在两个终端之间来回敲一句"这件事自动化。

    python3 .agents/skills/pair-protocol/scripts/drive.py \\
        --tester "claude -p" --dev "claude -p"

**这里没有任何协议逻辑。** 轮到谁、要不要停,全部由
`pair.py whose-turn` 回答;这个脚本只认它的一行输出,然后拉起对应的命令。
判定一旦在这里复制一份,它就成了协议的第二个实现;两份判定迟早不一致,
门禁看着还在、实际拦不住 —— 和 CLI 那条"零协议逻辑"同源,同样有测试钉着。

## 为什么默认不开自动

ADR-010:人类是时钟。手动交接顺带保证了三件事 —— 每回合有一个天然的
观察窗口、跑飞的成本有上界、契约由人类维护这件事有了执行时机。
自动化会把每个还没暴露的设计缺陷放大成事故,所以它是**可选项**,
而且在下面这些时刻一律停下来交给人:

  - 协议自己说该停(死锁闸、项目完成、未通过开工前校验、状态被改)
  - agent 进程非零退出
  - 一个回合跑完而状态没有前进(卡住了,再跑一遍只会卡在同一处)
  - 超过回合预算(默认 24)

## 一条硬纪律

**驱动器自己绝不碰 git。** 结对期间人类提交任何东西都可能把某一方停在
工作区里的产出提交走,而"打回之后必须真的动了测试"那条检查按工作区判断,
会把它读成"你什么都没干"。见 INSTALL.md 的「人类介入的纪律」。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAIR_PY = HERE / "pair.py"
TURNS_REL = ".pair/turns"

DEFAULT_PROMPT = (
    "轮到你了。按 SKILL.md 的规矩走这一回合:先跑 status,照它说的做,"
    "做完用 handoff 交接。不要越界,不要替对方做事。"
)


def ask(root):
    """问协议:接下来该谁。返回 (kind, rest) —— kind 是 'turn' 或 'stop'。"""
    proc = subprocess.run([sys.executable, str(PAIR_PY), "whose-turn"],
                          cwd=str(root), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    line = proc.stdout.decode("utf-8", "replace").strip().splitlines()
    if proc.returncode != 0 or not line:
        return "stop", ("whose-turn 自己失败了:\n%s"
                        % proc.stdout.decode("utf-8", "replace").strip())
    head, _, rest = line[-1].partition(" ")
    if head not in ("turn", "stop"):
        return "stop", "看不懂 whose-turn 的输出:%r" % line[-1]
    return head, rest


def snapshot(root):
    """状态指纹。用来判断一个回合有没有真的把回合推进。"""
    try:
        st = json.loads((root / ".pair" / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return (st.get("phase"), st.get("item"), st.get("round"),
            st.get("changes_count"), st.get("last_actor"),
            tuple(st.get("completed_items", [])))


def next_log(root, role):
    """下一个回合日志的路径。按序号递增,重跑不覆盖。"""
    d = root / TURNS_REL
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("*.log"))) + 1
    return d / ("%03d-%s.log" % (n, role))


def run_turn(root, command, role, prompt, dry):
    """拉起一方跑一个回合。

    命令按 shell 解释,角色通过 `PAIR_ROLE` 环境变量传(协议解析角色的
    第一优先级),提示语从**标准输入**喂进去 —— 那是最通用的一条路,
    命令不读 stdin 也不会出错。

    输出**边打边落盘**:实时打给你看,同时留一份在 .pair/turns/。
    只落盘不打印,等于为了留痕把你正在看的东西关掉;只打印不落盘,
    全自动跑一轮下来什么都不剩 —— 而上一轮最值钱的发现恰恰来自
    人在中间看了一眼(见 docs/dogfood-run-1.md)。
    """
    print("\n" + "=" * 60)
    print(" 轮到 %s —— %s" % (role, command))
    print("=" * 60)
    if dry:
        print("(--dry-run:不真的拉起)")
        return 0

    log = next_log(root, role)
    proc = subprocess.Popen(command, shell=True, cwd=str(root),
                            env=dict(os.environ, PAIR_ROLE=role),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    with open(log, "wb") as f:
        f.write(("$ %s   (PAIR_ROLE=%s)\n\n" % (command, role)).encode("utf-8"))
        try:
            proc.stdin.write((prompt or "").encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass                      # 子进程不读 stdin,不是错误
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
            f.write(line)
    code = proc.wait()
    print("\n(本回合输出已存到 %s)" % log.relative_to(root))
    return code


def _where(root):
    d = root / TURNS_REL
    logs = sorted(d.glob("*.log")) if d.exists() else []
    if not logs:
        return ""
    return "\n>>> 每回合的完整输出在 %s/,最后一个是 %s" % (
        TURNS_REL, logs[-1].name)


def drive(root, cmds, prompt, max_turns, dry):
    stalled_at = None
    for n in range(1, max_turns + 1):
        kind, rest = ask(root)
        if kind == "stop":
            print("\n>>> 协议要求停下:%s" % rest)
            print(">>> 交给人类。%s" % _where(root))
            return 0

        role = rest.strip()
        if role not in cmds or not cmds[role]:
            print("\n>>> 轮到 %s,但没给它的启动命令(--%s)。" % (role, role))
            return 2

        before = snapshot(root)
        code = run_turn(root, cmds[role], role, prompt, dry)
        if dry:
            return 0
        if code != 0:
            print("\n>>> %s 的进程非零退出(%d)。交给人类。%s"
                  % (role, code, _where(root)))
            return 1

        after = snapshot(root)
        if after == before:
            if stalled_at == before:
                print("\n>>> 连续两个回合状态没有前进 —— 卡住了,再跑只会卡在同一处。")
                print(">>> 交给人类。%s" % _where(root))
                return 1
            stalled_at = before
            print("\n(状态没变,再给一次机会 —— 有可能它这一回合被门禁拦下并改好了)")
        else:
            stalled_at = None
        time.sleep(0.5)

    print("\n>>> 到了回合预算上限(%d)。这是驱动器自己的保险,不是协议的。"
          % max_turns)
    print(">>> 想继续就加大 --max-turns,但先看一眼它们在干什么。")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="drive.py",
        description="自动驱动两个结对 agent。协议判定全在 pair.py,这里只负责拉起。")
    ap.add_argument("--tester", metavar="命令", help="拉起 tester 的 shell 命令")
    ap.add_argument("--dev", metavar="命令", help="拉起 dev 的 shell 命令")
    ap.add_argument("--both", metavar="命令",
                    help="两边用同一条命令(同工具同模型,最省事的起步配置)")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT,
                    help="喂给 agent 的第一句话。默认让它按 SKILL.md 走一个回合")
    ap.add_argument("--max-turns", type=int, default=24,
                    help="回合预算,超了就停下交给人类(默认 24)")
    ap.add_argument("--dry-run", action="store_true",
                    help="只问协议该谁,不真的拉起 agent")
    args = ap.parse_args(argv)

    cmds = {"tester": args.tester or args.both, "dev": args.dev or args.both}
    if not any(cmds.values()) and not args.dry_run:
        ap.error("至少要给 --both,或者 --tester 与 --dev")

    root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"],
                               stdout=subprocess.PIPE).stdout
                .decode("utf-8").strip() or ".")

    # 回合日志落在 .pair/ 下,而协议把 .pair 当冻结路径。没被 git 忽略的话,
    # 第一份日志就会让下一次交接判越界 —— 而且 agent 删不干净,下一回合又生成。
    ignored = subprocess.run(["git", "check-ignore", "-q", TURNS_REL + "/x.log"],
                             cwd=str(root)).returncode == 0
    if not ignored:
        print("!! %s/ 没有被 git 忽略。" % TURNS_REL)
        print("!! 回合日志会让下一次 handoff 判越界(.pair 是冻结路径)。")
        print("!! 往 .gitignore 加一行 `%s/` 再跑。\n" % TURNS_REL)
        return 2

    return drive(root, cmds, args.prompt, args.max_turns, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
