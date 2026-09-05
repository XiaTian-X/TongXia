# 贡献指南

> 这个项目要做成的事:**让两个 agent 共同把 `docs/PLAN.md` 里的工作项
> 交付出来**。下面的贡献纪律几乎全是同一条手段的推论 —— **防漂移**:
> 文档、CLI、适配层一旦和 `pair.py` 说的不一样,门禁看着还在、实际拦不住,
> 交付就会悄悄变废。

## 单一真源

```
.agents/skills/pair-protocol/     ← 唯一真源
├── SKILL.md                        协议正文
├── references/rules.md             规则详解与判例
└── scripts/pair.py                 全部判定逻辑
```

- **协议逻辑只能写在 `pair.py` 里。** CLI、未来的 MCP 层、任何适配层都必须是
  纯转发。一旦它们开始自己判定,就会和真源漂移(见
  [ADR-006](design-decisions.md#adr-006-cli-不含任何协议逻辑))。
- **`docs/` 描述行为,`pair.py` 定义行为。** 两者不一致以 `pair.py` 为准,
  并且那是一个需要修的 bug。
- 构建时协议目录被 `pyproject.toml` 的 `force-include` 原样打进 wheel。
  不要在打包时改写它。

## 两条必跑的命令

```bash
# 1. 一致性测试:扮演作弊的 agent,断言 pair.py 拦得住
python3 tests/conformance/run.py

# 2. 变异检查:逐个拆掉防护,确认每一条都有测试能发现它消失
python3 tests/conformance/mutation_check.py
```

**改动强制逻辑后两个都要跑。** 只跑第一个是不够的 ——
一个恒真的测试集比没有测试更危险,它会让人以为强制力还在,
而执行层可能已经什么都不拦了。

### run.py:并行 + 改了什么测什么

测试本身不慢,慢在**每个用例都要起真的 git 仓库、真的 `pair.py` 子进程**。
`run.py` 把用例轮转分片到多个进程里跑。8 进程下全量从约 170 秒降到约 44 秒 ——
**下面这些秒数都是 8 进程实测,换机器会变**,别把它们当承诺。

```bash
python3 tests/conformance/run.py --changed   # 按 git diff 选测试模块
python3 tests/conformance/run.py memory      # 模块名模糊匹配
python3 tests/conformance/run.py -j1         # 串行,调试时输出不交错
python3 tests/conformance/run.py --list      # 只列出会跑哪些
```

`--changed` 的取舍写在 `CHANGED_RULES` 里,原则是**保守优先**:没有匹配规则的
改动一律跑全量。**改了 `pair.py` 也一律跑全量** —— 不是做不到更细,是做细了
不安全:守卫之间有顺序依赖,靠路径猜覆盖面会漏。真正需要细粒度选择的是变异
检查,那里用的是缓存,见下。

### mutation_check.py:缓存

一个变异只要**有任何一个测试**抓到它就算过关。所以第一次跑完全量之后,
把"谁抓到了它"记进 `tests/conformance/mutation-cache.json`,之后先只跑那一个。
70 个变异点的变异阶段从十几分钟降到约 26 秒(整条命令约 70 秒,差的是基线)。
这两项都是 8 进程、缓存全命中(70/70,零回退)时的实测。

```bash
python3 tests/conformance/mutation_check.py --full      # 忽略缓存,全部重跑
python3 tests/conformance/mutation_check.py --only 死锁  # 只跑名字含"死锁"的
python3 tests/conformance/mutation_check.py --slice 1/6  # 分片(CI 或分次建缓存)
```

**缓存只影响快慢,不影响结论。** 子集没抓到会回退跑全量再下结论;缓存失效
(测试改名、防护挪位)会自动走回退路径重建。缓存文件**要提交**。

每个变异点只记**一个**抓手。回退路径用的是 `failfast`,遇到第一个失败就停,
本来也只拿得到一个;而且 `loaded` 要求"请求了几个就跑了几个",多记几个不但没有
冗余作用,反而让失效更频繁。所以它不是一份"每条防护由哪些测试守着"的完整清单,
只是"至少有这一个守着"。

新增一个变异点时不用手工填缓存,第一次跑会自己补上(那一个约 2 分钟)。

**缓存里还存着一份基线指纹**(`pair.py` + 全部测试代码的哈希)。快路径的前提是
"基线是绿的" —— 只有基线绿,才能把"这些测试失败了"归因到变异上。`--no-baseline`
恰好关掉了那个前提,所以它要过**两道闸**。

**第一道是指纹闸**(`baseline_verified`)。`--no-baseline` 时要求缓存里的指纹与
当前指纹相等,不等就停用快路径、退化成逐个变异点跑全量,并在输出里说明。

**它管的是成本,不是假绿。** `2a32b5f` 之后,一个正改到一半、某个测试本来就
红着的工作区会先被下面那道预检闸拦下、`return 2`,一个变异都不会跑(而光
预检就要付 36~44s)。所以没有指纹闸并不会让它报出"全部被抓到" —— 代价换
成白付一次全量预检加 70 次全量回退。指纹闸的价值是让这件事在 0.1 秒内
说明白:指纹对不上,快路径直接停用,不必等预检和回退把时间烧完。

**第二道是基线预检闸**(`precheck_no_baseline`)。`--no-baseline` 时先在
**未变异**的隔离副本里跑一遍全量套件,副本与判定环境同构 —— 同构的是两项
代码事实:`copytree` 排除 `.git`(`isolated_copy`)、env 里设
`PAIR_MUTATION_RUN=1`。失败集非空或运行器 rc≠0,就打印失败清单、归因说明与
三条下一步,以**退出码 2** 拒绝执行;全绿才放行。这道闸是**无条件**的,
不看指纹对不对得上,也不写缓存、不放宽 `verified`。

**但运行器不是同一个,别把它记进同构清单。** 预检用的是 `run_baseline` 那
一个**并行**运行器(`run.py -j <jobs>`);`check_one` 的判定跑的是**串行**
`unittest` —— 快路径 `unittest -q <ids>`,回退路径 `unittest discover -f`。
两者发现的用例集相同(都指向 `tests/conformance`),差异只在并发与中断策略。
同构的是"在哪个副本里、带哪个环境变量跑",不是"用哪个运行器跑"。

**为什么有了指纹闸还要第二道:** 指纹闸只闸得住快路径。指纹对不上时回退路径
照跑,而回退路径的判据只有 rc≠0 —— **分不清失败来自变异还是来自环境**。基线
本来就红的环境里,每个隔离副本都复现同一个失败,于是每条变异都被判成"抓到",
报出一个恒真的 70/70 和退出码 0。两道闸的分工因此是:指纹闸管的是
**快路径可不可信**,预检闸管的是**归因可不可信**。

退出码:`0` = 全部被抓到。`1` 有**四种**来源:有变异点存活、变异点没匹配到
源码、默认路径下基线不绿、`--only`/`--slice` 一个变异点都没选出来(输出
"没有匹配 '<子串>' 的变异点。")—— 把 rc=1 一律读成"有变异点存活"会
误诊一次拼写错误。`2` 有**两种**来源:`--no-baseline` 被预检拒绝,**以及**
argparse 的用法错误(`--slice` 不是 `k/n`、长选项拼错;`argparse.error` 走
`SystemExit(2)`)。**区分这两种 `2` 看 stderr 有没有 `usage:`** —— argparse
一定带,预检拒绝不带(它打的是失败清单、归因说明与三条下一步)。撞码的干净
修法是预检拒绝改退 3、把 2 留给 argparse,已登记进 improvements;本轮按人类
裁决走文档口径,不动代码 —— 动它会让刚刷新的变异指纹失配,得重跑约 70 秒
并追加一次缓存提交。

默认路径(不加 `--no-baseline`)的行为与成本一行未变 —— 预检与它自己那次
`run_baseline` 同量级,恰好接替了被跳过的那一次全量运行。

#### 这里有两个坑,已经用测试封住了

改这块之前先读 `test_mutation_tooling.py`,它测的是**变异检查自己失效的方式**:

1. **变异运行必须设 `PAIR_MUTATION_RUN=1`。** 否则 `test_docs_consistency`
   里的"变异点仍能匹配到源码"会因为源码被改坏而失败,于是**每个变异都显得
   被抓到了**,真正存活的变异被掩盖。
2. **缓存里必须存完整的 `module.Class.method`,而且要验证它们真的跑起来了。**
   `unittest` 对认不出的 id 会报 `_FailedTest` 并非零退出 —— 这和"抓到了变异"
   在退出码上一模一样。不识别这一点,一份过期缓存就能让 70 个变异全部假装通过。

两个坑是同一类:**让一个本该有拦截力的检查变成恒真的,而且看着是绿的。**
这正是这个项目最在意的失败模式,所以它们自己也必须被测住。

起一个可跑的样板项目:

```bash
python3 examples/make-demo.py /tmp/pair-demo
```

它只在 git 自己推不出 **author 或 committer** 身份时才兜底 —— 探测
`git var GIT_AUTHOR_IDENT` 与 `GIT_COMMITTER_IDENT` 两条的退出码,**任一**
非 0 才往样板仓库的 `.git/config` 写 `user.name=conformance` /
`user.email=conformance@test`(取值沿用 `tests/conformance/harness.py` 的既有
约定)。两个 ident 都要探,因为 `git commit` 要 author 与 committer 两份身份、
各自可以独立来源:只注入 `GIT_AUTHOR_*` 的机器上 author 探测 rc=0 而
committer 探测 rc=128,只探一条就会一字不写、随后 commit 照样失败。已经有
身份的机器一字不写(两条都 rc=0 才不写),写进去的也只是仓库级配置、不碰
`~/.gitconfig`;而且已注入的那一份仍然优先 —— 实测 author 保持人类给的值,
只有 committer 落到兜底上。想用自己的身份,在样板仓库里
`git config user.email 你的邮箱`。

## 新增一条防护时

五步,缺一不可:

1. **在 `pair.py` 里加拒绝分支。** 拒绝文案要包含:拦了什么、为什么、怎么改。
   agent 只能看到这段文字 —— 它就是这条规则的全部说明书。
2. **在 `tests/conformance/` 里加一个扮演作弊 agent 的用例**,断言它被拦住。
3. **在 `mutation_check.py` 的 `MUTATIONS` 里补上对应变异点** ——
   一段能拆掉这条防护的字符串替换。没补的防护等于没有保障。
4. **在 `pair.py` 的 `ENFORCEMENTS` 里登记一个 id**,并在
   [protocol-spec.md](protocol-spec.md) §4 或 [architecture.md](architecture.md)
   的强制力分布表上方那行 `<!-- pair-enforcements: ... -->` 注释里加上它。
5. **同步文档**:`references/rules.md`(判例)、
   [protocol-spec.md](protocol-spec.md)(规范)、
   [troubleshooting.md](troubleshooting.md)(被拒了怎么办)、
   [design-decisions.md](design-decisions.md)(值得留 ADR 的决策)。

第 4 步不是形式主义:`tests/conformance/test_docs_consistency.py` 会拿
`ENFORCEMENTS`、`DEFAULT_STATE`、子命令列表逐一核对文档,漏改就红。

**这条纪律本身就是这个项目的论点用在自己身上:** 散文规则靠不住。
在那个测试出现之前,"同步文档"这一步只靠记性 —— 而它已经漏过一次
(SKILL.md 写「五条命令」,README 写「六条」)。

### 改了 `pair.py` 的行数,或者增删了一条 ADR / 不变量

同一份测试还盯着两类会**静默漂移**的东西:

- **散文里的计数。** `README.md` / `docs/README.md` 写的"N 条 ADR""16 条
  不变量",分别与 `## ADR-` 的条数和 `len(HANDOFF_INVARIANTS)` 对齐。
  提案文档(`improvements.md`)豁免 —— 它会引用过去与将来的计数。
- **文档里的 `文件.py:行号` 引用。** 这类引用是硬编码的坐标:被引文件
  上方插一行,下面每一处就都指向别处。`fc5c212` 一次让 7 处同时失效,
  而当时没有任何东西会红。

行号那条钉的是**触发条件**,不是内容:`CITED_LINE_COUNTS` 记着每个被引
文件的行数,一变就红,并把每一处引用**当前指到的内容**打出来 ——

```
INSTALL.md 的 pair.py:2375-2382   现在指到:def put(rel, content): / ...
```

逐条看一眼、改对,再更新 `CITED_LINE_COUNTS`。

**它是绊线,不是校验器,别读成"行号已经有脚本守着了"。** 行数不变的内容
修改抓不到;`improvements.md` 里只写 `` `:1787` ``(省掉文件名)的那几处
也不在扫描范围内;逃逸口(不核对就改数字)与变异缓存的基线指纹同级。
内容比对试过并且**否掉了**:引用旁的反引号片段常常是*描述*而不是原文
(`put()` vs `def put(rel, content):`),按片段比对会误伤。

变异点的写法就是拿一段唯一的源码片段换成不生效的版本:

```python
("拆掉测试删除防护",
 "    if deleted and not args.allow_deletion:",
 "    if False:"),
```

跑变异检查时它会逐个应用替换,确认对应测试**由绿变红**。
如果拆掉之后测试仍然全绿,说明那条防护没有任何测试在守着它。

## 拒绝文案的写法

拒绝文案是这个项目里最重要的文本,因为它是 agent 唯一会读到的解释。

**好的拒绝文案:**

```
拒绝交接 —— 你删除了已有测试:
  tests/test_auth.py

测试是规格,删除它等于悄悄缩小验收范围。
确有正当理由(比如该用例已被更好的用例取代)就显式声明:
  python3 <路径> handoff "说明" --allow-deletion "删除理由"
理由会写进提交记录,对方在评审时必然看到。
```

三个要素:**具体拦了哪个文件 / 为什么这是个问题 / 下一步该敲什么命令。**

**不要**写成"操作被拒绝,请检查配置"。agent 会去猜,而猜的方向通常是绕过。

## 修改协议语义时

改阶段序列、红绿纪律、角色边界这类**语义**变更,先回答三个问题:

1. **它能被编码吗?** 不能就别加进 `pair.py`,写进 `rules.md` 当判例,
   或者设计一个"强制留痕"的替代品(参考 `--allow-deletion` /
   `--no-decision` / 契约歧义结论的做法)。
2. **它会不会削弱另一条防护?** 记忆层就踩过这个坑:
   `docs/notes/` 若并进 `shared_paths`,"异议必须写下来"那条检查会被随手写的
   笔记静默满足。`verify-setup` 里那条路径重叠检查就是为此存在的。
3. **老仓库怎么办?** 新的 state 字段要有默认值,缺失时对应检查自动跳过
   (`contract_sha` 是范例);新的 config 字段要可选,不配时行为与现在完全一致。

## 反向约束

这些是明确不做的,提 PR 之前先读 [ADR](design-decisions.md) 和
[improvements.md 的"不做的事"](improvements.md#不做的事反向约束):

- 不加第三个评审角色
- 不让两个 agent 直接对话
- 决策条目不加"分析"字段
- agent 不能改 `docs/CONTRACT.md`
- 自动唤醒对方不能是默认行为
- 协议逻辑不能出现在 CLI / MCP / 任何适配层

想推翻其中一条,请在 PR 里针对对应 ADR 的**理由和代价**逐条回应,
不要只说"这样更方便"。

## 依赖纪律

`pair.py` **只用标准库**,单文件。

理由:它要被复制进任意一个项目、由任意一个 harness 执行。
多一个依赖就多一处安装失败的可能,而安装失败等于协议失效。

`requires-python = ">=3.9"`。用到更新的语法前先确认没必要。

## 文档纪律

- **定位口径有绊线守着。** 入口文档(README、SKILL.md、docs/README、
  design-philosophy、本文)的**开头**必须写明目的:两个 agent 共同把
  `PLAN.md` 里的工作项交付出来;而"防漂移""防点头""对抗"这类**手段词
  不能出现在目的槽位**(见 [ADR-022](design-decisions.md))。
  `test_docs_consistency.py` 的两条检查会红。既有 ADR、improvements、
  运行报告豁免 —— 它们是记录,不是主张。
  **它是绊线不是校验器:** 换一种没列进表里的句式照样能漂。
- **全部 md。** 目录见 [docs/README.md](README.md)。
- **一件事只在一个地方说清楚,别处链过去。** 现在的分工:
  为什么 → `design-philosophy.md`;是什么 → `protocol-spec.md`;
  怎么用 → `command-reference.md`;出错了 → `troubleshooting.md`;
  别人怎么做 → `prior-art.md`;为什么不那样 → `design-decisions.md`。
- **外部结论要带出处链接。** 这个项目的很多设计依赖实证
  (比如"不加第三个 agent"),没有出处就没法被后来人评估。
- 中文正文,代码/路径/命令保持原样。

## 提交信息

普通开发提交用 conventional commits(`feat:` / `fix:` / `docs:` / `chore:`)。

注意:`pair.py` 自己生成的提交有固定前缀(`test:` / `feat:` /
`review(impl)/approve` / `dispute:` / `chore(pair):`),那是协议事件,
不要手工模仿。

## 版本

`SKILL.md` 的 `metadata.version` 与 `pyproject.toml` / `cli/pair_bootstrap`
的 `__version__` 是两条独立的线:

- **协议版本**(SKILL.md)—— 语义变更时 +1。存量仓库靠"新字段有默认值"
  平滑升级,不做迁移脚本。
- **CLI 版本** —— 打包变更时 +1。

协议语义变更要在 PR 描述里写清楚**老仓库会不会被卡住**。
