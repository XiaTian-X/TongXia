# W28 — review-test(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

隔离克隆(`.pair/scratch/w28`,用完删掉)里只跑 `TestClaudeMdForbidsHandingOff` 3 条,每次只注入一处:

| 注入 | 红 |
|---|---|
| `CLAUDE_MD` 改回旧句子,样板与本仓库不动 | `test_init_写的_CLAUDE_md_不再按谁在跑来禁`、`test_样板_CLAUDE_md_与_init_写出的逐字节一致` |
| 只把本仓库 `CLAUDE.md` 改回旧句子 | `test_本仓库的_CLAUDE_md_同一句跟着改` |
| 只改 `CLAUDE_MD` 一个字(impl 回合探过,即你登记的变异形状) | 只有一致性那条 |
| 干净 | 无 |

- 三条各守一件事,互不蒙混:缺陷回来了(模板)、本仓库没跟上、样板没跟上。
- **不是新措辞探测器**:`AMBIGUOUS` 只列旧说法里出错的两处,新句子里我照样写了"subagent"(在豁免那半句),判据不冲突 ——
  它钉的是"按谁在跑来禁",不钉新句子怎么写。
- **一致性那条走真实路径**:`merge_entry(d, "CLAUDE.md", ENTRY_FILES["CLAUDE.md"])` 写进临时目录再逐字节比,
  用的是 `init` 自己的写入函数与模板表,不是手抄一份期望文本。
- **`init` 那条跑的是真 `init`**(`BareRepo(PY_PROJECT)`),不是直接读常量 —— `init` 若改成写别的模板,它照样能红。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W28`。

## 未覆盖

- 新措辞本身没有用例:一个不含那两个旧说法、却仍按"谁在跑"来禁的新句子能全绿。契约明写措辞不写成用例,靠评审 ——
  你在 review-impl 以读者身份核过一遍。
- `AMBIGUOUS` 用子串判:今后若有人在 `CLAUDE.md` 里正当地用到"主会话"一词(比如解释这个仓库自己的编排),这条会误红。
  现在没有这种用法,记一句。
- 其余七个入口文件的一致性:路线图 33。
