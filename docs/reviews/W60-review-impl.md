# W60 — review-impl(tester)

结论:**通过**。

## 查过的地方

- 认领时 `item_base` = 那一刻的 HEAD,在 `save_state` 之前取 —— 认领提交本身只改状态文件,状态文件在排除项里,取哪一个都不影响路径。
- `gate_command`:`PAIR_TEST_CMD` 覆盖、没配 `affected_test_cmd`、全量日志、缺任一兜底键 → 门禁;状态里没有工作项或 `item_base` → 门禁;
  路径为空或超过 200 条 → 门禁;`item_changed_paths` 的 `git diff` 失败返回 None,同样落到"路径为空"那一支 —— 不会拿一个算错的集合去选。
  `run_tests` 里 `cmd = cmd or gate_command(...)`:显式给了命令的调用(全量、`init` 的探测)不走选择,`status`、`handoff`、`verify-setup` 自动共用。
- `item_changed_paths`:`<item_base>` 到工作区的差异加未跟踪的,只留 `is_file()` 的(删除的不传),去掉 `fingerprint_excluded`(状态、协议日志、报告、评审目录、记忆层),排序。
  与契约「本工作项改动的路径」逐项一致;排序保证同样内容生成同样命令,W57 复用照常。
- `verify-setup`:配了 `affected_test_cmd` 却缺兜底键,`bad` 里点名缺的是哪个(`full_test_cmd` / `full_test_report`)。
- 文档:`protocol-spec.md` 配置表与状态 schema、`command-reference.md`、`INSTALL.md`(jest/vitest/testmon 写法、必须配全量与报告、选择器也写同一份 `test_report`、
  选择器要能忽略非代码路径)—— 我在笔记里提醒的两处都写了。路线图 53 标 ✅。

## 变异点

登记七个(锚点各只出现一次):空集与超限不退回、运行时不看兜底配置、路径排除项不排、路径含已删除的、路径只算本回合、认领时不记 `item_base`、
不检查兜底配置。`--only` 结果见本文件末尾的补记。

## 没覆盖的

- `item_base` 指向的提交不在了(人类改写了历史)时 `git diff` 失败、退回门禁 —— 没有用例;本仓库约定不变基。
- 选择器自己漏选的情形由 W59 在完成时兜住,本项不另测。

## 补记:变异点 `--only` 结果

七个全部被抓到,基线(隔离副本)全绿:空集与超限不退回(`test_认领之后还没有改动`)、运行时不看兜底配置(`test_没配全量报告时工作项进行中也走门禁`)、
路径排除项不排(`test_认领之后还没有改动`)、路径含已删除的(`test_删除的文件不进路径`)、路径只算本回合(`test_从认领起算_dev_回合里有_tester_写的测试`)、
不检查兜底配置(`test_没配全量命令时_verify_setup_失败并说明`)、认领时不记 `item_base`(`test_路径正好_200_条仍走选择器`)。
