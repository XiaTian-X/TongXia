# W24 — review-test(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

- **锚点**:`mutation_check.py` 新登记的「verify-setup 不警告 refactor 缺保护测试」,old 串在 `pair.py` 里恰好出现 1 次。
- **变异在隔离克隆里实跑**(`.pair/scratch` 外的 scratchpad 克隆,`PYTHONDONTWRITEBYTECODE=1`):
  - 把 `if not refs:` 改成 `if False:` → `test_v1_brownfield` + `test_v1_shipped` 41 条里只红
    `test_verify_setup_对没声明保护测试的_refactor_照旧警告` 一条;样板那两条照绿 —— 正好说明你补正面是对的,
    "样板里不出现警告"单向,拆掉警告它守不住。
  - 删掉样板 W4 的 `保护测试: tests` → `TestDemoPlanIsReady` 两条都红。
  - 干净克隆 41 条全绿。
- **不是变更探测器**:判据是 `PROTECT_REF_RE`(脚本自己用的那个正则,不是手抄一份)与 verify-setup 的既有警告前缀
  "没声明保护它的测试";对照组只差那一行,两条共用同一份 `_plan`。
- **`TestDemoPlanIsReady` 按块切 PLAN**:`re.split` 在每个 `- [ ] **` 行首切块,refactor 块取到 W4 自己的子弹行,
  不会把相邻工作项的 `保护测试:` 算到 W4 头上;`assertTrue(refactors)` 防"没有 refactor 项就恒绿"。
- **`_verify` 的环境**:`env` 只给 `PAIR_ROLE` 和 `PATH`,与已有的 `test_开工前校验只卡在契约审查结论那一步` 同口径;
  `TestDemoProject._make(self)` 借用时 `addCleanup` 落在调用方用例上,临时目录会被清掉。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W24`(tester spec 回合写的),晋升闸有着落。

## 未覆盖

- **保护测试指向"还不存在的文件"不会红**:把样板 W4 改成 `保护测试: tests/test_slugify.py`,两条样板用例照绿
  (verify-setup 那条只是警告,而用例只断言没有"没声明"那句)。按契约这不是缺陷 —— 到认领 W4 时 W1 已经写出了那个文件;
  我选 `tests` 是为了新用户开工时少一条警告,这个选择目前没有用例钉住。记在这里,不要求。
- 正面用例的 `assertIn("R1", r.text)` 偏弱(`R1` 也出现在别的输出里),承重的是第二句;不影响裁决。
- **孤儿 8 个与入口文件缺激活段落**:不在本项,完成后进路线图(review-test 回合我写不了 `docs/improvements.md`,
  交给下一回合或人类)。
