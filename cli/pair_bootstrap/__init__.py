# -*- coding: utf-8 -*-
"""结对协议的 bootstrap CLI —— 唯一职责是把协议搬进目标项目。

    uvx --from git+https://github.com/<你>/TongXia pair init [目标目录]

**这里不含任何协议逻辑。** 判定、边界、红绿、回合全部在 skill 里的 pair.py,
本模块只做两件事:

    1. 把 .agents/skills/pair-protocol/ 复制进目标项目 + 建 .claude/skills 软链接
    2. 调用刚复制过去的 pair.py init,把后续全部交出去

这条约束是刻意的:一旦 CLI 里出现协议逻辑,它就会和 skill 漂移 ——
两份判定不一致时门禁看着还在、实际拦不住,交付会悄悄变废。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_REL = ".agents/skills/pair-protocol"
CLAUDE_SKILL_REL = ".claude/skills/pair-protocol"
PAIR_PY_REL = SKILL_REL + "/scripts/pair.py"

__version__ = "1.0.0"


def find_bundled_skill():
    """装成 wheel 时在包内(见 pyproject 的 force-include);从源码跑时在仓库根。"""
    packaged = Path(__file__).resolve().parent / "skill"
    if (packaged / "SKILL.md").exists():
        return packaged
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / SKILL_REL
        if (candidate / "SKILL.md").exists():
            return candidate
    return None


def fail(msg):
    sys.stderr.write("\n[pair] %s\n\n" % msg)
    sys.exit(1)


def cmd_init(args):
    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        fail("目标目录不存在:%s" % target)

    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=target,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        fail("%s 不是 git 仓库。结对协议依赖 git 做交接,请先 git init。" % target)
    root = Path(proc.stdout.decode("utf-8").strip())

    skill = find_bundled_skill()
    if skill is None:
        fail("找不到随包分发的协议目录。这是 CLI 打包问题,请报告。")

    dest = root / SKILL_REL
    fresh = not (dest / "SKILL.md").exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill, dest, dirs_exist_ok=True)
    print("[pair] %s 协议 → %s" % ("已复制" if fresh else "已更新", SKILL_REL))

    link = root / CLAUDE_SKILL_REL
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists() and not link.is_symlink():
        try:
            link.symlink_to(Path("../../.agents/skills/pair-protocol"))
            print("[pair] 已建软链接 %s（Claude Code 读这个目录）" % CLAUDE_SKILL_REL)
        except OSError:
            # Windows 无管理员权限时会失败,退化成桩文件
            link.mkdir(parents=True, exist_ok=True)
            (link / "SKILL.md").write_text(
                "本文件是桩。真正的协议在 `.agents/skills/pair-protocol/SKILL.md`,"
                "请立即读取它并严格遵守。\n", encoding="utf-8")
            print("[pair] 无法创建软链接,已改用桩文件 %s" % CLAUDE_SKILL_REL)

    print("[pair] 交给 pair.py init ——\n")
    return subprocess.call([sys.executable, str(root / PAIR_PY_REL), "init"],
                           cwd=str(root))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pair", description="把双 agent 结对协议装进一个项目")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="把协议装进目标项目并初始化")
    p.add_argument("target", nargs="?", default=".", help="目标项目目录(默认当前目录)")
    p.set_defaults(func=cmd_init)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
