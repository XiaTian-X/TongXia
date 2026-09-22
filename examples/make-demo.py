#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 examples/demo-project/ 实例化成一个可跑的结对仓库。

    python3 examples/make-demo.py /tmp/pair-demo

样板项目本身不能直接跑 —— 它是本仓库的子目录,而 pair.py 用
`git rev-parse --show-toplevel` 定位项目根,会一路找到 TongXia 的根。
所以要先复制出去、单独 git init。
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "examples" / "demo-project"
SKILL = REPO / ".agents" / "skills" / "pair-protocol"


def tracked_demo_files():
    """本仓库 git 跟踪的样板文件(相对 DEMO 的路径);不是本仓库的检出时返回 None。

    **样板只发被跟踪的东西**(W29)。曾经这里是 `shutil.copytree(DEMO, …)` —— 样板目录里
    任何没纳入 git 的东西都被原样发出去:第十三轮的 tester 在新项目里看到一个空的
    `tests/conformance/`,那是本仓库样板目录里早就在、git 不跟踪、所以没人发现的空目录。
    下一次可能是测试缓存或编辑器文件。

    "本仓库的检出"要求 `--show-toplevel` 正好是 REPO:zip 解压进用户自己的某个 git 项目时,
    上级那个仓库里 `ls-files` 一个都列不出来,照它复制就是一个空项目。
    """
    top = subprocess.run(("git", "rev-parse", "--show-toplevel"), cwd=REPO,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if top.returncode != 0:
        return None
    if Path(top.stdout.decode("utf-8").strip()).resolve() != REPO:
        return None
    rel = DEMO.relative_to(REPO).as_posix()
    out = subprocess.run(("git", "ls-files", "-z", "--", rel), cwd=REPO,
                         stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    return [Path(p).relative_to(rel) for p in out.split("\0") if p]


def copy_demo(target):
    """把样板复制进 target。在本仓库的检出里只复制被跟踪的文件;否则(zip 下载)
    退回整目录复制、只复制文件 —— 空目录因此自然被跳过。"""
    files = tracked_demo_files()
    if files is None:
        print("(不在 TongXia 的 git 检出里,问不了哪些文件被跟踪:整目录复制样板、跳过空目录。)")
        files = [p.relative_to(DEMO) for p in sorted(DEMO.rglob("*"))
                 if p.is_file() or p.is_symlink()]
    for rel in files:
        src, dst = DEMO / rel, target / rel
        if not (src.exists() or src.is_symlink()):
            continue  # 被跟踪、但工作区里删掉了:按工作区为准,不去复活它
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(src.readlink())
        else:
            shutil.copy2(src, dst)


def ensure_identity(target):
    """git 自己推不出提交者身份时,给这个仓库补一份仓库级的兜底身份。

    hostname 不是 FQDN 时(`scutil --get HostName` 没设置的机器就是这样,
    `gethostname()` 返回的名字里不含点),git 会拒绝拿 `username@hostname`
    自动推导 email,于是任何 commit 都 rc=128。而样板仓库必须能被 `pair.py`
    提交 —— `verify-setup` 与 `handoff` 都会提交,`test_v1_shipped.py` 断言的
    正是"出厂的样板项目必须能通过全部脚本检查"。

    **两个 ident 都要探。** `git commit` 要 author 与 committer 两份身份,
    两份可以各自独立来源(环境变量、各级配置、自动推导),所以只探
    `GIT_AUTHOR_IDENT` 不够:只注入 `GIT_AUTHOR_*` 而没注入
    `GIT_COMMITTER_*`、各级配置又无 `user.*` 的机器上,author 探测 rc=0 而
    committer 探测 rc=128(`fatal: unable to auto-detect email address`),
    于是一字不写、随后 `git commit` 照样 rc=128。所以**任一**探测失败就写
    兜底。写进去的 `user.*` 对两个 ident 都生效,但已注入的那一个仍然优先
    —— 实测 author 保持 `Env <env@example.com>`,只有 committer 落到兜底上,
    不会覆盖人类已经给出的身份。

    **只在探测失败时才写。** 这个目录人类可能真的留着继续用;无条件塞一份假
    身份进去,他之后的每个提交都会被错误归属 —— 那比原来响亮地失败更坏。
    取值照抄 `tests/conformance/harness.py` 里 `PairRepo`/`BareRepo` 的既有
    约定,不新造一个。写的是仓库级 `.git/config`,不碰全局配置,所以它能穿过
    `test_v1_shipped.py` 那处被剥成 {PAIR_ROLE, PATH} 的 env —— 仓库级身份
    既不依赖 HOME 也不依赖环境变量。
    """
    # for...else:两条探测都 rc=0 才走 else 里的 return(一字不写);
    # 任一条 rc≠0 就 break 出循环、落到下面写兜底。
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        probe = subprocess.run(("git", "var", var), cwd=target,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if probe.returncode != 0:
            break
    else:
        return
    for args in (("config", "user.email", "conformance@test"),
                 ("config", "user.name", "conformance")):
        subprocess.run(("git",) + args, cwd=target, check=True)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    target = Path(sys.argv[1]).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        print("目标目录 %s 非空,拒绝覆盖。" % target)
        return 1

    target.mkdir(parents=True, exist_ok=True)
    copy_demo(target)
    shutil.copytree(SKILL, target / ".agents" / "skills" / "pair-protocol",
                    dirs_exist_ok=True)
    (target / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    link = target / ".claude" / "skills" / "pair-protocol"
    if not link.exists():
        link.symlink_to(Path("../../.agents/skills/pair-protocol"))

    subprocess.run(("git", "init", "-q"), cwd=target, check=True)
    ensure_identity(target)
    for args in (("add", "-A"),
                 ("commit", "-q", "-m", "chore: 装上结对协议")):
        subprocess.run(("git",) + args, cwd=target, check=True)

    print("已创建:%s\n" % target)
    print("试跑:")
    print("  cd %s" % target)
    print("  PAIR_ROLE=tester python3 .agents/skills/pair-protocol/scripts/pair.py status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
