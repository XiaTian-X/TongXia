# 第十五轮独立运行 —— 编排日志

- 项目:examples/make-demo.py 用 TongXia be39b2e(第十四轮完成后)生成的全新样板项目,工作项 W1–W4
- 目录:/Users/xbase/workspace/TongXia-run15;日志放在仓库外(本文件)
- 参与者:两个 general-purpose subagent,各持续一个会话(tester / dev),用 SendMessage 续接
- 编排者只发两种消息:第一条(角色 + 目录 + PAIR_ROLE 用法)与固定提示(drive.py 的 DEFAULT_PROMPT 原文)
- 不回答任何需要判断的问题,原样转给人类;轮到谁只问 whose-turn
- 同设置、同项目:这一轮是第十四轮修复的对照实验。开跑前没有任何人类定稿

## 事先定好的观察项(第十三轮对照)

| # | 观察项 | 第十三轮 | 本轮期望 |
|---|---|---|---|
| 1 | 生成的项目里有没有空目录 / 未跟踪残留 | 有空的 tests/conformance/ | 无(W29,编排者开跑前已核) |
| 2 | 样板契约的组合符规则 | क़ → क,两个会话交人类 | 契约写明,不再上报(W29 文档) |
| 3 | 验证副本放哪 | 会话自带 scratchpad(目录外),.pair/scratch 从未被用 | 简报提示后是否用 .pair/scratch/(W30) |
| 4 | 人类介入 | 0 | 0 |
| 5 | 开工前警告 / 契约问题上报 | 0 / 0 | 0 / 0 |
| 6 | report | 16 / 25% / 0 / 0 / 0 | 只读对比 |

**开跑前核实观察项 1**:生成的 run15 里 `find -type d -empty` 为空,工作区干净。

## 发出的每一条消息

### 1 → tester(派出)
与前几轮第一条逐字相同,只换目录(TongXia-run15)。

**tester 回合 1 结果**:setup-verification-tester.md(逐节点名,全 Unicode 核过组合符与小写化两条规则不冲突),verify-setup --drafter other 通过(b3910b2);试 claim 被拒(W19,dev 未校验)。无契约问题上报 —— **组合符规则没有被当成问题**,观察项 2 兑现。
**它报告了两个未跟踪的 `.DS_Store`**(根目录与 docs/),不是它建的、它没碰。编排者核实:创建于 12:16:50–55,在生成(12:15:32)之后、tester 的校验提交(12:17:13)之前 —— macOS Finder / 系统在有人浏览这个目录时写下的,不是 make-demo 带出去的(本仓库样板里没有)。
**潜在问题**:TongXia 本仓库的 `.gitignore` 忽略 `.DS_Store`,但 `init` 的 `GITIGNORE_LINES` 与样板的 `.gitignore` **都没有这一行**;未跟踪的 `.DS_Store` 不属于任何角色,**下一次 handoff 很可能被写权限边界拒绝**。编排者不动它(不干预实验),看两个会话怎么处理。→ 协议问题候选 ①
whose-turn: turn dev

### 2 → dev(派出)
与前几轮第二条逐字相同,只换目录。

**dev 回合 1 结果**:setup-verification-dev.md,verify-setup --drafter other 通过(358bb68)。**没有照抄 tester 的结论**,自己在全字符上跑了四条实现前提(str.split 与 isspace 一致、三类不重叠、小写化不产生分隔符、NFC 不改变是否算字母数字),全部成立。
**第一次有会话点出 W4 与新契约的张力**:"W4 那个分类函数没法只看单个字符,因为组合符留不留要看它前一个字符" —— 第十四轮 W29 加的组合符规则让样板 PLAN 里 W4 的原措辞("每个字符归为保留/分隔/丢弃的判定提成一个具名函数")不再能照字面做到。看 W4 时怎么处理。→ 协议问题候选 ②
也看到了 `.DS_Store`,没动。
whose-turn: turn tester

### 3 → tester(固定提示)

**tester 回合 2 结果**:claim W1(9119e0c),tests/test_slugify.py 13 条(含 128 个 ASCII 字符逐个夹在两个字母之间对照契约),RED 确认;内存里的参考实现全过,两个错误实现各红 8 / 2 条。
**handoff 被拒** —— 正是编排者预判的那一处:两个未跟踪的 `.DS_Store` 不属于任何角色,写权限边界拒绝;拒绝文案让它问人类、不要删;`.gitignore` 是冻结路径,它也改不了。它照做,停下来请人类二选一(删掉,或 `.gitignore` 加一行并提交),测试与笔记留在工作区未提交。
**协议问题 ① 坐实**:`init` 的 `GITIGNORE_LINES` 与样板 `.gitignore` 都不忽略 `.DS_Store`,而 macOS 上只要有人用 Finder 看一眼项目目录就会生成它 —— 任何 macOS 用户的第一次交接都可能被这样卡住。**编排者不代答,转人类(人类介入候选 1)。**

### 4 → 人类介入 1:`.gitignore` 加 `.DS_Store`(人类裁决 A)
编排者以人类身份提交 a1a7c41,只改 `.gitignore`(加一行 `.DS_Store`)。tester 未提交的测试与笔记原样留在工作区,没有被带进这个提交。
之后 `git status` 里只剩 tester 自己的两个文件,whose-turn 仍是 turn tester。

### 5 → tester(固定提示)

**tester 回合 3 结果**:笔记补一句"阻碍已解除",重跑同一个 handoff,通过(aa59a6d),带上 tests/test_slugify.py 13 条与笔记。
whose-turn: turn dev

### 6 → dev(固定提示)

**dev 回合 2 结果**:W1 实现 src/slugify.py,全绿,handoff 8d5f5e2;按整份契约实现(含新组合符规则),契约里的非 ASCII 例子(Café 两种写法、½、U+0958、ΟΔΟΣ、İ、纯组合符抛错)逐个跑过全对。笔记再次提醒 W4 的分类没法只看单个字符。
(它说测试 14 条,tester 说 13 条 —— 一条之差可能是冒烟用例,不影响。)
whose-turn: turn tester

### 7 → tester(固定提示)

**tester 回合 4 结果**:W1 review-impl approve(b2eac9b)。另写参考实现(空白直接用 str.split() 判,不采信 dev 说的 isspace 等价)在全部码位 × 4 种上下文、20 万随机串上对比,0 差异。
参考实现"kept in memory and never saved" —— 仍是内存里跑,没有用 `.pair/scratch/`(编排者查:run15 没有这个目录)。它的首选本来就是规则的首选,不算反例。
whose-turn: turn dev

### 8 → dev(固定提示)

**dev 回合 3 结果**:W1 review-test approve(7394ff7),**W1 完成**。内存里 11 个错误版本抓 10 个;漏的"整串一次性小写"是 ASCII 范围的物理上限,写明 W3 必须补 `ΟΔΟΣ → οδοσ`。
**晋升 DECISIONS ## W1,把"W4 重构时组合符不能只看单个字符分类"写成了长期结论** —— 协议问题 ② 已经从笔记进了决策记录,W4 的会话会在记忆注入里看到。
whose-turn: turn tester

### 9 → tester(固定提示)

**tester 回合 5 结果**:claim W2,tests/test_truncate.py 15 条(含"原样返回不做规范化":5 个码位的分解式 Café 在 n=5 时原样,不变成 4 个码位的合成式;全表覆盖每个长度 × n 从 1 到长度+2),RED,handoff 6dd87a1;10 个错误版本全抓。推断出来的三条(False → ValueError、浮点 → TypeError、"原样"= 不规范化)写进笔记。
whose-turn: turn dev

### 10 → dev(固定提示)

**dev 回合 4 结果**:W2 实现 src/truncate.py,29 条绿,handoff 19b33b7,无异议;笔记记了 IntEnum 等 int 子类也会被接受(契约没提)。
whose-turn: turn tester

### 11 → tester(固定提示)

**tester 回合 6 结果**:W2 review-impl approve(db4e678)。10 万组随机 (text, n) 对照内存参考实现(含组合符、`…`、孤立代理、emoji;n 取负数、布尔、浮点、字符串、None、10³⁰),结果与异常全一致。
whose-turn: turn dev

### 12 → dev(固定提示)

**dev 回合 5 结果**:W2 review-test approve(56a2b74),**W2 完成**。内存里 15 个错误版本全抓,其中 5 个是 tester 笔记没列过的(退到单词边界、n==1 返回空串等)。两条推断读法(False → ValueError、浮点 → TypeError)双方开工前各自写过同样的读法。晋升 DECISIONS ## W2。
whose-turn: turn tester

### 13 → tester(固定提示)

**tester 回合 7 结果**:claim W3(cover),tests/test_slugify_unicode.py 18 条,47 条全绿,handoff fd75c35。
- 覆盖新组合符规则的正反两面:跟在保留字符后面保留(含连续几个)、在开头 / 分隔符后 / 被丢字符后丢弃、U+0958 拆成两个码位、纯组合符抛 ValueError。
- 12 个错误版本抓 11 个,包括 **W1 抓不住、DECISIONS ## W1 点名要 W3 补的那三个**(整串小写、不做 NFC、组合符一律保留)—— 决策记录跨工作项被接住。第 12 个(先小写再分类)逐码位 × 5 种上下文证明与真实现无差。
- cover 两节笔记齐全,冻结的三条可疑行为(输出不再 NFC、Unicode 连字符把词粘在一起、零宽字符丢弃)都是契约要求的。
**编排者核实**:测试文件 0 个非 ASCII 字符(连中文注释都没有)、40 处 `chr(`、对 NFC 是不动点。
whose-turn: turn dev

### 14 → dev(固定提示)

**dev 回合 6 结果**:W3 review-test **打回(本轮第 1 次)**(b031e24)。
- 契约 `docs/CONTRACT.md:48` 明文"结果不再做一次 NFC";tester 笔记说这条已冻结,依据是 İ 与 U+0958 —— 但**这两个例子的输出本身就是 NFC**,多不多做一次规范化结果一样。"算完再做一次 NFC"的错误版本在 31 条 slugify 用例下 0 条红。
- 找到能区分的输入:`Ϊ` + U+0301 —— 契约要 U+03CA U+0301,错误版本得 U+0390。穷举"所有字符 + 常见变音符号"5 种组合,会输出非 NFC 的只有 10 例,全是大写希腊字母带变音那一类。
- 要求:加这条用例,并加一行断言证明期望值本身**不是** NFC(否则用例没有区分力);修正笔记第 16 行。
- 其余:18 个期望值逐条手推全对,另造的两个错误版本被抓,"先小写再判定"等价的说法独立核对成立。
**这是 W29 新契约规则的第二处连带影响**:"结果不再做一次 NFC"是我在第十四轮写进样板契约的,当时只给了 U+0958 这一个例子,而它恰好是 NFC 不动点 —— 契约自己的例子就没有区分力。
whose-turn: turn tester

### 15 → tester(固定提示)

**tester 回合 8 结果**:接受打回并先自己复核:6 个变音符号 × 全部字符,找到 21 个能区分的输入(全是"大写字母 + 没有合成形式的变音、而小写有合成形式"),其中有纯拉丁的 `"T"` + 分音符。新增 `test_result_is_not_renormalised`(`T` + U+0308、`Ϊ` + U+0301),**每个例子自带两条前提断言**:输入本身已是 NFC、期望值做一次 NFC 会变 —— 证明这条用例真有区分力。再规范化的错误版本现在红;文件仍 0 个非 ASCII 字符。笔记更正。handoff 94b05fc。
**比 dev 给的例子更好**:dev 只找到希腊字母那 10 例,tester 扩大到 6 个变音符号后找到了一个 ASCII 字母的例子。
W17 捷径生效。
whose-turn: turn dev

### 16 → dev(固定提示)

**dev 回合 7 结果**:W3 复审 approve(e2cd869),**W3 完成**。独立核对两个新例子;错误版本复跑:再 NFC 由红 0 变红 1、整串小写红 1、NFKC 红 3,真实现 0。它指出 tester 那两行前提断言的额外价值:换了 Unicode 版本、例子不再成立时测试会变红,而不是悄悄恒绿。晋升 DECISIONS ## W3(契约自带的 İ 与 U+0958 测不出"结果不再 NFC")。
whose-turn: turn tester

### 17 → tester(固定提示)

**tester 回合 9 结果**:claim W4(bcde56d),回合归 dev。**它从决策记录读到了 W4 的张力**,并提前说明评审时要看:新函数要么加第四类"组合符",要么带上前一个字符的状态;并打算逐码位比对新旧版本。
whose-turn: turn dev

### 18 → dev(固定提示)

**dev 回合 8 结果**:W4 impl,48 条绿,handoff 52d297b。新增 `_classify_char(ch, prev_kept)` —— **把"前一个字符是否保留"作为参数显式传入**,不开第四类,照 W1 决策的提醒解决了 PLAN 措辞与新契约的张力。新旧版本从 git 读进内存逐一比对(全部码位 × 7 种上下文共 7,798,784 个输入、30 万随机串、非 str 与 str 子类),返回值、类型、异常类型与消息 0 处不同。考古记录三节;自报两处拿不准(`KEEP`/`SEPARATE`/`DROP` 没加下划线、用 `is` 比较),请 tester 重点看 —— 第十一轮 dev 正是在"用 is 比较字符串常量"上修过一次隐患。
whose-turn: turn tester

### 19 → tester(固定提示,PLAN 的最后一个阶段)

**tester 回合 10 结果**:W4 review-impl approve(cf0c2b2),**W4 完成,PLAN 全部完成**。刻意用 dev 没用过的输入比对(6 种上下文含三个连续组合符;30 万随机串含 emoji、私用区、未分配码位),0 差异;逐行核对新旧循环等价。`KEEP`/`SEPARATE`/`DROP` 没加下划线不打回(不从包导出、契约不涉及)。**没有评 `is` 比较**(dev 请它重点看的两处之一)。

## 结算

report:完成 4、交接 14、认领 4、打回 14% (1/7,脚本判偏低)、协议开销 0、未判定 0、死锁 0、异议 0、决策/完成 4/4。22 个提交,1 个是人类(`.gitignore` 加 `.DS_Store`)。
人类介入 1 次(`.DS_Store` 挡住 tester 的第一次交接);用量中断 0;W17 捷径 1 次。
**`.pair/scratch/` 仍未被使用**:两个会话的参考实现与错误版本全程只在内存里跑、没有落成文件 —— 这是规则的首选做法,W30 的提示没有机会被验证。
