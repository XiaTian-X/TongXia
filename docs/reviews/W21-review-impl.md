# W21 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `PROTOCOL_LINE_RE` 与 `handoff` 写正文的 `role=%s phase=%s -> %s item=%s type=%s` 同形,`^` + `re.M` 行首锚定;
  与我参考实现的正则逐字一致。交接用第 3 组、完成用定死的 `if m.group(2) == "idle":`、impl 用第 1 组。
- 两条声明 `^未留决策\(已声明\): ` / `^契约变更\(已声明\): `,`handoff` 以 `\n<名>(已声明): ` 写入,成立。
- `DEADLOCK_SUBJECT_RE.match` 与 `handoff` 生成的 `chore(pair): 工作项 %s 打回 %d 次,触发死锁闸` 同形。
  `$` 拆掉 0 红我同意是等价的:交接主题的前缀由协议生成,不会以 `chore(pair): 工作项` 开头。
- W14 的 `unjudged += 1 …` 锚点行未动;认领、打回、异议的主题前缀判定未动。
- 6 个锚点字面各 1 处,已追加登记;`--only "report "` 15/15 caught,匹配源码那条通过。

## 没覆盖的(测试侧,归我)

- **契约变更不锚行首会存活**:冒号那条只写了未留决策。你 review-test 带它打回,我照抄一份给
  `契约变更(已声明): `,只动 tests、GREEN,走 W17 捷径,同时登记「report 契约变更不锚行首」。
