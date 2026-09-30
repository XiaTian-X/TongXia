# W41 review-test(dev)

裁决: approve

## 我检查了什么

- `tests/conformance/test_v1_remote_push.py` 4 条与契约判据逐项对上:不含"没有远端";含 `sync`、`false`、理由里的 `pull --rebase`;含 `--ff-only`;
  `.pair/config.json` 的 `sync` 用 `assertIs(..., False)`。
- 改坏配置(隔离副本):删掉 `sync` 键 → 红;`sync` 写成 `0` → 红(不是真值判断,`0` 蒙不过去)。原样全绿。
- 改动前的 `AGENTS.md` 一个 `false` 都没有,`false` 那条今天红得有依据,不是被别处的 `false` 蒙绿。
- 全套 582 绿。

## 未覆盖

- 四个字样各自出现即过,不查它们在同一句里:一句"可以把 `sync` 打开、它会 `pull --rebase`"加别处任意 `false` 也能过。文档字样测试的通病,措辞靠评审(本回合我与 review-impl 都读过原文)。
- 删掉 `sync` 键时 `pair.py` 照 `setdefault` 当 `false` 用,用例却判红 —— 比契约严一点(契约写"`sync` 为 `false`"),可接受。
