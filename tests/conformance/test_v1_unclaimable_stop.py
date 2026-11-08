# -*- coding: utf-8 -*-
"""W83:每个待办项都认领不了时,`whose-turn` 停下交给人类。

契约「每个待办项都认领不了时停下」。

- idle 时裁判副本与正本不一致 → `stop`,说明要人类重钉。
- idle 时未完成的工作项每一项都过不了 `claim` 的工作项级检查 → `stop`,
  一行里逐项写 `<ID>:<拒绝理由的头一行>`,项之间用 `;`。只要有一项能认领 → 照旧 `turn`。
- 已完成项不算;工作项进行中两条都不判;idle 归 dev 时同样判。
- 只读、退出码 0、一行、以 `stop ` 开头。

被拦的项全用 PLAN 与契约造(人类的产物),不碰判定代码 —— 那是 dev 的事。
"""

import re
import unittest

from harness import REPO, PAIR_PY, PairTestCase, VERIFY_OK, setup_report

ENFORCER = ".pair/enforcer.py"
MARK = "[待澄清: 部件的单位是什么]"
DOC_BASIS = "已有文档 docs/api.md §3(待核实)"


def section(name, basis="人类定稿", extra=""):
    return ("\n## %s\n\n- 依据: %s\n\n**行为** 规格为空时返回空部件。\n%s"
            % (name, basis, ("\n%s\n" % extra) if extra else ""))


def item(item_id, name, typ="feature", done=False, protect=True):
    text = ("- [%s] **%s** [%s] — 给%s写用例\n  - 验收标准:见契约\n  - 对应契约:`docs/CONTRACT.md` → %s\n"
            % ("x" if done else " ", item_id, typ, name, name))
    if typ == "refactor" and protect:
        text += "  - 保护测试: tests\n"
    return text


# 四种拦法,各自一节契约 + 一个工作项。值是 (小节, 工作项, 理由头一行里该出现的关键词)。
# 关键词取自 claim 拒绝文案的头一行:待澄清那条头一行只说"还有 N 处待澄清的标记",不含标记原文;
# refactor 那条写的是"保护它的测试"。
def marked(item_id, name, done=False):
    return section(name, extra=MARK), item(item_id, name, done=done), "待澄清"


def doc_basis(item_id, name, done=False):
    return section(name, basis=DOC_BASIS), item(item_id, name, done=done), "依据"


def unprotected(item_id, name, done=False):
    return section(name), item(item_id, name, "refactor", done=done, protect=False), "保护"


def bad_type(item_id, name, done=False):
    return section(name), item(item_id, name, "chore", done=done), "非法"


def claimable(item_id, name, done=False):
    return section(name), item(item_id, name, done=done), None


class StopBase(PairTestCase):

    def lay(self, *parts):
        """以人类身份提交 PLAN 与契约。parts 是上面那几个函数的返回值。"""
        self.repo.set_plan("# 项目规划\n\n## 工作项\n\n" + "".join(p[1] for p in parts),
                           "# 接口契约\n" + "".join(p[0] for p in parts))

    def snapshot(self):
        return (self.repo.commit_count(), self.repo.read(".pair/state.json"),
                self.repo.git("status", "--porcelain").stdout)

    def turn(self, role="tester"):
        """跑 whose-turn:退出 0、只读、只有一行。返回那一行。"""
        before = self.snapshot()
        r = self.repo.run("whose-turn", role=role)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.snapshot(), before, "whose-turn 不该提交、不该改状态、不该写文件")
        line = r.out.strip()
        self.assertTrue(line, r)
        self.assertNotIn("\n", line, "whose-turn 只输出一行:%r" % r.out)
        return line

    def assertStop(self, line, *needles):
        self.assertTrue(line.startswith("stop "), line)
        for n in needles:
            self.assertIn(n, line)
        self.assertNotIn("拒绝认领", line, "理由的头一行要去掉「拒绝认领 —— 」前缀")


class TestEachRefusalStops(StopBase):
    """唯一的待办项被认领闸拦住 → stop,点名工作项与理由。"""

    def check(self, make):
        part = make("W1", "部件构造")
        self.lay(part)
        self.assertStop(self.turn(), "W1", part[2])

    def test_待澄清标记(self):
        self.check(marked)

    def test_依据不可断言(self):
        self.check(doc_basis)

    def test_refactor_没声明保护测试(self):
        self.check(unprotected)

    def test_类型非法(self):
        self.check(bad_type)

    def test_对照_唯一的待办项能认领时照旧轮到_tester(self):
        self.lay(claimable("W1", "部件构造"))
        self.assertEqual(self.turn(), "turn tester")

    def test_停下时那一项确实认领不了(self):
        """对照:用例造的确实是认领闸会拦的东西,不是 whose-turn 自己的另一份判定。"""
        self.lay(marked("W1", "部件构造"))
        self.assertNotEqual(self.repo.run("claim", "W1", role="tester").code, 0)


class TestSomeClaimable(StopBase):

    def test_一项被拦_一项能认领_照旧轮到_tester(self):
        self.lay(marked("W1", "部件构造"), claimable("W2", "部件拆卸"))
        self.assertEqual(self.turn(), "turn tester")

    def test_能认领的那项排在前面也一样(self):
        self.lay(claimable("W1", "部件构造"), unprotected("W2", "部件拆卸"))
        self.assertEqual(self.turn(), "turn tester")

    def test_已完成项被拦_未完成项能认领_照旧轮到_tester(self):
        self.lay(marked("W1", "部件构造", done=True), claimable("W2", "部件拆卸"))
        self.assertEqual(self.turn(), "turn tester")

    def test_已完成项能认领_未完成项被拦_停下(self):
        """已完成项不算:能认领的只有一个已完成的,等于没有。"""
        self.lay(claimable("W1", "部件构造", done=True), marked("W2", "部件拆卸"))
        self.assertStop(self.turn(), "W2", "待澄清")

    def test_cover_项指向不存在的小节_照旧轮到_tester(self):
        """cover 不查契约小节 —— claim 放行,whose-turn 也不该停。"""
        self.repo.set_plan(
            "# 项目规划\n\n## 工作项\n\n"
            "- [ ] **C1** [cover] — 给老代码补特征测试\n  - 验收标准:见笔记\n"
            "  - 对应契约:`docs/CONTRACT.md` → 根本没有这一节\n",
            "# 接口契约\n" + section("部件构造"))
        self.assertEqual(self.turn(), "turn tester")

    def test_两项都被拦_两个_ID_在同一行(self):
        self.lay(marked("W1", "部件构造"), unprotected("W2", "部件拆卸"))
        line = self.turn()
        self.assertStop(line, "W1", "W2", "待澄清", "保护", ";")

    def test_三项都被拦_每一项都点名(self):
        self.lay(doc_basis("W1", "部件构造"), bad_type("W2", "部件拆卸"),
                 marked("W3", "部件清点"))
        self.assertStop(self.turn(), "W1", "W2", "W3", "依据", "非法", "待澄清")


class TestJudgeCopy(StopBase):
    """裁判副本不一致时每一次认领都会被拒,而副本是冻结文件 —— 只有人类能重钉。"""

    def pin(self, extra=""):
        self.repo.write(ENFORCER, self.repo.read(PAIR_PY) + extra)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "chore: 钉住裁判副本")

    def test_idle_时副本不一致_停下_要人类重钉(self):
        self.pin("\n# 副本多了一行注释\n")
        self.assertStop(self.turn(), "重钉", "人类")

    def test_对照_副本一致时照旧轮到_tester(self):
        self.pin()
        self.assertEqual(self.turn(), "turn tester")

    def test_对照_副本不一致时认领确实被拒(self):
        self.pin("\n# 副本多了一行注释\n")
        self.assertNotEqual(self.repo.run("claim", "W1", role="tester").code, 0)

    def test_进行中副本不一致_照旧轮到当前阶段的归属(self):
        """dev 正在改正本时副本不一致是常态 —— 进行中判它会让每个 impl 回合都停。"""
        self.pin()
        self.repo.advance_to("spec")
        self.repo.write(PAIR_PY, self.repo.read(PAIR_PY) + "\n# 本回合 dev 改过 pair.py\n")
        self.assertEqual(self.turn(), "turn tester")


class TestInProgress(StopBase):

    def test_进行中其余项和当前项都被拦_照旧轮到当前阶段的归属(self):
        """把进行中的那一项也弄成被拦,才分得开"进行中也判"。"""
        self.repo.advance_to("spec")
        self.lay(marked("W1", "W1"), unprotected("W2", "W2"))
        self.assertEqual(self.turn(), "turn tester")

    def test_进行中到了_impl_照旧轮到_dev(self):
        self.repo.advance_to("impl")
        self.lay(marked("W1", "W1"), marked("W2", "W2"))
        self.assertEqual(self.turn(role="dev"), "turn dev")


class TestIdleOwnedByDev(StopBase):
    """dev 重跑校验解不开认领闸 —— 归属是 dev 时也要停,不能让 dev 白跑一回合。"""

    config = {"require_setup_verification": True}

    def verify(self, role):
        self.repo.write("docs/reviews/setup-verification-%s.md" % role, setup_report("W1", "W2"))
        r = self.repo.run(*VERIFY_OK, role=role)
        self.assertEqual(r.code, 0, r)

    def only_refactor(self, protect):
        """只改 PLAN 不改契约:tester 那一份校验仍作数,dev 那一份从没跑过。"""
        self.repo.set_plan(
            "# 项目规划\n\n## 工作项\n\n" + item("W1", "W1", "refactor", protect=protect))

    def test_对照_能认领时轮到_dev(self):
        self.verify("tester")
        self.only_refactor(protect=True)
        self.assertEqual(self.turn(), "turn dev")

    def test_所有项被拦时停下_不是轮到_dev(self):
        self.verify("tester")
        self.only_refactor(protect=False)
        self.assertStop(self.turn(), "W1", "保护")


class TestExistingStopsComeFirst(StopBase):
    """判在现有四种 stop 之后:没通过开工前校验时,说的仍是那一条。"""

    config = {"require_setup_verification": True}

    def test_尚未通过校验且所有项被拦_仍是校验那一条(self):
        self.lay(marked("W1", "部件构造"))
        line = self.turn()
        self.assertStop(line, "verify-setup")
        self.assertNotIn("W1", line)


class TestCommandReference(unittest.TestCase):
    """驱动器的作者读的是 command-reference §6.6 —— 新的两种 stop 理由要写进去。"""

    def section_66(self):
        doc = (REPO / "docs" / "command-reference.md").read_text(encoding="utf-8")
        m = re.search(r"^## 6\.6 .*?(?=^## )", doc, re.S | re.M)
        self.assertIsNotNone(m, "command-reference 里找不到 §6.6")
        return m.group(0)

    def test_写了认领不了时停下(self):
        self.assertIn("认领", self.section_66())

    def test_写了副本不一致要重钉(self):
        self.assertIn("重钉", self.section_66())
