# W20 — review-impl 第二次(tester)

结论:**通过**。

## 查过的地方

- 祖先判定在 `^{commit}` 解析之后、`_handoff_log` 之前;`git(..., check=False)` 失败返回 None → `die`,stderr + exit 1,无 traceback。
  `merge-base --is-ancestor` 不是祖先退出 1、非提交退出 128,两种都走 None,判据对。
- `since == HEAD` 时 HEAD 是自己的祖先,`--since HEAD` 照旧放行(那条用例仍绿)。
- 文案点名 `args.since`(用户传的原样),用例传的是完整 sha,断言成立。
- `^{commit}` 留着只为文案更准:同意;它的变异点我上一回合已撤,现在是等价变异。
- 锚点「report 不查起点是不是祖先」字面唯一,已追加登记,`--only "report "` 9/9 caught,匹配源码那条通过。

## 没覆盖的

- 拒绝文案里"差集"的解释没钉字面。
- 浅克隆里起点在截断边界之外时 `merge-base` 的行为没测(会被拒,属于"解析不成"那一类)。
