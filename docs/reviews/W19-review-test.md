# W19 review-test(dev 审 tester 的测试)

裁决: **changes**。三处测试侧缺口,impl 回合就点名过,你在 review-impl 同意归 spec 回合补。
每一处都是**真行为差异**:我在隔离克隆里注入对应变异,全套 0 红。

## ① 工作项进行中,`whose-turn` 不该被 idle 例外带走 —— 没有用例守

`tests/conformance/test_v1_both_roles.py:97` 的 `TestWhoseTurnAtIdle` 五条全在 idle。
变异:`phase_owner` 里 `if phase == "idle" and cfg["require_setup_verification"]:` → `if cfg["require_setup_verification"]:`
(不限 idle),全套 0 红。后果:认领之后人类改了契约、tester 在自己的 spec 回合重跑了 `verify-setup`、dev 还没跑 ——
`whose-turn` 输出 `turn dev`,**驱动器在 tester 的回合去调度 dev**。契约写明"工作项进行中不受影响"。
**候选**:两边都校验、认领、改契约、tester 重跑,断言 `whose-turn` 仍是 `turn tester`(阶段仍是 spec)。

## ② 门禁关着时归属不该变 —— 没有用例守

同一个类的 `config = {"require_setup_verification": True}` 让所有场景都开着门禁。
变异:同一行 → `if phase == "idle":`(不看门禁),全套 0 红。后果:门禁关着、tester 顺手跑过一次 `verify-setup`、
dev 没跑,idle 归 dev —— 而门禁关着时 dev 根本不需要校验,驱动器会调度一个无事可做的 dev。
**候选**:门禁关着、只有 tester 校验过,断言 `turn tester`。

## ③ `test_dev_的_status_归属那一行是_dev_且给出重跑指引` 的 `verify-setup` 断言被另一样东西替它成立

`tests/conformance/test_v1_both_roles.py:106`。`status` 在打回合说明之前,先打"你上次的开工前校验已经不作数了"
那段提示,里面本来就有 `verify-setup`。变异:idle 归 dev 时照旧打认领说明(`if phase == "idle" and owner == "dev":` → `if False:`),
全套 0 红 —— dev 被告知去做它做不了的 `claim`。**本轮第四次这个形状**(W16 删文件、W18 文案文件名、W18 状态字节相同)。
**候选**:断言 dev 的 `status` **不含** `claim <ID>`。

## 查过、没问题的

- `claim` 一组六条:两个都作数放行、只有 tester/只有 dev 校验过各点名对方、契约变了只有一方重跑照样拒、两个都过期两个都点名、
  中途契约变了不挡交接。判据只碰退出码与角色名,不碰状态键名。
- 契约点名的 6 条既有用例按新行为改(认领前补 dev 校验),守的性质一个字没动。
- idle 五条里被抓住的四个方向(不看 tester 作数、不看 dev 不作数、例外从不生效、两处共用)各有用例红。
- 五个锚点 `+21/-0` 纯追加、字面与我笔记表一致。补完用例后,那三个存活的变异可以一并登记。
