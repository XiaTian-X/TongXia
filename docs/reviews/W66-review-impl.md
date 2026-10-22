# W66 — review-impl(tester)

结论:**通过**。另有一处是**我的用例**守不住,请在 review-test 打回给我补(见最后一节)。

## 查过的地方

- `writable_paths`:在"评审只读"那两行锚点**之前**、非 idle 时把提案并进可写清单 —— 锚点原样;四个工作阶段两个角色都可写,不并进 `shared_paths`。
- `proposal_rewrite`:提案目录顶层 `.md`、已在 HEAD、相对 HEAD 有删除行 → 违例;挂在评审改写那道之后的第二个循环里,不分阶段与角色;删除也走到(`has_rewrite` 数删除行)。
- 四处不认它:异议举证、位置引用、评审命名都还只读 `shared_paths`,没碰;规范性文档另起一支跳过提案。
- scope 豁免、W57 指纹(连带 W60 路径)排除、`inbox` 散文路径、交接正文 `提案:` 一行、`init` 模板 —— 各一处,与契约逐项对上。
- `proposal_overlaps` 按 ⑳:两边代表路径互相匹配;不含通配符的取本身与 `<它>/x.md`,含通配符的换具体名字(字符类取第一个字符),负模式不参与;失败信息点名键(`roles.tester` 这种带角色名的写法也含 `roles`)。
- `ENFORCEMENTS` 加 `proposal-append-only`;`rules.md`、`protocol-spec.md`、`command-reference.md`、`architecture.md`、`INSTALL.md`、路线图(D1 ✅、`artifact_paths` 评估点结论)跟上。

## 变异点

登记九个(锚点各只出现一次)。`--only "提案_"`:八个被抓到 —— 评审阶段不可写、不查只能追加、不查重叠、要求 `--doc-reason`、进指纹、不豁免 scope、
正文不写提案行、`init` 不写提案目录;**`提案_inbox_不摆出` 存活**。

## 存活的那一个是我的用例的问题,不是实现的

`inbox` 在"对方这一回合写给你的"那一节之前,先把 HEAD 的完整 diff 打出来了 —— 提案的原文就在 diff 里。我的 `test_对方的_inbox_摆出提案原文`
只断言"输出里有那句话",diff 就满足了,拆掉散文那一节照样绿。正是第十几轮记过的"被别处的输出满足"那种失效。
请在 review-test 以"缺这条用例"打回,我把断言收窄到"对方这一回合写给你的"那个标题**之后**,并重跑这个变异点。实现不用改。

## 没覆盖的

- 提案目录是 glob 模式时"顶层"的含义(父目录与模式字符串相等才算)只对不含通配符的模式成立 —— 契约的默认与 `init` 都是 `docs/proposals`,接受。
