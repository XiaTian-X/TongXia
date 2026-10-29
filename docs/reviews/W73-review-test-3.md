# W73 — review-test 第二次(dev)

结论:**通过**。

## 这次补的,逐条查过

- `test_名字只在_tester_的测试文件里_不报漂移`(`tests/conformance/test_v1_contract_shape.py:323`):类 `TestDriftNegativePatterns` 用 `GO_CONFIG`,
  dev 是 `**/*.go` + `!**/*_test.go`。名字只在 `pkg/widget_test.go` 里,`widget.go` 只有 `package` → 不报。两边模式拼成一个列表时 dev 的负模式会排除测试文件,这条变红。
  这是 review-impl 第一次打回的探针。
- `test_对照_两边都没有照报`(`:329`):同样的布局,测试文件里也没有这个名字 → 报漂移。没有它,上一条的"不报"可能只是 Go 布局下根本没查。我打回时没要这条,补得对。
- `test_中文紧挨着的调用名也抽`(`:301`):代码块只有 `// 调用build_gadget(spec)`,`src/` 下没有 → 报漂移且文案含 `build_gadget`。`spec)` 后面没有 `(`,所以前边界改回 `\b` 后一个名字都抽不到、整节不查,这条就变红。
- 两个变异点:
  - `形状_漂移两个角色的模式拼成一个列表`:锚点是 `identifiers_tracked` 里那行 `if not (matches_any(...) or matches_any(...)):`;
  - `形状_抽名字的前边界改回_b`:锚点是 `_IDENT_CALL_RE` 的前缀。
  两个锚点在 `pair.py` 里都只出现一次,我用 `--full` 不走缓存各跑了一遍,都被抓到。`--only "形状_"` 20 个全抓。
- `test_v1_contract_shape` 39 条全绿。

## 其余

上一次评审(`W73-review-test-2.md`)列的"成立的"几条这次没有变动:断言都在可观测输出上、每节只触发一条检查、范围与严格模式对上判据。
契约在我开工前校验(`a4b35e0`)之后没有改动,不需要重做校验。

小事,不打回:`_IDENT_DEF_RE` 的前边界没有单独登记变异点。`def`/`class` 前面紧挨中文的写法少见,而且 `def` 的名字后面通常就跟着 `(`,调用那条会兜住。
