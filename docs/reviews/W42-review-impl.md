# W42 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `_stack_hits` 收集根上全部命中;`cmd_init` 只在没有已有 `test_cmd` 时判,命令去重多于一条就 `die`。位置在铺任何文件之前,
  `_detect_stack` 一字没动 —— 单栈与已有 config 两条路径照旧。与我参考实现同形。
- 拒绝文案点名每一对(探测文件 → 命令),给出两条出路(覆盖全部 / 收窄并写 `baseline.md`),路径用 `CONFIG_REL`、`BASELINE_REL` 常量。
- 已有 config 但没写 `test_cmd` 时多栈照样拒绝:与"根本没有 config"同一个判定,同意不单独钉。
- 不进 `ENFORCEMENTS`:`init` 的拒绝一向不在那张表里,同意。
- 两个锚点(多栈不拒绝、同一条命令也算多个栈)落在同一行、字面唯一,已追加登记,各被对应用例抓住;匹配源码那条通过。
- 文档:`INSTALL.md` 把多语言仓库从「不适用」挪出来单成一节,`command-reference`、`troubleshooting` 各补一段 —— 契约 ⑥ 照做。

## 没覆盖的

- 文档措辞没有用例守。
- 子目录里的栈照旧探测不到(契约「不做」)。
