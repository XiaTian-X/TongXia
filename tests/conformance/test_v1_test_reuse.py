# -*- coding: utf-8 -*-
"""W57:测试结果按内容记,内容没变就不重跑。

契约「测试结果按内容记,内容没变就不重跑」。指纹 = 实际执行的测试命令 + 工作区内容的树哈希(排除协议自己写的东西)
+ 已跟踪路径的集合(spec 回合带声明补,开工前审查 ⑯)。指纹与上一次相同就复用退出码,不执行、不改日志。

**怎么数执行次数**:测试命令先跑一个**仓库外**的小脚本,往同样在仓库外的计数文件追加一行、打印"RUN-第几次",再跑 harness 原来的判定
(`tests/X` 存在时 `src/X` 也要存在)。计数文件在仓库外,它的变化不进指纹;打印的次数让"日志仍是那次运行的输出"可以判。
"""

import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from harness import EVIDENCE, TEST_CMD, VERIFY_OK, PairTestCase, setup_report

COUNTER_SCRIPT = (
    "import os, sys\n"
    "p = sys.argv[1]\n"
    "n = sum(1 for _ in open(p)) if os.path.exists(p) else 0\n"
    "open(p, 'a').write('x\\n')\n"
    "print('RUN-%d' % (n + 1))\n"
)
TESTLOG = ".pair/.last-test.log"
FULL_TESTLOG = ".pair/.last-full-test.log"
# 外层环境若设了它,每一条"复用"都会变成重跑;只有 "1" 才算强制。
NO_FRESH = {"PAIR_FRESH_TESTS": ""}


def counting_cmd(counter, tail=TEST_CMD):
    d = Path(counter).parent
    script = d / "count.py"
    if not script.exists():
        script.write_text(COUNTER_SCRIPT, encoding="utf-8")
    return "%s %s %s && %s" % (shlex.quote(sys.executable), shlex.quote(str(script)),
                               shlex.quote(str(counter)), tail)


class ReuseBase(PairTestCase):
    """每个用例一个独立的计数文件;测试命令写进配置。"""

    def setUp(self):
        self.outside = Path(tempfile.mkdtemp(prefix="pair-reuse-"))
        self.addCleanup(shutil.rmtree, self.outside, True)
        self.counter = self.outside / "runs"
        self.config = {"test_cmd": counting_cmd(self.counter)}
        self.more_config(self.config)
        super().setUp()

    def more_config(self, cfg):
        pass

    def runs(self):
        return sum(1 for _ in open(self.counter)) if self.counter.exists() else 0

    def pair(self, *args, role="tester", env=None):
        e = dict(NO_FRESH)
        e.update(env or {})
        return self.repo.run(*args, role=role, env=e)

    def status(self, role="tester", env=None):
        r = self.pair("status", role=role, env=env)
        self.assertAccepted(r)
        return r

    def log(self, rel=TESTLOG):
        return self.repo.read(rel)


class TestReusedWhenNothingChanged(ReuseBase):

    def test_连续两次_status_只跑一次(self):
        self.status()
        self.assertEqual(self.runs(), 1)
        self.status(role="dev")
        self.assertEqual(self.runs(), 1, "内容与命令都没变,第二次 status 应复用")

    def test_status_之后的_verify_setup_不再跑(self):
        self.status()
        before = self.runs()
        # 评审目录在排除项里:写校验结论、verify-setup 提交它,都不改指纹。
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK))
        self.assertEqual(self.runs(), before)

    def test_评审回合的_status_与交接不再跑(self):
        """tester 回合开头的 status 跑过之后,只写评审的 approve 看到的内容一样,不再跑。
        (dev 交接时 `src/W1` 还没被跟踪、提交后被跟踪了 —— 已跟踪集合变了,status 那一次照 ⑯ 要重跑,所以基准取在它之后。)"""
        self.repo.advance_to("review-impl")
        self.status()
        before = self.runs()
        self.status()
        self.repo.write("docs/reviews/W1-review-impl.md", "# W1 评审\n\n通过。\n")
        self.assertAccepted(self.pair("handoff", "approve", "查过无硬编码", *EVIDENCE))
        self.assertEqual(self.runs(), before)
        self.assertEqual(self.repo.state()["phase"], "review-test", "前提:交接确实成功推进了")


class TestRerunWhenFingerprintChanges(ReuseBase):
    """对照组:每一格都要多跑一次。今天它们本来就跑,所以今天绿 —— 守的是"复用"做出来之后别复用过头。"""

    def setUp(self):
        super().setUp()
        self.status()
        self.base = self.runs()

    def test_改了实现或测试文件(self):
        self.repo.write("src/W9", "新实现")
        self.status()
        self.assertEqual(self.runs(), self.base + 1)
        self.repo.write("tests/W9", "新测试")
        self.status()
        self.assertEqual(self.runs(), self.base + 2)

    def test_同一个文件内容变了(self):
        self.repo.write("src/W9", "一")
        self.status()
        self.repo.write("src/W9", "二")
        self.status()
        self.assertEqual(self.runs(), self.base + 2)

    def test_测试命令变了_配置文件不动(self):
        """PAIR_TEST_CMD 覆盖:配置文件一个字不变,只有实际执行的命令不同。指纹不含命令的实现在这里复用。"""
        other = counting_cmd(self.counter) + " && true"
        self.status(env={"PAIR_TEST_CMD": other})
        self.assertEqual(self.runs(), self.base + 1)

    def test_强制重跑(self):
        self.status(env={"PAIR_FRESH_TESTS": "1"})
        self.assertEqual(self.runs(), self.base + 1)

    def test_删掉日志(self):
        (self.repo.dir / TESTLOG).unlink()
        self.status()
        self.assertEqual(self.runs(), self.base + 1)

    def test_改了配置文件但测试命令没变(self):
        """`.pair/config.json` 不排除(测试可能读它)。排除项多排了它的实现在这里复用。"""
        p = self.repo.dir / ".pair" / "config.json"
        p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.status()
        self.assertEqual(self.runs(), self.base + 1)

    def test_未跟踪文件只是被提交_内容没变(self):
        """⑯:树哈希里跟踪与否不分;依赖"哪些文件被跟踪"的测试(本仓库的规范文档检查)提交后结果可能不同。"""
        self.repo.write("src/W9", "新实现")
        self.status()
        self.repo.git("add", "src/W9")
        self.repo.git("commit", "-q", "-m", "chore: 提交 W9")
        self.status()
        self.assertEqual(self.runs(), self.base + 2)



@unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                 "要靠读权限让 git add -A 失败:Windows 与 root 下 chmod 000 不拦读")
class TestFingerprintUnavailable(ReuseBase):
    """W57 review-impl 打回过的那一格:`git add -A` 失败时临时索引原样是真实索引的副本,工作区改动不进指纹 ——
    改了实现也复用旧结果。算不出指纹就照常执行、不留记录。"""

    def test_有读不了的文件时_加了没有实现的测试照样重跑_是红的(self):
        secret = self.repo.dir / "secret.bin"
        secret.write_text("x", encoding="utf-8")
        secret.chmod(0)
        self.addCleanup(secret.chmod, 0o644)
        self.status()
        before = self.runs()
        self.repo.write("tests/W9", "没有实现的测试")
        r = self.status()
        self.assertEqual(self.runs(), before + 1, "算不出指纹时不该复用")
        self.assertIn("RED", r.out.split("测试状态", 1)[1].split("\n", 1)[0])


class TestExcludedPaths(ReuseBase):
    """协议自己写的东西不进指纹。"""

    def setUp(self):
        super().setUp()
        self.status()
        self.base = self.runs()

    def assertReused(self):
        self.status()
        self.assertEqual(self.runs(), self.base)

    def test_评审目录(self):
        self.repo.write("docs/reviews/W1-review-impl.md", "# 评审\n")
        self.assertReused()

    def test_笔记(self):
        self.repo.write("docs/notes/W1.md", "# 笔记\n")
        self.assertReused()

    def test_决策记录(self):
        self.repo.write("docs/DECISIONS.md", "# 决策\n")
        self.assertReused()

    def test_没被_gitignore_忽略的协议日志(self):
        """harness 的 .gitignore 只忽略 .last-test.log;全量日志与简报要显式排除。"""
        self.repo.write(FULL_TESTLOG, "上一次全量\n")
        self.repo.write(".pair/.last-brief.md", "# 简报\n")
        self.assertReused()

    def test_状态文件(self):
        """回合开始时的内容与上一次交接测的内容只差 state.json(交接提交时才写它)。"""
        p = self.repo.dir / ".pair" / "state.json"
        p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.repo.git("add", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "chore: 状态文件换了个换行")
        self.assertReused()


class TestMemoryOff(ReuseBase):
    """记忆层关着时,notes_dir 与 decisions_file 是普通文件,要进指纹。"""

    def more_config(self, cfg):
        cfg["memory"] = False

    def setUp(self):
        super().setUp()
        self.status()
        self.base = self.runs()

    def test_记忆层关着时笔记目录照常进指纹(self):
        self.repo.write("docs/notes/W1.md", "# 普通文件\n")
        self.status()
        self.assertEqual(self.runs(), self.base + 1)


class TestReusedResultIsFaithful(ReuseBase):

    def test_复用时绿仍是绿_日志仍是那次的输出(self):
        r1 = self.status()
        log1 = self.log()
        self.assertIn("RUN-1", log1)
        r2 = self.status()
        self.assertEqual(self.runs(), 1)
        self.assertIn("GREEN", r2.out)
        self.assertNotIn("RED", r2.out.split("测试状态", 1)[1].split("\n", 1)[0])
        self.assertEqual(self.log(), log1, "复用时不该改日志")

    def test_复用时红仍是红(self):
        self.repo.write("tests/W9", "没有实现的测试")
        r1 = self.status()
        self.assertIn("RED", r1.out.split("测试状态", 1)[1].split("\n", 1)[0])
        log1 = self.log()
        r2 = self.status()
        self.assertEqual(self.runs(), 1)
        self.assertIn("RED", r2.out.split("测试状态", 1)[1].split("\n", 1)[0])
        self.assertEqual(self.log(), log1)


class TestFullSuiteRecordedSeparately(ReuseBase):
    """`test_cmd` 与 `full_test_cmd` 各记各的:门禁那条跑了,不该冲掉全量那条的记录。"""

    def more_config(self, cfg):
        # 全量的计数脚本放在另一个目录,两个计数互不相干。
        d = Path(tempfile.mkdtemp(prefix="pair-reuse-full-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.full_counter = d / "runs"
        cfg["full_test_cmd"] = counting_cmd(self.full_counter)

    def full_runs(self):
        return sum(1 for _ in open(self.full_counter)) if self.full_counter.exists() else 0

    def test_两次_verify_setup_全量只跑一次(self):
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK))
        self.assertEqual(self.full_runs(), 1, "前提:verify-setup 跑全量")
        self.status()
        self.repo.write("docs/reviews/setup-verification-dev.md", setup_report("W1", "W2"))
        self.assertAccepted(self.pair(*VERIFY_OK, role="dev"))
        self.assertEqual(self.full_runs(), 1)
        self.assertIn("RUN-1", self.log(FULL_TESTLOG))


if __name__ == "__main__":
    unittest.main()
