# -*- coding: utf-8 -*-
"""W12:开工前校验的产物按角色分,索引无差异时不再失败。

契约「开工前校验的产物与退出码」。两处缺陷,同一条命令:

- **报告路径对两个角色是同一个文件名。** 第三轮 dev 把 tester 的结论整份
  覆盖过一次(`2ff494f`),靠 git 逐字节还原。
- **索引无差异时必然 exit 1。** `verify-setup` 结尾无条件 `git commit`,
  而它 `add` 的三类东西都没变时 git 拒绝空提交 —— 所有校验都打印了通过,
  退出码却是 1。状态是对的、退出码是错的,而调用方只看退出码。

**判据尽量不碰措辞。** 契约只给了一个字面子串(`没有需要提交的改动`);
其余一律看**行为**:退出码、读的是哪一份文件、文件有没有被覆盖、入没入库、
交接放不放行。凡是断言里出现的中文,要么是契约给的字面,要么是既有用例
早已钉住的既有文案(`过短`、`未提交的代码改动`)。
"""

import unittest

from harness import PairTestCase, VERIFY_OK, setup_report

REVIEWS = "docs/reviews"
OLD = REVIEWS + "/setup-verification.md"


def role_path(role):
    return "%s/setup-verification-%s.md" % (REVIEWS, role)


class SetupReportBase(PairTestCase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def verify(self, role="dev"):
        return self.repo.run(*VERIFY_OK, role=role)

    def warnings(self, result):
        """`verify-setup` 既有的警告出口是 `[警告]`(孤儿清单、ignore_paths
        清单、入口文件缺激活段落都走它)。契约只说"打印一条警告"、没给措辞,
        所以回落那两条用例**比行数,不比字面**:同一个仓库里,回落的那次
        必须比不回落的那次多出至少一条。dev 若换了别的警告出口,打回我。"""
        return result.text.count("[警告]")


class TestReportIsPerRole(SetupReportBase):
    """报告按角色分:`docs/reviews/setup-verification-<角色>.md`。"""

    def test_只有角色文件时照样通过(self):
        """旧的单一路径根本不存在 —— 通过就说明读的是角色文件。"""
        self.repo.write(role_path("dev"), self.REPORT)
        self.assertFalse(self.repo.exists(OLD))
        self.assertAccepted(self.verify("dev"))
        self.assertTrue(self.repo.state()["setup_verified"])

    def test_两个角色各写各的互不覆盖(self):
        """第三轮真实发生过的事:dev 的 `verify-setup` 在后台跑的那两分钟里
        tester 提交了自己的结论,dev 没看见就整份覆盖。按角色分之后,
        两份各自落地、各自入库,谁也碰不到谁。"""
        mine = {"tester": self.REPORT + "\n(这一份是 tester 写的)\n",
                "dev": self.REPORT + "\n(这一份是 dev 写的)\n"}
        for role in ("tester", "dev"):
            self.repo.write(role_path(role), mine[role])
            self.assertAccepted(self.verify(role))
        for role in ("tester", "dev"):
            self.assertEqual(self.repo.read(role_path(role)), mine[role],
                             "%s 的结论被改动过" % role)
        tracked = self.repo.git("ls-files").stdout.decode("utf-8")
        for role in ("tester", "dev"):
            self.assertIn(role_path(role), tracked, "%s 的结论没有入库" % role)

    def test_角色文件在就只读它_不回落也不读并集(self):
        """角色文件优先,缺失才回落。**读并集的话,一个角色可以交一句废话、
        靠另一份把字数与小节名凑满** —— 那等于没审。

        场景:旧位置有一份合格的,自己那份是敷衍的。必须按自己那份判。"""
        self.repo.write(OLD, self.REPORT)
        self.repo.write(role_path("dev"), "看过了没问题\n")
        self.assertRefused(self.verify("dev"), "过短")


class TestFallbackToSharedPath(SetupReportBase):
    """回落到旧的单一路径时不拒绝,但要说出来。"""

    def test_解析不出角色时回落到旧路径并说出来(self):
        """`verify-setup` 是新项目接入后的**第一条**命令,那时 `PAIR_ROLE`
        与 `.pair/whoami` 都可以还没配(脚手架里两者都没有、分支也不叫
        `pair/*`,`role=None` 时角色确实解析不出来)。**别把接入的第一步卡死。**"""
        self.repo.write(role_path("dev"), self.REPORT)
        base = self.verify("dev")
        self.assertAccepted(base)
        self.repo.delete(role_path("dev"))
        self.repo.write(OLD, self.REPORT)
        r = self.repo.run(*VERIFY_OK, role=None)
        self.assertAccepted(r)
        self.assertGreater(
            self.warnings(r), self.warnings(base),
            "解析不出角色、回落到旧路径时没有多出任何警告:\n%s" % r.text)

    def test_角色文件缺失时回落到旧路径并说出来_且不搬迁旧文件(self):
        """存量项目里已经有那份旧文件。角色能解析、但自己的角色文件还没写时,
        回落到旧的单一路径 —— 同样要说出来:它是两个角色共用的旧位置。

        **不做**:不自动搬迁已有的那一份,搬文件是人类的决定。"""
        self.repo.write(role_path("dev"), self.REPORT)
        base = self.verify("dev")
        self.assertAccepted(base)
        self.repo.write(OLD, self.REPORT)
        r = self.verify("tester")                # tester 没有自己的角色文件
        self.assertAccepted(r)
        self.assertGreater(
            self.warnings(r), self.warnings(base),
            "角色文件缺失、回落到旧路径时没有多出任何警告:\n%s" % r.text)
        self.assertEqual(self.repo.read(OLD), self.REPORT, "旧文件被改动了")
        self.assertFalse(self.repo.exists(role_path("tester")),
                         "旧文件被自动搬迁成了角色文件 —— 契约写明不做")


class TestRoleReportNamesAreExempt(PairTestCase):
    """`docs/reviews/` 下的顶层 `.md` 全归评审文件命名检查管,名字对不上
    任何工作项 ID 就拒绝交接。**新的两份结论必须进豁免** —— 不做的话,
    这一项落地当天,第一份新报告一出现在工作区就会把下一次交接卡死,
    而拒绝文案还会叫 agent 去改名或删掉一份不是它写的文件。"""

    def _handoff_with(self, rel):
        self.repo.advance_to("spec")
        self.repo.write("tests/W1")                  # spec 结束时必须 RED
        self.repo.write(rel, "一份契约审查结论。")
        return self.repo.run("handoff", "W1 的失败用例", role="tester")

    def test_tester_的结论文件不挡交接(self):
        self.assertAccepted(self._handoff_with(role_path("tester")))

    def test_dev_的结论文件不挡交接(self):
        self.assertAccepted(self._handoff_with(role_path("dev")))


class TestNoIndexDiffDoesNotFail(SetupReportBase):
    """索引里没有差异时,不提交,也不失败。

    这一组**故意用旧的单一路径**搭场景:这样它们今天红的原因只有一个 ——
    空提交那一步 —— 和报告按角色分那半边无关。
    """

    def test_原样重跑不再失败(self):
        """第四轮实测:结论已经提交过,契约改完想重跑一次确认,必失败。"""
        self.repo.write(OLD, self.REPORT)
        first = self.verify("dev")
        self.assertAccepted(first)
        self.assertNotIn("没有需要提交的改动", first.text,
                         "真的提交了的那一次,不该说没有需要提交的改动")
        head = self.repo.git("rev-parse", "HEAD").stdout
        r = self.verify("dev")
        self.assertAccepted(r)
        self.assertIn("没有需要提交的改动", r.text)
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout, head,
                         "索引没有差异时不该产生提交")

    def test_工作区不干净但索引无差异时照样不失败_且照打那段警告(self):
        """**判据是索引,不是工作区。** `src/` 下一份未跟踪的偷跑实现让工作区
        永远不干净 —— 拿"工作区干净"当判据的实现会照样去提交、照样空提交、
        照样 exit 1,缺陷原样保留,而上面那条用例是绿的。这一条专门打死它。

        跳过提交时,"工作区里有未提交的代码改动"那段警告**照打**:
        它的触发条件和提交与否无关。"""
        self.repo.write(OLD, self.REPORT)
        self.assertAccepted(self.verify("dev"))
        self.repo.write("src/偷跑的实现", "本该由 dev 在 impl 回合写")
        r = self.verify("dev")
        self.assertAccepted(r)
        self.assertIn("没有需要提交的改动", r.text)
        self.assertIn("未提交的代码改动", r.text)
        self.assertIn("偷跑的实现", r.text)
        tracked = self.repo.git("ls-files").stdout.decode("utf-8")
        self.assertNotIn("偷跑的实现", tracked,
                         "verify-setup 不该把角色路径下的改动提交进基线")


if __name__ == "__main__":
    unittest.main()
