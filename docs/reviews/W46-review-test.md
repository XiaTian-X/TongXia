# W46 review-test(dev)

裁决: approve

## 我检查了什么

- `tests/conformance/test_v1_shipped.py` 新增 `TestAllEntryFilesMatchInit`:按 `PAIR.ENTRY_FILES` 遍历,每个入口文件用 `merge_entry` 在空目录写一份,
  与 `examples/demo-project/` 里那份逐字节比;样板缺文件也算不一致;开头断言注册表非空,防遍历空表恒绿。
- 隔离副本(`git archive`)里三种漂移:改 `ACTIVATOR` 首行、改 `CURSOR_MDC` 的 description、样板 `.clinerules` 末尾多一行 —— 各红这一条。
- 两个新变异点的字面在 `pair.py` 里各一处(匹配源码那条通过);`CLAUDE_MD` 那条照旧由 W28 的用例抓,这条也会一起红。
- 用例加载的是 `test_v1_shipped` 同目录推出来的 `pair.py`,变异检查在副本里改的正是它 —— 变异能被这条看见。
- 全套 609 绿。

## 未覆盖

- 仓库根上本项目自己的入口文件不在比较范围(契约「不做」,它们本来就不等于模板)。
- `merge_entry` 合并进已有文件的路径(样板项目里入口文件已存在时重跑 `init`)不在这条里,由既有的 `test_v1_setup` 守。
