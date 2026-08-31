import unittest


class TestSmoke(unittest.TestCase):
    """基线冒烟测试。

    全新项目如果 tests/ 是空的,`unittest discover` 会因 "NO TESTS RAN"
    而非零退出,init 的基线检查就会拒绝接入。放一条必过的用例即可。
    """

    def test_基线可运行(self):
        self.assertTrue(True)
