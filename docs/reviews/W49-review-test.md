# W49 review-test(dev)

裁决: approve

## 我检查了什么

- `test_v1_shipped.py` 的 `TestDemoDecisionsAndExitCodes` 两条:样板 `docs/DECISIONS.md` == `DECISIONS_SKELETON`;`protocol-spec.md` 的 §9(切到下一个 `## ` 为止)里码 2 的行中有一行含"全量"。
- 隔离副本(`git archive`)里:样板头改回旧口径 → 第一条红;把 §9 全量那一行的码改掉 → 第二条红;在 §9 标题下插一个新的 `## ` 把那一行挤出 §9 → 第二条红(切片确实只看 §9)。
- 变异点「DECISIONS_SKELETON 改了而样板没跟上」在 spec 回合已登记,锚点取自源码原样(全角标点);匹配源码那条绿。
- 全套 616 绿。

## 未覆盖

- §9 新行与表下"两种来源"说明的措辞没有用例守,只钉"码 2 有一行说全量"。
- 推送失败那一行被删掉不会红(这一项只要求补上全量那行)。
