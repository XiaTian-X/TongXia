# W15 review-test(dev 审 tester 的测试)

裁决: **changes**。一处缺口,impl 回合就预告过,你在 review-impl 独立复现并同意。

## 问题:被测代码里的 `-z` 没有一条用例守着

`tests/conformance/test_v1_setup_commit.py:40` 的 `TestOnlyTheAddedBatchIsCommitted` 两条里,
**进入 `git commit --` 的路径全是 ASCII**(`setup-verification.md`、`.pair/state.json`);
`AD` 那条的 `草稿.md` 恰恰是**不进**提交的那个。

变异 `staged_paths` 去掉 `-z`、按换行切,全套 **0 红**。而它是真缺陷:结论改一句 +
`docs/reviews/` 下新写一份 `中文评审.md`(不预先暂存),`git diff` 把名字转义成
`"docs/reviews/\344\270\255…"`,交回给 `git commit --` 报 pathspec 不匹配、**`exit 1`**,
状态位已写进工作区却没提交。契约 `CONTRACT.md:883` 给集合时写的就是 `-z`、
`:890` 写"路径已不被 git 认得时不能让提交失败"。与验收 ①′ 的 `AD` 同一类。

**候选形状**(两边都在克隆里验过:正确实现绿、只有这个变异红):上面那个场景,
断言 `exit 0`、`docs/reviews/中文评审.md` 在 HEAD 的树里(`git_paths` 整路径)。

**锚点**:`    out = git("diff", "--cached", "--name-only", "-z", "--", *paths, cwd=root)`
连同下一行 `    return [p for p in out.split("\0") if p]` 一起锚(下一行单独在 `pair.py`
里出现两次)。建议同时登记 `去掉 --cached` 那个(只红 ①③④ 那条,已验);
`退回全部 to_add` 与既有的「提交范围回到第一版的全部 to_add」是同一个行为,不必重复。

你在 review-impl 说得准:**守住了"判据别被转义骗",没守"实现别被转义骗"**。

## 查过、没问题的

- **三处死断言改法对**:`test_v1_setup.py:189`、`test_v1_setup_report.py:177` 与 `:209`
  都换成 `git_paths(... "-z")` 的整路径比,期望值是 `src/偷跑的实现` 整条路径而不是子串;
  `:194` 的 docstring 更正保留了原句。
- **`git_paths` 不带 `-z` 直接断言失败**:让下一个人写不出第四条死断言,是结构性的修法,好。
- **①③④ 那条的 `assertIn(IMPL, ls-files)` 正向对照**:同一个函数找得到它,前一句
  `assertNotIn` 就不是恒真 —— 这正是 W12 缺的那一种对照。
- **既有「拆掉 verify-setup 的提交范围」(`add -A`)** 现在由改好的两条 `-z` 断言接住,
  `mutation_check` 124/124(我 impl 回合跑的),开工前审查 ③ 说的缺口确实补上了。
- **没有断言私有实现细节**:`staged_paths` 这个名字用例里没出现;`staged` 变量名只在
  `MUTATIONS` 锚点里,那是契约允许 tester 定的一行。

## 未覆盖(不构成打回)

- `shared_paths` 下重命名只提交新路径一半、路径按通配解释:两边都记过,不在本项。
