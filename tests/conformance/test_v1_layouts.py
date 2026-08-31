# -*- coding: utf-8 -*-
"""存量项目布局:glob 路径匹配、负模式、ignore_paths。

v0 的 under() 只做目录前缀比较,Go 与 JS 的同目录测试布局无法表达 ——
那让协议只能用于恰好是 tests/ + src/ 的新项目。
"""

from harness import PairTestCase, GO_CONFIG

GO_PLAN = """# 规划

## 工作项

- [ ] **G1** [feature] — Go 布局的工作项
  - 对应契约:`docs/CONTRACT.md` → W1
"""


class TestGoColocatedLayout(PairTestCase):
    """foo.go 与 foo_test.go 在同一目录,只能靠 glob + 负模式切分。"""

    config = GO_CONFIG

    def setUp(self):
        super().setUp()
        self.repo.set_plan(GO_PLAN)

    def test_tester_可以写测试文件(self):
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("pkg/slug/slug_test.go", "package slug")
        r = self.repo.run("handoff", "G1 的失败用例", role="tester")
        self.assertAccepted(r)

    def test_tester_不能写同目录下的源码(self):
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("pkg/slug/slug_test.go", "package slug")
        self.repo.write("pkg/slug/slug.go", "package slug")   # 越界
        r = self.repo.run("handoff", "顺手把实现也写了", role="tester")
        self.assertRefused(r, "pkg/slug/slug.go", "越界")

    def test_dev_可以写源码但不能写测试(self):
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("pkg/slug/slug_test.go", "package slug")
        self.repo.run("handoff", "用例", role="tester")

        self.repo.write("pkg/slug/slug.go", "package slug")
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))

    def test_dev_的负模式排除了测试文件(self):
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("pkg/slug/slug_test.go", "package slug")
        self.repo.run("handoff", "用例", role="tester")

        self.repo.write("pkg/slug/slug.go", "package slug")
        self.repo.write("pkg/slug/other_test.go", "package slug")   # 越界
        r = self.repo.run("handoff", "顺手改了测试", role="dev")
        self.assertRefused(r, "other_test.go", "越界")

    def test_深层目录也能匹配(self):
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("a/b/c/d/deep_test.go", "package d")
        self.assertAccepted(self.repo.run("handoff", "深层用例", role="tester"))

    def test_根目录文件也能匹配(self):
        """`**/` 必须能匹配零层目录,否则根目录的文件会被判越界。"""
        self.repo.run("claim", "G1", role="tester")
        self.repo.write("root_test.go", "package main")
        self.assertAccepted(self.repo.run("handoff", "根目录用例", role="tester"))


class TestIgnorePaths(PairTestCase):
    """构建副产物不该让交接失败 —— dev 跑一次 npm install 就该被拒是不合理的。"""

    config = {"ignore_paths": ["package-lock.json", "**/*.lock", "build"]}

    def test_lockfile_改动不被判越界(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("package-lock.json", '{"v": 2}')
        r = self.repo.run("handoff", "写用例时装了依赖", role="tester")
        self.assertAccepted(r)

    def test_glob_形式的忽略路径生效(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("deps/go.lock", "x")
        self.assertAccepted(self.repo.run("handoff", "用例", role="tester"))

    def test_忽略目录下的文件生效(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("build/out.bin", "x")
        self.assertAccepted(self.repo.run("handoff", "用例", role="tester"))

    def test_未被忽略的越界文件仍然被拒(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("src/sneaky", "x")
        r = self.repo.run("handoff", "用例", role="tester")
        self.assertRefused(r, "src/sneaky", "越界")


class TestBackwardCompatiblePaths(PairTestCase):
    """v0 的纯目录前缀配置必须继续有效。"""

    def test_目录前缀语义不变(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/nested/deep/case.txt")
        self.assertAccepted(self.repo.run("handoff", "嵌套用例", role="tester"))

    def test_前缀不会误伤同名前缀的兄弟目录(self):
        """`tests` 不应匹配 `tests-extra/`。"""
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        self.repo.write("tests-extra/x.txt")
        r = self.repo.run("handoff", "用例", role="tester")
        self.assertRefused(r, "tests-extra/x.txt", "越界")
