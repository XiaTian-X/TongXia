# -*- coding: utf-8 -*-
"""路径归属的可见性(W4)。

边界有两个缺口,都只在**第 N 个回合**突然发作:

- **孤儿** —— 不属于任何角色、也没被冻结的文件。两个 agent 都改不了,
  而这件事在开工时没有任何地方说过。
- **`ignore_paths`** —— 完全不受边界保护(它的 `continue` 落在角色与阶段
  判断之前),这是它的用途,但"哪些文件已经不受保护"从没摆给人看过。

前两轮三次卡顿全出自前者,**没有一次是开工前发现的**。所以这一组守两个
时机:开工前把缺口摆出来,以及真正撞上时说清楚 —— 后者尤其要紧,
因为原来的拒绝文案是"请撤销这些改动后重试",而撞上的往往是人类刚改的东西,
agent 照做就会撤销掉不是它写的。
"""

import re
import unittest

from harness import PairTestCase, setup_report


class TestOrphanListing(PairTestCase):
    """开工前的孤儿清单。"""

    config = {"require_setup_verification": True}
    REPORT = setup_report("W1", "W2")

    def _verify(self):
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        return self.repo.run("verify-setup", "--drafter", "other", role="dev")

    def _commit(self, msg="人类提交"):
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", msg)

    def test_开工前把孤儿列出来(self):
        """默认装出来的仓库就有孤儿 —— `init` 铺的入口文件不属于任何角色。
        这不是构造出来的边角场景,是**每个新项目开箱即有**的状态。"""
        r = self._verify()
        self.assertIn("孤儿", r.text)
        self.assertIn("AGENTS.md", r.text)
        self.assertIn(".gitignore", r.text)

    def test_孤儿只是警告不阻断(self):
        """存量项目接入时必然有大量孤儿,阻断会让它根本进不来。"""
        r = self._verify()
        self.assertIn("孤儿", r.text, "前提:这一轮得真的检出了孤儿,"
                                      "否则「不阻断」是恒真的")
        self.assertAccepted(r)
        self.assertTrue(self.repo.state()["setup_verified"])

    def test_首行含孤儿总数(self):
        """"有几个"决定人类要不要现在处理 —— 只列文件不给总数,
        超过十个被截断时就看不出规模了。"""
        r = self._verify()
        heads = [l for l in r.text.split("\n") if "孤儿" in l]
        self.assertTrue(heads, "输出里没有任何一行提到孤儿")
        self.assertRegex(heads[0], r"\d+", "孤儿清单首行要含总数:%r" % heads[0])

    def test_未被跟踪的文件不算孤儿(self):
        """契约把管辖范围划在 `git ls-files` 上 —— 没入库的东西
        本来就不在协议管辖内,把它算进来会让清单被临时文件淹掉。"""
        self.repo.write("没入库的临时文件.txt", "x")
        r = self._verify()
        self.assertIn("孤儿", r.text,
                      "前提:得先有孤儿清单,否则下面那条恒真")
        self.assertNotIn("没入库的临时文件", r.text)

    def test_记忆层不算孤儿(self):
        """它被排除在角色/冻结/共享之外**不是配置疏忽,是 verify-setup
        自己强制的** —— 三种归法它都会 bad()。不排除的话这条警告
        结构上无法清零,几次之后就没人看了。"""
        self.repo.write("docs/notes/W1.md", "笔记")
        self.repo.write("docs/DECISIONS.md", "# 决策记录\n")
        self._commit()
        r = self._verify()
        self.assertIn("孤儿", r.text,
                      "前提:得先有孤儿清单,否则下面两条恒真")
        self.assertNotIn("docs/notes/W1.md", r.text)
        self.assertNotIn("docs/DECISIONS.md", r.text)

class TestOrphanTruncation(PairTestCase):
    """截断:超过十个只列前十,并说明**还剩多少**。

    单独一个类,因为它需要"孤儿只有用例自己造的" —— `init` 铺的那 3 个
    入口文件会占掉截断名额,而**契约没有规定清单内部的顺序**,
    按名字前缀数行、或断言谁排在第 10 位,都是在断言一条契约没写的排序
    承诺(规则 4)。把那 3 个划给 dev,数量就干净可数了。
    """

    config = {"require_setup_verification": True,
              "roles": {"tester": ["tests"],
                        "dev": ["src", "*.md", ".gitignore"]}}
    REPORT = setup_report("W1", "W2")

    def _verify(self):
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        return self.repo.run("verify-setup", "--drafter", "other", role="dev")

    def _commit(self, msg="人类提交"):
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", msg)

    def test_超过十个只列前十并说明还剩多少(self):
        """剩余数不是总数 —— 契约点名了这一点。
        列全会刷屏,只列不说剩多少则看不出规模。"""
        made = ["孤儿%02d.txt" % i for i in range(12)]
        for name in made:
            self.repo.write(name, "x")
        self._commit()
        r = self._verify()
        # 数"被列出的孤儿有几个",不按名字前缀数行、也不假设谁排在前面
        listed = [n for n in made if n in r.text]
        self.assertEqual(len(listed), 10,
                         "12 个孤儿应当只列出 10 个,实际 %d" % len(listed))

        # 剩余那一行:**不能用 assertIn("2", r.text)** —— 首行是"12 个孤儿",
        # 里面就含 "2",那样的断言是恒真的(dev 用变异证明过:把补剩余数
        # 那两行整段删掉,301 条一条都不红)。契约的括号「总数减 10,
        # 不是总数」是定稿时专门加的,得真的守住。
        #
        # 也不断言措辞("还有""没列出")—— 契约只规定"再补一行说明还剩
        # 多少个",没规定怎么说。所以用**结构**定位:孤儿块里既不含总数、
        # 也不是被列出路径的那一行。这样双向都挡得住:不实现 -> 找不到这样
        # 的行;打印总数当剩余数 -> 那行含 "12" 被排除,同样找不到。
        lines = r.text.split("\n")
        head = next(k for k, l in enumerate(lines) if "孤儿" in l and "12" in l)
        block = lines[head:]
        block = block[:next((k for k, l in enumerate(block) if not l.strip()),
                            len(block))]
        rest = [l for l in block
                if any(c.isdigit() for c in l)
                and "12" not in l
                and not any(n in l for n in made)]
        self.assertTrue(
            rest, "契约要求再补一行说明还剩多少个,孤儿块里没找到这样一行:\n"
                  + "\n".join(block))
        # 取整数比,不用子串:`"2" in l` 会被"还有 20 个"满足,
        # 而 20 正是"补的是总数+8"这类错误实现会打出来的数。
        nums = {int(x) for l in rest for x in re.findall(r"\d+", l)}
        self.assertIn(
            2, nums,
            "剩余数应当是 12 − 10 = 2,那一行里的数字是 %s:%r" % (sorted(nums), rest))


class TestIgnorePathsListing(PairTestCase):
    """`ignore_paths` 的覆盖清单 —— 哪些文件已经不受保护,要摆给人看。"""

    config = {"require_setup_verification": True,
              "ignore_paths": ["build/缓存.json"]}
    REPORT = setup_report("W1", "W2")

    def test_列出_ignore_paths_覆盖的被跟踪文件(self):
        self.repo.write("build/缓存.json", "{}")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "副产物入库")
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        r = self.repo.run("verify-setup", "--drafter", "other", role="dev")
        self.assertAccepted(r)
        self.assertIn("不受边界保护", r.text)
        self.assertIn("build/缓存.json", r.text)

    def test_命中_ignore_paths_的文件不算孤儿(self):
        """`ignore_paths` 在这一节里被用在两处,语义**相反**:孤儿判据里它是
        排除项(命中就不算孤儿),覆盖清单里它是来源(命中就要列出来)。
        少了 `is_orphan` 里那一句排除,同一个文件会同时出现在两段警告里 ——
        而孤儿那段的表头自己写着"也不在 `ignore_paths` 里"。

        判据是**整份输出里只出现一次**,不是"在某一段里"。
        `TestIgnorePathsListing` 原来只断言它出现在"不受边界保护"那段,
        没断言它**不在**孤儿清单里,所以拆掉排除那一句 10 条一条都不红。
        """
        self.repo.write("build/缓存.json", "{}")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "副产物入库")
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        r = self.repo.run("verify-setup", "--drafter", "other", role="dev")
        self.assertIn("孤儿", r.text,
                      "前提:这一轮得真的打印了孤儿清单,否则下面那条恒真")
        self.assertEqual(
            r.text.count("build/缓存.json"), 1,
            "命中 ignore_paths 的文件只该出现在「不受边界保护」那一段。"
            "出现两次说明 is_orphan 没把它排除掉,而孤儿表头自己写着"
            "「也不在 ignore_paths 里」。输出:\n%s" % r.text)

    def test_首行含不受保护的文件总数(self):
        """和孤儿那一侧对称:只列文件不给总数,超过十个被截断时
        就看不出规模了。"""
        self.repo.write("build/缓存.json", "{}")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "副产物入库")
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        r = self.repo.run("verify-setup", "--drafter", "other", role="dev")
        heads = [l for l in r.text.split("\n") if "不受边界保护" in l]
        self.assertTrue(heads, "输出里没有任何一行提到不受边界保护")
        self.assertRegex(heads[0], r"\d+",
                         "这一段的首行要含总数:%r" % heads[0])


class TestIgnorePathsTruncation(PairTestCase):
    """截断:`ignore_paths` 这一侧同样超过十个只列前十。

    孤儿那侧有 `TestOrphanTruncation` 守着,这一侧原来没有 —— 把
    `PATH_LISTING_LIMIT` 调成 10000,10 条一条都不红。

    `ignore_paths` 写成 `"build"`(不含通配符)走目录前缀语义,
    所以只有本用例造的那批命中,数量干净可数。
    """

    config = {"require_setup_verification": True,
              "ignore_paths": ["build"]}
    REPORT = setup_report("W1", "W2")

    def test_超过十个只列前十并说明还剩多少(self):
        made = ["build/产物%02d.json" % i for i in range(12)]
        for name in made:
            self.repo.write(name, "{}")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "副产物入库")
        self.repo.write("docs/reviews/setup-verification.md", self.REPORT)
        r = self.repo.run("verify-setup", "--drafter", "other", role="dev")

        listed = [n for n in made if n in r.text]
        self.assertEqual(len(listed), 10,
                         "12 个应当只列出 10 个,实际 %d" % len(listed))

        # 判据照孤儿那侧:结构定位,不数名字前缀、不断言措辞、
        # 更不能 assertIn("2") —— 首行"12 个文件"里就含 "2",那是恒真的。
        lines = r.text.split("\n")
        head = next(k for k, l in enumerate(lines)
                    if "不受边界保护" in l and "12" in l)
        block = lines[head:]
        block = block[:next((k for k, l in enumerate(block) if not l.strip()),
                            len(block))]
        rest = [l for l in block
                if any(c.isdigit() for c in l)
                and "12" not in l
                and not any(n in l for n in made)]
        self.assertTrue(
            rest, "契约要求这一段同样补一行说明还剩多少个,没找到:\n"
                  + "\n".join(block))
        # 取整数比,不用子串:`"2" in l` 会被"还有 20 个"满足,
        # 而 20 正是"补的是总数+8"这类错误实现会打出来的数。
        nums = {int(x) for l in rest for x in re.findall(r"\d+", l)}
        self.assertIn(
            2, nums,
            "剩余数应当是 12 − 10 = 2,那一行里的数字是 %s:%r" % (sorted(nums), rest))


class TestBoundaryRefusalMentionsOrphan(PairTestCase):
    """撞上那一刻的文案 —— 这一节真正要救的场景。"""

    def test_越界项里有孤儿时要说清楚别撤销(self):
        """`AGENTS.md` 是孤儿:tester 写不了,dev 也写不了。
        原文案让 agent"撤销这些改动",而它多半是人类刚改的。"""
        self.repo.advance_to("spec")
        self.repo.write("AGENTS.md", "人类刚改过的入口文件\n")
        r = self.repo.run("handoff", "写了用例", role="tester")
        self.assertRefused(r, "AGENTS.md", "不属于任何角色")
        self.assertIn("划归", r.text)
        self.assertNotIn("请撤销这些改动后重试", r.text,
                         "越界项里有孤儿时,末尾那句必须跟着改 —— "
                         "只在中间加提示、末尾留一句相反的指令,agent 照样照后者做")

    def test_越界项里没有孤儿时末尾维持原样(self):
        """`src/` 属于 dev,不是孤儿 —— tester 越界写它,
        正确的出路就是撤销。这条是上一条的对照,防止把文案改成无条件的。"""
        self.repo.advance_to("spec")
        self.repo.write("src/偷跑的实现.py", "x = 1\n")
        r = self.repo.run("handoff", "写了用例", role="tester")
        self.assertRefused(r, "越界")
        self.assertIn("请撤销这些改动后重试", r.text)
        self.assertNotIn("不属于任何角色", r.text)


if __name__ == "__main__":
    unittest.main()
