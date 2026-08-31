# -*- coding: utf-8 -*-
"""正向场景:必须放行的合法操作。

这些用例防的是"过度拦截" —— 一个把所有东西都拒绝掉的执行层,
违规测试也能全绿,但完全没用。
"""

from harness import PairTestCase


class TestUnicodeAndSpecialChars(PairTestCase):
    """bash 版的 P2:中文文件名被 git 转义后误判越界;`|` 让 sed 崩溃。"""

    def test_中文文件名正常放行(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/测试_登录.txt")
        r = self.repo.run("handoff", "验证登录", role="tester")
        self.assertAccepted(r)

    def test_含空格文件名正常放行(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/login case.txt")
        r = self.repo.run("handoff", "验证登录", role="tester")
        self.assertAccepted(r)

    def test_说明里的特殊字符不会破坏状态(self):
        self.repo.run("claim", "W1", role="tester")
        self.repo.write("tests/W1")
        r = self.repo.run("handoff", "验证 a|b 与 k:v 的解析", role="tester")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "impl")

    def test_工作项_ID_含特殊字符(self):
        self.repo.write("docs/PLAN.md",
                        "# 规划\n\n- [ ] **W|3: 解析 a:b** — 标题\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "docs: 人类更新了规划")
        r = self.repo.run("claim", "W|3: 解析 a:b", role="tester")
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["item"], "W|3: 解析 a:b")


class TestFullCycle(PairTestCase):

    def test_完整四阶段循环并勾选_PLAN(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例", role="tester"))
        self.assertEqual(self.repo.state()["phase"], "impl")

        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertEqual(self.repo.state()["phase"], "review-impl")

        self.assertAccepted(self.repo.run("handoff", "approve", "无硬编码", role="tester"))
        self.assertEqual(self.repo.state()["phase"], "review-test")

        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约", role="dev"))

        st = self.repo.state()
        self.assertEqual(st["phase"], "spec")
        self.assertEqual(st["item"], None)
        self.assertEqual(st["completed_items"], ["W1"])
        self.assertEqual(st["round"], 1)
        self.assertIn("- [x] **W1**", self.repo.read("docs/PLAN.md"))
        self.assertIn("- [ ] **W2**", self.repo.read("docs/PLAN.md"))

    def test_全部完成后停止轮转(self):
        for item in ("W1", "W2"):
            self.repo.run("claim", item, role="tester")
            self.repo.write("tests/%s" % item)
            self.repo.run("handoff", "%s 用例" % item, role="tester")
            self.repo.write("src/%s" % item)
            self.repo.run("handoff", "实现 %s" % item, role="dev")
            self.repo.run("handoff", "approve", "实现没问题", role="tester")
            self.repo.run("handoff", "approve", "测试没问题", role="dev")

        self.assertEqual(self.repo.state()["completed_items"], ["W1", "W2"])

        s = self.repo.run("status", role="tester")
        self.assertAccepted(s)
        self.assertIn("全部完成", s.text)

        r = self.repo.run("handoff", "还想继续", role="tester")
        self.assertRefused(r, "全部完成")


class TestRoleResolution(PairTestCase):
    """bash 版的 P0-2:只认环境变量,GUI 与云端 harness 无法配置。"""

    def test_从_whoami_文件解析角色(self):
        self.repo.write(".pair/whoami", "dev\n")
        r = self.repo.run("status", role=None)
        self.assertAccepted(r)
        self.assertIn("你的角色 : dev", r.text)
        self.assertIn(".pair/whoami", r.text)

    def test_环境变量优先于_whoami(self):
        self.repo.write(".pair/whoami", "dev\n")
        r = self.repo.run("status", role="tester")
        self.assertAccepted(r)
        self.assertIn("你的角色 : tester", r.text)

    def test_从分支名解析角色(self):
        self.repo.git("switch", "-q", "-c", "pair/dev")
        r = self.repo.run("status", role=None)
        self.assertAccepted(r)
        self.assertIn("你的角色 : dev", r.text)

    def test_无法确定角色时停下来求助(self):
        r = self.repo.run("status", role=None)
        self.assertRefused(r, "无法确定你的角色", "告诉人类")

    def test_非法角色值被拒绝(self):
        r = self.repo.run("status", role="architect")
        self.assertRefused(r, "无效")
