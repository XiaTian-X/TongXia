# 接入项目

## 一条命令

```bash
uvx --from git+https://github.com/<你>/TongXia pair init /你的项目
```

CLI 只做两件事:把协议复制进去、建好 Claude Code 需要的软链接,然后调用
协议自带的 `pair.py init`。**它不含任何协议逻辑** —— 判定、边界、红绿、回合
全部在 skill 里,CLI 只是个交接壳子,不会和协议漂移。

不想用 CLI 也可以手工来:

```bash
cp -R /path/to/TongXia/.agents/skills/pair-protocol 你的项目/.agents/skills/
mkdir -p 你的项目/.claude/skills
ln -s ../../.agents/skills/pair-protocol 你的项目/.claude/skills/pair-protocol
cd 你的项目 && python3 .agents/skills/pair-protocol/scripts/pair.py init
```

`.agents/skills/` 是跨客户端惯例(Codex、Cursor、Gemini CLI、Copilot、VS Code、
Goose、OpenCode、Amp、Factory、Junie、Kiro 等都从这里扫描)。**Claude Code 读的是
`.claude/skills/`**,所以要一条软链接指向同一份真源。Windows 上创建软链接需要
管理员权限或开发者模式,CLI 会自动退化成桩文件。

`init` 会探测技术栈和布局、写配置、铺各家入口文件、起草 PLAN 与 CONTRACT 骨架,
并且**幂等** —— 已存在的文件一律跳过,可以反复跑。

## 基线必须全绿

`init` 会先跑一次测试,**不全绿就拒绝接入**。

这不是洁癖:`impl` 阶段"测试必须 GREEN"这条不变量依赖基线全绿。基线本来就红,
协议要么直接卡死,要么那条不变量形同虚设。先把现有测试修绿,再接入。

**全新项目要注意:空的测试目录往往不算绿。** `python3 -m unittest discover`
在没有任何用例时会报 `NO TESTS RAN` 并非零退出,`go test ./...` 在没有测试文件
时也可能如此。先放一条必过的冒烟用例(见
`examples/demo-project/tests/test_smoke.py`),基线才成立。

## 存量项目的布局

`init` 会自动探测,但存量项目布局千奇百怪,**务必核对 `.pair/config.json` 里的
`roles`**。两个角色的路径**绝对不能重叠** —— 那是零冲突保证的全部来源。

### 目录切分(最常见)

```json
"roles": { "tester": ["tests"], "dev": ["src"] }
```

也识别 `test/` `spec/` 和 Java 的 `src/test` / `src/main`。

### 同目录布局:Go、JS/TS

Go 的 `foo_test.go` 和 `foo.go` 在同一个目录,只能靠 glob + **负模式**切分:

```json
"roles": {
  "tester": ["**/*_test.go"],
  "dev":    ["**/*.go", "!**/*_test.go"]
}
```

`!` 开头的是负模式:一个路径属于某角色 = 命中至少一个正模式且不命中任何负模式。
少了那条 `!`,`**/*.go` 会同时匹配测试文件,边界就废了 —— `verify-setup` 会拿
真实文件树逐个试匹配并报出重叠。

JS/TS 同理:

```json
"roles": {
  "tester": ["**/*.test.*"],
  "dev":    ["src/**", "!**/*.test.*"]
}
```

### Rust:不支持

Rust 的 `#[cfg(test)] mod tests` 写在**同一个文件里**,目录切分物理上不成立,
glob 也救不了。要用这套协议,得把测试移到 `tests/` 集成测试目录。
文件内单元测试不在支持范围。

### 构建副产物

dev 跑一次 `npm install` 改了 lockfile 就被判越界是不合理的。把这类路径放进
`ignore_paths`,它们完全不参与边界检查:

```json
"ignore_paths": ["package-lock.json", "**/*.lock", "dist", "build"]
```

代价是两个角色都能悄悄改它们且不留痕。只放真正的副产物。

## 写规划和契约

`docs/PLAN.md` 的工作项格式**必须**是这一行形态,`claim` 靠它识别:

```markdown
- [ ] **W1** [feature] — 标题
  - 验收标准:<可观测的、能写成断言的条件>
  - 对应契约:`docs/CONTRACT.md` → <小节名>
```

`对应契约` 那一行是必须的,`verify-setup` 会检查它指向的小节真实存在。

类型标记决定阶段序列和红绿纪律,省略则为 `feature`:

| 类型 | 用途 | 适合谁 |
|---|---|---|
| `feature` | 新功能 | 新项目 |
| `bug` | 修缺陷(写复现测试 → 修绿) | **已完成项目的最佳场景** |
| `cover` | 为已有行为补测试 | 存量项目提覆盖率 |
| `refactor` | 不改行为地重构 | 存量项目还技术债 |

粒度决定成败:小到一个回合写三五个用例就覆盖完。"实现用户系统"太大,
"密码哈希用 bcrypt,cost=12"才是一个工作项。

`docs/CONTRACT.md` 是承重墙,别偷懒。**没写进契约的东西,tester 不许断言。**

## 启动两个 agent

### 拓扑 A:同目录(两个 CLI harness)

两边写路径不相交,可以共用一个工作目录。用环境变量分配角色:

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

### 开工顺序

1. 让**还没动手的那一方**跑 `pair.py verify-setup`。它会要求通读契约并把歧义
   写进 `docs/reviews/setup-verification.md` —— **交出这份结论之前校验不通过,
   也不能认领工作项**
2. 人类看这份歧义报告,定稿契约
3. 在任意一个 agent 那里说"继续"。不该它动的那个会自己停下 —— 回合状态在
   `.pair/state.json` 里,不在对话里,所以你不用记现在轮到谁

你是时钟。每次交接后手动去另一边敲一句。

如果某个 agent 没自动激活技能,直接让它调用(Claude Code 里是 `/pair-protocol`),
或者让它读 `.agents/skills/pair-protocol/SKILL.md`。
