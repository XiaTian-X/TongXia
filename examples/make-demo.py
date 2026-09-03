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


def ensure_identity(target):
    """git 自己推不出提交者身份时,给这个仓库补一份仓库级的兜底身份。

    hostname 不是 FQDN 时(`scutil --get HostName` 没设置的机器就是这样,
    `gethostname()` 返回的名字里不含点),git 会拒绝拿 `username@hostname`
    自动推导 email,于是任何 commit 都 rc=128。而样板仓库必须能被 `pair.py`
    提交 —— `verify-setup` 与 `handoff` 都会提交,`test_v1_shipped.py` 断言的
    正是"出厂的样板项目必须能通过全部脚本检查"。

    **只在探测失败时才写。** 这个目录人类可能真的留着继续用;无条件塞一份假
    身份进去,他之后的每个提交都会被错误归属 —— 那比原来响亮地失败更坏。
    取值照抄 `tests/conformance/harness.py` 里 `PairRepo`/`BareRepo` 的既有
    约定,不新造一个。写的是仓库级 `.git/config`,不碰全局配置,所以它能穿过
    `test_v1_shipped.py` 那处被剥成 {PAIR_ROLE, PATH} 的 env —— 仓库级身份
    既不依赖 HOME 也不依赖环境变量。
    """
    probe = subprocess.run(("git", "var", "GIT_AUTHOR_IDENT"), cwd=target,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
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

    shutil.copytree(DEMO, target, dirs_exist_ok=True)
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
