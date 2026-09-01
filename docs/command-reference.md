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
pair.py verify-setup
```

开工前**一次性**的只读校验,由**还没动手的那一方**跑。检查配置自洽、基线全绿、
PLAN 格式、契约覆盖度、记忆层路径合法性、入口文件齐备 ——
完整检查表见 [protocol-spec.md §5.4](protocol-spec.md#54-verify-setup)。

**它还要求一件只有你能做的事。** 脚本查得了引用完整性,查不了语义清晰度,
所以它强制你通读契约,把认为有歧义的条款写进
`docs/reviews/setup-verification.md`(至少 120 字)。

交出这份结论之前:校验不通过,也不能 `claim`。

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
```

**这条命令是给人类的,不是给 agent 的。** 只读,纯读 git log,不碰状态、不产生提交。

它存在的理由只有一条:**"两个 agent 互相点头"在此之前不可观测。** 脚本能强制
`approve` 带上 `--checked` / `--uncovered`(结构),强制不了它有内容。打回率长期
接近 0 是那件事唯一的量化证据 —— 而这套协议存在的全部理由就是防它。

| 指标 | 健康区间 | 区间之外意味着 |
|---|---|---|
| **打回率**(changes / 评审总数) | 15%–50% | **接近 0 = 互相点头**;接近 100% = 契约有问题 |
| 每工作项回合数 | 4–8 | 过高 = 工作项切太大 |
| 死锁工作项占比 | <10% | 过高 = 契约含糊 |
| 决策 / 完成项 | — | 长期为 0 = 记忆层空转 |
| `--no-decision` 使用率 | <50% | 过高 = 晋升 gate 被当噪音绕过 |

**区间之外不等于错,等于值得看一眼。** 评审次数少于 5 次时它不下任何结论 ——
三次评审算出的打回率没有意义。

退出码始终 0:它是仪表盘,不是门禁。

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
