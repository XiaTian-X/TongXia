# 同类工作调研

> 调研时间:2026-09。目的有两个:确认这套协议是不是在重复造轮子;
> 从别人已经踩过的坑里,找出本项目应该吸收的东西。
> 结论落到 [improvements.md](improvements.md) 的具体改进项里。

## 一句话结论

比较的主轴是**谁更能保障两个 agent 共同把规划交付出来**,不是"谁更能防
互相点头" —— 后者只是前者的手段层。

**没有找到功能重合的项目。** 最接近的四类工作各自解决了这套协议的一部分,
但没有一个同时具备:双 agent 严格轮流、写权限按路径物理切分、红绿作为回合信号、
通信只走 git、协议以可执行脚本强制、跨 harness 中立。

反过来说,每一类都有本项目该学的东西 —— 尤其是 **强制力的粒度**(TDD Guard)、
**结构化异议**(Adversarial Review)、**规格的机器可校验性**(Spec Kit),
以及 **"多不等于好"** 这条实证结论。

---

## A. 双 agent 交叉验证

### the-pair(timwuhaotian/the-pair)

桌面应用(Tauri + Rust + React),一个 **Mentor**(规划 + 只读评审)配一个
**Executor**(写代码 + 执行命令),跨 harness 支持 Claude Code / Codex / Gemini /
opencode。

它明确的问题陈述和本项目一致:

> One model writing *and* reviewing its own code can miss its own mistakes.

值得学的:

- **迭代预算 + 人类闸门。** 默认 20 轮,到点强制暂停交给人类。本项目目前只有
  "同一工作项打回 3 次"这一个闸,没有全局预算 —— 一个工作项可以在 approve
  路径上无限来回。
- **停滞检测。** 60 秒无活动即判定卡死并提示。本项目完全没有活性检测。
- **会话快照可恢复。** 本项目的状态全在 git 里,天然可恢复,这一条已经更强。
- **认知事件流。** 把每回合的 intent / 推理步骤 / 工具调用暴露给人看。
  本项目只有 commit 记录,粒度粗得多,但成本也低得多。

差异:

| | the-pair | 本项目 |
|---|---|---|
| 角色切分 | 职能(规划 vs 执行) | **产物**(测试 vs 实现) |
| 冲突处理 | 无自动化,人类介入 | 路径不相交,冲突不存在 |
| 通信 | Tauri IPC + 结构化交接 prompt | git commit |
| 强制力 | 应用层编排 | 仓库内可执行脚本 |
| 形态 | 桌面 app,自带 UI | 协议 + 单文件脚本,无 UI |
| 依赖 | 必须用它的 app | 任何能跑 shell 的 harness |

**关键区别:the-pair 的 Mentor 只评审,不产出可验证的东西。**
本项目的 tester 产出的是失败的测试 —— 一个能被机器判定的对象。
这是"用红绿当回合信号"和"用 LLM 判断当回合信号"的分界。

---

## B. TDD 强制层

### TDD Guard(nizos/tdd-guard)

Claude Code 的 hook,实时拦截 agent 的写操作,强制 TDD:

- **没有失败测试就不许写实现**
- **不许写超出当前测试要求的实现**(over-implementation 检测)
- 多语言 reporter:Vitest / Jest / pytest / PHPUnit / Go / Rust / RSpec / Minitest
- 可配置校验模型、lint 集成、忽略模式、会话级开关

这是本项目最该学的一个:

1. **它有 reporter 层,能知道"哪几条测试红了"**,而本项目只看退出码 0/非 0。
   本项目因此无法验证"这一回合新增的测试确实是红的那一条" —— 现在只要整体
   RED 就放行。理论上 tester 可以写一条恒过的测试、同时靠别的原因让套件变红。
   (实践中被基线全绿要求挡住了大半,但不是零。)
2. **over-implementation 检测。** 本项目靠 tester 在 review-impl 回合人工发现
   "dev 多写了没被测试要求的东西",没有任何机器辅助。
3. **它是单 agent 的。** hook 拦的是同一个 agent 的手,不存在对抗性 ——
   这正是本项目的差异点:强制的对象是**两个各自尽力、需要互相验收的
   agent 的交接**,而不是一个 agent 的手速。

差异定位:TDD Guard 保证"一个 agent 按 TDD 的顺序写代码";
本项目保证"两个 agent 各写各的、互相验收"。前者是纪律,后者是分权。
**两者不冲突,理论上可以叠加使用。**

同类还有 `xiaolai/tdd-guardian-for-claude`,思路相同,附加了质量闸。

---

## C. 研究工作

### AgentCoder(arXiv:2312.13010)

三个 agent:**Programmer**、**Test Designer**、**Test Executor**。核心论证与
本项目的角色切分完全一致:

> 当同一个 agent 既写代码又写测试,那些测试可能验证的是有缺陷的逻辑本身,
> 而不是真实需求。

结果:GPT-4 上 HumanEval pass@1 96.3%(SOTA 90.2%),MBPP 91.8%(SOTA 78.9%),
且 token 开销**更低**(56.9K vs 138.2K)。

这条实证支持很有用:**分工不是成本,是省钱的** —— 每个 agent 的上下文更窄,
返工更少。本项目的 README 里应该引用它。

差异:AgentCoder 是函数级 benchmark 里的进程内编排,没有仓库、没有回合、
没有权限边界,也不面向"任意两个第三方 harness"。它证明的是**分工原理成立**,
本项目做的是**把这个原理落到真实仓库和真实工具上**。

### Adversarial Review(arXiv:2608.18167)

三 agent 代码评审协议:coding agent + reviewer + **critic**,critic 的职责是
**审计评审本身**。它命名了本项目在**手段层**最警惕的失败模式:

> **false-consensus failure mode** —— agents converge on agreement without
> sufficient evidence.

它的处方是:**disagreement must be minimal, structured, and evidence-grounded**
(异议要少、要结构化、要有证据支撑)。

结果里有一条对本项目非常重要:**3 个 agent 打赢了 5 个 agent 的基线。**
也就是说,"再加一个评审 agent"不是通用解 —— 结构比数量重要。
这直接否掉了本项目"要不要加第三个 reviewer 角色"这个念头。

可落地的:本项目的规则 6 说"禁止 LGTM 这类空话",但**脚本拦不住**,
只靠职业操守。Adversarial Review 的"evidence-grounded"是可以机器化的 ——
见 improvements.md 的 P0-2。

### Talk Isn't Always Cheap(arXiv:2509.05396)

多 agent 辩论的失败模式实证。几条结论直接反驳"多 agent 一定更好":

- **正确→错误的翻转多于错误→正确。** 辩论会主动把本来答对的 agent 带偏。
- **孤立压力。** 一个 agent 被其他人反对时最容易翻供,与对错无关。
- **弱 agent 会拖垮强 agent**,即使强的占多数。
- 轮次越多,准确率越低。

建议的缓解方向:奖励"有依据的异议",惩罚"无依据的从众"。

对本项目的含义:

1. **两个 agent 是特性不是妥协。** 只有两方时不存在"多数压少数"的孤立压力。
2. **回合数要有上限。** 死锁闸(3 次打回)在方向上是对的,这篇给了它实证依据。
3. **不共享推理过程是对的。** 本项目的决策记录**故意不设"分析"字段**,
   只记事实和裁决 —— 这与"共享推理路径会导致趋同"的结论一致。

### MetaGPT(arXiv:2308.00352)

把人类 SOP 编码进多 agent 框架。五个机制里有三个与本项目同构:

- **结构化通信接口** —— agent 之间交换文档和图,不交换对话。理由是纯自然语言
  对话有"传话游戏"式的信息衰减。本项目的 `docs/reviews/`、`docs/notes/`、
  `docs/DECISIONS.md` 是同一思路。
- **发布订阅式共享消息池** —— 不做点对点,各角色按需订阅。本项目用 git 仓库
  充当这个池,`inbox` 是订阅端。
- **可执行反馈**(executable feedback)—— 让运行结果而不是 LLM 评审来驱动迭代。
  这正是本项目"红绿即时钟"的另一种说法。

差异:MetaGPT 是一个进程内框架,角色都是它自己的;本项目是一份**仓库内协议**,
两端是别人的 agent。前者能编排,后者只能约束。

ChatDev 同属这一类(瀑布式对话链、instructor/assistant 双角色),
但它的角色对是**在同一个进程里模拟的**,不解决跨工具问题。

---

## D. 规格驱动开发

### GitHub Spec Kit(github/spec-kit)

七步流程:`constitution` → `specify` → `plan` → `tasks` → `implement`,
外加 `clarify`(消歧)和 `analyze`(跨产物一致性校验)。核心主张:

> specifications become executable, directly generating working implementations
> rather than just guiding them.

映射到本项目:

| Spec Kit | 本项目 |
|---|---|
| `constitution` 项目宪法 | SKILL.md + rules.md(协议本身) |
| `specify` 规格 | `docs/CONTRACT.md` |
| `tasks` 任务拆分 | `docs/PLAN.md` 的工作项 |
| `clarify` 消歧 | `verify-setup` 的契约歧义审查 |
| `analyze` 一致性校验 | `verify-setup` 的契约覆盖度检查(弱得多) |

**该学的是 `clarify` 和 `analyze` 的机器化程度。** 本项目的 `verify-setup`
只做两件事:检查工作项有没有指向存在的契约小节;强制交出一份不短于 120 字的
歧义结论。它查不了"契约小节里到底有没有可断言的东西"。

而 README 自己承认:**契约含糊是唯一会致命的失败模式**。
这块的投入产出比最高。

### BMAD-Method

角色化的 agent 敏捷流程(Analyst / PM / Architect / SM / Dev / QA),
产出 PRD、架构文档,再由 Scrum Master 把它们**编译成自包含的 story 文件**,
Dev agent 只读 story 就能干活。

值得学的一条:**story 文件是刻意自包含的** —— 目的是让 Dev agent 不需要回溯
上游文档。本项目的 `status` 注入(工作项笔记全文 + 相干决策)是同一个思路的
轻量版,但注入的内容是**运行时拼出来的**,不是一份可以人工审阅的产物。

差异:BMAD 的分工是**流程阶段**(谁在什么阶段做什么),本项目的分工是
**产物所有权**(谁能写哪些文件)。BMAD 的强制力全在 prose 里 —— 换个模型
遵守程度就变。这正是本项目坚持"规则编码进脚本"的理由。

### Kiro

IDE 形态的 spec-driven 工具,requirements / design / tasks 三段式产物。
同样属于"结构化产物驱动",同样没有分权和对抗。

---

## E. 编排与隔离

### git worktree 系工具(container-use / Conductor / Crystal / Emdash / Mux 等)

2025—2026 年成熟的一类:给每个并行 agent 一份独立 worktree 或容器,
避免它们互相踩。Dagger 的 container-use 更进一步给每个 agent 独立容器 + 分支。

对比本项目的选择:

- 这类工具解决的是 **N 个 agent 做 N 件不相干的事**,隔离靠**空间复制**。
- 本项目解决的是 **2 个 agent 做同一件事**,隔离靠**路径切分**。
  两方写路径不相交 → 可以共用一个工作目录,不需要 worktree、不需要 merge 策略。

这是本项目 README 里"不需要锁、不需要 merge 策略、不需要 worktree"的底气,
但也意味着 **拓扑 B(分离工作副本)是二等公民** —— 现在只有 `"sync": true`
加 pull/push,没有任何自动化。worktree 生态已经把这块做得很成熟,
本项目可以直接借(见 improvements.md 的 P2-1)。

### Roo Code Boomerang / Orchestrator 模式

编排模式把复杂任务拆成子任务,每个子任务在**独立上下文**里跑,
只把摘要回传给编排者。核心价值是上下文隔离。

本项目的"两个 agent 看不到对方的对话"是同一个价值,但是**结构性的**而不是
编排出来的 —— 没有编排者,也就没有编排者的上下文瓶颈。代价是没人能全局调度,
所以 README 里那句"人类是时钟"。

### OpenHands / microagents

仓库内的 `.openhands/microagents/`:按触发词加载的知识片段 + repo.md 仓库级
说明。与 Agent Skills 的渐进式加载同构。OpenHands 现已直接支持 Agent Skills。

---

## F. 把一个 agent 拆成两个角色

### aider 的 architect/editor 模式

一个模型负责**推理**(怎么解这个问题),另一个负责**编辑**(改成正确的 diff 格式)。
o1-preview 当 architect 配 DeepSeek 当 editor 在 aider benchmark 上拿到 85%,
显著高于任一模型单干;Claude 3.5 Sonnet 自己配自己也从 77.4% 提升到 80.5%。

有意思的一点:**同一个模型分饰两角也有提升**。说明收益部分来自"一次只干一件事"
本身,而不只是来自"两个不同模型"。

对本项目的含义:tester 和 dev 用**同一个模型**也应该有效 —— 这一点值得写进
README 的适用范围,现在容易被误读成"必须两个不同厂商的 agent"。

差异:aider 的切分是**同一回合内的流水线**,两个角色不对抗,不互相评审,
没有独立的产物所有权。

---

## G. 生态标准

| 标准 | 与本项目的关系 |
|---|---|
| **Agent Skills**(agentskills.io,Anthropic 开源) | 本项目的分发形态。`SKILL.md` + `scripts/` + `references/` 的三段式渐进披露正是这个规范。已被 Claude Code / Codex / Cursor / Gemini CLI / Copilot / VS Code / Goose / OpenCode / OpenHands / Amp / Junie / Kiro / Roo Code 等广泛支持 |
| **AGENTS.md** | 跨工具入口约定。`init` 已经铺了 AGENTS.md / CLAUDE.md / GEMINI.md / .cursor / .windsurfrules / .clinerules,方向正确 |
| **MCP** | agent ↔ 工具。本项目的执行层是 shell 脚本,不能跑 shell 的 harness 直接出局。MCP 是把这条边界打开的现成路 |
| **A2A**(Agent2Agent) | agent ↔ agent,有正式的 task 生命周期与状态机。本项目的 `.pair/state.json` 是同类东西的仓库内土办法。**短期不必对齐** —— A2A 假设两端在线可寻址,而本项目刻意假设两端异步、互不可见 |

---

## 谱系图

```
              强制力在哪
        prose ──────────────────────► 可执行

  单 agent   BMAD          Spec Kit        TDD Guard
             Kiro          (analyze)       (hooks)
  ─────────────────────────────────────────────────────
  多 agent   ChatDev       MetaGPT         AgentCoder
             the-pair      (SOP+artifact)  (test executor)
                                           Adversarial Review
                                           ★ 本项目
```

本项目落在右下角,并且是这一格里**唯一不假设自己拥有两端 agent** 的:
AgentCoder 和 Adversarial Review 是进程内编排,MetaGPT 的角色是它自己的,
the-pair 必须用它的桌面 app。本项目只往仓库里放一个目录。

## 本项目独有的四条

调研之后确认这四条没有在别处同时出现:

1. **红绿作为回合信号。** "做完了没"由测试运行器回答,不由模型回答。
   AgentCoder 有 test executor,但它不是回合的时钟。
2. **写权限按路径物理切分。** 冲突不是被解决的,是不可能发生的。
   worktree 系靠复制工作区,本项目靠切分命名空间。
3. **通信只走 git,上下文靠重新推导。** 不传对话、不传摘要。
   MetaGPT 的消息池最接近,但它在进程内。
4. **协议随仓库分发、被脚本强制、对 harness 中立。** 复制一个目录就接入,
   不绑定任何厂商。

## 反过来,本项目明确落后的三条

1. **测试结果只有布尔值。** TDD Guard 的 reporter 层能定位到用例,本项目不能。
2. **评审质量无机器约束。** Adversarial Review 的 evidence-grounded 是可校验的,
   本项目只写在规则里。
3. **没有活性/预算保护。** the-pair 有 20 轮预算和停滞检测,本项目只有打回计数。

这三条构成 [improvements.md](improvements.md) 的 P0/P1。

## 参考

- [the-pair](https://github.com/timwuhaotian/the-pair) — Mentor + Executor 桌面结对
- [TDD Guard](https://github.com/nizos/tdd-guard) — Claude Code 的 TDD 强制 hook
- [AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation](https://arxiv.org/abs/2312.13010)
- [Adversarial Review: Structured Disagreement for Grounded Agentic Code Review](https://arxiv.org/abs/2608.18167)
- [Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate](https://arxiv.org/pdf/2509.05396)
- [MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)
- [GitHub Spec Kit](https://github.com/github/spec-kit) — 规格驱动开发工具包
- [BMAD-Method](https://github.com/bmadcode/BMAD-METHOD) — 角色化 agent 敏捷流程
- [aider: Separating code reasoning and editing](https://aider.chat/2024/09/26/architect.html)
- [Agent Skills 规范](https://agentskills.io/) / [agentskills/agentskills](https://github.com/agentskills/agentskills)
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Dagger container-use](https://github.com/dagger/container-use) — 并行 agent 的容器 + 分支隔离
- [Roo Code Boomerang Tasks](https://docs.roocode.com/features/boomerang-tasks)
