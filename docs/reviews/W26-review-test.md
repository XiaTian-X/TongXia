# W26 — review-test(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

隔离克隆(`.pair/scratch/w26`,`PYTHONDONTWRITEBYTECODE=1`,用完删掉)里跑 `test_v1_shipped`、`test_v1_setup`、
`test_v1_paths` 共 54 条,每次只注入一处错误:

| 注入 | 红几条 | 哪条 |
|---|---|---|
| 登记的变异:`elif ENTRY_MARK_BEGIN not in …` → `elif False:` | 1 | `test_入口文件缺激活段落时警告` |
| 只拆样板 `CLAUDE.md` 的标记块 | 1 | `test_CLAUDE_md_不缺激活段落` |
| 样板 `frozen_paths` 去掉 `GEMINI.md` | 1 | `test_没有孤儿那条` |
| 干净 | 0 | —— |

- 三处各自只红对应的那一条,判据没有互相蒙过去。
- **锚点**:新登记的「verify-setup 不警告入口文件缺激活段落」,old 串在 `pair.py` 里恰好 1 次。
- **不是变更探测器**:判据是 `verify-setup` 既有的警告文案里的文件名前缀("AGENTS.md 里没有协议激活段落"),
  不碰措辞的其余部分;"AGENTS.md 里"不会被"CLAUDE.md 里"那行误命中。
- **单向判据有前提守着**:样板三条"不出现"都依赖 `verify-setup` 真的跑完,同类里 `test_前提_校验跑通了`
  断言"开工前校验全部通过" —— 校验若提前退出,那三条会空转变绿,但这一条会红。
- **对照组**:只差 `AGENTS.md` 带不带标记块,且标记块是以人类身份提交的,不会被当成未提交改动另生警告。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W26`。

## 未覆盖

- **正面只打了 `AGENTS.md` 那一半。** 把 `verify-setup` 的检查循环收窄成只查 `("AGENTS.md",)`,
  正面照绿(它看的是 AGENTS.md)、样板那条 `CLAUDE.md` 也照绿(它断言的是"不出现")—— 没有用例红。
  两个文件走的是同一个循环,收窄它不是顺手会犯的错,不构成打回。
- `verify-setup` 只查 `AGENTS.md` 与 `CLAUDE.md` 两个入口文件的标记块,样板另外六个的标记块没有任何检查;
  本项契约只点了这两个,不在范围内。
- 样板契约与 `rules.md` 的措辞没有用例守,契约写明随实现交、评审回合看,你已看过。
