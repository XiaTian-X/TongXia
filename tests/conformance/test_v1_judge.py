# -*- coding: utf-8 -*-
"""W10:裁判副本的同步不变量。

契约「裁判副本的同步」:`.pair/enforcer.py` 存在时必须逐字节等于
`pair.py`,唯一的例外窗口是一个工作项进行中。`claim` 时校验,
`DONE` 且全绿时自动重钉。

**为什么必须逐字节比,不能比注册表**:上一轮真实发生过的漂移里,
`ENFORCEMENTS` 与 `HANDOFF_INVARIANTS` 两边差集**都是空的**,而两个
文件差 122 行、整节孤儿清单不在裁判里。拿注册表(或符号集合)当判据
是恒真的,所以下面 `test_只差一行注释也要拦` 与 `test_只差一个空白字符也要拦`
是这一组的核心 —— 它们专门用来打死那种实现。
"""

import os
import subprocess
import unittest

from harness import EVIDENCE, PAIR_PY, PairTestCase, Result

ENFORCER = ".pair/enforcer.py"


class JudgeMixin:
    """把副本钉成指定内容,并让工作区保持干净。"""

    def pin(self, content=None):
        src = self.repo.read(PAIR_PY)
        self.repo.write(ENFORCER, src if content is None else content)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "chore: 钉住裁判副本")
        return src

    def run_via_enforcer(self, *args, role="tester"):
        """用**副本自己**当裁判跑一条命令。`PairRepo.run` 跑的永远是
        skill 里那份 pair.py,而真实部署跑的是副本 —— 两者的差别正好是
        一个恒真实现的藏身处,见 `test_副本当裁判时也要拦`。"""
        e = dict(os.environ)
        e.pop("PAIR_TEST_CMD", None)
        e["PAIR_ROLE"] = role
        return Result(subprocess.run(
            ["python3", ENFORCER] + list(args), cwd=self.repo.dir, env=e,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE))

    def drift_pair_py(self, marker="\n# 本回合 dev 改过 pair.py\n"):
        """dev 在工作项进行中改 pair.py —— 副本因此落后。追加注释,
        不动任何逻辑,所以注册表、符号集合两边仍然完全相同。"""
        self.repo.write(PAIR_PY, self.repo.read(PAIR_PY) + marker)
        return marker


class TestJudgeSyncAtClaim(JudgeMixin, PairTestCase):
    """① 副本与 pair.py 不一致时,claim 拒绝认领。"""

    def test_副本落后时拒绝认领(self):
        src = self.pin()
        self.pin(src[:-800])          # 副本少了尾部,模拟真实的落后
        r = self.repo.run("claim", "W1", role="tester")
        self.assertRefused(r, ENFORCER, PAIR_PY)

    def test_只差一行注释也要拦(self):
        """专杀"比注册表/比符号集合"的实现:这两份文件的 ENFORCEMENTS、
        HANDOFF_INVARIANTS、函数集合完全相同,只差一行注释。"""
        src = self.pin()
        self.pin(src + "\n# 副本上多出来的一行注释\n")
        self.assertRefused(self.repo.run("claim", "W1", role="tester"),
                           ENFORCER)

    def test_只差一个空白字符也要拦(self):
        """专杀 `a.strip() == b.strip()` 的实现。契约写的是逐字节。"""
        src = self.pin()
        self.pin(src + "\n")
        self.assertRefused(self.repo.run("claim", "W1", role="tester"),
                           ENFORCER)

    def test_副本当裁判时也要拦(self):
        """实现若拿 `__file__` 去比,跑副本时就是在跟自己比 —— 恒真,
        而"跑副本"正是这一轮的真实部署方式。这里用副本自己当裁判,
        它仍然必须发现自己和 skill 里那份不一致。"""
        src = self.pin()
        self.pin(src + "\n# 副本上多出来的一行注释\n")
        r = self.run_via_enforcer("claim", "W1")
        self.assertRefused(r, ENFORCER)

    def test_逐字节一致时放行(self):
        self.pin()
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def test_副本不存在时放行(self):
        """④ 默认用法里 pair.py 自己当裁判,不该凭空要求一份副本。"""
        self.assertFalse(self.repo.exists(ENFORCER))
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))


class TestJudgeRepinAtDone(JudgeMixin, PairTestCase):
    """②③⑤ 工作项进行中不校验、不重钉;DONE 时重钉,且钉在两头之间。

    `.agents` 从 frozen_paths 挪进 dev 的路径 —— 本轮 dev 要改的正是
    `pair.py`,而这一组用例的前提就是"工作项进行中 pair.py 会变"。
    """

    config = {
        "roles": {"tester": ["tests"], "dev": ["src", ".agents"]},
        "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md", ".pair"],
    }

    def run_to_done(self):
        self.pin()
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例",
                                          role="tester"))
        self.repo.write("src/W1")
        marker = self.drift_pair_py()
        # ② 工作项进行中两者本就该不等,handoff 不能拿这个拦人
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "无硬编码",
                                          *EVIDENCE, role="tester"))
        return marker

    def test_工作项进行中不校验也不重钉(self):
        marker = self.run_to_done()
        # 还没到 DONE:副本必须仍是旧的,否则等于把没验过的裁判钉了上去
        self.assertNotIn(marker, self.repo.read(ENFORCER))
        self.assertEqual(self.repo.state()["phase"], "review-test")

    def test_DONE_时把副本重钉成逐字节一致(self):
        self.run_to_done()
        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约",
                                          *EVIDENCE, role="dev"))
        self.assertEqual(self.repo.state()["completed_items"], ["W1"])
        self.assertEqual(self.repo.read(ENFORCER), self.repo.read(PAIR_PY))

    def test_重钉的_sha_进提交正文(self):
        self.run_to_done()
        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约",
                                          *EVIDENCE, role="dev"))
        sha = self.repo.git("hash-object", PAIR_PY).stdout.decode().strip()
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertTrue(
            len(sha) >= 7 and sha[:7] in body,
            "提交正文里没有重钉后的 sha(%s)。正文:\n%s" % (sha[:7], body))

    def test_重钉发生在_git_add_之前所以进了提交(self):
        """⑤ 只钉"边界校验之后"这一头不够:落在 `git add -A` 之后,
        重钉过的副本会留在工作区没进提交,下一个回合对方被冻结判定拦住,
        而那个改动不是它做的、撤销又会把重钉一起撤掉 —— 没有出路。"""
        self.run_to_done()
        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约",
                                          *EVIDENCE, role="dev"))
        dirty = self.repo.git("status", "--porcelain").stdout.decode()
        self.assertEqual(dirty.strip(), "",
                         "DONE 之后工作区不干净,重钉多半落在 git add 之后:\n%s"
                         % dirty)
        files = self.repo.git("show", "--name-only", "--format=",
                              "HEAD").stdout.decode()
        self.assertIn(ENFORCER, files,
                      "重钉过的副本没进 DONE 那次提交。改动的文件:\n%s" % files)


class TestJudgeAbsent(JudgeMixin, PairTestCase):
    """④ 的另一半:没有副本的项目,DONE 也不该凭空造一份。"""

    def test_DONE_不会凭空造出副本(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "用例", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "无硬编码",
                                          *EVIDENCE, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约",
                                          *EVIDENCE, role="dev"))
        self.assertEqual(self.repo.state()["completed_items"], ["W1"])
        self.assertFalse(self.repo.exists(ENFORCER),
                         "项目本来没有裁判副本,DONE 之后不该多出一份")


if __name__ == "__main__":
    unittest.main()
