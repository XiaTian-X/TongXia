# -*- coding: utf-8 -*-
"""W13:校验与沉淀的有效期。

契约「校验与沉淀的有效期」。两条强制在同一个形状上出错:

- **过期的"做过了"被当成仍然有效。** `setup_verified` 一旦为真就永不复位,
  契约改过之后 `claim` 照样放行,没有任何机制要求任何一方读过新内容。
- **仍然有效的"做过了"被当成没做。** `contract-change-note` 与笔记晋升闸
  只认"这一次交接里新追加的"决策;同一工作项更早回合留下的,到完成时不算。
  第四轮实测发作三次,最后一次挡着整轮收尾。

**判据尽量不碰措辞。** 契约没给拒绝文案的字面,所以"契约变过"那一组只断言
拒绝了、且拒绝理由里有重跑校验的那条命令名 `verify-setup` —— 说"要重跑校验"
而不提命令名是做不到的。其余一律看行为:退出码、阶段、状态文件与 HEAD 动没动。
沉淀那一组断言的都是既有用例早已钉住的既有文案(`没有对应记录`、
`笔记还没被处理`、`第 2 次打回`、`本回合没有留下决策`)。

**状态里那个新键叫什么,契约没定,这里也不碰。** "键缺失"用存量项目升级上来
的真实形状模拟:一份 `setup_verified` 为真、但从没被新代码写过的状态文件。
"""

import json
import unittest

from harness import EVIDENCE, PLAN_TEMPLATE, PairTestCase, VERIFY_OK, setup_report, with_loc
from test_v1_memory import LONG_NOTE

CONTRACT = "docs/CONTRACT.md"
PLAN = "docs/PLAN.md"
STATE = ".pair/state.json"

# 契约读不到时要拒绝 —— 但非 cover 的工作项在契约读不到时**早就**被既有的
# 「契约小节不存在」拒绝了,用它测等于测既有行为。cover 跳过那道检查,
# 所以只有拿 cover 才看得出 W13 这一条在不在。
COVER_PLAN = PLAN_TEMPLATE + """- [ ] **C1** [cover] — 给 W1 补特征测试
  - 验收标准:现状被固化进测试
"""


def role_report(role):
    return "docs/reviews/setup-verification-%s.md" % role


class ValidityBase(PairTestCase):

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def verify(self, role):
        self.repo.write(role_report(role), self.REPORT)
        self.assertAccepted(self.repo.run(*VERIFY_OK, role=role))

    def change_contract(self, extra="**补充** 允许空输入。"):
        """人类改契约并提交。"""
        self.repo.set_plan(self.repo.read(PLAN),
                           contract=self.repo.read(CONTRACT) + "\n%s\n" % extra)

    def claim(self, item="W1"):
        return self.repo.run("claim", item, role="tester")

    def head(self):
        return self.repo.git("rev-parse", "HEAD").stdout

    def state_dirty(self):
        out = self.repo.git("status", "--porcelain", "-z", "--", STATE).stdout
        return bool(out)


class TestContractChangeInvalidatesVerification(ValidityBase):
    """契约变了,之前的校验作废 —— 现场算,按角色,只作用于 `claim`。"""

    def test_契约改过之后不能认领(self):
        """**不写状态**:唯一能发现"契约变了"的时机是 `claim` 的拒绝路径,
        而那是 `die`。拒绝之后 `setup_verified` 仍为真、状态文件没被改写、
        也没有产生提交 —— 塞一个写入者会撞上"状态文件任何未提交改动一律
        判篡改"那条检查。"""
        self.verify("tester")
        self.change_contract()
        head = self.head()
        r = self.claim()
        self.assertRefused(r, "verify-setup")
        st = self.repo.state()
        self.assertEqual(st["phase"], "idle")
        self.assertTrue(st["setup_verified"],
                        "setup_verified 那个键被改写了 —— 契约写明现场算、不写状态")
        self.assertEqual(self.head(), head, "拒绝认领却产生了提交")
        self.assertFalse(self.state_dirty(), "拒绝认领却改写了状态文件")

    def test_重跑校验之后恢复(self):
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        self.verify("tester")
        self.verify("dev")                    # W19 起 claim 看两个角色
        self.assertAccepted(self.claim())

    def test_dev_重跑不替_tester_解锁(self):
        """**按角色各存一份,`claim` 只看执行者自己那一份。** 单值下
        "dev 读过新契约、tester 没读过"时门是开着的,而 tester 正是照契约
        写断言的那一方。"""
        self.verify("tester")
        self.verify("dev")
        self.change_contract()
        self.verify("dev")
        self.assertRefused(self.claim(), "verify-setup")
        self.verify("tester")
        self.assertAccepted(self.claim())

    def test_只有_dev_校验过时_tester_不能认领(self):
        """同一条的另一面:tester 从没通过过校验,dev 的那一次不算它的。"""
        self.verify("dev")
        self.assertRefused(self.claim(), "verify-setup")
        self.verify("tester")
        self.assertAccepted(self.claim())

    def test_人类没提交的契约改动也算_且重跑之后不会锁死(self):
        """**sha 取工作区内容,两端同口径。** 人类在两个工作项之间改了契约
        还没提交,是这个仓库的常态。

        两半各打一种错误实现:
        - 比对端取 HEAD → 前半截放行了,红;
        - 记录端取 HEAD、比对端取工作区 → 重跑校验记下的还是旧的,
          后半截永久拒绝,红。契约说这会"把整轮锁死"。"""
        self.verify("tester")
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 还没提交。\n")
        self.assertRefused(self.claim(), "verify-setup")
        self.verify("tester")                 # 契约改动仍未提交
        self.verify("dev")                    # W19 起 claim 看两个角色
        self.assertTrue(self.repo.git("status", "--porcelain", "--", CONTRACT).stdout,
                        "场景前提:契约改动应当还在工作区里")
        self.assertAccepted(self.claim())

    def test_提交之后同一份内容不必再校验(self):
        """口径是**内容**:同一份内容提交前后算作同一份。"""
        self.verify("tester")
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n**补充** 先改后提交。\n")
        self.verify("tester")
        self.verify("dev")                    # W19 起 claim 看两个角色
        self.repo.git("add", "--", CONTRACT)
        self.repo.git("commit", "-q", "-m", "docs: 人类提交了契约改动")
        self.assertAccepted(self.claim())

    def test_状态里没有这份记录时要求重跑(self):
        """**键缺失算作废。** 存量项目升级上来时,状态里 `setup_verified` 为真,
        但从没有谁记过"校验的是哪一份契约"。放行的话所有存量项目永远绕过
        这条新门,而升级代价只是重跑一次。"""
        st = self.repo.state()
        st["setup_verified"] = True
        self.repo.write(STATE, json.dumps(st, indent=2))
        self.repo.git("add", "--", STATE)
        self.repo.git("commit", "-q", "-m", "chore: 升级前的状态文件")
        self.assertRefused(self.claim(), "verify-setup")
        self.verify("tester")
        self.verify("dev")                    # W19 起 claim 看两个角色
        self.assertAccepted(self.claim())

    def test_契约文件读不到时拒绝(self):
        """**不照抄既有那条"取不到就静默放行"的写法。** 用 cover 工作项:
        它跳过契约小节检查,只有这样才看得出 W13 这一条在不在。"""
        self.verify("tester")
        self.repo.delete(CONTRACT)
        self.repo.set_plan(COVER_PLAN)
        r = self.claim("C1")
        self.assertRefused(r)
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_工作项中途契约变了不挡交接(self):
        """**只作用于 `claim`。** 本轮每一个工作项都要改契约,
        挡在交接上等于每一项都半途停摆。"""
        self.verify("tester")
        self.verify("dev")                    # W19 起 claim 看两个角色
        self.assertAccepted(self.claim())
        self.change_contract()
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例", role="tester"))

    def test_whose_turn_与_status_不停也不写(self):
        """`whose-turn` 不动:它的全部用途是给驱动器一行输出,输出 `stop`
        会让整轮在半途停摆。`status` 可以加提示,但它是只读的。"""
        self.verify("tester")
        self.change_contract()
        head = self.head()
        r = self.repo.run("whose-turn", role="tester")
        self.assertAccepted(r)
        self.assertTrue(r.out.strip().startswith("turn"),
                        "契约变过之后 whose-turn 不该输出 stop:\n%s" % r.out)
        self.assertAccepted(self.repo.run("status", role="tester"))
        self.assertEqual(self.head(), head, "只读命令产生了提交")
        self.assertFalse(self.state_dirty(), "只读命令改写了状态文件")
        self.assertTrue(self.repo.state()["setup_verified"])


class TestGateOffIsUnaffected(PairTestCase):
    """没开 `require_setup_verification` 时,这条门不存在 —— 它是既有门禁的延伸。"""

    def test_没开门禁时契约改过照样认领(self):
        self.repo.set_plan(PLAN_TEMPLATE,
                           contract=self.repo.read(CONTRACT) + "\n**补充** 允许空输入。\n")
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))


class SettledBase(PairTestCase):

    def claim(self):
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))

    def spec(self, decision=None):
        self.repo.write("tests/W1")
        if decision:
            self.repo.append_decision(decision, title="spec 回合就留下的结论")
        self.assertAccepted(self.repo.run("handoff", "W1 的失败用例", role="tester"))

    def impl(self, note=None, decision=None):
        self.repo.write("src/W1")
        if note:
            self.repo.write("docs/notes/W1.md", note)
        if decision:
            self.repo.append_decision(decision, title="impl 回合就沉淀下来的结论")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))

    def approve_impl(self):
        self.assertAccepted(self.repo.run("handoff", "approve", "实现没问题",
                                          *EVIDENCE, role="tester"))

    def done(self):
        return self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")

    def human_changes_contract(self):
        self.repo.set_plan(PLAN_TEMPLATE,
                           contract=self.repo.read(CONTRACT) + "\n**补充** 允许空输入。\n")


class TestSettledByItem(SettledBase):
    """「已沉淀」按工作项算:决策记录里存在 id 等于本工作项的条目 —— 纯 id。"""

    def test_契约变更_决策在_spec_回合留过_完成时放行(self):
        """第四轮第 1 次发作的原样:W9 的 spec 回合带声明改了契约、当场留了决策,
        走到 `DONE` 又被 `contract-change-note` 拦下。"""
        self.claim()
        self.repo.write("tests/W1")
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n新增一句。\n")
        self.repo.append_decision("W1", title="契约这一节改成新的说法")
        self.assertAccepted(self.repo.run(
            "handoff", "用例", "--doc-reason", "契约那一节的措辞会误导实现方",
            "--contract-change", "docs/DECISIONS.md", role="tester"))
        self.impl()
        self.approve_impl()
        r = self.done()
        self.assertAccepted(r)
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_笔记晋升_决策在_impl_回合留过_完成时放行(self):
        """第四轮第 2 次发作的原样:笔记已在上一个 impl 回合沉淀成决策,
        晋升闸在 `approve` 照样拦。"""
        self.claim()
        self.spec()
        self.impl(note=LONG_NOTE, decision="W1")
        self.approve_impl()
        self.assertAccepted(self.done())
        self.assertEqual(self.repo.state()["phase"], "idle")

    def test_认领之前就有的同_id_条目也算(self):
        """**纯 id,不看是不是 `claim` 之后写的。** 契约点名接受这个代价:
        再引入一个"从 claim 起算"的窗口,等于换一个更隐蔽的偏移量判据。"""
        self.repo.append_decision("W1", title="上一个工作项里提前写下的")
        self.repo.git("add", "--", "docs/DECISIONS.md")
        self.repo.git("commit", "-q", "-m", "docs: 人类提交的决策")
        self.claim()
        self.human_changes_contract()
        self.spec()
        self.impl(note=LONG_NOTE)
        self.approve_impl()
        self.assertAccepted(self.done())

    def test_只有别的工作项的决策时_契约变更照样要记录(self):
        """`有` 的判定放宽到一个工作项,不是放宽到"决策记录非空"。"""
        self.claim()
        self.human_changes_contract()
        self.spec(decision="W2")
        self.impl()
        self.approve_impl()
        self.assertRefused(self.done(), "没有对应记录")

    def test_只有别的工作项的决策时_笔记照样要处理(self):
        self.claim()
        self.spec()
        self.impl(note=LONG_NOTE, decision="W2")
        self.approve_impl()
        self.assertRefused(self.done(), "笔记还没被处理")


class TestSameTurnGatesUnchanged(SettledBase):
    """**另外两处用同一套"本回合新追加"的检查一个字都不改** —— 它们要的就是当场。
    这两条今天是绿的,守的是"只改两处"那半句:把"按工作项算"推广到所有用
    `mine` / `new_decision_entries` 的地方,它们会红。"""

    def test_第二次打回_更早回合的决策不算(self):
        self.claim()
        self.spec(decision="W1")
        self.impl()
        self.assertAccepted(self.repo.run("handoff", "changes", with_loc("问题一"),
                                          role="tester"))
        self.assertAccepted(self.repo.run("handoff", "改好了", role="dev"))
        r = self.repo.run("handoff", "changes", with_loc("问题二"), role="tester")
        self.assertRefused(r, "第 2 次打回")

    def test_带声明改契约_更早回合的决策不算当场(self):
        self.claim()
        self.spec(decision="W1")
        self.repo.write("src/W1")
        self.repo.write(CONTRACT, self.repo.read(CONTRACT) + "\n新增一句。\n")
        r = self.repo.run("handoff", "实现 W1", "--doc-reason", "契约措辞会误导",
                          "--contract-change", "docs/DECISIONS.md", role="dev")
        self.assertRefused(r, "本回合没有留下决策")


if __name__ == "__main__":
    unittest.main()
