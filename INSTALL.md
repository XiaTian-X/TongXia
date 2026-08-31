# 接入已有项目

## 1. 复制协议

```bash
cp -R /path/to/TongXia/.agents/skills/pair-protocol \
      你的项目/.agents/skills/pair-protocol
```

`.agents/skills/` 是跨客户端惯例(Codex、Cursor、Gemini CLI、Copilot、VS Code、
Goose、OpenCode、Amp、Factory、Junie、Kiro 等都从这里扫描技能)。

**Claude Code 读的是 `.claude/skills/`**,加一条软链接指向同一份真源:

```bash
mkdir -p 你的项目/.claude/skills
ln -s ../../.agents/skills/pair-protocol 你的项目/.claude/skills/pair-protocol
```

Windows 上创建软链接需要管理员权限或开发者模式;那种情况下改成在
`.claude/skills/pair-protocol/SKILL.md` 放一个指向真源的桩文件。
接入其他工具时查一下它扫描哪个目录,照此加一条。

## 2. 写配置

`.pair/config.json`:

```json
{
  "test_cmd": "npm test",
  "roles": {
    "tester": ["tests"],
    "dev": ["src"]
  },
  "shared_paths": ["docs/reviews"],
  "frozen_paths": ["docs/PLAN.md", "docs/CONTRACT.md", ".agents", ".pair"],
  "plan_file": "docs/PLAN.md",
  "sync": false
}
```

`test_cmd` 必须全绿退出 0、有失败退出非 0。
`roles` 的两组路径**不能重叠**——那是零冲突的全部来源。

`.pair/state.json` 初始内容:

```json
{"round": 0, "phase": "spec", "item": null,
 "last_actor": null, "changes_count": 0, "completed_items": []}
```

`.gitignore` 补两行:

```
.pair/.last-test.log
.pair/whoami
```

## 3. 铺入口文件

协议真源只有 `SKILL.md` 一份,其余全是十行以内的**激活器**——因为技能是按需
激活的,而结对协议必须从第一个回合就生效。照抄
`examples/demo-project/` 里的这几个文件:

| 文件 | 服务的工具 |
|---|---|
| `AGENTS.md` | Codex / Cursor / Copilot / Windsurf / Zed / Aider / Amp / Devin … |
| `CLAUDE.md` | Claude Code(`@AGENTS.md` 原生 import) |
| `GEMINI.md` | Gemini CLI |
| `.clinerules` | Cline |
| `CONVENTIONS.md` | Aider |
| `.windsurfrules` | Windsurf |
| `.cursor/rules/pair.mdc` | Cursor |
| `.github/copilot-instructions.md` | GitHub Copilot |

## 4. 写规划和契约

`docs/PLAN.md` 的工作项格式**必须**是这一行形态,`pair.py claim` 靠它识别:

```markdown
- [ ] **W1** — 标题
  - 验收标准:<可观测的、能写成断言的条件>
```

粒度决定成败:小到一个 spec 回合能写三五个用例就覆盖完。
"实现用户系统"太大,"密码哈希用 bcrypt,cost=12"才是一个工作项。

`docs/CONTRACT.md` 是承重墙,别偷懒。**没写进契约的东西,tester 不许断言。**

## 5. 启动两个 agent

### 拓扑 A:同目录(两个 CLI harness)

两边写路径不相交,可以直接共用一个工作目录。用环境变量分配角色:

```bash
PAIR_ROLE=tester <agent A 的命令>    # 终端 1
PAIR_ROLE=dev    <agent B 的命令>    # 终端 2
```

### 拓扑 B:分离工作副本(GUI / 云端 harness)

Cursor、VS Code、Windsurf 从 GUI 启动,Devin、Jules 跑在云端,都没有可靠的地方
塞环境变量。给它们各自一份独立 clone 或 worktree,用文件或分支名声明角色:

```bash
echo tester > .pair/whoami        # 或者:git switch -c pair/tester
```

此拓扑要在 `config.json` 里开 `"sync": true`,`status` 会先 `git pull --rebase`,
`handoff` 会在提交后 `git push`。

### 然后

在**任意一个** agent 那里说"继续"。不该它动的那个会自己停下——回合状态在
`.pair/state.json` 里,不在对话里,所以你不用记现在轮到谁。

你是时钟。每次交接后手动去另一边敲一句。

如果某个 agent 没自动激活技能,直接让它调用(Claude Code 里是 `/pair-protocol`),
或者让它读 `.agents/skills/pair-protocol/SKILL.md`。
