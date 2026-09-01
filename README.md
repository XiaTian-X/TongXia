# 双 Agent 结对编程协议

让**任意两个** AI coding agent(Claude Code / Codex / Cursor / Gemini CLI /
Copilot / Goose / OpenCode …)结对开发同一个项目:一个只写测试,一个只写实现,
严格轮流交接,互相评审。

协议以 [Agent Skill](https://agentskills.io) 形态随仓库分发,**靠可执行脚本强制
执行规则,而不是靠散文约束模型自觉**。

```
tester 写失败测试  →  dev 实现至绿  →  tester 审实现  →  dev 审测试  →  下一项
```

```bash
uvx --from git+https://github.com/<你>/TongXia pair init /你的项目
```

## 为什么是这个设计

**回合信号用测试的红绿,不用 LLM 判断。** spec 回合结束时测试必须是红的,
impl 回合结束时必须是绿的——`handoff` 强制检查。"做完了没"这个问题由测试
运行器回答,不由模型回答。

**写权限按目录切分,物理上不可能冲突。** tester 只能写 `tests/`,dev 只能写
`src/`,越界提交被直接拒绝。不需要锁,不需要 merge 策略,不需要 worktree。

**对抗性是结构性的。** tester 的工作定义就是写出 dev 过不了的用例。这比
"请评审一下"有效得多——两个 LLM 互相点头是这类方案最常见的失败方式,
这里靠角色定义绕开了它。

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
刻意的:一旦 CLI 里出现协议逻辑,它就会和 skill 漂移,而防漂移正是这个项目
从头到尾在做的事。

## 命令

| 命令 | 谁跑 | 何时 |
|---|---|---|
| `pair init` (CLI) | 人类或第三方 agent | 接入项目,一次 |
| `pair.py verify-setup` | 结对的另一方 | 开工前,一次。含契约歧义审查 |
| `pair.py status` | 双方 | 每回合开头 |
| `pair.py claim <ID>` | tester | 认领工作项 |
| `pair.py handoff …` | 双方 | 每回合结尾。`changes` 用于评审打回和测试异议 |
| `pair.py inbox` | 双方 | 看对方做了什么 |

## 开发

```bash
python3 -m unittest discover -s tests/conformance -t tests/conformance
```

一致性测试**扮演作弊的 agent**——抢回合、篡改状态、越界写、评审夹带私货、
删测试——断言 `pair.py` 拦得住。

但全绿本身证明不了什么,一个恒真的测试集比没有测试更危险。所以还有变异检查:

```bash
python3 tests/conformance/mutation_check.py
```

它逐个拆掉 `pair.py` 里的防护,确认每一条都有测试能发现它消失了。
**改动强制逻辑后两个都要跑。**新增防护时,在 `MUTATIONS` 里补上对应变异点。

起一个可跑的样板项目:

```bash
python3 examples/make-demo.py /tmp/pair-demo
```

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
