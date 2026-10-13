# W52 review-test(dev)

裁决: approve

## 我检查了什么

- `mutation_check.py` 的改动:预检拒绝出口 `return 2` → `return 3`,带注释说明 2 留给 argparse;别处的退出码没动(0、1 与 argparse 的 2)。
- `tests/conformance/test_mutation_exit_codes.py`:替换 `precheck_no_baseline` 后调 `main`,有失败项与运行器崩溃(失败集为空、rc≠0)两种拒绝都退 3;
  `--slice abc` 退 2、输出含 `usage:`、替身断言"不该走到预检"没被触发;`contributing.md` 三条字样断言。
- 隔离副本里:退回 `return 2` → 两条拒绝用例红;拒绝改成 `return 1` → 同样两条红(不只是"不等于 2",确实钉在 3 上)。
- 不端到端跑预检(替换函数),成本毫秒级;与 W45 的判定真值表互补:W45 守"什么时候拒绝",W52 守"拒绝时退几"。
- 全套 634 绿。

## 未覆盖

- 默认路径(不加 `--no-baseline`)基线不绿时的 1 没有新用例 —— 本项没动它。
- CI 的周跑走默认路径,碰不到 3。
