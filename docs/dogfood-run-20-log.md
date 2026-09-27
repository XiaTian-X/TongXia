# 第二十轮独立运行 —— 编排日志

- 项目:examples/make-demo.py 用 TongXia 7b0c559(第十九轮完成后)生成的全新样板项目,工作项 W1–W4
- 目录:/Users/xbase/workspace/TongXia-run20;日志放在仓库外(本文件)
- 参与者:两个 general-purpose subagent,各持续一个会话(tester / dev),用 SendMessage 续接
- 编排者只发两种消息:第一条(角色 + 目录 + PAIR_ROLE 用法)与固定提示(drive.py 的 DEFAULT_PROMPT 原文)
- 不回答任何需要判断的问题,原样转给人类;轮到谁只问 whose-turn
- 同设置、同项目:这一轮是第十九轮修复的对照实验。开跑前没有任何人类定稿

## 事先定好的观察项(第十八轮对照)

| # | 观察项 | 第十八轮 | 本轮期望 |
|---|---|---|---|
| 1 | W3 的用例覆盖组合符三类(Mn/Mc/Me) | 只有 Mn,被打回 | 一开始就覆盖(W36 给了例子) |
| 2 | W3 的用例分得开 lower 与 casefold | 分不开,被打回(第十三轮也是) | 一开始就分得开 |
| 3 | 文档里写码位 | 转义 4 次被写文件工具解掉 | 用 `U+XXXX` 文字,不再撞上 |
| 4 | 人类介入 | 0 | 0 |
| 5 | `.pair/scratch/` | 六个文件 | 只读对比 |
| 6 | report | 14 / 14% / 0 / 0 / 0 | 只读对比 |

## 发出的每一条消息

### 1 → tester(派出)
与前几轮第一条逐字相同,只换目录(TongXia-run20)。

**tester 回合 1 结果**:setup-verification-tester.md,verify-setup --drafter other 通过(675d9d8);无阻断歧义。**又试了一次 claim W1 被拒**(第十三轮也试过,第十八轮没试)—— W27 的结尾提示点了名,它仍去试;拒绝时什么都没改。
**观察项 3 没兑现**:tester 的审查结论里 0 处反斜杠转义、3 处 `U+XXXX` 文字,**但有 6 个裸组合符嵌在引号里**(第 14、19、22、33、34 行,如 `a-` 与 `b` 之间真嵌着一个 U+0301)。它没写转义 —— 所以没有"被解掉"这回事 —— 而是直接写了字符本身;W36 的 rules.md 那一句明说"也不嵌字符本身"。这次它自己没有发现(第十八轮四次都是自己发现改回的,那时是转义被解掉、写出来的东西和想写的不一样;这次写的就是它想写的)。
→ 协议问题候选 ①:rules.md 那句话在会话写审查结论时没有被读到或没被当回事 —— 开工前校验时会话读的是 SKILL.md 与 references,那一句在 rules.md 第 6 节验证小节的最后一条。
whose-turn: turn dev

### 2 → dev(派出)
与前几轮第二条逐字相同,只换目录。

**dev 回合 1 结果**:setup-verification-dev.md,verify-setup --drafter other 通过(a31d57c)。契约 slugify 的例子全部在内存里按它的读法跑过,全码位核了三件事;与 tester 的读法逐条对过一致。
**小的文案问题**:它说 status 让它"往末尾追加",但这个文件原来不存在、只能新建 —— 简报里那句话在第一次校验时不准确。
**dev 的审查结论同样嵌了 8 个裸组合符**,0 处转义、1 处 `U+XXXX`。两个会话都没照 rules.md 那一句写。
whose-turn: turn tester

### 3 → tester(固定提示)
**编排者核实"末尾追加"**:出处是 `pair.py` 的 `IDLE_REVERIFY_BRIEF`(W19 加的,idle 归 dev 时打的那段)—— 它假定 dev 以前校验过、契约变了才要重跑,所以写"通读变了的那几节、往末尾追加";而项目刚开工、dev 从没校验过时走的也是这一段。→ 协议问题候选 ②

**tester 回合 2 结果**:claim W1,tests/test_slugify.py 8 条只 ASCII,RED,handoff 0168b2b;`.pair/scratch/` 里参考实现 + 6 个错误版本各红。
whose-turn: turn dev

### 4 → dev(固定提示)

**dev 回合 2 结果**:W1 实现 src/slugify.py(又是与函数同名的模块),9 条绿,handoff 2cc8aaf;按整份契约实现,契约非 ASCII 例子逐个跑过。
whose-turn: turn tester

### 5 → tester(固定提示)

**tester 回合 3 结果**:W1 review-impl approve(c9d1385)。契约里 23 个例子全对;与自写的独立实现在 20 万条难字符随机串上 0 差异;5 万条 ASCII 随机串形状检查;脚本放 `.pair/scratch/`。
评审记录里又有 8 个裸组合符、2 处 `U+XXXX`(协议问题 ① 继续)。
whose-turn: turn dev

### 6 → dev(固定提示)

**dev 回合 3 结果**:W1 review-test **打回(本轮第 1 次)**(eacedc8)。
- 缺口:**只有数字、没有字母的输入没有用例**。"没有字母就抛 ValueError"(把"字母或数字"错读成"必须有字母")的实现 9 条全绿。指到 `tests/test_slugify.py:56-60`,建议补 `slugify("123") == "123"`、`slugify("!1!") == "1"`。
- 另 10 种典型写错法全抓;`casefold` 代替 `lower` 在纯 ASCII 上无从区分,明确划给 W3。
- 这一回合**没写任何临时文件**(进程里临时换函数)。
whose-turn: turn tester

### 7 → tester(固定提示)

**tester 回合 4 结果**:接受打回,新增 `test_只有数字没有字母也是合法输入`(`"123"`、`"  2024  "`、`"!1!"`、`"1 - 2_3"`),"必须有字母"的错误版本现在只红这一条;handoff 60c1507,W17 捷径(spec -> review-test)。
笔记里写下为什么漏:**只改坏了"该报错"那一侧,从没改坏"不该报错"那一侧** —— 变异测试只朝一个方向做。
whose-turn: turn dev

### 8 → dev(固定提示)

**dev 回合 4 结果**:W1 复审 approve(3b87259),**W1 完成**。12 种错误写法全抓(含上次漏的"没有字母就报错")。晋升 DECISIONS ## W1:W1 就按整份契约实现(W3 没有实现回合)、报错条件要两头都测。
**没写 `W1-review-test-2.md`**:status 让它写,它把检查内容放进了 `--checked`/`--uncovered`,handoff 照样接受。W1 第一次 review-test 有评审文件,第二次没有 —— 协议对第二次评审不强制文件,只强制两个 flag。→ 协议问题候选 ③(不严重:flag 自包含,提交正文里有全部内容)
whose-turn: turn tester

### 9 → tester(固定提示)

**tester 回合 5 结果**:claim W2,tests/test_truncate.py 14 条,**照 W1 的决策"每个边界两头都测"**(刚好不截 / 多一个字符就截、True 算 1 / False 算 0 报错、类型先于取值两个方向);`.pair/scratch/w2_mut.py` 正确版本 + 11 个错误版本全抓;RED,handoff e64c632。决策记录跨工作项被用上。
whose-turn: turn dev

### 10 → dev(固定提示)

**dev 回合 5 结果**:W2 实现 src/truncate.py,24 条绿,handoff 0102124,无异议;省略号写成 `chr(0x2026)`;笔记记了为什么不用 `type(n) is int` 与否掉的写法。
whose-turn: turn tester

### 11 → tester(固定提示)

**tester 回合 6 结果**:W2 review-impl approve(92556f4)。10 万组随机输入与独立实现一致(含组合符、emoji、孤立代理、CJK、非字符串 text、True/False/1.0/None/"3"/10**30);极值 n=±10**30 正确。
whose-turn: turn dev

### 12 → dev(固定提示)

**dev 回合 6 结果**:W2 review-test **打回(本轮第 2 次)**(3c81f0f)。
- 缺口在 `tests/test_truncate.py:64-67`:注释与笔记都说这条是为了挡"遇到组合符就回退、不肯把字母和音调拆开"的实现,**但两个断言都没切在那里** —— n=4 时长度正好等于 n 不截断;n=3 时切点落在第一个音调符与下一个字母之间。回退写法 14 条全绿,而 `truncate("e"+U+0301+"e"+U+0301, 2)` 契约要 `"e…"`、回退写法给 `"…"`。
- **用例名义上守的东西与实际守的东西对不上** —— 注释写对了意图,断言没做到。同一形状在第九轮 W1 也出现过("看起来在守、其实守不住")。
- 另 15 种写错法全抓;回退写法是唯一漏网的。
whose-turn: turn tester

### 13 → tester(固定提示)

**tester 回合 7 结果**:接受打回,新增 `test_切点落在基字母与组合符之间也照切不回退`(`e`+U+0301+`e`+U+0301 截到 2 得 `e…`、`a`+`e`+U+0301+`b` 截到 3 得 `ae…`),旧用例保留、注释改成"每个组合符算一个字符";回退写法现在只红这一条;handoff 63abdc4,W17 捷径。
**笔记里自认的漏**:spec 回合列了 11 个错误版本,**偏偏没跑自己笔记里说这条用例要挡的那一个** —— 写下了意图,没验证意图。
whose-turn: turn dev

### 14 → dev(固定提示)

**dev 回合 7 结果**:W2 复审 approve(7393db9),**W2 完成**。10 种错误版本全抓,回退写法被新用例抓住。这次写了 `W2-review-test-2.md`(W1 那次没写,协议问题 ③ 它自己补上了)。晋升 DECISIONS ## W2:按字符个数切不回退;**在笔记里声称"这条用例能挡住某种写错法"之前,先真的跑一遍那种写错法**。
whose-turn: turn tester

### 15 → tester(固定提示)

**tester 回合 8 结果**:claim W3(cover),tests/test_slugify_unicode.py 17 条,全绿,handoff 8da8de8。
- **观察项 1、2 兑现**:三类组合符(Hindi 的 Mc 词、`a`+U+20DD 的 Me、U+0301 的 Mn)一开始就在;`ß` 用例一开始就分开 `lower` 与 `casefold`。11 个错误版本(含只认一类组合符、casefold)每个都红 W3、都绿 W1 —— 证明这些都是 W3 才补上的区分力。**第十三、十八轮在这里各被打回一次,这次没有。**
- 等价变异给出证明:先小写再保留组合符的写法与真实现不可区分;逐码位核过,会被小写改变的非字母非组合符只有 U+24B6..U+24CF,两种写法都丢弃;10 万随机串 0 差异。
- cover 两节齐全,"冻结的可疑行为:无"。
whose-turn: turn dev

### 16 → dev(固定提示)

**dev 回合 8 结果**:W3 review-test **一次通过**(146b544),**W3 完成**。20 种错误版本每种都红 W3、都绿 W1;独立核过等价变异。晋升 DECISIONS ## W3:两种顺序在本机 Unicode 数据下结果相同,W4 重构时都可用,但 İ 小写带出的点必须保留。
**本轮核心观察兑现:第十三、十八轮 W3 都被打回,第二十轮一次通过** —— 样板契约的例子(W36)覆盖了三类组合符与 `ß`,tester 照着写,用例从一开始就有区分力。
whose-turn: turn tester

### 17 → tester(固定提示)

**tester 回合 9 结果**:claim W4(035f56f),回合归 dev,没改别的文件。(这次正确说出 refactor 只有 dev 实现与 tester 评审两步。)
whose-turn: turn dev

### 18 → dev(固定提示)

**dev 回合 9 结果**:W4 impl,42 条绿,handoff 053d42d。`classify_char(ch, prev_kept)` 返回 KEEP/SEPARATE/DROP,主循环里 `prev_kept = kind == KEEP` 一行更新状态;不对外导出。旧版本从 git 读进内存逐个比对:全码位 × 5 种位置约 557 万输入、30 万随机串,0 差异。考古记录三节;自报拿不准:长串连续组合符只靠推理没穷举。
whose-turn: turn tester

### 19 → tester(固定提示,PLAN 的最后一个阶段)

**tester 回合 10 结果**:W4 review-impl approve(f7642ec),**W4 完成,PLAN 全部完成**。逐分支论证了 dev 说"没穷举"的那一处(组合符分支从不改 prev_kept,统一一行赋值对任意长度的组合符链等价)—— **补上了对方自报的不确定处**;30 万余组新旧对比 0 差异;4 个改坏的 `classify_char` 各让全套红 6/6/3/4 条。用 `--no-decision`(dev 的笔记与 W3 决策已覆盖)。

## 结算

report:完成 4、交接 16、认领 4、打回 25% (2/8,脚本判 ok)、协议开销 0、未判定 0、死锁 0、异议 0、决策/完成 3/4(W4 用 --no-decision)。23 个提交,人类 0 个。
人类介入 0 次;用量中断 0 次(编排者这边的用量重置一次,子会话未受影响);W17 捷径 2 次。
**文档里的裸组合符共 26 个**,分布在五份文档(两份开工前审查、W1 实现评审、W1 与 W2 笔记);测试文件里 0 个。

**编排者自己也中了一次**:这份日志第 27 行最初照抄 tester 的例子时,同样把一个 U+0301 直接嵌进了引号里 —— 入库前用脚本扫出来改成了文字。
