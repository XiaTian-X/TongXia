# -*- coding: utf-8 -*-
"""W69:`discuss_limit` 与 `report` 的讨论频次(P0-5 的 D4)。

契约「讨论额度与频次」。

- 额度:真走 `discuss` / `resume`(同 W67 的写法:发言 = 往提案末尾追加一段);
- `report` 的三行:以人类身份直接造空提交 —— 主题与正文第一行照协议自己写的格式 —— 再数。契约说三行"都按协议自己写的提交识别",
  这样造正好钉住识别口径,也不必真走五个工作项来凑 `MIN_SAMPLE`。
"""

import re

from harness import EVIDENCE, VERIFY_OK, PairRepo, PairTestCase, setup_report

PROPOSAL = "docs/proposals/方向.md"


class QuotaBase(PairTestCase):

    config = {"proposal_paths": ["docs/proposals"]}

    def say(self, text):
        old = self.repo.read(PROPOSAL) if self.repo.exists(PROPOSAL) else "# 方向\n"
        self.repo.write(PROPOSAL, old + "\n" + text + "\n")

    def open(self, role="tester", why="先对齐方向"):
        self.say("## %s 发起\n\n%s" % (role, why))
        return self.repo.run("discuss", "--proposal", PROPOSAL, why, role=role)

    def round_trip(self, opener="tester", other="dev"):
        """进一次 discuss 并恢复:发起方开、对方追加后直接 resume。"""
        self.assertAccepted(self.open(role=opener))
        self.say("## %s\n\n同意。" % other)
        self.assertAccepted(self.repo.run("resume", "维持原意", role=other))

    def turn(self):
        return self.repo.run("whose-turn", role="tester").out.split("\n", 1)[0].strip()


class TestLimitTwo(QuotaBase):

    config = {"proposal_paths": ["docs/proposals"], "discuss_limit": 2}

    def test_能进两次_第三次被拒_文案指向人类与_discuss_limit(self):
        self.repo.advance_to("spec")
        self.round_trip()
        self.round_trip()
        r = self.open()
        self.assertRefused(r, "人类", "discuss_limit")
        self.assertEqual(self.repo.state()["phase"], "spec")

    def test_撞上额度只拒绝这一次_不停轮转(self):
        self.repo.advance_to("spec")
        self.round_trip()
        self.round_trip()
        before = self.repo.read(".pair/state.json")
        self.assertRefused(self.open())
        self.assertEqual(self.turn(), "turn tester", "撞额度不停轮转")
        self.assertEqual(self.repo.read(".pair/state.json"), before, "被拒不改状态")


class TestDefaultLimit(QuotaBase):

    def test_默认额度是_1_第二次被拒(self):
        self.repo.advance_to("spec")
        self.round_trip()
        self.assertRefused(self.open(), "人类", "discuss_limit")

    def test_一个工作项的额度不影响下一个(self):
        self.repo.advance_to("spec")
        self.round_trip()
        self.repo.write("tests/W1")
        self.assertAccepted(self.repo.run("handoff", "写了 W1 的失败用例", role="tester"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        self.assertAccepted(self.repo.run("handoff", "approve", "查过无硬编码", *EVIDENCE, role="tester"))
        self.assertAccepted(self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev"))
        self.assertAccepted(self.repo.run("claim", "W2", role="tester"))
        self.assertAccepted(self.open())


class TestLimitZero(QuotaBase):

    config = {"proposal_paths": ["docs/proposals"], "discuss_limit": 0}

    def test_额度为_0_第一次就被拒(self):
        self.repo.advance_to("spec")
        self.assertRefused(self.open(), "discuss_limit")
        self.assertEqual(self.repo.state()["phase"], "spec")


class TestVerifySetup(PairTestCase):

    def verify(self, limit):
        self.repo.cleanup()
        self.repo = PairRepo({"proposal_paths": ["docs/proposals"], "discuss_limit": limit})
        self.addCleanup(self.repo.cleanup)
        self.repo.write("docs/reviews/setup-verification-tester.md", setup_report("W1", "W2"))
        return self.repo.run(*VERIFY_OK)

    def test_不是非负整数判失败(self):
        for bad in (-1, "2", True, 1.5):
            self.assertRefused(self.verify(bad), "discuss_limit")

    def test_对照组_0_与_3_通过(self):
        for ok in (0, 3):
            self.assertAccepted(self.verify(ok))


class TestStatusShowsRemaining(QuotaBase):

    def remaining(self):
        out = self.repo.run("status", role="tester").out
        m = re.search(r"讨论额度[^\n]*?还剩\s*(\d+)\s*次", out)
        return int(m.group(1)) if m else None

    def test_显示剩余额度_进过一次之后少_1(self):
        self.repo.advance_to("spec")
        self.assertEqual(self.remaining(), 1)
        self.round_trip()
        self.assertEqual(self.remaining(), 0)


class TestStatusWithoutProposals(PairTestCase):

    def test_没配提案目录时不显示额度(self):
        self.repo.advance_to("spec")
        self.assertNotIn("讨论额度", self.repo.run("status", role="tester").out)


class Rows(dict):
    """缺哪一行就让用例失败(不是 KeyError 出错)。"""

    def __missing__(self, key):
        raise AssertionError("report 里没有「%s」这一行:%s" % (key, dict(self)))


class TestReport(PairTestCase):
    """以人类身份造空提交:主题与正文第一行照协议自己写的格式。"""

    def commit(self, subject, body=""):
        args = ["commit", "-q", "--allow-empty", "-m", subject]
        if body:
            args += ["-m", body]
        self.repo.git(*args)

    def claims(self, n, start=1):
        for i in range(start, start + n):
            self.commit("chore(pair): 认领工作项 W%d [feature]" % i)

    def opened(self, n):
        for i in range(n):
            self.commit("discuss: 方向问题 %d" % i, "discuss=open role=tester item=W1 挂起于 spec\n提案: %s" % PROPOSAL)

    def noise(self):
        """讨论回合与恢复:主题也以 discuss 开头,但不算进"讨论"。"""
        self.commit("discuss: 我的看法", "discuss=reply role=dev item=W1\n提案: %s" % PROPOSAL)
        self.commit("discuss(resume): 维持原意", "discuss=resume role=dev item=W1 恢复到 spec\n结论: 维持原意")
        self.commit("discuss: 主题像讨论,正文第一行不是", "role=tester phase=spec -> impl item=W1 type=feature")

    def rows(self, *extra):
        out = self.repo.run("report", *extra, role="tester").out
        found = Rows()
        for line in out.splitlines():
            m = re.match(r"^\s*(讨论 / 认领|讨论|人类批准的提案)\s{2,}(.*?)\s{2,}(\S.*)?$", line)
            if m:
                found[m.group(1)] = (m.group(2).strip(), (m.group(3) or "").strip())
        return found

    def test_两个工作项各讨论一次(self):
        self.claims(2)
        self.opened(2)
        self.noise()
        r = self.rows()
        self.assertEqual(r["讨论"][0], "2", r)
        self.assertEqual(r["讨论 / 认领"][0], "2 / 2", r)
        self.assertNotIn("偏高", r["讨论 / 认领"][1], "样本不足只给数")

    def test_认领满样本且从未讨论(self):
        self.claims(5)
        self.noise()
        self.assertIn("从未讨论", self.rows()["讨论 / 认领"][1])

    def test_认领不满样本时不判从未讨论(self):
        self.claims(4)
        self.assertNotIn("从未讨论", self.rows()["讨论 / 认领"][1])

    def test_讨论过半标偏高(self):
        self.claims(5)
        self.opened(3)
        self.assertIn("偏高", self.rows()["讨论 / 认领"][1])

    def test_对照组_恰好一半不算偏高(self):
        self.claims(6)
        self.opened(3)
        verdict = self.rows()["讨论 / 认领"][1]
        self.assertNotIn("偏高", verdict)
        self.assertNotIn("从未讨论", verdict)

    def test_人类批准的提案计数(self):
        self.commit("chore(pair): 人类批准提案 %s" % PROPOSAL, "签字: tester、dev")
        self.commit("chore(pair): 人类批准提案 docs/proposals/另一份.md", "签字: tester、dev")
        self.commit("chore: 人类批准提案的说明(不是协议的提交)")
        self.assertEqual(self.rows()["人类批准的提案"][0], "2")

    def test_since_只数区间里的(self):
        self.claims(1)
        self.opened(1)
        self.commit("chore(pair): 人类批准提案 %s" % PROPOSAL)
        since = self.repo.git("rev-parse", "HEAD").stdout.decode().strip()
        self.claims(1, start=2)
        self.opened(1)
        r = self.rows("--since", since)
        self.assertEqual(r["讨论"][0], "1", r)
        self.assertEqual(r["讨论 / 认领"][0], "1 / 1", r)
        self.assertEqual(r["人类批准的提案"][0], "0", r)


if __name__ == "__main__":
    import unittest
    unittest.main()
