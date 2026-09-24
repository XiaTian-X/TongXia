# W33 — review-test(dev 审 tester 的测试与 mutation_check 的改动)

裁决: approve

## 我检查了什么

`cover` 项:`mutation_check.py` 的改动与用例都是 tester 写的,我审的是"它们挡不挡得住回归"。
隔离克隆(`.pair/scratch/w33`,用完删掉)里只跑 `test_mutation_baseline_env`,每次只改 `mutation_check.py` 一处:

| 注入 | 红 |
|---|---|
| `run_baseline` 退回在本仓库(`REPO`)里跑 | `test_只在无_git_时失败的用例让基线变红` |
| 基线环境带上 `PAIR_MUTATION_RUN=1` | `test_基线不带_PAIR_MUTATION_RUN` |
| 干净 | 无 |

- **两个方向各有一条、互不重叠**:前者守"同一个文件系统",后者守 spec 回合补的"不是同一个环境变量"(⑨)——
  锚点检查因此仍留在基线里。
- **"只在无 `.git` 时失败"的前提被核实了**:那条用例先在迷你仓库原地跑一遍、断言是绿的,再断言基线红 ——
  排除了"这个小测试本来就红、跟环境无关"的假阳性。
- **不在测试里跑全套**:迷你仓库只有 `mutation_check.py`、`run.py`、存根 `pair.py` 与一个小测试,自己 `git init`;
  `mutation_check` 按自己的位置找 `REPO`,所以 `isolated_copy` 复制的正是迷你仓库。三条共约十几秒。
- 对照组与环境变量那条只看"基线全绿"这一句、不看退出码 —— 借来的 `--only 拆掉死锁闸` 在存根上匹配不到会让退出码非零,
  笔记里写明了这是借用,判据不依赖它,成立。
- 真实仓库的基线在无 `.git` 副本里照绿(我在第十四轮 W30 复审时也实测过全套在无 `.git` 副本里全绿)。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W33`。

## 未覆盖

- 你在笔记里冻结的那一处我同意:缓存指纹仍按本仓库的文件算,今天与副本逐字节相同(只差 `.git`);
  `isolated_copy` 的排除规则将来变宽时"本仓库指纹 = 验证过的环境"会失效,没有用例钉它。
- 每次跑 `mutation_check` 多复制一次整个仓库做基线,代价是几秒;没有测性能,契约也不要求。
