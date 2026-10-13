# -*- coding: utf-8 -*-
"""W51:make-demo 里 git 失败要说明白。

契约「make-demo 里 git 失败要说明白」。`make-demo.py` 的 `git init` / `add -A` / `commit` 用 `check=True`,
任一步失败用户看到的是一整段 `CalledProcessError` 堆栈。

**怎么让 git 失败**:PATH 最前放一个叫 `git` 的 shell 脚本,第一个不以 `-` 开头的参数等于要失败的那一步时
往标准错误打一句固定文字、退 128;其余参数原样转给真 git(起测前用 `shutil.which` 找好)。
`tracked_demo_files`、`ensure_identity` 里的 `rev-parse` / `ls-files` / `var` / `config` 都走转发。

**"点名是哪一步"按 ASCII 词边界判**:修好之后输出里会有"最常见原因"`commit.gpgsign` —— 按子串找 `commit`,
任何失败都会被它满足。所以 `commit.gpgsign` 那种带点的不算;中文紧挨着英文也算词边界(用 ASCII 字符类,不用 `\\w`)。
另有一条:`init` 失败时不该点名 `commit` —— 不论哪步失败都打同一句"init/add/commit 之一失败"的实现在这里红。
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAKE_DEMO = REPO / "examples" / "make-demo.py"
REAL_GIT = shutil.which("git")
# 假 git 打出的错误文字。不含 init / add / commit 这几个词,免得替"点名是哪一步"作答。
FAKE_ERROR = "fatal: W51 测试替身让这一步失败(假错误 7f3e)"


def names_step(out, step):
    """输出里有没有把 `step` 当成一个独立的词说出来(`commit.gpgsign` 不算)。"""
    return re.search(r"(?<![A-Za-z0-9_.\-])%s(?![A-Za-z0-9_.\-])" % re.escape(step), out) is not None


@unittest.skipIf(REAL_GIT is None or os.name == "nt", "要一个真 git 来转发,假 git 是 sh 脚本")
class FakeGit(unittest.TestCase):

    def run_make_demo(self, fail=None):
        d = Path(tempfile.mkdtemp(prefix="fakegit-"))
        self.addCleanup(shutil.rmtree, d, True)
        exe = d / "git"
        exe.write_text(
            "#!/bin/sh\n"
            "sub=\n"
            'for a in "$@"; do case "$a" in -*) ;; *) sub="$a"; break;; esac; done\n'
            'if [ "$sub" = "%s" ]; then echo "%s" >&2; exit 128; fi\n'
            'exec "%s" "$@"\n' % (fail or "", FAKE_ERROR, REAL_GIT),
            encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=str(d) + os.pathsep + os.environ.get("PATH", ""))
        target = Path(tempfile.mkdtemp(prefix="demo-")) / "proj"
        self.addCleanup(shutil.rmtree, target.parent, True)
        proc = subprocess.run([sys.executable, str(MAKE_DEMO), str(target)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), target

    def assertExplainedFailure(self, rc, out):
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertIn(FAKE_ERROR, out, "git 的原始输出要给用户看到")


class TestPremise(FakeGit):

    def test_对照组_假_git_什么都不拦时照常生成(self):
        """假 git 本身若把转发弄坏了,下面几条"失败"会白白成立。"""
        rc, out, target = self.run_make_demo(fail=None)
        self.assertEqual(rc, 0, out)
        self.assertIn("已创建", out)
        self.assertNotIn(FAKE_ERROR, out)
        self.assertTrue((target / ".git").exists())


class TestCommitFails(FakeGit):

    def test_commit_失败_点名这一步_给出_git_原话_没有堆栈(self):
        rc, out, _ = self.run_make_demo(fail="commit")
        self.assertExplainedFailure(rc, out)
        self.assertTrue(names_step(out, "commit"), out)

    def test_commit_失败_给出最常见的两个原因(self):
        """身份没配(`git config user.name/user.email`)与配了签名却没有密钥(`commit.gpgsign`)。"""
        rc, out, _ = self.run_make_demo(fail="commit")
        self.assertExplainedFailure(rc, out)
        self.assertIn("user.email", out)
        self.assertIn("commit.gpgsign", out)

    def test_失败时已建出的目标目录留着(self):
        """"出错就 rmtree"的实现在这里红 —— 契约要留给用户看。"""
        rc, out, target = self.run_make_demo(fail="commit")
        self.assertNotEqual(rc, 0, out)
        self.assertTrue((target / "docs" / "PLAN.md").exists(), out)
        self.assertTrue((target / ".git").exists(), out)


class TestInitFails(FakeGit):

    def test_init_失败_点名这一步_给出_git_原话_没有堆栈(self):
        rc, out, _ = self.run_make_demo(fail="init")
        self.assertExplainedFailure(rc, out)
        self.assertTrue(names_step(out, "init"), out)

    def test_init_失败时不说是_commit(self):
        """不论哪步都打同一句"init/add/commit 之一失败"的实现,上一条照绿、这一条红。"""
        rc, out, _ = self.run_make_demo(fail="init")
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(names_step(out, "commit"), out)


class TestAddFails(FakeGit):

    def test_add_失败_点名这一步_给出_git_原话_没有堆栈(self):
        rc, out, _ = self.run_make_demo(fail="add")
        self.assertExplainedFailure(rc, out)
        self.assertTrue(names_step(out, "add"), out)


if __name__ == "__main__":
    unittest.main()
