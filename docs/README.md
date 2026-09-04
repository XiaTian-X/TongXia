# 文档

双 Agent 结对编程协议的完整文档。项目总览在 [../README.md](../README.md),
接入步骤在 [../INSTALL.md](../INSTALL.md)。

## 按你要做的事找

| 你想…… | 看这里 |
|---|---|
| 理解这套东西为什么这么设计 | [design-philosophy.md](design-philosophy.md) |
| 知道有哪些组件、数据怎么流动 | [architecture.md](architecture.md) |
| 查某条规则的准确定义 / 配置字段 | [protocol-spec.md](protocol-spec.md) |
| 查某条命令怎么用 | [command-reference.md](command-reference.md) |
| 解决一个报错或一个可疑现象 | [troubleshooting.md](troubleshooting.md) |
| 了解同类开源项目和研究工作 | [prior-art.md](prior-art.md) |
| 知道某个选择为什么不是另一种 | [design-decisions.md](design-decisions.md) |
| 看接下来要做什么 | [improvements.md](improvements.md) |
| 给这个项目提 PR | [contributing.md](contributing.md) |

## 全部文档

### [design-philosophy.md](design-philosophy.md) — 设计理念

九条第一性原理,每条都服务同一个目的:**让两个 agent 各自尽力,合起来
真的把 `PLAN.md` 里规划的工作项交付出来**。防互相点头是其中一层手段,
不是北极星。

红绿即时钟 · 路径切分即隔离 · 对抗性写进角色定义 · 协议可执行 ·
通信只走 git · 仓库即记忆 · 范围收窄是前提 · 人类是时钟 · 单一真源

### [architecture.md](architecture.md) — 架构

三层结构(引导 / 协议 / 执行)、一个回合的完整数据流、状态机、
**强制力分布表**(哪些规则是脚本拦的,哪些只能靠留痕)、跨 harness 的接入面。

### [protocol-spec.md](protocol-spec.md) — 协议规格

规范性文档。角色解析、阶段与归属、工作项类型与流程、16 条不变量、
命令契约、记忆层、配置 schema、状态 schema、退出码。

### [command-reference.md](command-reference.md) — 命令参考

八个 `pair.py` 子命令逐一:参数、前置条件、副作用、被拒了怎么办、退出码;
另含 bootstrap `pair init` 与可选的 `drive.py`。

### [prior-art.md](prior-art.md) — 同类工作调研

the-pair · TDD Guard · AgentCoder · Adversarial Review · 多 agent 辩论失败模式 ·
MetaGPT · Spec Kit · BMAD · aider architect/editor · worktree 系工具 ·
Agent Skills / AGENTS.md / MCP / A2A。

含谱系图、对比表、**本项目独有的四条**、以及**明确落后的三条**。

### [design-decisions.md](design-decisions.md) — 决策记录

24 条 ADR,每条含背景 / 决策 / 理由 / 代价 / **被否掉的方案**。
写下来是为了以后不用重新讨论,尤其是"为什么不那样做"。

### [improvements.md](improvements.md) — 改进提案与路线图

每一条都来自调研里某个项目已经验证过的做法。P0 补核心主张的缺口
(用例级测试结果 / 评审带证据 / 契约可校验),P1 明显该有,P2 扩面,
外加一份**明确不做的清单**。

### [troubleshooting.md](troubleshooting.md) — 故障排查

按阶段组织:接入 → 回合中 → 交接与同步 → **质量问题(脚本抓不到的)**。
最后一节最值得读 —— 那些没有报错但比报错更危险的现象。

### [contributing.md](contributing.md) — 贡献指南

单一真源纪律、两条必跑的命令、**新增一条防护的四步**、
拒绝文案的写法、反向约束、依赖与文档纪律。

## 阅读顺序建议

**第一次接触这个项目:**
[../README.md](../README.md) → [design-philosophy.md](design-philosophy.md) →
[architecture.md](architecture.md)

**要把它用到自己项目上:**
[../INSTALL.md](../INSTALL.md) → [command-reference.md](command-reference.md) →
[troubleshooting.md](troubleshooting.md)

**要改这个项目:**
[design-decisions.md](design-decisions.md) →
[protocol-spec.md](protocol-spec.md) → [contributing.md](contributing.md) →
[improvements.md](improvements.md)

**在评估它值不值得用:**
[prior-art.md](prior-art.md) →
[architecture.md 的强制力分布表](architecture.md#强制力分布) →
[design-philosophy.md 的已知边界](design-philosophy.md#已知边界)
