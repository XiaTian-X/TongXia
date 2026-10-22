# W65 review-test(dev)

裁决: changes

## 我检查了什么

- `tests/conformance/test_v1_requests.py` 30 条与契约「代办通道」的判据逐项对上:
  - request 的形状与八种拒绝;
  - 带代办的异议不计数,对照组照计;
  - fulfill 校验改动、只提交状态文件;
  - 归属与回合分开钉;
  - decline 补计与不补计,补到上限撞死锁闸;
  - 收口、`claim` 清空、`status` 与 `report`。
- review-impl 第二次登记的七个变异点,与我 impl 回合在项目内 `.pair/scratch/` 放的 13 个探针一致。

## 打回原因:两处行为没有用例守着

**① `report` 认"死锁闸里的拒绝代办"**(review-impl 第二次已约定由这里打回)
- `.agents/skills/pair-protocol/scripts/pair.py:3331` 的 `DEADLOCK_SUBJECT_RE.match(subject) and DECLINE_LINE_RE.search(body)` 没有用例。
- 拆掉它,补计撞上死锁闸的那一次拒绝就不进被拒率,今天全绿。
- 请在 `test_补计到上限触发死锁闸` 同一个场景里跑 `report`:"死锁工作项占比"的分子是 1,"代办被拒率"是 1/1。

**② 冻结路径落在对方 `roles` 里**(impl 交接时我请你评估的那个存活探针)
- `.agents/skills/pair-protocol/scripts/pair.py:3045` 的冻结判断去掉,今天全绿。
- `tests/conformance/test_v1_requests.py:112` 用的 `docs/CONTRACT.md` 同时是孤儿:冻结判断去掉之后,它落进孤儿那一支,照样被拒,文案同样含"人类"。
- 区别出现在冻结路径同时匹配对方 `roles` 的时候。那时不拦,就会收下一条对方在写权限边界上根本改不了的代办,对方只能 decline。
  本仓库就有这种重叠的可能(dev 的 `*.md`、`docs/*.md` 与冻结路径并列)。
- 请补一条:类级配置让对方 `roles` 覆盖到某个冻结路径,request 那个路径被拒,文案含"人类"。

## 未覆盖(不阻断)

- `fulfill` 只看"请求的路径自 `base` 起有改动",不看改得对不对:契约就是这么定的(记账,不是执行),对不对由后面的红绿与评审判。
