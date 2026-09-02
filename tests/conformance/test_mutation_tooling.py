# -*- coding: utf-8 -*-
"""变异检查工具自身的防护。

变异检查是"测试集有没有拦截力"的唯一保证,所以**它自己失效的方式**
必须被测住 —— 否则就是又一层看着是绿的、其实什么都没验的东西。

最危险的一种:缓存里的测试 id 过期(改名、删除)。unittest 对认不出的 id
会报 _FailedTest 并非零退出,这和"抓到了变异"在退出码上一模一样。
不识别它,一份过期缓存就能让每个变异都假装通过。
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "mutation_under_test", Path(__file__).with_name("mutation_check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MUT = _load()

# 一条一定存在、一定通过的测试,用来验证正常路径
KNOWN_GOOD = "test_docs_consistency.TestDocsConsistency.test_文档里提到的子命令都真实存在"


class TestCacheStalenessIsDetected(unittest.TestCase):
    """run_suite 的第三个返回值:这些测试到底跑起来了没有。"""

    def test_认不出的测试_id_不算跑过(self):
        rc, _, loaded = MUT.run_suite(REPO, ["nope.NoSuch.test_不存在"])
        self.assertNotEqual(rc, 0, "unittest 对认不出的 id 本来就该非零退出")
        self.assertFalse(
            loaded,
            "认不出的测试 id 被当成跑过了 —— 过期缓存会让每个变异都假装通过")

    def test_跑起来的测试算数(self):
        rc, _, loaded = MUT.run_suite(REPO, [KNOWN_GOOD])
        self.assertEqual(rc, 0)
        self.assertTrue(loaded)

    def test_只跑起来一部分也不算数(self):
        rc, _, loaded = MUT.run_suite(
            REPO, [KNOWN_GOOD, "nope.NoSuch.test_不存在"])
        self.assertFalse(
            loaded, "请求 2 个只跑了 1 个,不足以判定变异被抓到")


class TestBaselineFingerprint(unittest.TestCase):
    """快路径的前提是基线全绿 —— 只有基线绿,才能把"这些测试失败了"归因到变异上。

    --no-baseline 把那个前提关掉了。不加这道闸,一个正改到一半、某个测试本来
    就红着的工作区,能在 0.8 秒内报"全部被抓到" —— 看着是绿的,其实什么都没验。
    """

    def _fp(self, *contents):
        """在临时文件上算指纹 —— 不碰仓库里的真实文件。
        并行分片下动真实文件是竞态:别的进程可能正在导入它。"""
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for n, text in enumerate(contents):
                p = Path(d) / ("f%d.py" % n)
                p.write_text(text, encoding="utf-8")
                paths.append(p)
            return MUT.fingerprint(paths)

    def test_内容变了指纹就变(self):
        self.assertNotEqual(self._fp("a = 1"), self._fp("a = 2"),
                            "内容变了指纹没变 —— 这道闸形同虚设")

    def test_内容没变指纹稳定(self):
        self.assertEqual(self._fp("a = 1", "b = 2"), self._fp("a = 1", "b = 2"))

    def test_真实指纹覆盖执行层与测试代码(self):
        """两类文件都要进指纹:pair.py 变会让防护变,测试变会让基线变。"""
        h = MUT.fingerprint()
        self.assertNotEqual(h, self._fp(""))
        self.assertEqual(h, MUT.fingerprint(), "同一棵树上必须稳定")

    def test_跑过基线就直接算数(self):
        self.assertTrue(MUT.baseline_verified(False, "", "abc"))
        self.assertTrue(MUT.baseline_verified(False, "旧的", "abc"))

    def test_跳过基线时指纹必须对得上(self):
        self.assertTrue(MUT.baseline_verified(True, "abc", "abc"))
        self.assertFalse(
            MUT.baseline_verified(True, "旧的", "abc"),
            "指纹对不上还敢走快路径 —— 一个改到一半的工作区能在一秒内报全绿")
        self.assertFalse(
            MUT.baseline_verified(True, "", "abc"),
            "没有指纹就是没有证据,不能当成验证过")

    def test_旧的扁平缓存不被当成已验证(self):
        """老格式没有基线指纹。把它当成"验证过"等于默认相信一个来历不明的缓存。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"某变异": ["a.B.c"]}), encoding="utf-8")
            fp, catchers = MUT.load_cache(p)
        self.assertEqual(fp, "", "旧格式必须被当成「指纹未知」,快路径不放行")
        self.assertEqual(catchers, {"某变异": ["a.B.c"]}, "条目本身要留着")

    def test_损坏的缓存文件不炸(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text("{ 这不是 json", encoding="utf-8")
            self.assertEqual(MUT.load_cache(p), ("", {}))


class TestRunnerDoesNotFakePass(unittest.TestCase):
    """跑不到测试就不能报成功 —— 那是最坏的一种假绿。"""

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "runner_under_test", Path(__file__).with_name("run.py"))
        self.run_py = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.run_py)

    def test_拼错的模块名不算通过(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = self.run_py.main(["这个模块名不存在"])
        self.assertEqual(code, 2, "匹配不到任何模块却返回 0,等于谎报测试通过")
        self.assertIn("没有模块匹配", err.getvalue())

    def test_对得上的模块名照常列出(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.run_py.main(["--list", "docs_consistency"])
        self.assertEqual(code, 0)
        self.assertIn("test_docs_consistency", out.getvalue())


class TestCacheShape(unittest.TestCase):

    def test_缓存里的条目名都在_MUTATIONS_里(self):
        _, cache = MUT.load_cache()
        names = {m[0] for m in MUT.MUTATIONS}
        stale = sorted(set(cache) - names)
        self.assertFalse(
            stale, "缓存里有已经不存在的变异点,删掉它们:%s" % stale)

    def test_MUTATIONS_没有重名(self):
        names = [m[0] for m in MUT.MUTATIONS]
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.assertFalse(dupes, "变异点重名会让缓存互相覆盖:%s" % dupes)


if __name__ == "__main__":
    unittest.main()
