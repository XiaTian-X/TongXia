# W20 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `_handoff_log(root, since)`:有起点走 `<sha>..HEAD`,无起点参数与原来逐字相同 —— 不带 `--since` 的读取路径没变。
- 起点解析 `rev-parse --verify -q <rev>^{commit}`,空即 `die` 点名起点;`die` 走 stderr + exit 1,无 traceback。
  `^{commit}` 的理由(`check=False` 会把 `<tree>..HEAD` 报错吞成全零表)成立,锚点也钉住了。
- `finished` 在 `item=` 且非 none 的那批里数 `phase=\S+ -> idle `:只有 DONE 把 `next_phase` 设成 idle,
  认领提交正文不是 `phase=… -> idle` 形状,不会误计。
- `per_done = finished if since else done`:不带 `--since` 时两行与偏高判定照旧用状态 → 输出一个字不变。
- 表头起点行只在带 `--since` 时打印;已完成/进行中/决策与完成项仍用 `done`。
- argparse:`--since` 为可选、默认 None。

## 锚点登记(本回合追加进 mutation_check.py)

你给的 7 个字面各恰好出现 1 次(第三个我缩成 `"-q", args.since + "^{commit}",` 那一段,仍唯一),`--only "report "` 7/7 caught,匹配源码那条通过。

## 存活的两个与契约外一处(测试侧,归我)

1. **不带 `--since` 时分母也用区间完成数**:测试仓库里状态完成数与历史完成交接数恒等,所以 0 红;本仓库是 17 与 18,
   违反"一个字不变"。补法:造一个历史里多出来的完成交接(空提交正文 `phase=review-test -> idle item=W9`),断言不带 `--since` 时分母是状态里的数。
2. **偏高判定照读状态**:我 spec 笔记里声明过没钉,这次一起补。
3. **旁支起点静默统计差集**:我判断**要做**。`report` 存在的理由是让指标不在"好看"或"错"的方向上静默偏,
   一张退出 0、看起来合理的差集表正是那种失败;修法一行、行为可断言。我在 spec 回合带声明补契约与用例
   (改契约不走 W17 捷径,会经过一次 impl)。
