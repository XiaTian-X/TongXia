# W73 review-impl —— 契约形状检查

**裁决:打回(changes)。** 一处偏离契约(漂移把 tester 名下的文件漏了),一处同类的顺手修。其余逐条对过,没问题。

## 问题

### 1. 漂移判"在不在两个角色名下"时把两边的模式拼成一个列表,`!` 负模式会互相吃掉 —— `.agents/skills/pair-protocol/scripts/pair.py:4717`

`pats = cfg["roles"]["tester"] + cfg["roles"]["dev"]` 再 `matches_any(f, pats)`(:4720)。`matches_any` 的语义是"命中任一正模式且**不命中任何**负模式"(:463),
于是 dev 的负模式会把 tester 自己的文件排除掉。Go 同目录布局(harness 的 `GO_CONFIG`:tester `**/*_test.go`,dev `**/*.go` + `!**/*_test.go`)下,
`*_test.go` 一个都不算 —— 契约写的是"在 `roles.tester` 与 `roles.dev` 名下的已跟踪文件里"。

探针(`.pair/scratch/`,已删):`GO_CONFIG`,cover 项 C1 引用的小节代码块里是 `make_widget(spec)`,`pkg/widget_test.go` 里调用了 `make_widget`、`pkg/widget.go` 只有 `package pkg`
→ 报了"契约小节 '部件构造'(C1 引用)可能已经和代码对不上:代码块里的 make_widget 一个都不在 roles.tester / roles.dev 名下的已跟踪文件里",文案自己就和事实相反。
对照组(名字在 `widget.go` 里)不报。JS/TS 的同目录测试(`dev: src, !src/**/*.test.ts`)同理。

**修法**:分别判,`matches_any(f, tester) or matches_any(f, dev)` —— 同一个函数上面边界重叠那段(`cmd_verify_setup` 开头)就是这么分开判的。

### 2. 抽名字的 `\b` 在中文紧挨着时不成立 —— `pair.py:4644`、`:4645`

notes 里写了"匹配用 ASCII 前后断言而不是 `\b`:`\b` 在中文紧挨着名字时不成立",可抽取那一侧的 `_IDENT_DEF_RE` / `_IDENT_CALL_RE` 仍是 `\b`。
Python 的 `\b` 按 Unicode 判,`调用build_gadget(spec)` 里"用"与 `b` 都是词字符,`build_gadget(` 抽不出来,整节"抽不到不查" —— 漂移漏报。
探针:代码块只有 `// 调用build_gadget(spec)`,cover 项引用,`src/` 里没有这个名字 → 没有任何一条提到该节。契约是"`名字(` 形态"。
**修法**:抽取也用 `(?<![A-Za-z0-9_])`。这条只造成漏报、不改任何已有结论,和第 1 条一起改。

## 逐条查过、没问题的

- 范围:`shaped_refs` 在逐项循环里收集,前面的 `continue`(没引用、重名、不存在)已把这些排掉,`if ok:` 只收可断言的;`pending` 不含已完成项。待核实的小节上面那条旧警告照旧。
- 正文:`contract_sections_full` 找标题前把围栏换成**等长**空白,切原文 —— 偏移不错位,代码块整块留着,`# 注释` 行不再当标题;同名小节 `setdefault` 取第一个,重名本来就单独 `bad` 并跳过。
- 形状:围栏内容去掉首尾两行后判非空;表格只在围栏外找,分隔行只由 `|-: ` 组成且上一行有 `|`,数据行到第一行不含 `|` 为止,去掉竖线还有字才算。模板的两张空表不算。
- 关键词:去掉 HTML 注释之后对全文(含代码块)小写匹配;注释可跨行(`re.S`)。
- 严格:`strict = cfg.get("strict_contract") is True`,非布尔值另一处 `bad`(此时 `is True` 不成立,不会把检查也升级);漂移始终 `warn`,文案不含"阻断"。
- 只报一次:三条检查在循环之后按小节各跑一次,文案 `ids` 列出全部引用者,漂移只列 cover/refactor/bug。
- 没有针对用例输入的特判:`部件构造`、`make_widget`、`W1`/`C1` 都不在实现里。
- 模板补了「不做」;`ENFORCEMENTS` 加 `contract-shape`,`protocol-spec` §5.4 表、§7 配置、`command-reference`、`architecture`、`troubleshooting`、`rules.md`、路线图 P0-3 都跟上了,措辞与契约一致。

## 测试侧的缺口(review-test 时再说)

第 1 条是实现与用例同时漏的:harness 默认布局没有负模式,`test_函数名在测试目录下存在也不警告` 照样绿。修好之后,review-test 那一轮我需要补一条 `GO_CONFIG` 布局的用例(路线图开放条目 58 说的正是这种情况)。
变异点等这一轮通过时登记。

---

# W73 review-impl 第二次 —— 通过(approve)

dev 按打回改了两处,都与打回描述一致:

- `identifiers_tracked`(`pair.py:4721`)改成 `matches_any(f, tester) or matches_any(f, dev)` 分别判。复跑上次的探针:`GO_CONFIG` 下名字只在 `pkg/widget_test.go` 里 → 不报;
  两边都没有 → 报。
- `_IDENT_DEF_RE` / `_IDENT_CALL_RE`(`pair.py:4644`–`4645`)前边界改成 `(?<![A-Za-z0-9_])`。探针:代码块只有 `// 调用build_gadget(spec)`、`src/` 里没有 → 报,文案列出 `build_gadget`。
- 改动只有这两处(diff 9 行),其余与第一次审过的一致。

## 变异点

登记 18 个(`形状_` 前缀),`--only 形状_` 全被抓到:契约列的八个(不查子小节、空数据行的表也算、不去 HTML 注释、不可断言的也查、严格模式不升级、
漂移不限工作项类型、漂移在严格模式下也升级、漂移把 `docs/` 也算进去),加十个:围栏里的井号当标题、漂移不按整词、漂移只认 dev 名下、关键词区分大小写、
关键词不看代码块、不抽 `class` 后的名字、非布尔值照收、空代码块也算形状、漂移附上会阻断、同一节每个引用者各报一次。

## 还没登记、留给 review-test 的

这两条打回修好的行为,现有用例都抓不到(harness 默认布局没有负模式,用例里也没有中文紧挨着的名字):

- 两个角色的模式拼回一个列表(`matches_any(f, cfg["roles"]["tester"] + cfg["roles"]["dev"])`);
- 抽名字的前边界改回 `\b`。

现在登记它们会是两个"没抓到"。等 review-test 补了 `GO_CONFIG` 布局与中文紧挨两条用例,再一起登记。
