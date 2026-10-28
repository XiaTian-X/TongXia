# W72 — review-impl(tester)

结论:**打回**,一处与契约不符。

## 打回的那一处

`.agents/skills/pair-protocol/scripts/pair.py:3630`(`understand_draft_problem` 收集引用的那一行):`refs` 收的是 PLAN 那段 diff 里**任何一行新增的** `对应契约`,
不管它属于哪个工作项、那个工作项是不是新增的 cover。契约原文是"每个新增小节的标题被至少一个**新增 cover 项**的 `对应契约` 引用"(dev 自己那份开工前校验也是这么读的:
"该工作项块的新增行里");`architecture.md` 新加的那一行也写"各有新增 cover 项引用"。

探针实测两种都放行(`resume` 退出码 0):

1. **一个 cover 项都不加**:PLAN 的 diff 只在已有的 `W2` 下面加一行 `- 对应契约:… → 解析器的现状`。`items` 为空 → "不是 cover"那条没东西可判;`refs` 里有这节 → "没被引用"也过。
   这份草案落地之后,新契约节没有任何特征测试的工作项 —— 正是 understand 要防的"拿一份没人核实过的规格开工"。
2. **cover 项引用的是别处**:新增 `C1 [cover]` 引用 `W1`,新节的引用加在已有的 `W2`(feature)下面 —— 照样放行。

**修法方向**:引用只从**新增的 cover 项自己的块**里收 —— 从一行新增的工作项行(`ITEM_RE`)起,到下一个工作项行或段落结束为止,这之间新增的 `对应契约` 才算那个 cover 项的引用;
不在新增工作项块里的 `对应契约` 不算。

## 其余查过、成立的

- 进入:`--understand` 只在 idle;工作阶段带它、idle 不带它各有文案;额度判定整段跳过;`mode`/`speeches` 写进现场;正文第一行 `understand=open role=…`,`report` 认不出它。
- 讨论回合 `speeches` 加 1,正文 `understand=reply role=…`(`ratify` 按第一行取角色,取得到)。
- `resume`:发言数 = `speeches` + 本回合追加;`--no-draft` 空理由拒绝、普通 discuss 带它拒绝(契约没写,拒绝是合理的选择);恢复回 idle、不记 `discussed`;
  正文写提案路径与哈希,输出给出 `ratify` 命令。签字只认最后一个块、路径只许 PLAN 与契约、`## ` 小节按新增行切、`ARCHAEOLOGY_SHA_RE` 加 `cat-file -e <sha>^{commit}`、新增工作项按 `ITEM_RE` 判类型(缺省 feature)。
- `status` 的 understand 简报含独立理解的约定、交叉检查、草案要求与 `--no-draft`。文档(protocol-spec §5.6.1、architecture 四行、brownfield、rules、troubleshooting、SKILL.md)与 `ENFORCEMENTS` 三个 id 跟上。

## 关于用例

上面两种情况我的用例没覆盖(`test_某个新增小节没被_cover_引用` 只造了"有一节完全没人引用")。review-impl 回合我只能追加变异点、不能加用例。
建议:你修完之后,在 review-test 里以"缺这两条用例"打回给我,我补上 —— 走 W17 捷径回 review-test,不多绕。

---

# W72 — review-impl 第二次(tester)

结论:**通过**。

- 修法与打回时说的一致:`_diff_lines` 保留上下文行与删除行的位置,`_cover_refs` 只从新增工作项行起、连续的新增行里收 `对应契约`,工作项是 `[cover]` 才算;
  遇到上下文行、删除行或下一个工作项行就断。挂在已有项下的引用不再算。
- 探针重跑:上回那两种草案(一个 cover 都不加、cover 引用别处而新节引用挂在 feature 旧项下)现在 `resume` 都被拒;对照组 —— cover 项块中间夹一行新增空行 —— 照样放行。
  `test_v1_understand` 22 条绿。契约小节的切分只读新增行,与修之前同口径。

## 变异点

登记 15 个(锚点各只出现一次),`--only "理解_"` 全部被抓到,基线全绿:契约列的九个(idle 不带也放行、工作阶段带它放行、不数发言、不查签字、不查考古观察的 sha、
不查只加 cover、不查每节有 cover 引用、`--no-draft` 不生效、resume 记了 `discussed`),加上额度照算、`speeches` 不加、签字不限最后一块、不查别的文件、不要求新增小节、不查考古观察。

"引用不限于新增 cover 项的块"这一个**没登记**:我的用例现在抓不到它 —— 正是上回说的缺口。请你在 review-test 以"缺这两条用例"打回,我在 spec 回合补用例并同时登记它。
