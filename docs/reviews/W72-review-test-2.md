# W72 — review-test(dev)

结论:**打回**。缺两条用例,两条都是 tester 在 review-impl 里自己指出、自己提议在这里补的。

## 缺的两条

`tests/conformance/test_v1_understand.py:265`(`test_某个新增小节没被_cover_引用`)只造了"新增小节完全没人引用"。"每个新增小节被至少一个**新增 cover 项**的 `对应契约` 引用"
里的"新增 cover 项"这半句,现在没有用例在判 —— 把 `_cover_refs`(`.agents/skills/pair-protocol/scripts/pair.py:3592`)换回"PLAN diff 里任何新增的 `对应契约` 都算",22 条照样全绿。
review-impl 第一次打回的就是这个,修好了,但没有用例守着,下次改回去不会有任何东西变红。

1. **一个 cover 项都不加,引用挂在已有项下**:PLAN 的 diff 只在已有工作项(harness 里最后一个是 `W2`)的块末尾新增一行 `- 对应契约:… → 解析器的现状`,不加任何工作项。应被拒。
   `draft()` 把 `plan_add` 追加在 PLAN 末尾,正好落进 `W2` 的块里,不用改夹具。
2. **cover 项引用别处,新节的引用挂在已有项下**:新增 `C1 [cover]` 引用 `W1`,新节的那行引用放在 `C1` **之前**(也就是落进 `W2` 的块)。应被拒。
   顺序要紧:放在 `C1` 后面就成了 `C1` 自己块里的引用,那是合规的。

同时登记变异点:"引用不限于新增 cover 项的块"(比如让 `_cover_refs` 不看 `cur == "cover"`、遇到上下文行不断开)。这两条补上之后它应该被抓到。

## 可选,由你决定

`--no-draft ""`(空理由)被拒、普通 discuss 的 `resume` 带 `--no-draft` 被拒,这两处实现里有(`pair.py:3520`、`3531`),没有用例。契约没写死这两条,你在 review-impl 里说拒绝是合理的选择;
空理由放行会让"已声明"变成一句空话,我倾向补一条,但不作为打回理由。

## 其余查过、成立的

- **口径都是可观测行为**:状态字段(`phase`、`discuss.mode`、`speeches`、`discussed`)、提交正文第一行、`whose-turn`、`report` 的行、拒绝时提交数与 `state.json` 不变。
  没有断言私有函数或文案细节,唯一的文案断言是"idle 不带它的拒绝含 `--understand`"和"简报含独立",两者都是契约写明的。
- **草案用真 `git diff` 造**(`draft()` 改、取 diff、还原),签字走真 `sign`,落地走真 `ratify`:放行用例从开场一路走到人类 `ratify` 把新节和 `C1` 写进 PLAN/契约,是完整走通的一条。
- **被拒的七条**各只破一个条件,其余部分都是合规草案的原样(同一个 `draft()` 默认值),所以红只能归到那一条:缺签字、签的不是最后一块、碰别的文件(先提交那份文件,确保 diff 真的碰到已有文件)、
  没新增小节、没写考古观察、sha 不存在(`deadbeef0123` 形似 sha、格式过、仓库里没有)、PLAN 新增了 feature。
- **交叉检查**:两次发言、本回合不追加 → 被拒且状态不变;追加之后放行。这正好区分了"数 `speeches`"和"把本回合追加算一次"。
- **额度**:`discuss_limit = 0` 照样能进,`resume` 后 `discussed` 为空,同时判了"不计额度"和"不记 discussed"。
- **`report`**:走完一次 understand 后"讨论"一行是 0。
- 15 个变异点覆盖了契约列的九个加实现里另外六处检查;锚点唯一由文档一致性检查守着,全部被抓是 tester 在 review-impl 第二次里报告的。

小事,不打回:`test_v1_understand.py:211` 的 `import hashlib` 写在用例里,其他地方都在文件头导入。
