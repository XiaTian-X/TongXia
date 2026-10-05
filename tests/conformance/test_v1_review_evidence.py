# -*- coding: utf-8 -*-
"""评审必须带证据。

这里扮演的作弊 agent 是**最难抓的那一种**:它不越界、不改测试、不篡改状态,
红绿全对,流程全走完 —— 它只是敷衍地点头。多 agent 代码评审的实证研究把这个
失败模式叫 false-consensus,而它恰好是这套协议唯一会致命的失效方式。

脚本查不了内容,只能查结构。这些用例断言的就是那道结构门。
"""

from harness import EVIDENCE, LOC, PairTestCase, with_loc


class TestApproveNeedsChecklist(PairTestCase):
    """approve 必须交出 --checked 与 --uncovered。"""

    def test_空手通过被拒绝(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "approve", "看起来不错", role="tester")
        self.assertRefused(r, "检查清单", "--checked", "--uncovered")

    def test_只给一半也被拒绝(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "approve", "没问题",
                          "--checked", "查了 src/W1", role="tester")
        self.assertRefused(r, "--uncovered")

    def test_空字符串不算数(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "approve", "没问题",
                          "--checked", "  ", "--uncovered", "无", role="tester")
        self.assertRefused(r, "--checked")

    def test_两段都给了就放行(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "实现没问题", *EVIDENCE, role="tester"))

    def test_无也是一句明确主张(self):
        """--uncovered "无" 放行 —— 它是被记录在案的主张,不是沉默。"""
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run(
            "handoff", "approve", "实现没问题",
            "--checked", "逐行看过 src/W1,没有针对测试输入的特判",
            "--uncovered", "无", role="tester"))

    def test_检查清单进了提交记录(self):
        """对方只能通过 git 看到它 —— 不落进提交体等于没写。"""
        self.repo.advance_to("review-impl")
        self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE, role="tester")
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertIn("检查了:", body)
        self.assertIn("未覆盖:", body)
        self.assertIn("超长输入", body)


class TestChangesNeedsLocation(PairTestCase):
    """changes 必须指到 `路径:行号`,而且路径要真实存在。"""

    def test_没有位置引用被拒绝(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "changes", "实现有问题", role="tester")
        self.assertRefused(r, "具体到位置", "路径:行号")

    def test_引用不存在的文件被拒绝(self):
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "changes",
                          "src/根本没有这个文件.py:42 有特判", role="tester")
        self.assertRefused(r, "不存在的文件")

    def test_理由里带真实位置就放行(self):
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", with_loc("契约这一条和实现对不上"), role="tester"))

    def test_写在评审文件里也算(self):
        """详细意见写进 docs/reviews/,理由字段只放摘要 —— 这是规则鼓励的写法。"""
        self.repo.advance_to("review-impl")
        self.repo.write("docs/reviews/W1-impl.md",
                        "# 评审\n\n`%s` 这一条与实现不符,应当按契约抛错。\n" % LOC)
        self.assertAccepted(self.repo.run(
            "handoff", "changes", "详见 docs/reviews/W1-impl.md", role="tester"))

    def test_异议路径同样要带位置(self):
        """dev 在 impl 阶段打回测试,也必须指得出位置。"""
        self.repo.advance_to("impl")
        self.repo.write("docs/reviews/W1-dispute.md", "这条测试与契约矛盾。\n")
        r = self.repo.run("handoff", "changes", "测试写错了", role="dev")
        self.assertRefused(r, "路径:行号")

    def test_后缀式引用能对上真实文件(self):
        """写 `CONTRACT.md:3` 而不是全路径,也应该能对上。"""
        self.repo.advance_to("review-impl")
        self.assertAccepted(self.repo.run(
            "handoff", "changes", "CONTRACT.md:3 那一条与实现不符", role="tester"))

    def test_碰巧像位置的数字不算(self):
        """"打回 2 次" 这种不是位置引用,不能蒙混过关。"""
        self.repo.advance_to("review-impl")
        r = self.repo.run("handoff", "changes", "这已经是第 2:3 次了", role="tester")
        self.assertRefused(r)


class TestBriefAsksForDisagreement(PairTestCase):
    """(类名沿用:`docs/improvements.md` 用符号引用指着它。)评审简报要求**两个方向**都拿证据:通过要说查过哪里,打回要指到路径:行号,而为了显得没在点头
    制造一次打回同样失真(ADR-023 把正向要求从"配额"改成"证据")。

    W47:这条原先只断言"裁决必须带证据""先找问题""--checked" —— 那三个字符串在新简报里都还在,
    把"同样失真"那一句删掉它照样绿。现在两个评审阶段都断言到那两句。简报原文在 `pair.py` 里折行,"同样失真"与
    "指到路径:行号"各自落在同一行内,不受折行影响。"""

    def brief(self, phase, role):
        self.repo.advance_to(phase)
        r = self.repo.run("status", role=role)
        self.assertAccepted(r)
        return r.text

    def test_评审实现的简报要求两个方向都拿证据(self):
        out = self.brief("review-impl", "tester")
        self.assertIn("裁决必须带证据", out)
        self.assertIn("指到路径:行号", out)
        self.assertIn("同样失真", out)

    def test_评审测试的简报要求两个方向都拿证据(self):
        out = self.brief("review-test", "dev")
        self.assertIn("指到路径:行号", out)
        self.assertIn("同样失真", out)
