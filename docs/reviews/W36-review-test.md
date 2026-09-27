# W36 — review-test(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

隔离克隆(`.pair/scratch/w36`,用完删掉)里只跑 `TestContractExamplesCoverCategories` 与 W32 的 `TestContractExampleDiscriminates`,
每次只改样板契约一处:

| 注入 | 红 |
|---|---|
| 印地语词的期望输出丢掉两个 `Mc` | `test_期望输出里的组合符覆盖_Mn_Mc_Me` |
| `a` + U+20DD 的期望输出丢掉 U+20DD | 同上 |
| `Stra` + U+00DF + `e` 的期望输出给成 `strasse`(casefold) | `test_有例子分得开_lower_与_casefold` |
| 干净 | 无(W32 两条也绿) |

- **组合符看期望输出、不看输入**:例子若把组合符丢掉,只认 Mn 的实现照样"对" —— 看输出才分得开。前两行正是这种改法,都被抓住。
- **小写化按逐字符读**:三个条件(输入里有 lower≠casefold 的字符、期望输出含它的 lower、期望输出再 casefold 会变)缺一不可;
  第三行给成 casefold 的写法被第三个条件抓住。`ΟΔΟΣ` 那个例子不会误判(词尾 Σ 的 lower 与 casefold 相同)。
- 取法认 `slugify("…")` 是 `"…"` 与 `"…"` → `"…"` 两种写法,范围限在 `## slugify` 一节,truncate 一节的例子不混进来。
- **决策**:之前没有 `## W36`,我补了一条。

## 未覆盖

- 只查了组合符与小写化两条;契约别的按类别下定义的规则(比如"Unicode 空白按 `str.split()`")例子有没有覆盖每一类,没有同样的检查。
- **我自己的探针第一版是错的**:shell 命令里写的反斜杠加 u 转义被工具当场解掉,三次注入都没对上字符串、全部"OK"。
  改成在 Python 里用 `chr(92)` 拼转义后才是上表的结果 —— 条目 43 那一类不只发生在写文件时,也发生在命令行里,已写进决策。
