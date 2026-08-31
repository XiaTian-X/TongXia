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

    for args in (("init", "-q"),
                 ("add", "-A"),
                 ("commit", "-q", "-m", "chore: 装上结对协议")):
        subprocess.run(("git",) + args, cwd=target, check=True)

    print("已创建:%s\n" % target)
    print("试跑:")
    print("  cd %s" % target)
    print("  PAIR_ROLE=tester python3 .agents/skills/pair-protocol/scripts/pair.py status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
