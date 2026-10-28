# W73 — review-test(dev)

结论:**打回**。缺两条用例,守的是 review-impl 打回修掉的两处;tester 在 review-impl 第二次里已说明这两处的变异点现在登记会是"没抓到",要等用例补上。

## 缺的两条

1. **Go 同目录布局下,名字只在测试文件里 → 不报漂移。** `tests/conformance/test_v1_contract_shape.py` 的 `TestDrift.test_函数名在测试目录下存在也不警告` 用的是 harness 默认布局(`tests` / `src`,没有负模式),
   把 `identifiers_tracked`(`.agents/skills/pair-protocol/scripts/pair.py:4721`)改回 `matches_any(f, tester + dev)` 照样绿。
   请用 `GO_CONFIG`(harness 里的测试命令只查 `*_test.go` 有同名 `.go`,不需要 Go 工具链):cover 项引用的小节代码块是 `make_widget(spec)`,
   `pkg/widget_test.go` 里调用它、`pkg/widget.go` 只有 `package pkg` → 不该有提到这一节的条目。对照组可以不另写(`test_函数名在_src_下存在不警告` 的反面已有)。
2. **名字前紧挨中文也能抽出来。** 代码块只有 `// 调用build_gadget(spec)`,cover 项引用,`src/` 下没有这个名字 → 报漂移且文案列出 `build_gadget`。
   把 `_IDENT_CALL_RE`(`pair.py:4645`)的前边界改回 `\b` 时它会变成"抽不到不查",一条都不报。

同时登记这两个变异点(两边模式拼回一个列表、抽名字前边界改回 `\b`)。

## 其余查过、成立的

- 断言都在可观测输出上:退出码、`[警告]` / `[失败]` 分条之后提到小节名的那几条、工作项 ID、标识符、`strict_contract` / `阻断` 字样;不依赖文案措辞的其余部分,也不依赖三条检查的先后。
- 每个小节只造"一条检查会触发"的形状(有关键词没形状 / 有形状没关键词 / 两样都有),红只能归到那一条;只有散文的两条都触发,只断言至少一条 —— 不依赖实现怎么分条。
- 范围三条(待核实不查、已完成不查、同一节只报一次并列出 W1 与 W2)、严格三条(两条升失败、漂移仍警告、非布尔值失败)、默认通过,都对上契约的判据。
- 原样复制的模板与「不做」用的是真 `init` 铺出来的文件,不是用例自己抄的模板。
- 18 个变异点(契约列的八个加十个)tester 报告 `--only 形状_` 全抓。

小事,不打回:`TestDrift` 的 `test_函数名在测试目录下存在也不警告` 为了满足 harness 的测试命令放了一个 `src/probe.py`,注释已说明,不影响它测的东西。
