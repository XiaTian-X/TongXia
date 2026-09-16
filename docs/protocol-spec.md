# 协议规格

> 规范性文档。描述 `pair.py` **实际**的行为。
> 与实现不一致时以 `pair.py` 为准,并且那是一个需要修的 bug。
>
> 关键词:**必须** / **不得** / **应当**。前两者由脚本强制,后者靠留痕与评审。

## 1. 角色

两个角色,`tester` 与 `dev`。

### 1.1 角色解析

按优先级依次尝试,先命中先用:

1. 环境变量 `PAIR_ROLE`
2. 文件 `.pair/whoami`(内容为角色名,首行)
3. 当前 git 分支名形如 `pair/<角色>`

三者都没有时脚本**停止**并要求 agent 去问人类。角色**不得**由 agent 自行假定。

### 1.2 默认写权限

| | tester | dev |
|---|---|---|
| 可写 | `tests/` | `src/` |
| 不得写 | `src/` | `tests/` |
| 职责 | 把工作项翻译成**会失败**的测试 | 让失败的测试变绿 |

实际路径以 `.pair/config.json` 的 `roles` 为准。两个角色的路径集合
**不得**存在交集 —— 这是零冲突保证的全部来源,`verify-setup` 会拿真实文件树
逐个试匹配并报出重叠。

## 2. 阶段与归属

| 阶段 | 归属 | 含义 |
|---|---|---|
| `idle` | tester | 无工作项在进行,等认领 |
| `spec` | tester | 写失败的测试 |
| `impl` | dev | 最小实现至绿 |
| `review-impl` | tester | 审实现是否作弊 |
| `review-test` | dev | 审测试是否过拟合 |

`review-impl` 与 `review-test` 是**评审阶段**,只读:本回合只能写
`shared_paths`(默认 `docs/reviews`)与记忆层路径。夹带任何代码改动都会被拒绝。

`impl` 是**异议阶段**:dev 在此可以用 `handoff changes` 打回,详见 §5.3。

## 3. 工作项

### 3.1 PLAN 格式

`docs/PLAN.md` 里的工作项**必须**是这一行形态,`claim` 靠它识别:

```markdown
- [ ] **W1** [feature] — 标题
  - 验收标准:<可观测的、能写成断言的条件>
  - 对应契约:`docs/CONTRACT.md` → <小节名>
```

- 类型标记可省略,缺省 `feature`。
- `对应契约` 那一行是**必须**的,`verify-setup` 会检查它指向的小节真实存在。
- 完成时由脚本把 `[ ]` 勾成 `[x]`。这是脚本的权限,不是 agent 的。

### 3.2 类型与流程

| 类型 | 起始阶段 | 转移 | 红绿要求 | 额外强制 |
|---|---|---|---|---|
| `feature` | `spec` | spec→impl→review-impl→review-test→DONE | spec=**RED**,其余=**GREEN** | — |
| `bug` | 同 `feature` | 同 `feature` | 同 `feature` | — |
| `cover` | `spec` | spec→review-test→DONE | 全程 **GREEN** | spec 回合**必须**新增或修改测试文件 |
| `refactor` | `impl` | impl→review-impl→DONE | 全程 **GREEN** | impl 回合**必须**交出考古记录 |

打回边:

| 从 | 裁决 | 到 |
|---|---|---|
| `review-impl` | `changes` | `impl` |
| `review-test` | `changes` | `spec` |
| `impl` | `changes`(异议) | `spec` |

不在表内的 `(阶段, 裁决)` 组合被拒绝,提示"状态可能已损坏"。

**只涉及测试的打回走捷径**(`feature` / `bug`):`review-test changes` 之后的 spec 回合,若交接时
**GREEN**、这一回合**实际没改**规划或契约、且契约与最近一次 review-impl approve 时的工作区内容相同,
下一阶段是 **review-test**,跳过 impl 与 review-impl —— 实现在那之后没有人能改过。
任一条件不满足、或状态里没有记录(老状态),照旧进 impl。死锁计数不因捷径清零。

### 3.3 认领

`claim <ID>` 的前置条件,任一不满足即拒绝:

- 执行者是 `tester`
- 当前阶段是 `idle`
- `require_setup_verification` 为真时,`state.setup_verified` 必须为真
- 同上为真时,**执行者这个角色**上次通过校验时读的契约
  (`state.setup_verified_contract[<角色>]`,取**工作区内容**的 blob sha)必须和现在
  工作区里的一致;记录缺失或契约读不到都算不一致 —— 契约改过就要重跑 `verify-setup`
- 工作项存在于 PLAN、未完成、类型合法
- `state.json` 未被篡改

成功后:写入 `item` / `item_type` / `phase`(该类型的起始阶段),
`changes_count` 归零,记录 `contract_sha`(契约文件当前的 git blob sha),
并**立即提交** —— 既是留痕,也让 state 文件回到"干净",
否则下一次 `handoff` 的篡改检测会误伤它。

## 4. 不变量

`handoff` 按以下顺序校验。任何一条不过即拒绝提交,**不得**绕过。

<!-- pair-enforcements: turn-ownership project-done state-untampered verdict-valid transition-valid write-boundary test-deletion new-tests review-naming dispute-evidence review-evidence archaeology-sha document-shape memory-gate red-green deadlock -->

| # | 不变量 | 触发条件 |
|---|---|---|
| 1 | 回合归属 | 执行者必须是当前阶段的归属角色 |
| 2 | 项目未结束 | PLAN 里还有未完成的工作项 |
| 3 | 状态未被篡改 | `.pair/state.json` 在工作区里未被改动。改动即还原为上次提交的版本并拒绝 |
| 4 | 裁决合法 | 评审阶段必须给 `approve`/`changes` 且理由非空;`approve` 只能出现在评审阶段 |
| 5 | 流程合法 | `(阶段, 裁决)` 在该类型的转移表里 |
| 6 | 写权限边界 | 每个改动文件必须命中当前阶段的可写路径,不在 `frozen_paths` 下,且(配了 `scope` 时)落在 `scope` 内 —— 评审目录与记忆层对 `scope` 豁免。**评审目录顶层已提交的 `.md` 只能追加**:相对 HEAD 有删除行(含删除、改名)即拒绝,不分阶段、不分角色;`verify-setup` 对它那份结论同样判,且拒绝早于写状态 |
| 7 | 测试删除 | 删除 tester 路径下的文件必须带 `--allow-deletion "理由"`。改名按旧路径删除 + 新路径新增判 |
| 8 | 新增测试 | `cover` 的 spec 回合必须有非删除的测试文件改动 |
| 9 | **评审目录命名** | 顶层 `.md` 的名字要对上 PLAN 里某个工作项,或是固定名 |
| 10 | 异议举证 | `impl` 阶段的 `changes` 必须在 `shared_paths` 下写了文件 |
| 11 | **评审证据** | `approve` 必须带 `--checked` 与 `--uncovered`;`changes` 的理由或本回合的评审文件里必须有一处 `路径:行号`,且路径真实存在 |
| 12 | **考古 sha** | `依据: 考古观察@<sha>` 的 sha 必须是真实 commit |
| 13 | **文档形状** | 异议必须存在且三小节;`contract-change-<ID>.md` 四小节;`baseline.md` 两小节 |
| 14 | 记忆层门禁 | 见 §6 |
| 15 | 红绿 | 按类型的 `expect`。**提异议那一回合全豁免**;**打回之后紧接着的 spec 回合只豁免 RED**(cover 的 GREEN 仍然强制),并另外要求本回合真的改动了 tester 路径下的文件 |
| 16 | 死锁闸 | 同一工作项 `changes_count` 达到 3 时停止轮转 |

### 4.1 路径归属判定

一个路径属于某模式集合,当且仅当:**命中至少一个正模式,且不命中任何负模式。**
以 `!` 开头的是负模式。

`.pair/.last-test.log` 与 `ignore_paths` 命中的路径完全不参与边界检查。

`review_append_paths` 里评审阶段执行者名下的路径单独判:文件必须已在 HEAD 里、相对 HEAD 没有删除行,否则拒绝;满足就放行,不再走越界判定。

支持的通配:`*`(不跨 `/`)、`**`(跨 `/`)、`?`、`[...]`。
不含通配字符的模式按**前缀目录**匹配(`tests` 匹配 `tests/a/b.py`)。

### 4.2 红绿判定

`run_tests()` 执行 `PAIR_TEST_CMD` 环境变量或 `config.test_cmd`,
输出重定向到 `.pair/.last-test.log`,**退出码为 0 即 GREEN**。

`cover` 类型在 GREEN 要求未满足时给出专门文案:测试变红说明发现了真实缺陷,
应当告诉人类改成 `[bug]` 类型,**不得**在 cover 回合里放宽断言让它变绿。

### 4.3 死锁闸

`changes_count` 绑定在工作项上,`claim` 时归零。达到 3 时:
写入 state、追加 `deadlock_hits` 留痕、单独提交一次、然后拒绝并要求交给人类。

`approve` 路径**不**被硬锁 —— 打回三次后一方说"我接受"是合理的收敛,
而且它带理由、进提交记录、人类看得见。

## 5. 命令契约

完整用法见 [command-reference.md](command-reference.md)。此处只列规范要点。

### 5.1 status

**必须**是每回合的第一条命令。**在跑它之前不得读代码、不得改任何文件。**

它输出:角色、当前阶段与归属、红绿、本阶段的具体任务,
并在轮到执行者时注入记忆(§6.3)。

`sync` 为真时先 `git pull --rebase`;失败会被上报。

### 5.2 handoff

```
pair.py handoff "说明"
pair.py handoff approve "摘要" --checked "…" --uncovered "…"   # 仅评审阶段
pair.py handoff changes "问题清单"     # 评审阶段,或 impl 阶段的异议
  [--allow-deletion "理由"]
  [--no-decision "理由"]
```

提交信息格式:

```
<前缀>: <说明>

role=<角色> phase=<从> -> <到> item=<ID> type=<类型>
[删除测试(已声明): <理由>\n  <文件列表>]
[未留决策(已声明): <理由>]
```

前缀:`test`(spec)、`feat`(impl)、`review(impl)`、`review(test)`,
带裁决时追加 `/approve` 或 `/changes`;异议路径固定为 `dispute`。

### 5.3 异议路径(dev 在 impl 阶段打回)

dev **不得**改或删测试,一条都不行。测试写错时的**唯一**出路:

1. 在 `docs/reviews/` 写清楚:哪条用例、和契约的哪一条矛盾、应该改成什么
2. `pair.py handoff changes "..."`

回合退回 tester 的 spec 阶段。该路径**豁免红绿不变量** —— dev 正是因为测试
写错、弄不绿才打回的,拿 GREEN 卡它等于逼它照错误断言写实现。
但边界仍然生效:只能写 `docs/reviews/`。

### 5.4 verify-setup

开工前一次性只读校验,由**还没动手的那一方**跑。检查项:

| 检查 | 级别 |
|---|---|
| 角色路径非空 | 失败 |
| 角色路径无重叠(拿真实文件树逐个试匹配) | 失败 |
| 角色路径与 `frozen_paths` 不冲突 | 失败 |
| 角色模式匹配到了已跟踪文件 | 警告 |
| `scope` 把某个角色的文件全排除 | 失败 |
| `scope` 匹配不到任何已跟踪文件 | 警告 |
| 被引用的契约小节写了 `依据` | 失败 |
| 非 `cover` 的待办项指向可断言的小节 | 警告(硬闸在 `claim`) |
| `refactor` 的 `保护测试` 已声明且存在 | 警告(硬闸在 `claim`) |
| `refactor` 的 `保护测试` 不属 tester | 失败 |
| `full_test_cmd` 是绿的 | 警告 |
| 入口文件含协议激活段落 | 警告 |
| 契约审查结论逐节点名(围栏内容不算) | 失败 |
| 给出了 `--drafter self\|other` 声明作者是否参与起草 | 失败 |
| 配了 `full_test_cmd` 就该有 `docs/reviews/baseline.md` | 警告 |
| `test_cmd` 已配置且基线全绿 | 失败 |
| PLAN 有合法工作项,类型合法 | 失败 |
| 每个工作项都指向存在的契约小节 | 失败 |
| 记忆层路径不在 `roles` 之下 | 失败 |
| 记忆层路径不在 `frozen_paths` 之下 | 失败 |
| 记忆层路径不在 `shared_paths` 之下 | 失败 |
| `SKILL.md` 存在 | 失败 |
| 各家入口文件齐备 | 警告 |
| **契约歧义审查结论已提交且 ≥120 字** | 失败 |

最后一条是脚本查不了的那件事的替代品:它至少强制交出一份结论。
没有歧义就明确写"无歧义"并说明逐条核对了什么 —— 空泛的一句"看过了"不算。

通过后写入 `state.setup_verified = true`,并按执行者的角色记下这次读的是哪一份契约
(`state.setup_verified_contract`),此后才能 `claim`。契约之后再变,那个角色就要
重跑一次 —— 对方重跑不能替它解锁。

## 6. 记忆层

### 6.1 两个位置

| | `docs/notes/<工作项ID>.md` | `docs/DECISIONS.md` |
|---|---|---|
| 寿命 | 工作项级 | 项目级 |
| 内容 | 负空间:试过什么没成、否掉了什么、哪里拿不准 | 结论与裁决 |
| 格式 | 无 | 四个必填字段,受校验 |
| 写法 | 随手写 | **追加式**,不得改历史 |
| 谁写 | 当前回合持有者 | 双方 |

两者两个角色都能写,评审回合也能写 —— 它们是散文,不是代码。
但**不得**并进 `shared_paths`:异议举证检查认的是 `shared_paths` 下的文件,
笔记若也算数,那条防护会被随手写的笔记静默满足。`verify-setup` 会检查这一点。

同理,记忆层路径**不得**落在 `roles` 之下(会变成单方私有)或 `frozen_paths`
之下(永远写不了)。

### 6.2 决策条目格式

```markdown
## <工作项ID> — <标题>
- 理由:<为什么是这个结论>
- 已否决:<考虑过但放弃的方案>
- 影响路径:<逗号分隔的路径,这是检索键>
```

- 三个字段缺一不可(`理由` / `已否决` / `影响路径`)。
- 单条**不得**超过 1500 字符。
- 已写下的条目**不得**修改。要推翻就追加一条说明为什么推翻。
  改动历史会被 `handoff` 检测并拒绝,与手工改 `state.json` 同级。
- 往 `DECISIONS.md` 写了内容但解析不出条目,同样被拒 —— 解析不出来的东西
  `status` 永远召回不到,等于没写,而 agent 会以为自己记录了。
- **故意没有"分析"字段。** 只共享事实和裁决,不共享推理过程。

`影响路径` 是检索键,**应当**写准写全。写漏了,这条结论就等于不存在。

### 6.3 召回

`status` 在轮到执行者时自动注入:

- 本工作项笔记全文,上限 3000 字符(超出取尾部)。笔记为空时打印一段提示,
  而不是静默跳过
- 相干的决策条目,上限 2000 字符 / 最多 5 条(取最后 5 条)

一条决策被判为"相干",当且仅当满足其一:

1. 它的工作项 ID 就是当前工作项;
2. 它的 `影响路径` 与**本阶段主体路径**有交集。

主体路径按阶段取:`spec` 与 `review-test` 取 tester 路径,
`impl` 与 `review-impl` 取 dev 路径,`idle` 取两者之和。

召回是**纯路径求交,不做语义检索** —— 这套协议连 LLM 的红绿判断都不信,
更不该把召回押在检索命中率上。代价是 `影响路径` 必须写准写全。

### 6.4 四个强制时刻

其余时候想写就写,这四处不写会被 `handoff` 拒绝:

| # | 时刻 | 要求 |
|---|---|---|
| ① | `refactor` 的 impl 回合 | 笔记必须有三个小节:`## 现状考古` / `## 我保留了哪些契约外行为` / `## 我不确定的地方`,每节正文 ≥40 字 |
| ② | 同一工作项**第二次**被打回 | 必须在 `DECISIONS.md` 留一条本工作项的条目 |
| ③ | 契约在本工作项期间被改过 | 完成时 `contract_sha` 变了则必须有对应决策条目 |
| ④ | 工作项完成且笔记 ≥80 字符 | 要么晋升成决策,要么 `--no-decision "为什么没有"` |

第三次打回不再要求写 —— 那时该说的已经说完了,再要一份文档只是噪音,
而且死锁闸会接管并交给人类。

`memory` 配置为 `false` 时,以上四个时刻全部失效,`status` 也不再注入。

## 7. 配置 schema

`.pair/config.json`,由人类维护,agent 只读。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `test_cmd` | string | 探测 | 测试命令。可被 `PAIR_TEST_CMD` 覆盖 |
| `roles.tester` | string[] | `["tests"]` | tester 可写路径/glob。**与 dev 不得重叠** |
| `roles.dev` | string[] | `["src"]` | dev 可写路径/glob |
| `shared_paths` | string[] | `["docs/reviews"]` | 双方任何阶段都能写。异议举证认这里 |
| `frozen_paths` | string[] | `["docs/PLAN.md","docs/CONTRACT.md",".agents",".claude",".pair"]` | agent 一律不得修改 |
| `ignore_paths` | string[] | `[]` | 完全不参与边界检查的构建副产物 |
| `review_append_paths` | object | `{}` | `{角色: [路径]}`。评审阶段的执行者可以往自己名下**已提交**的这些文件**只追加**(没有删除行,中间插入也算);不是 `shared_paths`,其他阶段不可写 |
| `scope` | string[] | `[]` | 本轮结对能碰的范围。空 = 不限。评审目录与记忆层豁免 |
| `full_test_cmd` | string\|null | `null` | 全量套件。只在工作项完成时跑一次,**只报告不阻断**(退出码 2) |
| `plan_file` | string | `docs/PLAN.md` | — |
| `contract_file` | string | `docs/CONTRACT.md` | — |
| `sync` | bool | `false` | 分离工作副本拓扑:status 前 pull,handoff 后 push |
| `require_setup_verification` | bool | `true` | 关掉则 claim 不检查开工前校验 |
| `notes_dir` | string | `docs/notes` | 工作项笔记目录 |
| `decisions_file` | string | `docs/DECISIONS.md` | 决策记录 |
| `memory` | bool | `true` | 关掉则记忆层的强制与注入全部停用 |

### 7.1 布局示例

**目录切分**(最常见,也识别 `test/` `spec/` 和 Java 的 `src/test`—`src/main`)

```json
"roles": { "tester": ["tests"], "dev": ["src"] }
```

**Go 同目录布局**

```json
"roles": {
  "tester": ["**/*_test.go"],
  "dev":    ["**/*.go", "!**/*_test.go"]
}
```

**JS/TS 同目录布局**

```json
"roles": {
  "tester": ["**/*.test.*"],
  "dev":    ["src/**", "!**/*.test.*"]
}
```

少了那条负模式,`**/*.go` 会同时匹配测试文件,边界就废了。

**Rust:不支持。** `#[cfg(test)] mod tests` 与实现在同一文件里,
目录切分物理上不成立,glob 也救不了。迁移路径:把测试移到 `tests/` 集成测试目录。

## 8. 状态 schema

`.pair/state.json`,**脚本独占写**。agent 修改它即视为伪造回合归属:
自动还原为上次提交的版本,并拒绝本次操作。

| 字段 | 类型 | 说明 |
|---|---|---|
| `round` | int | 已完成的工作项数 |
| `phase` | string | 当前阶段 |
| `item` | string\|null | 当前工作项 ID |
| `item_type` | string\|null | 当前工作项类型 |
| `last_actor` | string\|null | 上一次交接的角色 |
| `changes_count` | int | 本工作项累计打回次数,claim 时归零 |
| `completed_items` | string[] | 已完成的工作项 ID |
| `setup_verified` | bool | 开工前校验是否通过 |
| `deadlock_hits` | string[] | 撞过死锁闸的记录,形如 `W3 x3` |
| `contract_sha` | string\|null | claim 时契约文件的 blob sha |
| `setup_verified_contract` | object | 按角色记:该角色上次通过开工前校验时,契约文件**工作区内容**的 blob sha。`claim` 现场比对;与 `contract_sha`(按工作项记、取 HEAD)是两回事 |
| `after_rebound` | bool | 上一次交接是不是一次打回(异议或评审 changes)。打回之后的 spec 回合豁免 **RED** 要求(不豁免 GREEN) |
| `rebound_from` | string\|null | 上一次打回来自哪一阶段;不是打回的交接清成 `null`。只涉及测试的打回走捷径要看它 |
| `reviewed_contract` | string\|null | 最近一次 review-impl approve 时契约文件**工作区内容**的 blob sha。捷径要求现在的契约与它相同 |

老状态文件缺少新键时取默认值,对应检查自动跳过 —— 存量仓库零成本升级。
**例外是 `setup_verified_contract`**:缺失时 `claim` 要求重跑一次 `verify-setup`。
"不知道上次校验的是哪一份"和"校验的是另一份"风险一样,而升级代价只是重跑一次。

## 9. 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 拒绝或错误(全部 `die()` 路径) |
| 2 | 交接已提交,但 `sync` 模式下 push 失败 —— 提交只在本地,**等于没交接** |

退出码 2 时 agent **不得**告诉人类"已交接",必须报告推送失败。

## 10. 一致性测试

协议的强制力由 `tests/conformance/` 保证,它**扮演作弊的 agent**:
抢回合、篡改状态、越界写、评审夹带私货、删测试、空手交接、伪造决策 ——
断言 `pair.py` 拦得住。

```bash
python3 tests/conformance/run.py              # 全量,并行
python3 tests/conformance/run.py --changed    # 只跑与本次改动相关的
python3 tests/conformance/mutation_check.py   # 变异检查
```

**全绿本身证明不了什么。** 变异检查逐个拆掉 `pair.py` 里的防护,
确认每一条都有测试能发现它消失了。改动强制逻辑后两个都要跑;
新增防护时,在 `MUTATIONS` 里补上对应变异点。详见
[contributing.md](contributing.md)。
