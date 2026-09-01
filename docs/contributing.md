# 贡献指南

> 这个项目在做的事,一句话概括:**防漂移**。
> 所有贡献纪律都是这句话的推论。

## 单一真源

```
.agents/skills/pair-protocol/     ← 唯一真源
├── SKILL.md                        协议正文
├── references/rules.md             规则详解与判例
└── scripts/pair.py                 全部判定逻辑
```

- **协议逻辑只能写在 `pair.py` 里。** CLI、未来的 MCP 层、任何适配层都必须是
  纯转发。一旦它们开始自己判定,就会和真源漂移(见
  [ADR-006](design-decisions.md#adr-006-cli-不含任何协议逻辑))。
- **`docs/` 描述行为,`pair.py` 定义行为。** 两者不一致以 `pair.py` 为准,
  并且那是一个需要修的 bug。
- 构建时协议目录被 `pyproject.toml` 的 `force-include` 原样打进 wheel。
  不要在打包时改写它。

## 两条必跑的命令

```bash
# 1. 一致性测试:扮演作弊的 agent,断言 pair.py 拦得住
python3 -m unittest discover -s tests/conformance -t tests/conformance

# 2. 变异检查:逐个拆掉防护,确认每一条都有测试能发现它消失
python3 tests/conformance/mutation_check.py
```

**改动强制逻辑后两个都要跑。** 只跑第一个是不够的 ——
一个恒真的测试集比没有测试更危险,它会让人以为强制力还在,
而执行层可能已经什么都不拦了。

起一个可跑的样板项目:

```bash
python3 examples/make-demo.py /tmp/pair-demo
```

## 新增一条防护时

五步,缺一不可:

1. **在 `pair.py` 里加拒绝分支。** 拒绝文案要包含:拦了什么、为什么、怎么改。
   agent 只能看到这段文字 —— 它就是这条规则的全部说明书。
2. **在 `tests/conformance/` 里加一个扮演作弊 agent 的用例**,断言它被拦住。
3. **在 `mutation_check.py` 的 `MUTATIONS` 里补上对应变异点** ——
   一段能拆掉这条防护的字符串替换。没补的防护等于没有保障。
4. **在 `pair.py` 的 `ENFORCEMENTS` 里登记一个 id**,并在
   [protocol-spec.md](protocol-spec.md) §4 或 [architecture.md](architecture.md)
   的强制力分布表上方那行 `<!-- pair-enforcements: ... -->` 注释里加上它。
5. **同步文档**:`references/rules.md`(判例)、
   [protocol-spec.md](protocol-spec.md)(规范)、
   [troubleshooting.md](troubleshooting.md)(被拒了怎么办)、
   [design-decisions.md](design-decisions.md)(值得留 ADR 的决策)。

第 4 步不是形式主义:`tests/conformance/test_docs_consistency.py` 会拿
`ENFORCEMENTS`、`DEFAULT_STATE`、子命令列表逐一核对文档,漏改就红。

**这条纪律本身就是这个项目的论点用在自己身上:** 散文规则靠不住。
在那个测试出现之前,"同步文档"这一步只靠记性 —— 而它已经漏过一次
(SKILL.md 写「五条命令」,README 写「六条」)。

变异点的写法就是拿一段唯一的源码片段换成不生效的版本:

```python
("拆掉测试删除防护",
 "    if deleted and not args.allow_deletion:",
 "    if False:"),
```

跑变异检查时它会逐个应用替换,确认对应测试**由绿变红**。
如果拆掉之后测试仍然全绿,说明那条防护没有任何测试在守着它。

## 拒绝文案的写法

拒绝文案是这个项目里最重要的文本,因为它是 agent 唯一会读到的解释。

**好的拒绝文案:**

```
拒绝交接 —— 你删除了已有测试:
  tests/test_auth.py

测试是规格,删除它等于悄悄缩小验收范围。
确有正当理由(比如该用例已被更好的用例取代)就显式声明:
  python3 <路径> handoff "说明" --allow-deletion "删除理由"
理由会写进提交记录,对方在评审时必然看到。
```

三个要素:**具体拦了哪个文件 / 为什么这是个问题 / 下一步该敲什么命令。**

**不要**写成"操作被拒绝,请检查配置"。agent 会去猜,而猜的方向通常是绕过。

## 修改协议语义时

改阶段序列、红绿纪律、角色边界这类**语义**变更,先回答三个问题:

1. **它能被编码吗?** 不能就别加进 `pair.py`,写进 `rules.md` 当判例,
   或者设计一个"强制留痕"的替代品(参考 `--allow-deletion` /
   `--no-decision` / 契约歧义结论的做法)。
2. **它会不会削弱另一条防护?** 记忆层就踩过这个坑:
   `docs/notes/` 若并进 `shared_paths`,"异议必须写下来"那条检查会被随手写的
   笔记静默满足。`verify-setup` 里那条路径重叠检查就是为此存在的。
3. **老仓库怎么办?** 新的 state 字段要有默认值,缺失时对应检查自动跳过
   (`contract_sha` 是范例);新的 config 字段要可选,不配时行为与现在完全一致。

## 反向约束

这些是明确不做的,提 PR 之前先读 [ADR](design-decisions.md) 和
[improvements.md 的"不做的事"](improvements.md#不做的事反向约束):

- 不加第三个评审角色
- 不让两个 agent 直接对话
- 决策条目不加"分析"字段
- agent 不能改 `docs/CONTRACT.md`
- 自动唤醒对方不能是默认行为
- 协议逻辑不能出现在 CLI / MCP / 任何适配层

想推翻其中一条,请在 PR 里针对对应 ADR 的**理由和代价**逐条回应,
不要只说"这样更方便"。

## 依赖纪律

`pair.py` **只用标准库**,单文件。

理由:它要被复制进任意一个项目、由任意一个 harness 执行。
多一个依赖就多一处安装失败的可能,而安装失败等于协议失效。

`requires-python = ">=3.9"`。用到更新的语法前先确认没必要。

## 文档纪律

- **全部 md。** 目录见 [docs/README.md](README.md)。
- **一件事只在一个地方说清楚,别处链过去。** 现在的分工:
  为什么 → `design-philosophy.md`;是什么 → `protocol-spec.md`;
  怎么用 → `command-reference.md`;出错了 → `troubleshooting.md`;
  别人怎么做 → `prior-art.md`;为什么不那样 → `design-decisions.md`。
- **外部结论要带出处链接。** 这个项目的很多设计依赖实证
  (比如"不加第三个 agent"),没有出处就没法被后来人评估。
- 中文正文,代码/路径/命令保持原样。

## 提交信息

普通开发提交用 conventional commits(`feat:` / `fix:` / `docs:` / `chore:`)。

注意:`pair.py` 自己生成的提交有固定前缀(`test:` / `feat:` /
`review(impl)/approve` / `dispute:` / `chore(pair):`),那是协议事件,
不要手工模仿。

## 版本

`SKILL.md` 的 `metadata.version` 与 `pyproject.toml` / `cli/pair_bootstrap`
的 `__version__` 是两条独立的线:

- **协议版本**(SKILL.md)—— 语义变更时 +1。存量仓库靠"新字段有默认值"
  平滑升级,不做迁移脚本。
- **CLI 版本** —— 打包变更时 +1。

协议语义变更要在 PR 描述里写清楚**老仓库会不会被卡住**。
