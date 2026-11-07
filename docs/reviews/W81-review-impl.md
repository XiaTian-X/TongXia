# W81 review-impl —— cover 新增的用例确实跑了

**裁决:通过(approve)。** 实现与契约逐条对上,与我在 spec 回合写的参考实现同形。

## 查过的地方

- **判点**:`cmd_handoff` 里红绿不变量之后、W17 捷径之前,`phase in flow["require_new_tests"]` 时才调 `new_tests_ran`。
  - `require_new_tests` 只有 cover 的 `("spec",)`,feature / bug / refactor 都是空的,所以等价于"只在 cover 的 spec 判"。
  - 修正回合同样是 spec,照样判。
- **`new_tests_ran`**:
  - 门禁报告用 `junit_executed`,跳过的不算,与 W61 同口径。
  - 认领时基线用 `git show <item_base>:.pair/full-baseline.json`,不读工作区也不读 HEAD。
  - 减去 `renamed_tests` 的**值**。W78 在 tester 路径检查之后已把本回合的声明合进内存状态,所以同回合的声明算得上。
  - 读不出一律返回 None(不判):没配报告、没有 `item_base`、报告读不出、那一刻没有基线、不是合法 JSON、`executed` 不是列表。
- **拒绝**:只在返回空列表时。文案点明对照的是认领那一刻的全量基线,列了四种常见原因;`die` 退出,提交数与状态不变。
- **正文**:`新用例(跑过): N 条`,N 是去重后的条数,与契约逐字一致。
- **登记**:`ENFORCEMENTS` 加了 `cover-executed`,不进交接不变量;protocol-spec §4 表第 9 行补了说明;`pair-enforcements` 注释、正文格式、architecture、troubleshooting、rules 跟上;路线图 P0-1 ③ 标 ✅,① 写明不做。
- **范围外的顺手改动**:顺手补了 W79 `turn_budget_refusal` 漏补的 docstring(我在 W79 第二轮评审里误记为已补,已更正),只是注释,无行为变化。
- 没有针对用例输入的特判。

## 变异点

登记 15 个(`新用例_` 前缀),`--only 新用例_` 全被抓到:

| 类别 | 变异点 |
| --- | --- |
| 契约列的 | 不判、用工作区基线、跳过的算跑过、不扣改名新名、读不出时拦了(没配报告、没有 `item_base`、报告读不出、基线不是合法 JSON、认领时没有基线,各一个)、判到 feature 上、正文不写那一行 |
| 加的 | 用 HEAD 里的基线、扣改名扣成旧名、正文条数写死、拒绝文案不提认领 |

"文案不提认领"第一版只换掉了文案里两处"认领"中的一处,存活。这是变异写得不对,不是用例缺口。改成两处一起换掉之后被抓到。

## 没覆盖到的

和 spec 回合笔记里列的一样:
- 门禁报告读得出但一条用例都没有(实现按空集合拒绝,与我的读法一致,没有单造用例);
- 门禁与全量 ID 拼法对不上;
- 判点在红绿不变量之后的先后。
