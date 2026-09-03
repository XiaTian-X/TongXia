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

### 不适用的三类项目

`Rust` 那条是**布局**问题(见下),这三条是**协议本身不成立**:

**随机性主导的 ML 训练。** 它需要一份"机器写、可覆盖的指标基线"(阈值、容差、
种子),而那种文档在协议里无处安放:契约冻结、笔记随工作项作废、决策追加式不可改。
更要命的是 **dev 调低阈值让测试变绿,红绿、边界、评审格式没有一条抓得到** ——
它长得跟一次正当调参一模一样。只对确定性的那部分适用(数据加载、tokenize、
checkpoint IO)。

**声明式基础设施**(Terraform、k8s、Ansible)。角色切分没问题,但**契约和实现
会塌缩成同一份文档**:契约写"这个 bucket 开版本控制、禁止公开访问",实现就是
逐字那句话。这套协议的对抗价值全部来自"契约比代码高一个抽象层",两者一样高时,
tester 和 dev 是在把同一句话写两遍,评审只能互相点头 ——
结构性的 false-consensus,格式挡不住。

**多语言仓库需要手工配 `test_cmd`。** `init` 的栈探测**第一个命中就返回**:
一个同时有 `pom.xml` 和 `package.json` 的仓库会配一条只跑 Java 的命令,
然后基线绿、每回合绿、红绿"全程有效",**而 JS 那半从头到尾没有门禁**。
这条是静默的,所以务必自己核对 `.pair/config.json` 里的 `test_cmd`
真的覆盖了全部代码。见 `improvements.md` 的 P1-7。

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

## 现有项目接入

代码结构固定、只有零散文档、老套件可能是红的 —— 这一节讲怎么处理。
协议层面的纪律(契约依据、cover 的特征测试记录、refactor 的安全网)见
[`references/brownfield.md`](.agents/skills/pair-protocol/references/brownfield.md)。

### 两类容易漏配的文件

`init` 的探测只切分测试与实现,但现有项目里必然还有这两类:

**测试夹具 → 归 tester。** `testdata/`、`fixtures/`、`conftest.py`、mock。
不写进去,tester 加第一个 fixture 就被判越界:

```json
"roles": {
  "tester": ["tests", "**/testdata/**", "conftest.py"],
  "dev":    ["src", "pom.xml", "!**/testdata/**"]
}
```

**构建/依赖文件 → 归 dev,不要丢进 `ignore_paths`。** `pom.xml`、`package.json`、
`requirements.txt`。加一个依赖是需要被对方在评审时看见的**实质决策**,
而 `ignore_paths` 会让它完全无痕。`ignore_paths` 只放真正的副产物
(`target/`、`dist/`、lockfile)。

### 范围:切一条缝,不接全仓库

```json
"scope": ["src/*/java/com/acme/billing/**"]
```

范围外的改动一律被拒。存量项目最危险的不是结构不合适,是**蔓延** ——
改一个计费 bug,顺手动了三个公共工具类。有了 `scope`,"要不要扩大范围"
变成人类的显式决定。评审目录与记忆层永远豁免。

### 老套件红着,或者慢得没法每回合跑

**门禁套件可以收窄,但它必须是绿的:**

```json
"test_cmd":      "pytest tests/billing",
"full_test_cmd": "pytest"
```

`test_cmd` 是门禁,红绿不变量全押在它身上;`full_test_cmd` 只在工作项完成时
跑一次,红了不阻断但退出码是 2、要求 agent 报告而不是宣布"完成"。

在 `docs/reviews/baseline.md` 写明放弃了哪些用例、为什么。
**这不是把"绿"放宽,是缩小它的范围并留痕。**

### 已有的 CLAUDE.md / AGENTS.md 会被合并,不会被覆盖

`init` 把协议激活段落插到文件**开头**,原内容原样保留在后面,
用 `<!-- pair-protocol:begin -->` / `<!-- pair-protocol:end -->` 标记。
重跑 `init` 就地更新,不重复插入;人类把整块挪走之后也仍然认得。

### PLAN 不是从零规划

现有项目通常已经有 issue tracker、TODO、需求列表 —— 不是白纸,是**粒度不对**。
从既有清单里挑本轮范围内的,重切成"一个回合写三五个用例就覆盖完"。

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

**契约小节的形状按接口面选** —— 函数、HTTP 端点、CLI 命令、数据产物、消息消费、
渲染视图各有各的必填项(端点要写幂等性,消息要写重复投递和毒消息,
渲染视图**只能用无障碍树的语言**描述)。一份契约里不同小节用不同形状是常态。
菜单在 [`references/contract-templates.md`](.agents/skills/pair-protocol/references/contract-templates.md)。

每个小节还要写一行 `- 依据:`,记的是这一节凭什么可信:

| 值 | tester 能据此断言吗 |
|---|---|
| `人类定稿` | ✅ 新项目照骨架写,默认就是这个 |
| `考古观察@<sha>` | ✅ agent 读过代码、跑过代码之后写下来的现状 |
| `已有文档 <路径>(待核实)` | ❌ 只是线索 |

老文档过时是存量项目的头号病症,而照它写断言会让整条链每一步都合规、
结果却是错的。不可断言的小节只能由 `[cover]` 工作项建立事实,再由人类定稿。

## 记忆层的路径

`init` 会铺好 `docs/notes/` 和 `docs/DECISIONS.md`,并在 `config.json` 里写上:

```json
"notes_dir": "docs/notes",
"decisions_file": "docs/DECISIONS.md",
"memory": true
```

两个 agent 每一回合都是新来的:看不到彼此的对话,也不共享各自工具的记忆。
笔记记工作项级的负空间(试过什么没成、否掉了什么),决策记录记项目级的结论,
`status` 在轮到谁时把相干的部分读给谁听。详见 SKILL.md 的「记忆」一节。

改路径时有两条硬约束,`verify-setup` 会替你查:

- **不能落在 `roles` 之下** —— 记忆层必须两个角色都能写,被角色路径圈进去
  就变成单方私有的了
- **不能落在 `shared_paths` 之下** —— 「提了异议必须写下来」那条检查认的是
  `shared_paths` 下的文件,笔记若也算数,那条防护会被随手写的笔记满足

**存量项目可以先关掉**:`"memory": false`,四个强制时刻全部失效,`status`
也不再注入。等主流程跑顺了再打开。

## 启动两个 agent

### 拓扑 A:同目录(两个 CLI harness)—— 推荐的起步配置

两边写路径不相交,可以共用一个工作目录。用环境变量分配角色:

```bash
PAIR_ROLE=tester <agent A 的命令>    # 终端 1
PAIR_ROLE=dev    <agent B 的命令>    # 终端 2
```

**A 和 B 可以是同一个工具、同一个模型。** 分工本身(一次只干一件事、
产物所有权独立)就有收益,这一点有实证;两端换成不同厂商能多拿到多少,
目前没有证据。先用同一个工具开两个终端把流程跑顺,再考虑混搭。

### 拓扑 B:分离工作副本(GUI / 云端 harness)

Cursor、VS Code、Windsurf 从 GUI 启动,Devin、Jules 跑在云端,都没有可靠的地方
塞环境变量。给它们各自一份独立 clone 或 worktree,用文件或分支名声明角色:

```bash
echo tester > .pair/whoami        # 或者:git switch -c pair/tester
```

此拓扑要在 `config.json` 里开 `"sync": true`,`status` 会先 `git pull --rebase`,
`handoff` 会在提交后 `git push`。

### 想省掉来回敲那一步:自动驱动(可选)

```bash
python3 .agents/skills/pair-protocol/scripts/drive.py --both "claude -p"
```

它读协议的 `whose-turn`,拉起该轮到的那一方,跑完再问一次。**通信仍然只走 git** ——
它只是把"人敲键盘"换成"脚本敲键盘",判定一条都没搬过去。

**默认不开,而且建议先手动跑顺再用。** ADR-010 的理由:手动交接顺带保证了
每回合有一个天然的观察窗口、跑飞的成本有上界。自动化会把每个还没暴露的设计
缺陷放大成事故 —— 第一次真实运行就撞出一个协议死锁,而它是在人类的观察窗口里
被发现的(见 [docs/dogfood-run-1.md](docs/dogfood-run-1.md))。

驱动器在协议说该停、进程非零退出、连续两回合没进展、超过回合预算时都会停下。

每个回合的完整输出会落在 `.pair/turns/NNN-<角色>.log`(同时实时打在屏幕上),
停下来时驱动器告诉你看哪一份。**自动驱动如果不留痕,等于把观察窗口关掉。**

### 人类介入的纪律:只提交自己产生的东西

结对期间你随时可以介入 —— 修协议缺陷、加 `.gitignore`、裁决僵局。但有一条硬纪律:

> **`git add -A` 会把结对方停在工作区里的产出一起提交走。**

后果不只是"提交串位"。协议里那条「打回之后的修正回合必须真的动了测试」
是**按工作区改动**判断的,它的隐含前提是"这一回合的产出还在工作区里"。
你把对方的产出提交走,它的产出确实存在,但已经不在工作区 ——
检查会把它读成"你什么都没干"并拦下,而对方无从自证。

所以介入时:**只 `git add` 你自己改的那几个文件**,别用 `-A`。
改完立刻提交也是必须的 —— 留在工作区里的改动会让对方下一次交接判越界
(仓库根的文件不在任何角色的可写路径下)。

这条是真实踩出来的,见 [docs/dogfood-run-1.md](docs/dogfood-run-1.md)。

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
