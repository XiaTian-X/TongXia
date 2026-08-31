# 双 Agent 结对编程脚手架

让**任意两个** AI coding agent(Claude Code / Codex / Cursor / Gemini CLI /
Aider / Cline / Windsurf …)结对开发同一个项目:一个写测试,一个写实现,
互相评审。

不依赖任何单一工具的私有能力。只用了所有 harness 都有的四样东西:
**读文件、写文件、跑 shell、用 git**。

## 一次性设置

1. **配测试命令** —— 编辑 `.pair/config`:

   ```sh
   TEST_CMD="npm test"        # 或 pytest / go test ./... / cargo test …
   ```

   要求:全绿退出 0,有失败退出非 0。

2. **写规划和契约** —— 填 `docs/PLAN.md` 和 `docs/CONTRACT.md`。
   这一步别偷懒,契约含糊是这套机制唯一会致命的失败模式。

3. **首次提交**:

   ```sh
   git add -A && git commit -m "chore: 结对脚手架"
   ```

## 每天怎么跑

开两个终端,各启一个 agent,**用环境变量指定角色**:

```sh
# 终端 A —— 测试方
PAIR_ROLE=tester <你的 agent 命令>

# 终端 B —— 实现方
PAIR_ROLE=dev <你的 agent 命令>
```

然后在**任意一个**终端里说"继续"。不该它动的那个会自己停下 —— 回合状态在
`.pair/STATE.md` 里,不在对话里,所以你不用记现在轮到谁。

你是时钟。agent 之间不会自己唤醒对方,每次交接后你手动去另一个终端敲一句。

## 三个命令

| 命令 | 谁跑 | 作用 |
|---|---|---|
| `scripts/status` | agent,每回合开头 | 我是谁 / 轮到谁 / 红绿 / 该干什么 |
| `scripts/handoff "…"` | agent,每回合结尾 | 校验边界和红绿 → 提交 → 翻转回合 |
| `scripts/inbox` | agent,想看对方做了什么时 | 上一回合的 diff 和评审记录 |

路径前缀是 `.agents/skills/pair-protocol/`。脚本自己会定位 git 根,
在仓库任何子目录下调用都可以。

## 为什么是这个设计

**回合信号用测试的红绿,不用 LLM 判断。** spec 回合结束时测试必须是红的,
impl 回合结束时必须是绿的 —— `handoff` 会强制检查。"做完了没"这个问题
由测试运行器回答,不由模型回答。

**写权限按目录切分,物理上不可能冲突。** tester 只能写 `tests/`,dev 只能写
`src/`,`handoff` 会检查 `git status` 并拒绝越界提交。不需要锁,不需要
merge 策略,不需要 worktree。

**对抗性是结构性的。** tester 的工作定义就是写出 dev 过不了的用例。这比
"请评审一下"有效得多 —— 两个 LLM 互相点头是这类方案最常见的失败方式,
这里靠角色定义绕开了它。

**协议是可执行的,不是散文。** 不同模型对同一段 prose rules 的遵守程度差别
很大。把规则编码进技能的 `scripts/` 里,才能保证"任意两个 harness"都受同样
的约束。SKILL.md 只负责告诉 agent 去跑哪个脚本。

**通信只走 git。** 两个 agent 看不到对方的对话,上下文靠 repo 重新推导 ——
这恰好是 agent 擅长的,也比传递对话记录省 token。

## 产物形态

协议本体是一个 **Agent Skill**(2025-12 发布的开放标准,40+ 客户端支持):

```
.agents/skills/pair-protocol/
├── SKILL.md              # 协议正文(渐进式加载,不常驻上下文)
├── references/rules.md   # 硬性规则详解(按需加载)
└── scripts/              # 执行层:status / handoff / inbox
```

这样做的三个理由:

- **跨工具**:Claude Code、Codex、Cursor、Gemini CLI、Copilot、VS Code、Goose、
  OpenCode、Roo Code、Amp、Factory、Junie、Kiro 等 40+ 客户端读同一份 SKILL.md。
- **随仓库走**:技能提交进 repo,结对双方拿到的是同一份协议——而不是各自
  装在自己配置里的两份。插件做不到这点,那正是它不适合的原因。
- **渐进式披露**:启动时只有 `name` + `description` 进上下文(约 100 token),
  正文在激活时才加载,`references/` 更是按需。协议再长也不占常驻预算。

技能本身**不含任何项目状态**,所以它是可分发的:复制 `.agents/skills/pair-protocol/`
到任何项目,配一份 `.pair/config` 就能用。

### 目录分裂与解法

技能标准没有强制目录位置。`.agents/skills/` 是跨客户端惯例,但 Claude Code 读的是
`.claude/skills/`。本仓库的处理方式是**唯一真源 + 软链接**:

```
.claude/skills/pair-protocol -> ../../.agents/skills/pair-protocol
```

Windows 上创建软链接需要管理员权限或开发者模式;那种情况下改成在
`.claude/skills/pair-protocol/SKILL.md` 放一个指向真源的桩文件。
接入其他工具时查一下它扫描哪个目录,照此加一条软链接即可。

### 为什么还要 AGENTS.md

技能是**按需激活**的,但结对协议必须从第一个回合就生效——agent 要是没
激活技能,就不知道自己身处结对项目。所以 `AGENTS.md` 保留,但收缩成十行
以内的**激活器**:声明这是结对项目、命令 agent 立刻激活技能并跑 `status`。

同一份激活器复制成各家入口文件,协议真源仍然只有 SKILL.md 一份:

| 文件 | 服务的工具 |
|---|---|
| `AGENTS.md` | Codex / Cursor / Copilot / Windsurf / Zed / Aider / Amp / Jules / Devin … |
| `CLAUDE.md` | Claude Code(`@AGENTS.md` 原生 import) |
| `GEMINI.md` | Gemini CLI |
| `.clinerules` | Cline |
| `CONVENTIONS.md` | Aider |
| `.windsurfrules` | Windsurf |
| `.cursor/rules/pair.mdc` | Cursor |
| `.github/copilot-instructions.md` | GitHub Copilot |

如果某个 agent 没自动激活技能,人类可以直接让它调用(Claude Code 里是
`/pair-protocol`),或者让它读 `.agents/skills/pair-protocol/SKILL.md`。

## 已知边界

- **人类是时钟。** 没有自动唤醒。想全自动的话,可以在 handoff 后用 headless
  模式(`claude -p` / `codex exec` 等)拉起对方,但先把手动流程跑顺。
- **技能激活不是 100% 可靠的。** 渐进式披露意味着 agent 自己判断要不要加载。
  入口文件里的激活器是硬命令,但如果发现某个 agent 没按协议走,
  第一件事是检查它到底有没有读到 SKILL.md。
- **同一工作项被打回 3 次会强制停止**,交给人类裁决。这是防活锁的硬闸。
- **契约变更必须人类执行。** agent 只能提请求 + 互相签字,不能自己改
  `docs/CONTRACT.md`。刻意如此。
