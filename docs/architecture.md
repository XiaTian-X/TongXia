# 架构

> 为什么这么分层见 [design-philosophy.md](design-philosophy.md) 第四、九节。
> 规范性的字段与状态定义见 [protocol-spec.md](protocol-spec.md)。

## 三层

```
┌──────────────────────────────────────────────────────────────┐
│  引导层   cli/pair_bootstrap/                                 │
│           唯一职责:把协议目录搬进目标项目 + 建软链接           │
│           不含任何协议逻辑                                     │
└────────────────────────┬─────────────────────────────────────┘
                         │  复制 + 调用 pair.py init
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  协议层   .agents/skills/pair-protocol/                       │
│           SKILL.md            给 agent 读的协议正文(渐进披露) │
│           references/rules.md 硬性规则详解与判例(按需加载)   │
│                                                               │
│  执行层   scripts/pair.py     全部判定逻辑。单文件,仅 stdlib  │
└────────────────────────┬─────────────────────────────────────┘
                         │  读写
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  状态层   .pair/config.json   人类维护的配置                   │
│           .pair/state.json    脚本独占,agent 碰即拒绝          │
│           .pair/whoami        角色声明(可选,gitignore)       │
│           .pair/.last-test.log 最近一次测试输出(gitignore)    │
│                                                               │
│  产物层   docs/PLAN.md        工作项(冻结,人类维护)         │
│           docs/CONTRACT.md    接口契约(冻结,人类维护)       │
│           docs/reviews/       评审、异议、契约变更请求          │
│           docs/notes/<ID>.md  工作项笔记(负空间)             │
│           docs/DECISIONS.md   决策记录(追加式)               │
└──────────────────────────────────────────────────────────────┘
```

**协议层是唯一真源。** 引导层只搬运,构建时把整个协议目录原样打进 wheel
(`pyproject.toml` 的 `force-include`)。任何一处协议判定出现在引导层,
它就会和真源漂移。

## 谁读什么

| | tester | dev | 人类 | 脚本 |
|---|---|---|---|---|
| `SKILL.md` | 读 | 读 | 读 | — |
| `references/rules.md` | 按需读 | 按需读 | 读 | — |
| `docs/PLAN.md` | 读 | 读 | **写** | 读 + 勾选完成项 |
| `docs/CONTRACT.md` | 读 | 读 | **写** | 读 + 校验引用 |
| `docs/reviews/` | 读写 | 读写 | 读 | 校验有无写入 |
| `docs/notes/<ID>.md` | 读写 | 读写 | 读 | 注入 + 校验 |
| `docs/DECISIONS.md` | 追加 | 追加 | 读 | 注入 + 校验 |
| `tests/`(tester 路径) | **写** | 只读 | — | 边界校验 |
| `src/`(dev 路径) | 只读 | **写** | — | 边界校验 |
| `.pair/config.json` | 读 | 读 | **写** | 读 |
| `.pair/state.json` | — | — | 读 | **独占写** |

"—"表示不该碰。碰了 `handoff` 会拒绝。

## 一个回合的数据流

```
agent 被人类唤醒
  │
  ├─► pair.py status ──────────────────────────────────────┐
  │     ① 解析角色  PAIR_ROLE → .pair/whoami → git 分支名   │
  │     ② sync 模式下 git pull --rebase                     │
  │     ③ 读 state.json:阶段 / 工作项 / 类型 / 打回计数     │
  │     ④ 跑测试,得到红绿                                   │
  │     ⑤ 记忆注入:本工作项笔记全文                         │
  │                 + 影响路径与本回合相干的决策条目          │
  │     ⑥ 打印本阶段的具体任务(PHASE_BRIEF)                │
  │                                                          │
  │   不是你的回合 → 报告在等谁 → 停止 ◄────────────────────┘
  │
  ├─► (仅 idle 且 tester) pair.py claim <ID>
  │     检查 setup_verified 与本角色校验过的契约 → 解析 PLAN → 记 contract_sha
  │     → 按类型进入起始阶段 → 立即提交(留痕 + 让 state 变干净)
  │
  ├─► 干活:只写自己路径下的文件,随手往 notes 写负空间
  │
  └─► pair.py handoff [approve|changes] "说明"
        ① 回合归属          me == PHASE_OWNER[phase]?
        ② PLAN 是否已全完成
        ③ state.json 篡改检测(改了就还原 + 拒绝)
        ④ 解析裁决          评审阶段必须 approve/changes 且理由非空
        ⑤ 流程合法性        (phase, verdict) 在本类型的 transitions 里?
        ⑥ 写权限边界        逐个文件比对 allowed / frozen / ignore
        ⑦ 测试删除防护      删了测试且没有 --allow-deletion → 拒绝
        ⑧ require_new_tests cover 类型必须真的碰了测试文件
        ⑨ 异议举证          impl 阶段 changes 必须写了 shared_paths 下的文件
        ⑩ 记忆层门禁        追加式 / 条目格式 / 考古记录 / 二次打回 /
                            契约变更记录 / 笔记晋升
        ⑪ 红绿不变量        按类型的 expect,异议路径豁免
        ⑫ 死锁闸            同一工作项打回达 3 次 → 记录 + 提交 + 停止
        ── 全过 ──────────────────────────────────────────────
        ⑬ 翻转状态并写 state.json
        ⑭ git add -A && git commit(带结构化 body)
        ⑮ sync 模式下 git push;失败则打断并要求报告"推送失败"
```

**顺序是有意的:** 纸面上的问题(⑥⑦⑧⑨⑩)排在跑测试(⑪)之前 ——
一次越界提交不值得先花一遍测试时间。而篡改检测(③)排在一切之前,
因为它一旦发生,后面所有基于 state 的判断都不可信。

## 状态机

```
                 claim(feature/bug)          claim(cover)         claim(refactor)
                        │                         │                     │
                        ▼                         ▼                     ▼
 idle ──────────────► spec ────────► impl ──► review-impl ──► review-test ──► DONE ──► idle
   ▲                   ▲   \          │  \        │ approve       │ approve
   │                   │    \         │   \       │               │
   │                   │     \        │    changes│               │ changes
   │                   │      └───────┼───────────┘               │
   │                   └──────────────┼───────────────────────────┘
   │                    changes       │ changes(异议:测试与契约矛盾)
   └────────────────────────────────  └──► spec
                  DONE
```

三条流程的实际边表:

| 类型 | 起始 | 转移 | 红绿要求 |
|---|---|---|---|
| `feature` / `bug` | spec | spec→impl→review-impl→review-test→DONE | spec=RED,其余=GREEN |
| `cover` | spec | spec→review-test→DONE | 全程 GREEN,spec 必须真的写了测试 |
| `refactor` | impl | impl→review-impl→DONE | 全程 GREEN,impl 必须交考古记录 |

打回:`review-impl changes` → impl;`review-test changes` → spec;
`impl changes`(异议)→ spec。异议路径**豁免红绿检查**。
`review-test changes` 之后的 spec 回合若 GREEN 且契约自实现被审过之后没变,直接回 review-test。

## 强制力分布

这是理解这个架构最重要的一张表:**哪些规则是脚本拦的,哪些只能靠留痕。**

<!-- pair-enforcements: turn-ownership write-boundary red-green state-untampered test-deletion verdict-valid decision-format archaeology-note contract-change-note note-promotion deadlock setup-report review-evidence scope cover-note contract-provenance refactor-safety-net post-dispute-fix dispute-shape contract-change-shape baseline-shape setup-report-coverage doc-reason roadmap-basis contract-change-basis contract-change-now -->

| 规则 | 强制方式 | 失效条件 |
|---|---|---|
| 回合归属 | 脚本拒绝 | 改代码 |
| 写权限边界 | 脚本拒绝 | 改代码 |
| 红绿不变量 | 脚本拒绝 | 改代码 |
| 状态不可篡改 | 脚本检测 + 自动还原 | 改代码 |
| 删除测试 | 脚本拒绝,除非显式声明 | 改代码 |
| 评审理由非空 | 脚本拒绝 | 改代码 |
| 文档改动带理由 | 脚本拒绝 | 改代码 |
| 路线图改写有依据 | 脚本拒绝(依据要指向真实文件) | 改代码 |
| 承重文件带声明才放行 | 脚本拒绝;豁免只认 `plan_file` / `contract_file` 两个键 | 改代码 |
| 声明的那次交接当场留决策 | 脚本拒绝 | 改代码 |
| 决策格式与追加式 | 脚本拒绝 | 改代码 |
| 考古记录三小节 | 脚本拒绝 | 改代码 |
| 契约变更留记录 | 脚本拒绝(比对 blob sha) | 改代码 |
| 笔记晋升 | 脚本拒绝,除非 `--no-decision` | 改代码 |
| 死锁闸 | 脚本拒绝 | 改代码 |
| 契约歧义审查 | 脚本要求交出 ≥120 字结论 | 敷衍地写满 120 字 |
| 评审带证据 | 脚本拒绝(approve 要检查清单,changes 要位置引用) | 引用真文件 + 假行号 |
| 范围收缩 | 脚本拒绝(配了 `scope` 时) | 改代码 |
| 契约依据分级 | 脚本拒绝(不可断言的规格开不了非 cover 项) | 人类把 `依据` 填成"人类定稿"却没真核实 |
| cover 的特征测试记录 | 脚本拒绝(两个小节) | 写满字数但不说实话 |
| refactor 的安全网 | 脚本拒绝(保护测试路径必须存在且属 tester) | 指向一个跟本次重构无关的测试目录 |
| 异议后必须真的改测试 | 脚本拒绝(豁免红绿,但要求动过 tester 路径) | 改一个无关的测试文件 |
| 评审文件命名 | 脚本拒绝 | 改代码 |
| 异议的三要素 | 脚本拒绝(文件必须存在 + 三小节) | 每节写满 40 字废话 |
| 契约变更的四要素 | 脚本拒绝(**按文件名触发**) | 换个文件名 |
| 考古观察的 sha 真实 | 脚本拒绝(git 说了算) | 用真 sha 但没真读代码 |
| 契约审查逐节点名 | 脚本拒绝 | 「以下小节均无歧义:A、B、C」 |
| **不许过拟合断言** | ❌ 只有 prose + 对方评审 | 双方都敷衍 |
| **不许硬编码蒙混** | ❌ 只有 prose + 对方评审 | 双方都敷衍 |
| **契约不含糊** | ❌ 只有人类 | 人类偷懒 |

> **注意最后一行没有变。** 「契约审查逐节点名」只保证**覆盖面**,不保证消歧:
> 它挡得住"通篇没提任何一节",挡不住"每节都提了、每节都说没问题"。
> 把它当成已经守住了那条,就是 ADR-012 说的"让人以为强制力还在" ——
> 只不过这次发生在文档上。

最后三行是这套协议的真实边界。

「评审带证据」这一行原来也在其中(标着 ❌ 只有 prose)。现在脚本要求 `approve` 交出检查清单、`changes` 指到
`路径:行号` —— **脚本查得了结构,查不了内容**:引用一个真实文件配一个假行号
仍然过得去。这不是消灭敷衍,是把敷衍的成本从零抬到"必须真的打开过文件"。
剩下的靠 `report` 的打回率暴露。改进方案见 [improvements.md](improvements.md) 的 P0-1。

## 仓库结构

```
.agents/skills/pair-protocol/    ← 产物。复制这个目录就能接入任何项目
├── SKILL.md                       协议正文
├── references/rules.md            规则详解与判例
└── scripts/pair.py                执行层(1.8k 行,仅 stdlib)
.claude/skills/pair-protocol       → 软链接到上面(Claude Code 读这里)
cli/pair_bootstrap/__init__.py   ← 极薄 bootstrap
tests/conformance/               ← 一致性测试 + 变异检查
├── harness.py                     造一个临时仓库、扮演两个 agent
├── test_positive.py               正常流程走得通
├── test_boundaries.py             越界写被拦
├── test_invariants.py             红绿被拦
├── test_turn_and_state.py         抢回合、篡改状态被拦
├── test_v1_setup.py               init / verify-setup
├── test_v1_flows.py               三种工作项类型的流程
├── test_v1_layouts.py             目录切分 / Go / JS 的 glob 边界
├── test_v1_disputes.py            异议路径
├── test_v1_memory.py              记忆层六道门禁
├── test_v1_cli.py                 bootstrap CLI
└── mutation_check.py              逐个拆防护,确认测试抓得到
examples/                        ← 样板项目模板 + 生成脚本
docs/                            ← 本目录
```

## 跨 harness 的接入面

协议不假设自己拥有任何一端的 agent,只往仓库里放文件。被识别的路径有两类:

**技能发现路径**

- `.agents/skills/` —— 跨客户端惯例(Codex、Cursor、Gemini CLI、Copilot、
  VS Code、Goose、OpenCode、Amp、Factory、Junie、Kiro 等从这里扫描)
- `.claude/skills/` —— Claude Code 读这里,用软链接指向同一份真源。
  Windows 上创建软链接需要管理员权限或开发者模式,CLI 会自动退化成桩文件

**入口文件**(`init` 铺设,内容是同一段激活指令)

`AGENTS.md` · `CLAUDE.md` · `GEMINI.md` · `.cursor/rules/*.mdc` ·
`.windsurfrules` · `.clinerules` · `.github/copilot-instructions.md`

这两类合起来是"技能激活不是 100% 可靠"这条已知边界的对策:
入口文件里的激活器是硬命令,渐进披露的加载是软的。
某个 agent 没按协议走时,**第一件事是确认它到底有没有读到 SKILL.md**。
