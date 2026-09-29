# W38 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `verification_gap`:判定照旧(sha 相等即作数);不作数再分 never / legacy / changed / unreadable。`never` = 无记录且角色结论与旧共享结论都不在 ——
  比我开工前说的多认了旧共享文件,那正是 W12 的回落路径,同意。
- `reverify_how` 按 gap 说;`stale_verification` 的拒绝理由与 `IDLE_REVERIFY_BRIEF` 都读这两个函数,一处分、两处用。路径用 `SETUP_REPORT_ROLE_FMT`。
- 你撞上两个既有锚点后把 sha 与"读不到"那一支留在 `stale_verification` 原处、新函数接收 `now` —— 字面没动,`test_变异点仍能匹配到源码` 通过。
- 三个锚点(从没校验过当成存量、做法只说末尾追加、idle 做法固定按契约变了)字面各 1 处,已追加登记,各被对应用例抓住。

## 没覆盖的

- `unreadable` 那一种在 idle 提示里的说法没有用例(契约读不到在 `claim` 那边有既有用例)。
- `legacy` 在 idle 提示里说"往末尾追加":文件在,追加是对的;没单独钉。
