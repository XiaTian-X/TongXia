# 命令参考

所有协议命令都以 `python3 .agents/skills/pair-protocol/scripts/pair.py` 为前缀。
下文简写为 `pair.py`。

只有 `pair init` 是另一个东西 —— 它是 bootstrap CLI,见 §7。

| 命令 | 谁跑 | 何时 | 会写文件吗 |
|---|---|---|---|
| `pair init`(CLI) | 人类或第三方 agent | 接入项目,一次 | 是 |
| `pair.py verify-setup` | 结对的另一方 | 开工前,一次 | 只写 state |
| `pair.py status` | 双方 | **每回合开头** | 否 |
| `pair.py claim <ID>` | tester | 认领工作项 | 是(提交) |
| `pair.py handoff …` | 双方 | **每回合结尾** | 是(提交) |
| `pair.py inbox [N]` | 双方 | 想知道对方做了什么 | 否 |
| `pair.py report` | **人类** | 想知道这对结对是不是在走过场 | 否 |
| `pair.py whose-turn` | 驱动器 | 一行输出:接下来该谁,或为什么该停 | 否 |

---

## 1. `status`

```
pair.py status
```

**每回合的第一条命令。跑它之前不要读代码、不要改任何文件。**

输出:

- 你是谁(角色解析结果与来源)
- 当前阶段、归属角色、工作项 ID 与类型
- 测试是红是绿
- 可写路径:**你**现在能写什么。轮到你时是本阶段的角色路径加共享路径(评审阶段另标只追加);
  不轮到你时只有共享路径与记忆层 —— 对方的路径不列出来
- **本阶段具体该做什么**(按阶段定制的任务简报)
- 记忆注入:本工作项笔记全文 + 与本回合相干的决策条目

`sync` 为真时会先 `git pull --rebase`。

**不是你的回合时:** 跑 `inbox` 看对方做了什么,向人类报告在等谁,然后**停下**。
不要抢跑 —— 回合状态在 `.pair/state.json` 里,不在对话里。

退出码 0。这是只读命令,唯一的副作用是刷新 `.pair/.last-test.log`。

---

## 2. `claim`

```
pair.py claim W1
```

只有 tester 能跑,只有 `idle` 阶段能跑。

前置条件(任一不满足即拒绝):

- 执行者是 tester
- 当前阶段是 `idle`
- 已通过 `verify-setup`(除非 `require_setup_verification` 为 false)
- 工作项在 PLAN 里、未完成、类型合法
- 非 `cover` 类型时,它指向的契约小节 `依据` 可断言
  (`人类定稿` 或 `考古观察@<sha>`;`已有文档(待核实)` 不行)
- `refactor` 类型时,PLAN 里声明了 `- 保护测试: <路径>`,该路径存在且属 tester
- `.pair/state.json` 未被篡改

成功后会**立即提交一次** `chore(pair): 认领工作项 W1 [feature]`,
并根据类型进入起始阶段:

| 类型 | 起始阶段 | 归属 |
|---|---|---|
| `feature` / `bug` | `spec` | tester |
| `cover` | `spec` | tester |
| `refactor` | `impl` | **dev** |

`refactor` 认领之后直接轮到 dev —— 认领的人要告诉人类换边了。

---

## 3. `handoff`

```
pair.py handoff "这回合做了什么"                    # spec / impl 阶段
pair.py handoff approve "摘要" --checked "…" --uncovered "…"   # 评审阶段
pair.py handoff changes "问题清单"                  # 评审阶段,或 impl 阶段的异议
pair.py handoff "说明" --allow-deletion "删除理由"
pair.py handoff approve "摘要" --checked "查了什么" --uncovered "还没覆盖什么"
pair.py handoff changes "问题清单,至少一处 路径:行号"
```

**每回合的最后一条命令。** 它校验 → 提交 → 翻转回合。校验顺序与全部
不变量见 [protocol-spec.md §4](protocol-spec.md#4-不变量)。

### 参数

| 参数 | 说明 |
|---|---|
| 位置参数 | 第一个词是 `approve` / `changes` 时被解析为裁决,其余作为说明。说明**不得**为空 |
| `--allow-deletion "理由"` | 显式声明本回合删除了测试。理由和被删文件写进提交记录正文 |
| `--no-decision "理由"` | 显式声明本工作项的笔记没有值得沉淀成决策的内容 |
| `--checked "内容"` | **approve 必填。** 你具体检查了什么 |
| `--uncovered "内容"` | **approve 必填。** 你知道还没被覆盖到的是什么(没有就写"无")|

两个 flag 的内容**必须自包含**,整段只写"详见某文件"会被拒 ——
它们的强制力有一半来自进提交正文、对方在 `inbox` 里必然看到。
详情写进 `docs/reviews/<工作项ID>-<阶段>.md`,规范见
[documents.md](../.agents/skills/pair-protocol/references/documents.md)。

**声明类旗标(`--allow-deletion` / `--no-decision` / `--doc-reason` / `--basis` /
`--contract-change`)只在生效时写进提交正文** —— 这一回合真有检查读到了它
(删了测试、晋升闸真的会拦、改了规范性文档、路线图有改写、改了承重文件)。
不生效时不写、不进 `report` 的统计,但也**不拒绝**:要治的是统计被污染,
不是用法不整洁。

`approve` 只能出现在评审阶段。`changes` 在评审阶段是打回,在 `impl` 阶段是异议。

### 被拒了怎么办

**拒绝理由就是你要修的东西。不要想办法绕过去。** 常见拒绝与处理见
[troubleshooting.md](troubleshooting.md)。

三条最容易踩的:

- **越界** → 撤销越界改动。认为对方代码有问题就写进 `docs/reviews/`,
  在评审回合用 `changes` 打回,**不要自己动手改**。
- **红绿不对** → spec 阶段是绿的说明你写了个本来就能通过的用例;
  impl 阶段是红的说明还没弄绿,看 `.pair/.last-test.log`。
- **改了 state.json** → 已自动还原。重新跑 `status` 确认真实回合。

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 交接完成 |
| 1 | 被拒绝 |
| 2 | **提交成功但 push 失败**。提交只在本地,对方看不到 —— 这等于没交接。不要告诉人类"已交接",要报告推送失败 |
| 2 | **工作项完成那一回合全量套件红**(仅配了 `full_test_cmd` 时)。门禁套件仍绿、交接已提交,但全量红 —— 工作项本身按纪律走完了(PLAN 照常勾选),但**不能向人类宣布"完成"**。不要告诉人类"完成",要报告全量套件红了,由人类决定。同一屏那句"PLAN 里的工作项已全部完成、请向人类报告完成"是 **PLAN 维度**的结论,与本行不冲突:全量红时以退出码 2 与"不要告诉人类完成"为准 |

---

## 4. `inbox`

```
pair.py inbox        # 最近 1 次交接
pair.py inbox 5      # 最近 5 次
```

只读。打印最近 N 次交接的提交标题与正文 —— 包含对方写给你的说明、
裁决理由、`--checked` / `--uncovered` 的检查清单,以及 `--allow-deletion` / `--no-decision` 的声明。

这是协议里的收件箱。**两个 agent 看不到彼此的对话**,所以对方希望你知道的事
只会出现在这里和 `docs/reviews/` 里。

---

## 5. `verify-setup`

```
pair.py verify-setup --drafter self|other
```

`--drafter` 是必填的:`other` = 我没参与契约起草,`self` = 我参与了、
这份结论的证明力因此打折。声明写进提交正文,不写在结论里 ——
用参数而不是搜措辞的理由见 [ADR-024](design-decisions.md)。

开工前的只读校验,由**两个角色各跑一次**(`claim` 要求两份校验都作数)。检查配置自洽、基线全绿、
PLAN 格式、契约覆盖度、记忆层路径合法性、入口文件齐备 ——
完整检查表见 [protocol-spec.md §5.4](protocol-spec.md#54-verify-setup)。

**它还要求一件只有你能做的事。** 脚本查得了引用完整性,查不了语义清晰度,
所以它强制你通读契约,把认为有歧义的条款写进
`docs/reviews/setup-verification-<角色>.md`(至少 120 字,两个角色各写各的;
自己那份缺失时回落到旧的 `setup-verification.md` 并警告)。

原样重跑(结论与状态位都和上次提交时一样)时**不提交也不失败**,
输出含「没有需要提交的改动」。

提交**只带这次 `add` 的那批路径里真有差异的那些**。索引里事先暂存的其他东西
原样留着 —— 不提交,也不撤销;它若落在角色路径下,「未提交的代码改动」那段
警告会列出它。开工基线里因此不会夹带别人暂存的实现。

结论还必须**逐节点名**:每个被工作项引用的契约小节都要在结论里出现过。
把契约整段粘进 ``` 围栏不算 —— 围栏内容会被剥掉。

交出这份结论(并给出 `--drafter`)之前:校验不通过,也不能 `claim`。

没有歧义就明确写"无歧义"并说明逐条核对了什么 —— 空泛的一句"看过了"不算。

**为什么值得这么麻烦:** 契约歧义是这套机制唯一会致命的失败模式。
tester 测 `login() -> token`、dev 写 `authenticate() -> Session`,
两边各自都"对",合起来是废的 —— 而且要到很晚才会暴露。

---

## 6. `init`(协议层)

```
pair.py init
```

通常由 bootstrap CLI 调用,也可以手工跑。它会:

1. 探测技术栈(测试命令)与布局(角色路径)
2. **跑一次测试。不全绿就拒绝初始化**,且此时还没写任何文件,不留残骸
3. 写 `.pair/config.json`、`.pair/state.json`
4. 起草 `docs/PLAN.md`、`docs/CONTRACT.md`、`docs/DECISIONS.md` 骨架,
   建 `docs/reviews/`、`docs/notes/`
5. 铺各家入口文件(AGENTS.md / CLAUDE.md / GEMINI.md / .cursor / .windsurfrules /
   .clinerules / .github/copilot-instructions.md)
6. 往 `.gitignore` 追加 `.pair/.last-test.log`、`.pair/whoami`

**幂等** —— 已存在的文件一律跳过,可以反复跑。

探测不到测试命令时会停下,要求人类先手工创建 `.pair/config.json` 填入 `test_cmd`。

### 为什么基线必须全绿

`impl` 阶段"测试必须 GREEN"这条不变量依赖基线全绿。基线本来就红,
协议要么直接卡死,要么那条不变量形同虚设。

**全新项目要注意:空的测试目录往往不算绿。** `python3 -m unittest discover`
在没有任何用例时会报 `NO TESTS RAN` 并非零退出。先放一条必过的冒烟用例。

---

## 6.5 `report`

```
pair.py report
pair.py report --since <rev>
```

**这条命令是给人类的,不是给 agent 的。** 只读,纯读 git log,不碰状态、不产生提交。

**只认协议写进提交里的那几行**:交接、完成、impl 交接看行首的 `role=… phase=… -> … item=… type=…`,
两条声明看行首的 `未留决策(已声明): ` / `契约变更(已声明): `,死锁看 `handoff` 生成的完整主题。
评审旗标的值、人类手写的提交正文里顺带提到这些字样,不计 —— 之前按子串数,本仓库因此多算过一次交接、一次完成。

`--since <rev>` 只统计 `<rev>..HEAD` 里的提交,表头印出起点 —— 用来单看某次实验、某一轮,
不被更早的历史稀释。`--no-decision` 与 `--contract-change` 两条比率的分母也跟着起点走
(区间里完成的工作项数)。**不受起点影响**的是读状态的几行:已完成工作项、进行中、
决策/完成项。`<rev>` 解析不成提交(包括树这类合法对象)、或者**不在当前分支的历史上**
(不是 HEAD 的祖先)时非零退出 —— 旁支上的提交当起点,统计的会是两条分支的差集,
一张看起来合理的表比报错更糟。

它补的是一个观测缺口:**"交付会不会在悄悄变废"在此之前无法量化。** 脚本能
强制 `approve` 带上 `--checked` / `--uncovered`(结构),强制不了它有内容。
两个 agent 互相点头会让两份努力合起来仍是废的,而打回率长期接近 0(评审
样本足够时)是那件事唯一的量化证据。防点头是保障交付的手段,不是协议存在
的全部目的;report 盯的是手段层有没有在空转 —— 打回率只是其中一项。

| 指标 | 健康区间 | 区间之外意味着 |
|---|---|---|
| **打回率**(changes / 评审总数) | 15%–50% | **接近 0 = 互相点头**;接近 100% = 契约有问题 |
| `推进交付的回合` | —(不设区间) | 交接提交数减去协议开销;两数之和恒等于表头的「交接提交」 |
| `协议开销的回合` | —(不设区间) | 空转的 impl 回合:既没改执行者角色路径下的东西,也没带生效的 `--contract-change` 改承重文件 |
| `未判定的 impl 回合` | —(不设区间) | 正文里没有空转判定行的 impl 交接(旧版本留下的历史)—— 只报覆盖面,不猜 |
| 死锁工作项占比 | <10% | 过高 = 契约含糊 |
| 决策 / 完成项 | — | 长期为 0 = 记忆层空转 |
| `--no-decision` 使用率 | <50% | 过高 = 晋升 gate 被当噪音绕过 |

**区间之外不等于错,等于值得看一眼。** 评审次数少于 5 次时它不下任何结论 ——
三次评审算出的打回率没有意义。

退出码始终 0:它是仪表盘,不是门禁。

---

## 6.6 `whose-turn`

```
pair.py whose-turn
```

一行机器可读的输出,**给驱动器用的**,不是给人看的:

```
turn tester        接下来轮到 tester
turn dev           接下来轮到 dev(idle 时也可能是它:tester 的校验作数、dev 的不作数,dev 要先重跑 verify-setup)
stop <理由>        该停下来交给人类
```

`stop` 的四种理由:尚未通过开工前校验、PLAN 里的工作项已全部完成、
同一工作项已被打回 3 次(死锁闸)、`state.json` 被改动过。

**不跑测试**,所以很快 —— 它会被驱动器循环调用。退出码始终 0:它是查询,不是门禁。

存在的理由是**让驱动器里没有协议逻辑**。"轮到谁""要不要停"都是协议判断,
让驱动脚本自己读 `state.json` 猜,它就成了协议的第二个实现。有测试钉着这条约束。

---

## 6.7 `drive.py`(自动驱动,可选)

```bash
python3 .agents/skills/pair-protocol/scripts/drive.py --both "claude -p"
```

把"人在两个终端之间来回敲一句"自动化。**默认不开** —— 你不跑它,协议就是手动的。

| 参数 | 说明 |
|---|---|
| `--both <命令>` | 两边用同一条命令(同工具同模型,最省事的起步配置) |
| `--tester` / `--dev` | 分别指定 |
| `--prompt` | 喂给 agent 的第一句话,从标准输入进去。默认让它按 SKILL.md 走一个回合 |
| `--max-turns` | 回合预算,超了停下交给人类(默认 24)。**这是驱动器自己的保险,不是协议的** |
| `--dry-run` | 只问协议该谁,不真的拉起 |

角色通过 `PAIR_ROLE` 环境变量传给子进程。

**它在这些时刻一律停下来交给人:**

- 协议自己说该停(`whose-turn` 返回 `stop`)
- agent 进程非零退出
- 连续两个回合状态没有前进(卡住了,再跑只会卡在同一处)
- 超过回合预算

**每个回合的完整输出落在 `.pair/turns/NNN-<角色>.log`**,同时实时打在你屏幕上。
停下来时它会告诉你最后一份日志是哪个。这个目录必须被 git 忽略
(`init` 会写进 `.gitignore`;老项目里驱动器启动时会检查并拒绝启动)——
它落在 `.pair/` 下,而 `.pair` 是冻结路径,不忽略的话第一份日志就会让下一次
`handoff` 判越界。

**它绝不碰 git。** 结对期间任何人提交东西都可能把某一方停在工作区里的产出
提交走,而「打回之后必须真的动了测试」那条检查按工作区判断,会把它读成
"你什么都没干"。见 [INSTALL.md](../INSTALL.md) 的「人类介入的纪律」。

---

## 7. `pair init`(bootstrap CLI)

```bash
uvx --from git+https://github.com/<你>/TongXia pair init /你的项目
```

这是**另一个程序**,不是 `pair.py`。它只做两件事:

1. 把 `.agents/skills/pair-protocol/` 复制进目标项目,建 `.claude/skills/` 软链接
2. 调用刚复制过去的 `pair.py init`,把后续全部交出去

**它不含任何协议逻辑。** 判定、边界、红绿、回合全部在 skill 里。
这条约束是刻意的:一旦 CLI 里出现协议逻辑,它就会和 skill 漂移。

Windows 上创建软链接需要管理员权限或开发者模式,失败时自动退化成桩文件
(内容是"真正的协议在 `.agents/skills/pair-protocol/SKILL.md`,请立即读取它")。

不想用 CLI 也可以手工来,见 [INSTALL.md](../INSTALL.md)。

---

## 8. 环境变量

| 变量 | 作用 |
|---|---|
| `PAIR_ROLE` | 角色声明,优先级最高(`tester` / `dev`) |
| `PAIR_TEST_CMD` | 覆盖 `config.test_cmd`。调试用,**不要长期依赖** —— 它绕过配置,两边可能跑的不是同一套测试 |
