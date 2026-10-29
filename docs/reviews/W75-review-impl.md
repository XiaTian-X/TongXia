# W75 review-impl —— review-impl 的测试缺口

**裁决:通过(approve)。** 逐条对过契约,没有挑出偏离。

## 查过的地方

- **旗标用错地方**(`test_gap_refusal`,`cmd_handoff` 在转移表之后、抓改动之前调用):阶段不是 review-impl → 拒;`("review-impl", "approve")` 不通向 review-test → 拒、
  文案含 `[cover]`(refactor 通向 DONE;bug 与 feature 共用 `FEATURE_FLOW`,cover 没有 review-impl);说明去空白后为空 → 拒。
  "dev 带它":review-impl 归 tester,回合归属那一道先拦;dev 自己的 impl、review-test 被阶段这一道拦 —— 不另设一道是对的,用例 `dev 在 review-test 带被拒` 守着。
  讨论回合走 `discuss_handoff`,那边也调了一次,旗标不会在讨论里被静默吞掉。
- **写权限**:带旗标时 `allowed` 并入 `roles.tester`;只追加路径那一道排在"可写"之前、判完 `continue`,登记表仍只追加(用例:改写已有行被拒、只追加加真用例放行)。
- **必须补了用例**:排在删除测试防护之后,`test_paths` 就是 `roles.tester`;非删除、不命中只追加路径。只删测试那条带了 `--allow-deletion`,拒它的是这一道。
- **红绿**:`changes --test-gap` 把期望改成 RED,绿时单独文案点名 `approve --test-gap`;`approve --test-gap` 不动期望(review-impl 本来 GREEN)。
  W17 的捷径要求 `green`,红着打回不会被它改走;打回计数仍走 `verdict == "changes"`,死锁闸与第二次打回的决策闸没动。
- **正文** `测试缺口: <说明>`(去首尾空白)、简报两种用法、argparse 帮助、`HANDOFF_INVARIANTS` 加 `review-test-gap`;`SKILL.md` 规则 6、`rules.md`、`protocol-spec`(不变量表顺延)、
  `command-reference`、`architecture`、`troubleshooting`、README 计数 17 → 18、开放条目 58 —— 措辞与契约一致。
- 没有针对用例输入的特判:`tests/W1-缺口`、`checks/mutations.txt`、说明原文都不在实现里。

## 变异点

登记 10 个(`缺口_` 前缀),`--only 缺口_` 全被抓到:契约列的七个(不限 review-impl、不限有 review-test 的流程、`changes --test-gap` 不要求 RED、不要求动测试、
只追加文件算作补用例、带旗标不放开 tester 路径、空说明放行),加评审阶段都放行(守"dev 带")、删除算作补用例、正文不写 `测试缺口:`。

## 没覆盖到的

- `status` 的"可写路径"一行在 review-impl 不显示带旗标后放开的路径(dev 在 notes 里写明了,简报另有一段说明),契约没要求,不算问题。
- `affected_test_cmd` 配了时新用例会不会被选中,契约没说,没有用例。
