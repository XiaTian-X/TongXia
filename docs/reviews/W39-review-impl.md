# W39 — review-impl(tester)

结论:**实现通过**;`only` 那一支没有用例守 —— 归我,**请 review-test 打回**。

## 查过的地方

- `combining_in_new_lines` 加 `only`:给了只看那一个路径、不按 `shared_paths` 与记忆层过滤;判定与取新增行那几行原地没动,W37 四个锚点仍匹配。
  这正是我开工前提醒的"复用判定、不复用那道过滤"。
- `cmd_verify_setup` 在 `git add` 之前取结论那一条交给它(`only=report_rel`),"已收到"之后打印 `路径:行号  U+XXXX` 并说明只是提示;
  不拒绝、退出码不变、照常提交。
- 锚点「审查结论的组合符不提示」字面唯一,已追加登记,被抓。

## 没覆盖的(测试侧,归我)

- **去掉 `only`、走 `shared_paths` 过滤 4 条全绿**:harness 的 `shared_paths` 含 `docs/reviews`。你在内存里核过 `shared_paths` 为 `docs/other`
  时不传 `only` 返回空。补法:一个 `shared_paths` 不含 `docs/reviews` 的配置下跑"新写的结论带组合符"那条,断言照样点名;
  补完登记「审查结论的组合符走 shared_paths 过滤」(`, only=report_rel)` → `)`)。只动 tests,走 W17 捷径。
