# -*- coding: utf-8 -*-
"""W9:冻结文件改成带声明才放行。

契约「冻结文件改成带声明才放行」。`PLAN.md` / `CONTRACT.md` **仍留在
`frozen_paths` 里**,配置一个字不改;`handoff` 的冻结拒绝分支开一个口子:
改动落在 `plan_file` 或 `contract_file` 上、且带了 `--contract-change`
时放行,不带照旧拒绝。

**"放行"是跳过写权限边界的全部三道判定**(冻结、越界、`scope`),
不是只跳冻结那一道 —— 只跳一道的话,拒绝理由只是从"冻结"换成"越界"。

**只豁免这两份。** `frozen_paths` 里还有 `.pair`,而 `.pair/enforcer.py`
是本轮的裁判 —— 一个旗标能改判官,这条防护就整个塌了。

**`--contract-change` 与 `--doc-reason` 是两条独立的强制**:前者管"能不能
碰这份文件",后者管"改文档要说为什么"。两份文件都是规范性文档,所以两个都要。
`--basis` 被 `--contract-change` 取代(契约点名),但校验强度取高的那一档 ——
`--contract-change` 同样要指向一个真实存在的路径。
"""

import unittest

from harness import EVIDENCE, PairTestCase

PLAN = "docs/PLAN.md"
CONTRACT = "docs/CONTRACT.md"


class FrozenBase(PairTestCase):

    def setUp(self):
        super().setUp()
        # `install_protocol` 不铺决策记录。不先铺,`--contract-change
        # docs/DECISIONS.md` 会在**路径真实性**那一道就被拒 —— 那条用例
        # 就红得不对了(第一版正是这样,参考实现下报的是"没有指向真实文件
        # 的路径",而不是"没留决策")。
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "人类先放一份决策记录")

    def claim(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.repo.write("tests/W1")          # spec 结束时必须 RED

    def touch_contract(self):
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n新增一句。\n")

    def handoff(self, *extra):
        return self.repo.run("handoff", "改了契约", *extra, role="tester")

    def full(self, *extra):
        """一次合规的契约变更交接要带的东西:理由 + 声明 + 一条决策。"""
        self.repo.append_decision(item="W1", title="契约这一节改成新的说法")
        return self.handoff("--doc-reason", "契约那一节的措辞会误导实现方",
                            "--contract-change", "docs/DECISIONS.md", *extra)


class TestFrozenNeedsDeclaration(FrozenBase):

    def test_不带声明改契约照旧拒绝(self):
        self.claim()
        self.touch_contract()
        self.assertRefused(self.handoff("--doc-reason", "改措辞"),
                           "冻结", CONTRACT)

    def test_带声明改契约放行(self):
        self.claim()
        self.touch_contract()
        self.assertAccepted(self.full())

    def test_带声明改_PLAN_放行(self):
        self.claim()
        self.repo.write(PLAN, self.repo.read(PLAN) + "\n- 备注一句\n")
        self.assertAccepted(self.full())

    def test_声明进提交正文(self):
        self.claim()
        self.touch_contract()
        self.assertAccepted(self.full())
        body = self.repo.git("log", "-1", "--format=%b").stdout.decode("utf-8")
        self.assertIn("docs/DECISIONS.md", body)

    def test_声明要指向真实存在的路径(self):
        """校验强度取高的那一档 —— 和 `--basis` 同一条判据。
        只要求非空的话,它和 `--doc-reason` 效果完全一样。"""
        self.claim()
        self.touch_contract()
        self.repo.append_decision(item="W1", title="契约这一节改成新的说法")
        self.assertRefused(
            self.handoff("--doc-reason", "改措辞",
                         "--contract-change", "因为我觉得更好"),
            CONTRACT)


class TestFlagDoesNotUnlockOtherFrozenPaths(FrozenBase):
    """一个旗标能改判官,这条防护就整个塌了。"""

    def test_旗标不能豁免其他冻结路径(self):
        self.claim()
        self.repo.write(".pair/记事.txt", "我改了裁判旁边的东西\n")
        self.repo.append_decision(item="W1", title="契约这一节改成新的说法")
        self.assertRefused(
            self.handoff("--doc-reason", "顺手",
                         "--contract-change", "docs/DECISIONS.md"),
            "冻结", ".pair/记事.txt")

    def test_旗标不能把别的越界一起带过去(self):
        """豁免按 `plan_file` / `contract_file` 两个**配置键**点名,
        不是"这次交接整体放行"。"""
        self.claim()
        self.touch_contract()
        self.repo.write("src/偷偷改的实现.py", "x = 1\n")
        self.assertRefused(self.full(), "src/偷偷改的实现.py")


class TestDecisionIsMandatory(FrozenBase):
    """带声明的那次交接必须同时在 DECISIONS.md 追加一条。

    **这是一条新检查,不是复用**:既有那条的触发点是 `target == "DONE"`,
    拿 `claim` 时记下的 `contract_sha` 比对 —— 它抓的是"工作项完成时发现
    契约变过",抓不到改动发生的那一刻。
    """

    def test_带声明但没留决策被拒(self):
        self.claim()
        self.touch_contract()
        self.assertRefused(
            self.handoff("--doc-reason", "改措辞",
                         "--contract-change", "docs/DECISIONS.md"),
            # 关键词不能用 "DECISIONS":`--contract-change` 还不存在,
            # argparse 的 `unrecognized arguments: … docs/DECISIONS.md`
            # **回显了这个路径**,拿它当关键词这条现在就是绿的 —— 恒真。
            # 中文 argparse 造不出来。
            "决策")

    def test_留了决策就放行(self):
        self.claim()
        self.touch_contract()
        self.assertAccepted(self.full())


class TestExemptionSkipsAllThreeGates(FrozenBase):
    """"放行"是跳过三道判定,不是只跳冻结那一道。

    `scope` 在类级配置里开:第一版是在用例里改 `.pair/config.json`,
    把 `'"scope": []'` 替换成别的 —— 而 harness 的 `CONFIG` **根本没有
    `scope` 这个键**,那句替换是空操作,`scope` 一直是空的、那一道判定
    从来没被开过。变异「豁免只跳冻结和越界」当时一条都不红,就是这么发现的。

    只跳冻结,下一行就是越界判定 —— 这两份文件不在任何角色的路径里,
    五个阶段全部不在 `allowed` 中,于是拒绝理由只是从"冻结"换成"越界"。
    """

    config = {"scope": ["src", "tests"]}

    def test_只读评审回合带声明也能改契约(self):
        """越界那一道:评审阶段的可写路径只有评审目录与记忆层。"""
        self.repo.advance_to("review-impl")
        self.touch_contract()
        self.repo.append_decision(item="W1", title="评审时发现契约这一节有歧义")
        r = self.repo.run("handoff", "approve", "实现没问题", *EVIDENCE,
                          "--doc-reason", "评审时发现这一节会误导实现方",
                          "--contract-change", "docs/DECISIONS.md",
                          role="tester")
        self.assertAccepted(r)

    def test_范围之外也能改契约(self):
        """`scope` 那一道。契约不在 `src` / `tests` 里,不豁免就会被范围拦下。"""
        self.assertTrue(self.repo.state() is not None)
        self.claim()
        self.touch_contract()
        self.assertAccepted(self.full())


class TestReportShowsContractChanges(FrozenBase):

    def cycle(self, item, contract_change):
        """跑完一个工作项。`contract_change=True` 时在 spec 回合改一次契约。"""
        self.assertAccepted(self.repo.run("claim", item, role="tester"))
        self.repo.write("tests/%s" % item)
        if contract_change:
            self.touch_contract()
            self.repo.append_decision(item=item, title="契约这一节改成新的说法")
            r = self.repo.run("handoff", "用例", "--doc-reason", "措辞会误导",
                              "--contract-change", "docs/DECISIONS.md",
                              role="tester")
        else:
            r = self.repo.run("handoff", "用例", role="tester")
        self.assertAccepted(r)
        self.repo.write("src/%s" % item)
        self.assertAccepted(self.repo.run("handoff", "实现", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "无硬编码",
                                          *EVIDENCE, role="tester"))
        if contract_change:
            # 既有的 `contract-change-note` 在 DONE 还会再拦一次:它要的是
            # **这一次交接里新追加**的条目(`new_decision_entries` 按偏移量
            # 算),而上面那条是在 spec 回合追加、早就进了 HEAD。于是同一次
            # 契约变更要留两条决策。**这是 W9 与既有强制的交互,不是本用例
            # 要钉的规格** —— 所以只在脚手架里满足它,不写成断言;
            # 详见 W9 的笔记。
            self.repo.append_decision(item=item, title="完成时再记一次同一件事")
        self.assertAccepted(self.repo.run("handoff", "approve", "只断言契约",
                                          *EVIDENCE, role="dev"))

    def contract_row(self):
        r = self.repo.run("report", role="tester")
        self.assertAccepted(r)
        rows = [l for l in r.text.split("\n") if "contract-change" in l]
        self.assertEqual(len(rows), 1,
                         "report 里应当恰好有一行契约变更频率。输出:\n%s" % r.text)
        return rows[0]

    def test_report_那一行跟着契约变更走(self):
        """判据:**两次观测之间分母必须不变**,于是那一行只可能被分子推动。

        上一版是"跑两个工作项、断言那一行前后不同" —— 而 `_fmt_rate` 的
        分母是**完成项数**,第二个工作项本身就让那一行变了。把
        `contract_changes` 的自增改成永不发生,那一版照样绿:
        `0% (0/1)` → `0% (0/2)`,**分母替分子演了"变化"**。

        这一版:先完整跑掉 W1(不改契约),此时 `done == 1`;再认领 W2 并
        **只做一次带声明的交接**(W2 不完成),`done` 仍然是 1。
        两次观测的分母逐字相同,那一行还变了,就只能是分子变的。

        不断言措辞,也不钉 `_fmt_rate` 的格式 —— 换成"N 次"这种没有分母的
        写法,这条判据同样成立。
        """
        self.cycle("W1", contract_change=False)
        before = self.contract_row()

        self.assertAccepted(self.repo.run("claim", "W2", role="tester"))
        self.repo.write("tests/W2")
        self.touch_contract()
        self.repo.append_decision(item="W2", title="契约这一节改成新的说法")
        self.assertAccepted(self.repo.run(
            "handoff", "用例", "--doc-reason", "措辞会误导",
            "--contract-change", "docs/DECISIONS.md", role="tester"))
        after = self.contract_row()

        self.assertEqual(
            self.repo.state()["completed_items"], ["W1"],
            "前提:第二次观测时完成项数必须还是 1,否则分母会变、判据失效")
        self.assertNotEqual(
            before.strip(), after.strip(),
            "完成项数没变、只多了一次带声明的交接,report 那一行却没动:\n"
            "  前: %r\n  后: %r" % (before, after))


if __name__ == "__main__":
    unittest.main()
