# W50 review-test(dev)

裁决: approve

## 我检查了什么

- `tests/conformance/test_v1_done_dev_stale.py` 5 条与契约判据逐项对上:cover 项里契约中途改过 → dev 的 approve 被拒、含 `verify-setup`、阶段不推进;
  dev 重跑后同一条放行、tester 重跑后能认领 W2;refactor 由 tester 完成 → 放行、"已交接"之后提示 dev 与 `verify-setup`;两条对照组。
- 契约中途由人类 `set_plan` 改而不是 tester 带声明改:两者对两个角色校验的效果相同,带声明那条路径已有用例守 —— 这样简化成立。
- 隔离副本里另探两个(spec、review-impl 之外):去掉门禁开关条件 → 全套红 105(验证关着的既有用例全被误拦,间接守住了"开关关着不检查");
  不看执行者(tester 完成也拒)→ "tester 完成时放行"那条红。连同已登记的两个变异,四种写错法都有用例抓。
- 全套 621 绿。

## 未覆盖

- 拒绝文案里"下一次认领会被拒""先重跑再交接"两句措辞没有用例守,只钉 `verify-setup` 与阶段不推进。
- "开关关着不检查"没有直接用例,靠既有 105 条间接守。
