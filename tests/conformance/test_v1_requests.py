# -*- coding: utf-8 -*-
"""W65:代办通道 —— `request` / `fulfill` / `decline`。

契约「代办通道」。主场景:dev 在 impl 被 `tests/` 里的一个值挡住,`request` 发给 tester,带着开着的代办异议 —— 不计数;
tester 改了、`fulfill`,GREEN 交接进 impl。被请求方 `decline` 一条被异议带过的代办,计数补加 1。

harness 的布局:tester 拥有 `tests`,dev 拥有 `src`;`docs/CONTRACT.md` 等在冻结路径;`lib/` 谁都不拥有(孤儿)。
"""

import json
import re

from harness import EVIDENCE, PairTestCase, with_loc

WHAT = "把 tests/W1 里的期望值从 41 改成 42(契约「W1」写的是 42)"
WHY = "这个文件在 tester 的路径,我改不了"


class RequestBase(PairTestCase):

    def request(self, *paths, role="dev", what=WHAT, why=WHY):
        args = ["request"]
        for p in paths:
            args += ["--path", p]
        args += [what, "--reason", why]
        return self.repo.run(*args, role=role)

    def head_body(self):
        return self.repo.git("log", "-1", "--format=%B").stdout.decode("utf-8")

    def head_files(self):
        return self.repo.git_paths("show", "--name-only", "--format=", "-z", "HEAD")

    def head_sha(self):
        return self.repo.git("rev-parse", "HEAD").stdout.decode().strip()

    def requests(self):
        return self.repo.state().get("requests") or []

    def turn(self):
        return self.repo.run("whose-turn", role="tester").out.split("\n", 1)[0].strip()

    def dispute(self, reason="测试的期望值与契约矛盾"):
        self.repo.write_dispute()
        return self.repo.run("handoff", "changes", with_loc(reason), role="dev")

    def to_impl_with_impl_written(self):
        """dev 在 impl、实现已写(所以 tester 改完测试之后整体是绿的)。"""
        self.repo.advance_to("impl")
        self.repo.write("src/W1")

    def human_set_state(self, **kw):
        st = self.repo.state()
        st.update(kw)
        (self.repo.dir / ".pair" / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        self.repo.git("add", ".pair/state.json")
        self.repo.git("commit", "-q", "-m", "chore: 人类直接改状态(搭场景)")


class TestRequestShape(RequestBase):

    def test_request_不改阶段_归属与计数_记进状态(self):
        self.repo.advance_to("impl")
        base = self.head_sha()
        before = self.repo.state()["changes_count"]
        self.assertAccepted(self.request("tests/W1"))
        st = self.repo.state()
        self.assertEqual(st["phase"], "impl")
        self.assertEqual(self.turn(), "turn dev")
        self.assertEqual(st["changes_count"], before)
        self.assertEqual(len(self.requests()), 1)
        r = self.requests()[0]
        self.assertEqual((r["id"], r["by"], r["to"], r["paths"], r["status"], r["carried"], r["base"], r["item"]),
                         ("R1", "dev", "tester", ["tests/W1"], "open", False, base, "W1"))

    def test_只提交状态文件_提交信息与正文(self):
        self.repo.advance_to("impl")
        self.repo.write("src/W1", "写到一半的实现")
        self.assertAccepted(self.request("tests/W1"))
        self.assertTrue(self.repo.head_subject().startswith("chore(pair): 代办 R1"), self.repo.head_subject())
        self.assertEqual(self.head_files(), {".pair/state.json"})
        body = self.head_body()
        for needle in (WHAT, WHY, "tests/W1"):
            self.assertIn(needle, body)
        self.assertEqual(self.repo.read("src/W1"), "写到一半的实现", "工作区里没提交的改动原样留着")
        self.assertIn("src/W1", self.repo.git_paths("ls-files", "--others", "-z"))

    def test_编号在工作项内递增(self):
        self.repo.advance_to("impl")
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.request("tests/W2", what="第二件事"))
        self.assertEqual([r["id"] for r in self.requests()], ["R1", "R2"])

    def test_tester_在_spec_发给_dev(self):
        self.repo.advance_to("spec")
        self.assertAccepted(self.request("src/W1", role="tester", what="请在 src/W1 里导出一个空的占位", why="那是实现路径"))
        r = self.requests()[0]
        self.assertEqual((r["by"], r["to"]), ("tester", "dev"))


class TestRequestRefused(RequestBase):

    def test_路径归自己时拒绝(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("src/W1"))
        self.assertEqual(self.requests(), [])

    def test_孤儿路径拒绝_交人类(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("lib/helper"), "人类")

    def test_冻结路径拒绝_交人类(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("docs/CONTRACT.md"), "人类")

    def test_评审阶段拒绝(self):
        self.repo.advance_to("review-impl")
        self.assertRefused(self.request("src/W1", role="tester", what="改一下", why="评审只读"))

    def test_idle_拒绝(self):
        self.assertRefused(self.request("tests/W1"))

    def test_不是自己的回合拒绝(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("src/W1", role="tester", what="改一下", why="不是我的回合"))

    def test_内容或理由为空拒绝(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("tests/W1", what=" "))
        self.assertRefused(self.request("tests/W1", why=" "))
        self.assertEqual(self.requests(), [])

    def test_先查状态篡改(self):
        self.repo.advance_to("impl")
        self.repo.tamper_state(changes_count=0)
        self.assertRefused(self.request("tests/W1"))
        self.assertEqual(self.requests(), [])


class TestFrozenPathOwnedByOther(RequestBase):
    """冻结路径同时落在对方 `roles` 里:对方在写权限边界上照样改不了它 —— 要交人类,不能收成一条代办。
    (`docs/CONTRACT.md` 在默认配置里同时是孤儿,只靠孤儿那一支也会被拒;这里让它归 tester,冻结判断才是唯一拦它的。)"""

    config = {"roles": {"tester": ["tests", "docs"], "dev": ["src"]}}

    def test_冻结且归对方的路径被拒_交人类(self):
        self.repo.advance_to("impl")
        self.assertRefused(self.request("docs/CONTRACT.md"), "人类")
        self.assertEqual(self.requests(), [])

    def test_对照组_归对方且不冻结的照常放行(self):
        self.repo.advance_to("impl")
        self.assertAccepted(self.request("docs/guide.md", what="补一句说明", why="docs 归 tester"))


class TestCarriedDispute(RequestBase):

    def test_带着开着的代办异议_不计数_代办标为被带过_正文列出(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        before = self.repo.state()["changes_count"]
        self.assertAccepted(self.dispute())
        self.assertEqual(self.repo.state()["phase"], "spec")
        self.assertEqual(self.repo.state()["changes_count"], before)
        self.assertTrue(self.requests()[0]["carried"])
        self.assertIn("R1", self.head_body())

    def test_对照组_没有代办的异议照旧计数(self):
        self.to_impl_with_impl_written()
        before = self.repo.state()["changes_count"]
        self.assertAccepted(self.dispute())
        self.assertEqual(self.repo.state()["changes_count"], before + 1)

    def test_异议文件照旧必须写(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        r = self.repo.run("handoff", "changes", with_loc("测试与契约矛盾"), role="dev")
        self.assertRefused(r)
        self.assertEqual(self.repo.state()["phase"], "impl")


class TestFulfill(RequestBase):

    def setUp(self):
        super().setUp()
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.dispute())             # 进 spec,轮到 tester

    def test_请求的路径没有改动被拒(self):
        self.assertRefused(self.repo.run("fulfill", "R1", "改好了", role="tester"))
        self.assertEqual(self.requests()[0]["status"], "open")

    def test_改了之后_fulfill_只提交状态文件(self):
        self.repo.write("tests/W1", "期望值 42")
        self.assertAccepted(self.repo.run("fulfill", "R1", "按代办改成 42", role="tester"))
        self.assertEqual(self.requests()[0]["status"], "fulfilled")
        self.assertEqual(self.head_files(), {".pair/state.json"})
        self.assertEqual(self.repo.read("tests/W1"), "期望值 42", "fulfill 是记账,改动留在工作区由交接提交")

    def test_fulfill_之后_GREEN_交接进_impl(self):
        """上一次打回来自 impl,不是 review-test —— W17 捷径不成立。"""
        self.repo.write("tests/W1", "期望值 42")
        self.assertAccepted(self.repo.run("fulfill", "R1", "按代办改成 42", role="tester"))
        self.assertAccepted(self.repo.run("handoff", "按代办修正 W1", role="tester"))
        self.assertEqual(self.repo.state()["phase"], "impl")

    def test_发给自己的代办开着时交接被拒(self):
        self.repo.write("tests/W1", "期望值 42")
        r = self.repo.run("handoff", "修正 W1", role="tester")
        self.assertRefused(r, "R1")
        self.assertEqual(self.repo.state()["phase"], "spec")


class TestOwnership(RequestBase):
    """在发起方**自己的回合**里试 fulfill / decline:只靠"不是你的回合"拦住的实现,在这里放行。"""

    def setUp(self):
        super().setUp()
        self.repo.advance_to("impl")
        self.assertAccepted(self.request("tests/W1"))
        self.repo.write("tests/W1", "dev 在工作区里动了它(交接时会被边界拦,这里只看 fulfill)")

    def test_发起方_fulfill_被拒(self):
        self.assertRefused(self.repo.run("fulfill", "R1", "我自己办了", role="dev"))
        self.assertEqual(self.requests()[0]["status"], "open")

    def test_被请求方不在自己的回合也被拒(self):
        """现在是 dev 的 impl 回合:tester 不能抢先 fulfill。"""
        self.assertRefused(self.repo.run("fulfill", "R1", "抢先办了", role="tester"))
        self.assertEqual(self.requests()[0]["status"], "open")

    def test_发起方_decline_被拒(self):
        self.assertRefused(self.repo.run("decline", "R1", "我自己撤回", role="dev"))
        self.assertEqual(self.requests()[0]["status"], "open")


class TestDecline(RequestBase):

    def test_被带过的_decline_补计一次(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.dispute())
        before = self.repo.state()["changes_count"]
        self.assertAccepted(self.repo.run("decline", "R1", "期望值 41 是对的,契约写的是 41", role="tester"))
        self.assertEqual(self.requests()[0]["status"], "declined")
        self.assertEqual(self.repo.state()["changes_count"], before + 1)
        self.assertTrue(self.repo.head_subject().startswith("chore(pair): 拒绝代办 R1"), self.repo.head_subject())
        self.assertEqual(self.head_files(), {".pair/state.json"})

    def test_没被带过的_decline_不计数(self):
        """dev 发了代办又正常交接(没异议):tester 在评审里只能 decline,不该因此计数。"""
        self.repo.advance_to("impl")
        self.assertAccepted(self.request("tests/W1"))
        self.repo.write("src/W1")
        self.assertAccepted(self.repo.run("handoff", "实现 W1", role="dev"))
        before = self.repo.state()["changes_count"]
        self.assertAccepted(self.repo.run("decline", "R1", "评审回合改不了文件", role="tester"))
        self.assertEqual(self.repo.state()["changes_count"], before)

    def test_理由为空被拒(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.dispute())
        self.assertRefused(self.repo.run("decline", "R1", " ", role="tester"))
        self.assertEqual(self.requests()[0]["status"], "open")

    def decline_into_deadlock(self):
        self.repo.advance_to("impl")
        self.human_set_state(changes_count=2)
        self.repo.write("src/W1")
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.dispute())
        self.assertEqual(self.repo.state()["changes_count"], 2, "前提:带着代办的异议没计数")
        return self.repo.run("decline", "R1", "契约写的就是 41", role="tester")

    def test_补计撞上死锁闸_report_既数死锁也数拒绝(self):
        """W65 review-impl 打回过:撞闸那一次的主题若不是死锁闸原样,report 数不到死锁;主题原样之后,拒绝要从正文认。"""
        self.decline_into_deadlock()
        out = self.repo.run("report", role="tester").out
        deadlock = [l for l in out.splitlines() if "死锁工作项占比" in l]
        declined = [l for l in out.splitlines() if "被拒" in l]
        self.assertTrue(deadlock and "(1/1)" in deadlock[0], out)
        self.assertTrue(declined and "(1/1)" in declined[0], out)

    def test_补计到上限触发死锁闸(self):
        r = self.decline_into_deadlock()
        self.assertRefused(r, "人类")
        st = self.repo.state()
        self.assertEqual(st["changes_count"], 3)
        self.assertTrue(st["deadlock_hits"], "死锁闸要留痕")
        self.assertEqual(self.repo.run("whose-turn", role="tester").out.split()[0], "stop")


class TestLifecycle(RequestBase):

    def test_完成时有开着的代办被拒(self):
        """正常路径到不了这一格(发给谁,谁交接前就得处理);用人类直接改的状态搭出来 —— 这是兜底的那道检查。"""
        self.repo.advance_to("review-test")
        self.human_set_state(requests=[{
            "id": "R1", "item": "W1", "by": "dev", "to": "tester", "paths": ["tests/W1"], "what": WHAT,
            "reason": WHY, "base": self.head_sha(), "status": "open", "carried": False}])
        r = self.repo.run("handoff", "approve", "测试没问题", *EVIDENCE, role="dev")
        self.assertRefused(r, "R1")
        self.assertEqual(self.repo.state()["phase"], "review-test")

    def test_认领时清空(self):
        self.human_set_state(requests=[{
            "id": "R1", "item": "W0", "by": "dev", "to": "tester", "paths": ["tests/W0"], "what": WHAT,
            "reason": WHY, "base": self.head_sha(), "status": "declined", "carried": False}])
        self.assertAccepted(self.repo.run("claim", "W1", role="tester"))
        self.assertEqual(self.requests(), [])


class TestStatusAndReport(RequestBase):

    def test_status_列出发给自己还开着的代办(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.dispute())
        mine = self.repo.run("status", role="tester")
        self.assertIn("R1", mine.out)
        self.assertIn(WHAT, mine.out)
        theirs = self.repo.run("status", role="dev")
        self.assertNotIn(WHAT, theirs.out, "不是发给 dev 的,dev 的简报里不列")

    def test_report_代办次数与被拒率(self):
        self.to_impl_with_impl_written()
        self.assertAccepted(self.request("tests/W1"))
        self.assertAccepted(self.request("tests/W2", what="第二件事"))
        self.assertAccepted(self.dispute())
        self.repo.write("tests/W1", "期望值 42")
        self.assertAccepted(self.repo.run("fulfill", "R1", "改成 42", role="tester"))
        self.assertAccepted(self.repo.run("decline", "R2", "W2 不归本项", role="tester"))
        out = self.repo.run("report", role="tester").out
        count = [l for l in out.splitlines() if "代办" in l and "被拒" not in l]
        rate = [l for l in out.splitlines() if "被拒" in l]
        self.assertTrue(count and re.search(r"(?<![\d/])2(?![\d/%])", count[0]), out)
        self.assertTrue(rate and "1/2" in rate[0], out)


if __name__ == "__main__":
    import unittest
    unittest.main()
