# W19 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `pair.py` `cmd_claim`:逐字是 spec 定死的四行(`for r in ROLES` 收集、`"\n\n".join` 后 die),W13 两个重锚锚点与 ⑦ 各匹配 1 处。
- `phase_owner`:只在 `phase == "idle"` 且门禁开着时生效;tester 作数且 dev 不作数 → dev,其余 `PHASE_OWNER`。与契约 ⑧ 一致,tester 过期时 tester 先。
  不另判 `setup_verified` 我同意:tester 作数必然校验过。
- 两行相同的 `owner = PHASE_OWNER[phase]`:改的是 `cmd_status` 那一行,`cmd_handoff` 没动(交接归属不该受开工前校验影响)。
- `cmd_whose_turn`:改用 `phase_owner`,篡改检查仍在前面。
- `status` idle 归 dev 时打印 `IDLE_REVERIFY_BRIEF` 而非认领说明。小瑕疵(不打回):文案里 `docs/reviews/setup-verification-dev.md` 是写死的,没用 `SETUP_REPORT_ROLE_FMT % "dev"`;评审目录本身是常量,当前不会漂。
- `stale_verification` 文案点名角色、重跑命令带 `PAIR_ROLE=<角色>`,与 both_roles 的点名断言对得上。

## 锚点登记(本回合追加进 mutation_check.py)

dev 给的 5 个字面我核过各恰好出现 1 次,登记后 `--only` 跑:

| 变异 | 抓住的用例(缓存记的第一条) |
|---|---|
| idle 归 dev 不看 tester 作数 | test_tester_过期时照旧轮到_tester |
| idle 归 dev 不看 dev 不作数 | test_dev_重跑之后又轮到_tester |
| idle 例外从不生效 | test_dev_的_status_归属那一行是_dev_且给出重跑指引 |
| status 不用 idle 例外 | test_dev_的_status_归属那一行是_dev_且给出重跑指引 |
| whose-turn 不用 idle 例外 | test_dev_重跑之后又轮到_tester |

`test_变异点仍能匹配到源码` 通过。

## 存活的三个(测试侧缺口,归我)

dev 笔记里三个存活探针我逐条认:都是用例没守住,不是实现问题。

1. 不限 idle:工作项进行中 tester 重跑、dev 没跑时 `whose-turn` 会输出 `turn dev`。
2. 门禁关着也改归属。
3. dev 在 idle 看到认领说明:`verify-setup` 这个词先被"校验不作数"提示打出来了,判据被别的输出替它成立 —— 应断言不含认领说明。

这三条该在 review-test 打回、我走 W17 捷径在 spec 回合补用例并登记这三个锚点。
