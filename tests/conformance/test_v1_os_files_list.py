# -*- coding: utf-8 -*-
"""W34:操作系统文件的名单显式写出,不靠形状猜。

契约「操作系统文件的名单显式写出」。W31 的 `OS_FILES` 取 `GITIGNORE_LINES` 里"不含 `/` 也不含 `*`"的项 ——
今后加一个 `.env` 之类的裸文件名,越界文案会把它说成"操作系统写的文件",没有用例会红。

**判据在内存里改写 `pair.py` 的源码模拟今后的编辑**,执行后看模块里的两个名字。插入点靠 W34 的 spec 回合定死的字面
(见契约):`GITIGNORE_LINES` 里 `".pair/scratch/",` 那一处、`OS_FILES` 那一行的 `"desktop.ini")`。
字面对不上时用例直接报"插入点不见了",不会静默通过。
"""

import types
import unittest

from test_v1_shipped import SCRIPTS

OS_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def load(edit=None):
    """执行(可能改写过的)pair.py 源码,返回模块对象。`edit` 是 (旧片段, 新片段)。"""
    path = SCRIPTS / "pair.py"
    src = path.read_text(encoding="utf-8")
    if edit:
        old, new = edit
        assert src.count(old) == 1, "插入点不见了(或不唯一):%r" % old
        src = src.replace(old, new)
    mod = types.ModuleType("pair_edited")
    mod.__file__ = str(path)
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod


class TestExplicitList(unittest.TestCase):

    def test_往_GITIGNORE_LINES_加一个裸文件名_它不算系统文件(self):
        mod = load(('".pair/scratch/",', '".pair/scratch/", ".env",'))
        self.assertIn(".env", mod.GITIGNORE_LINES, "前提:编辑生效了")
        self.assertNotIn(".env", mod.OS_FILES)

    def test_名单本身不变(self):
        self.assertEqual(set(load().OS_FILES), OS_NAMES)

    def test_三个系统文件都在_GITIGNORE_LINES_里(self):
        lines = load().GITIGNORE_LINES
        for name in OS_NAMES:
            self.assertIn(name, lines)

    def test_名单是一处写_GITIGNORE_LINES_引用它(self):
        """③ 同源:往名单里加一项,它自动进 `GITIGNORE_LINES` —— 各抄一份的实现这里会红。"""
        mod = load(('"desktop.ini")', '"desktop.ini", "ehthumbs.db")'))
        self.assertIn("ehthumbs.db", mod.OS_FILES, "前提:编辑生效了")
        self.assertIn("ehthumbs.db", mod.GITIGNORE_LINES)
