# 双 Agent 结对编程协议

让**任意两个** AI coding agent(Claude Code / Codex / Cursor / Gemini CLI /
Copilot / Goose / OpenCode …)**共同把 `docs/PLAN.md` 里规划的项目做出来**:
一个只写测试,一个只写实现,严格轮流交接,互相评审,直到 PLAN 全部勾选、
门禁套件全绿;配了全量套件时,它红了不能宣布"完成"——如实告诉人类,由人类决定。

分工与评审不是为了把两个 agent 摆成对立面,而是为了让两份努力**可以合并、
不互相抵消**,收敛到同一个交付。协议以 [Agent Skill](https://agentskills.io)
形态随仓库分发,**靠可执行脚本强制执行规则,而不是靠散文约束模型自觉**。

```
tester 写失败测试  →  dev 实现至绿  →  tester 审实现  →  dev 审测试  →  下一项
```

```bash
uvx --from git+https://github.com/<你>/TongXia pair init /你的项目
```

## 为什么是这个设计

下面每一条都是手段,服务同一个目的:**让两个 agent 各自尽力,产出的东西
合起来是真的把 PLAN 做完了**,而不是看起来做完了。

**回合信号用测试的红绿,不用 LLM 判断。** spec 回合结束时测试必须是红的,
impl 回合结束时必须是绿的——`handoff` 强制检查。"做完了没"这个问题由测试
运行器回答,不由模型回答。

**写权限按目录切分,物理上不可能冲突。** tester 只能写 `tests/`,dev 只能写
`src/`,越界提交被直接拒绝。不需要锁,不需要 merge 策略,不需要 worktree。

**对抗性是结构性的,但它服务的是交付。** tester 的工作定义就是写出 dev
过不了的用例——这比"请评审一下"有效得多。评审的目的是保障交付质量:
既要真挑出问题,也不为了显得"没在互相点头"而制造无谓的打回——
后者会消耗掉该工作项三次打回额度里的一次(额度用尽即撞死锁闸、停轮转交
人类)、浪费至少两个回合、把交付往后拖。

**协议是可执行的,不是散文。** 不同模型对同一段 prose rules 的遵守程度差别很大。
把规则编码进 `pair.py`,才能保证"任意两个 harness"都受同样的约束。

**通信只走 git。** 两个 agent 看不到对方的对话,上下文靠仓库重新推导——这恰好是
agent 擅长的,也比传递对话记录省得多。`pair.py inbox` 就是收件箱。

**记忆放在仓库里,不放在 agent 里。** 各家 agent 的私有记忆格式、召回机制都不一样,
统一不了,也不该去统一——你能统一"写什么",统一不了"什么时候被读出来"。
所以项目知识沉在 `docs/notes/`(工作项级的负空间:试过什么没成、否掉了什么)和
`docs/DECISIONS.md`(项目级结论,追加式),由 `status` 在每回合开头按路径相关性
注入。**存了没人读等于没存**,而 `status` 是协议里唯一强制、每个 harness 都会跑
的时刻——这是"仓库即记忆"能成立的地方。

## 适用范围

| 场景 | 工作项类型 | 契合度 |
|---|---|---|
| 新项目做功能 | `feature` | ✅ |
| **已完成项目修 bug** | `bug` | ✅ **最佳场景** —— 写复现测试 → 修绿,天然就是 TDD |
| 存量项目提覆盖率 | `cover` | ✅ 跳过 impl,dev 只评审"这测试能否发现回归" |
| 存量项目还技术债 | `refactor` | ✅ 跳过 spec,tester 只评审"行为有没有变" |

**两端不必是两个不同的工具或模型。** 同一个 CLI、同一个模型开两个终端就成立,
**这也是上手成本最低的起步配置**。分工本身就有收益 —— aider 的 architect/editor
实验里,Claude 3.5 Sonnet 自己配自己也从 77.4% 提升到 80.5%。

证据的边界值得说清楚:aider 的 architect/editor 是**同一回合内的流水线**,
两个角色不互相评审、也没有独立的产物所有权。所以那条实证支持得起"分工的收益
同模型也成立",支持不起"对抗性评审的收益同模型也拿得到"。后者目前没有证据,
它正是打回率这个指标要测的东西(见 [improvements.md](docs/improvements.md) 的 P1-1)。

布局上支持目录切分(`tests/` + `src/`)和同目录布局(Go 的 `*_test.go`、
JS 的 `*.test.ts`,靠 glob 负模式切分)。**Rust 的文件内单元测试不支持** ——
`#[cfg(test)] mod tests` 和实现在同一个文件里,目录切分物理上不成立。

## 仓库结构

```
.agents/skills/pair-protocol/     ← 产物。复制这个目录就能接入任何项目
├── SKILL.md                        协议正文(渐进式加载,不常驻上下文)
├── references/rules.md             硬性规则详解与判例(按需加载)
└── scripts/pair.py                 执行层。单文件,仅 stdlib
cli/pair_bootstrap/               ← 极薄 bootstrap:复制 skill → 调用 pair.py init
tests/conformance/                ← 协议一致性测试 + 变异检查
examples/demo-project/            ← 样板项目模板
INSTALL.md                        ← 怎么接入已有项目
```

CLI **不含任何协议逻辑**,只负责把 skill 搬进目标项目然后交给它。这条约束是
刻意的:一旦 CLI 里出现协议逻辑,它就会和 skill 漂移——而漂移会让 agent
读到的规则不再是被强制的规则,交付质量因此失去保障。

## 命令

| 命令 | 谁跑 | 何时 |
|---|---|---|
| `pair init` (CLI) | 人类或第三方 agent | 接入项目,一次 |
| `pair.py verify-setup --drafter …` | 结对的另一方 | 开工前,一次。含契约歧义审查与起草人声明 |
| `pair.py status` | 双方 | 每回合开头 |
| `pair.py claim <ID>` | tester | 认领工作项 |
| `pair.py handoff …` | 双方 | 每回合结尾。`changes` 用于评审打回和测试异议 |
| `pair.py inbox` | 双方 | 看对方做了什么 |
| `pair.py report` | **人类** | 打回率等健康度指标。接近 0 = 互相点头 |
| `drive.py`(可选) | 人类 | 自动驱动两边,省掉来回敲。默认不开 |

## 文档

完整文档在 [`docs/`](docs/),索引见 [docs/README.md](docs/README.md)。

| | |
|---|---|
| [设计理念](docs/design-philosophy.md) | 九条第一性原理,以及每条的代价 |
| [架构](docs/architecture.md) | 三层结构、回合数据流、**强制力分布表** |
| [协议规格](docs/protocol-spec.md) | 状态机、16 条不变量、配置与状态 schema |
| [命令参考](docs/command-reference.md) | 全部命令的参数、前置条件、退出码 |
| [同类工作调研](docs/prior-art.md) | the-pair / TDD Guard / AgentCoder / Adversarial Review / Spec Kit / BMAD …… |
| [决策记录](docs/design-decisions.md) | 23 条 ADR,含被否掉的方案 |
| [改进提案](docs/improvements.md) | 从调研里提炼的路线图,以及明确不做的清单 |
| [故障排查](docs/troubleshooting.md) | 报错怎么办,以及那些不报错但更危险的现象 |
| [贡献指南](docs/contributing.md) | 单一真源纪律、新增防护的五步 |

## 开发

```bash
python3 tests/conformance/run.py              # 全量,并行(8 进程约 44 秒)
python3 tests/conformance/run.py --changed    # 只跑与本次改动相关的
python3 tests/conformance/run.py memory       # 只跑某几组
```

一致性测试**扮演作弊的 agent**——抢回合、篡改状态、越界写、评审夹带私货、
删测试——断言 `pair.py` 拦得住。

但全绿本身证明不了什么,一个恒真的测试集比没有测试更危险。所以还有变异检查:

```bash
python3 tests/conformance/mutation_check.py   # 约 70 秒(含它自己跑的基线)
```

它逐个拆掉 `pair.py` 里的防护,确认每一条都有测试能发现它消失了。
**改动强制逻辑后两个都要跑。**新增防护时,在 `MUTATIONS` 里补上对应变异点。
上面两处秒数都是 8 进程实测,换机器会变,别当承诺。

起一个可跑的样板项目:

```bash
python3 examples/make-demo.py /tmp/pair-demo
```

git 推不出 author 或 committer 身份时(没配 `user.*`,hostname 又不是 FQDN),
它会给样板仓库的 `.git/config` 写一份兜底身份 `conformance` /
`conformance@test`——只碰这个仓库,不碰全局配置,已有身份的机器一字不写
(两条 ident 都推得出才不写)。想换掉就在样板仓库里跑
`git config user.email 你的邮箱`。

## 已知边界

- **人类是时钟。** agent 之间不会自动唤醒对方,每次交接后需要人到另一个终端
  敲一句。想全自动可以在 handoff 后用 headless 模式拉起对方,但先把手动流程跑顺。
- **技能激活不是 100% 可靠。** 渐进式披露意味着 agent 自己判断要不要加载。
  入口文件里的激活器是硬命令,但如果某个 agent 没按协议走,第一件事是确认
  它到底有没有读到 SKILL.md。
- **不能执行 shell 命令的 harness 不在支持范围。** 执行层跑不起来,协议只能
  退化成纯 prose 约束,强制力归零。
- **基线必须全绿才能接入。** `impl` 阶段的 GREEN 要求依赖这一点,基线本来
  就红的话协议要么卡死、要么那条不变量形同虚设。`init` 会拒绝。
- **记忆层只解决"这一个工作项 + 约束它的前提",不解决"完全理解整个项目"。**
  没有方案能做到后者。协议本来就把范围收到一回合一个工作项 —— 正是这个收窄让
  "仓库即记忆"成立。如果某个工作项大到 agent 必须先理解全局意图才能动手,
  那是工作项切得太大了。
- **契约质量决定成败。** 两个 agent 从不交谈,只靠 `docs/CONTRACT.md` 对齐。
  契约含糊 → tester 测 `login() -> token`,dev 写 `authenticate() -> Session`,
  两边各自都"对",合起来是废的。这是唯一会致命的失败模式。
