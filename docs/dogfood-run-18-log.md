# 第十八轮独立运行 —— 编排日志

- 项目:examples/make-demo.py 用 TongXia 0bc48de(第十七轮完成后)生成的全新样板项目,工作项 W1–W4
- 目录:/Users/xbase/workspace/TongXia-run18;日志放在仓库外(本文件)
- 参与者:两个 general-purpose subagent,各持续一个会话(tester / dev),用 SendMessage 续接
- 编排者只发两种消息:第一条(角色 + 目录 + PAIR_ROLE 用法)与固定提示(drive.py 的 DEFAULT_PROMPT 原文)
- 不回答任何需要判断的问题,原样转给人类;轮到谁只问 whose-turn
- 同设置、同项目:这一轮是第十六、十七轮修复的对照实验。开跑前没有任何人类定稿

## 事先定好的观察项(第十五轮对照)

| # | 观察项 | 第十五轮 | 本轮期望 |
|---|---|---|---|
| 1 | 生成项目的 `.gitignore` 含系统文件 | 没有,`.DS_Store` 挡住第一次交接 | 有三行(W31,编排者开跑前已核) |
| 2 | 人类介入 | 1(`.DS_Store`) | 0 |
| 3 | 样板契约"结果不再 NFC"的例子 | U+0958(没有区分力),W3 被打回 | `T̈` 一类,W3 的用例一开始就有区分力(W32) |
| 4 | 样板 W4 的措辞 | "每个字符……",与组合符规则有张力 | 允许带上前一个字符的状态(W32) |
| 5 | 验证副本放哪 | 全在内存 | 只读对比 |
| 6 | report | 14 / 14% / 0 / 0 / 0 | 只读对比 |

**开跑前核实观察项 1**:run18 的 `.gitignore` 含 `.DS_Store`、`Thumbs.db`、`desktop.ini` 三行;没有空目录;工作区干净。

## 发出的每一条消息

### 1 → tester(派出)
与前几轮第一条逐字相同,只换目录(TongXia-run18)。

**tester 回合 1 结果**:setup-verification-tester.md,verify-setup --drafter other 通过(89922ad);**这次没有试 claim** —— 读到了 W27 那句"dev 的校验还不作数",直接说轮到 dev。契约里每个例子(含 `T̈`)实跑成立,无阻断歧义。
**又一次"工具悄悄改写字符"**:它写审查结论时,`́` 转义被写文件工具解成了真的组合符;它自己发现并改回转义文字。条目 27 那一类,第四次在独立运行里出现,这次是在评审文档里、不在测试里。
whose-turn: turn dev

### 2 → dev(派出)
与前几轮第二条逐字相同,只换目录。

**dev 回合 1 结果**:setup-verification-dev.md,verify-setup --drafter other 通过(f7f9691)。全码位扫了四类可能的两义(NFC 改变是否算字母数字、NFC 合字改变分类、组合符与分隔符重叠、str.split 与 isspace 不一致),都没有。书面承诺 W1 按整节契约实现。
**没有再点出 W4 措辞与组合符规则的张力** —— 第十五轮 dev 在这一步第一个点出;这次样板 PLAN 的 W4 已改(W32),没有可点的。观察项 4 待 W4 时再看。
whose-turn: turn tester

### 3 → tester(固定提示)

**tester 回合 2 结果**:claim W1,tests/test_slugify.py 9 条只 ASCII,RED,handoff 6be77e6;逐个拆掉五种行为,各有测试红。
**`.pair/scratch/` 第一次被用上**(第八轮 W23 引入以来,六轮独立运行里第一次):它把参考实现写成 `.pair/scratch/ref.py`,明说"git 忽略它,所以不在提交里"。编排者核实:文件在,`git status --ignored` 显示为被忽略,工作区干净。W30 的简报提示与 rules.md 的新写法在这一次需要落文件时起了作用。
whose-turn: turn dev

### 4 → dev(固定提示)

**dev 回合 2 结果**:W1 实现 src/slugify.py,10 条绿,handoff 22ad4b7,无异议;按整节契约实现,契约的非 ASCII 例子(含 `T̈`、U+0958)逐条核过;全码位查过组合符小写不变。笔记给 W4 留了提示。
whose-turn: turn tester

### 5 → tester(固定提示)

**tester 回合 3 结果**:W1 review-impl approve(cd12df0)。另写一份结构不同的实现放在 `.pair/scratch/`(第二次用上),契约例子 19 个、20 万条难字符随机串、20 万条 U+0000–U+2FFFF 随机串,返回值与异常类型全一致。
**又一次转义被解掉**:写评审记录时 `́` 等又被写文件工具解成真字符,它发现并改回 —— 本轮第二次,都在评审文档里。
**第一次有会话挑出"模块与函数同名"**:`src/__init__.py:1` 以同名导出函数,`src.slugify` 变成函数而非模块;不违反契约,但提醒 W4 若从那个模块导入具名辅助函数会被绊住。(第十三轮双方都没提。)
whose-turn: turn dev

### 6 → dev(固定提示)

**dev 回合 3 结果**:W1 review-test approve(1dcdfce),**W1 完成**。内存里 6 个错误版本全抓。
- **找到一处真缺口但不打回**:测试只覆盖空格、`\t`、`\n`;把 `\r`、`\x0b`、`\x0c`、`\x1c`–`\x1f` 当"丢弃"而非"分隔"的实现全绿(`"a\rb"` 会得 `"ab"`,契约要 `"a-b"`)。理由:W1 验收标准的"空白"已覆盖到,其余属 W3 范围;但 W4 的重构只靠现有测试保护,**必须在 W4 之前由 W3 补上** —— 写进决策记录。(第十三轮这一类缺口是被打回的,这次判为跨工作项的交接。)
- **第三次转义被解掉**:它自己上一回合笔记里的 `\u` 转义被渲染成了组合符,这次全部改写成 `U+XXXX` 文字 —— 本轮第三次,三次都在文档里。
whose-turn: turn tester

### 7 → tester(固定提示)

**tester 回合 4 结果**:claim W2(选 W2 不选 W3,但**明说读到了 DECISIONS ## W1 里"W3 必须在 W4 之前补空白"**),tests/test_truncate.py 14 条,`…` 与组合符用 `chr()` 常量("转义已经被悄悄改写两次了"),RED,handoff 7d90eca。`.pair/scratch/` 里的参考实现与 8 个错误版本全抓 —— 第三次用 scratch。
whose-turn: turn dev

### 8 → dev(固定提示)

**dev 回合 4 结果**:W2 实现 src/truncate.py,24 条绿,handoff a4f8432,无异议;笔记记了为什么不用 `type(n) is int`(会拒掉 bool)。
whose-turn: turn tester

### 9 → tester(固定提示)

**tester 回合 5 结果**:W2 review-impl approve(f78497c)。30 万组随机输入与自己的独立实现对比(全 Unicode、空串、非字符串、负数与极大 n、浮点、布尔),返回值与异常类型全一致。
**第四次转义被解掉**:它自己 W2 笔记第 6 行的 `́` 被写成真组合符,改回。本轮四次,全在文档里。预告下一项认领 W3,点名要补"其余空白字符"。
whose-turn: turn dev

### 10 → dev(固定提示)

**dev 回合 5 结果**:W2 review-test approve(12068dc),**W2 完成**。在 tester 的 8 个错误版本之外又试了 6 个(接受数字字符串、2.0 当 2、接受 bytes、先判长度导致 `truncate("", 0)` 不报错、n=0 返回省略号、按字形截断),全红。
**把"非 ASCII 一律写 chr(0x...) 常量、不写 \u 转义"晋升进决策记录** —— 本轮四次撞上转义被解掉,这条约定原本只在笔记里。(第九轮 tester 也做过同样的晋升;两轮的项目是各自独立的,DECISIONS 不跨项目。)
whose-turn: turn tester

### 11 → tester(固定提示)

**tester 回合 6 结果**:claim W3(cover),tests/test_slugify_unicode.py 21 条,45 条全绿,handoff da1fc10。
- **W1 决策留下的约束被接住**:其余 26 个 `str.split()` 认的空白逐个作分隔符 —— 列表写死在测试里,不用 `isspace()` 现算(免得与实现同源)。
- **`T̈` 这次一开始就在**:"结果不再 NFC"用样板契约新例子写,11 个错误版本(含"结果再 NFC 一次")全抓 —— 第十五轮在这里被打回,W32 的修复生效。
- cover 两节齐全,冻结的可疑行为列了四条(零宽空格让两边的词粘在一起、全角/小号/软连字符被丢、控制字符作分隔、数字后的组合符保留),都照契约字面、改要走契约变更。
**编排者核实**:文件里 515 个非 ASCII 字符全是中文(用例名、docstring)与几个中文标点、一个箭头,**0 个组合符或测试用的特殊字符**;75 处 `chr(`;对 NFC 是不动点。
whose-turn: turn dev

### 12 → dev(固定提示)

**dev 回合 6 中断**:会话用量上限(HTTP 429),dev 在 W3 review-test 中途被终止。编排者核实工作区后原样重发固定提示。
工作区干净,whose-turn 仍是 turn dev,最后一个提交仍是 tester 的 da1fc10 —— 中断没留下半截产出。

### 12'→ dev(固定提示,重发)

**dev 回合 6(重发后)结果**:W3 review-test **打回(本轮第 1 次)**(53ab3fa)。
- 核过的:期望值都有契约出处、cover 两节齐全、空白表全码位核对(isspace 为真 29 个 = 表里 26 + W1 的 3)、连字符表与符号表没有一个是空白/字母数字/组合符。
- **两个错误版本 0 红**:① 组合符只认 `Mn`、丢掉 `Mc`/`Me` —— 契约定义是类别以 `M` 开头,而用例里四个组合符全是 `Mn`;印地语 U+0939 U+093F U+0902 U+0926 U+0940 在这个版本下只剩 U+0939 U+0926,**元音符号整个没了、字被改了**;W4 提函数时写成 `== "Mn"` 是最顺手的错。② `casefold()` 代替 `lower()` —— 用例里的字母两种小写结果相同(第十三轮 W3 被打回的同一个缺口,在另一个项目里再现)。
- 给了具体补法:印地语词(Mc)、`a` + U+20DD(Me)、Mc 在开头/分隔符后被丢、U+00DF。
**编排者核实**:那个词的类别是 Lo Mc Mn Lo Mc;U+20DD 是 Me;`ß`.lower() 仍是 `ß`、casefold 是 `ss`。属实。
whose-turn: turn tester

### 13 → tester(固定提示)

**tester 回合 7 结果**:接受打回,补 3 条(Mc/Me 跟在保留字符后保留——印地语词 5 个码位原样、`a`+U+20DD、数字后一串 Me+Mc;Mc/Me 在开头/分隔符后/被丢字符后丢弃、单独一个抛 ValueError;`Straße` 保留 ß),handoff 41c4956。`.pair/scratch/` 里 4 个新错误版本(只认 Mn、只认 Mn+Mc、只认 Mn+Me、casefold)各红,原 11 个仍全抓。
笔记里写下一条教训:"按类别写的条款,每一类都要挑一个能把错误读法区分开的样本" —— 与第十六轮 W32 的决策同一个道理,在测试一侧重新长出来。
W17 捷径生效。
whose-turn: turn dev

### 14 → dev(固定提示)

**dev 回合 7 结果**:W3 复审 approve(f595146),**W3 完成**。上次四种错误版本全抓,另加两种(保留下来的组合符不再算"保留字符"、把 Mc 当字母数字)也抓;新用例的输入对 NFC 是不动点,期望值只取决于组合符规则。晋升 DECISIONS ## W3,把"照契约字面、可能不是人想要的"几条行为留档(U+200B 让两个词粘在一起、Unicode 连字符丢弃不分隔)。
whose-turn: turn tester

### 15 → tester(固定提示)

**tester 回合 8 结果**:claim W4(ee369dc),回合归 dev。(它说"最后 dev 审我这边"—— refactor 没有 review-test 阶段,小的误读,不影响流程。)
whose-turn: turn dev

### 16 → dev(固定提示)

**dev 回合 8 结果**:W4 impl,48 条绿,handoff e364bd7。
- **动手前把重构前的 `src/slugify.py` 拷到 `.pair/scratch/slugify_before_w4.py` 作对照** —— dev 这一侧第一次用 scratch(第十五轮是从 git 读进内存)。
- 提出 `classify_char(ch, prev_kept)`,返回 KEEP/SEPARATOR/DROP;照 W32 改过的 PLAN 措辞把"前一个字符是否保留"作为参数传入 —— **观察项 4 兑现:这次 W4 没有与组合符规则打架,也没人需要为措辞停下来**。
- 新旧对照约 40 万随机串 + 每个码位 × 4 种上下文 + 非字符串输入,返回值与异常类型全一致。考古记录三节;自报三处拿不准,其一是"用字符串常量、`is` 比较,没用 enum"—— 与第十一、十五轮同一处,看 tester 这次评不评。
whose-turn: turn tester

### 17 → tester(固定提示,PLAN 的最后一个阶段)

**tester 回合 9 结果**:W4 review-impl approve(222cdd1),**W4 完成,PLAN 全部完成**。自己取出 22ad4b7 与新版本对比约 808 万组输入(全码位 × 7 种上下文、30 万难字符随机串、非字符串参数),全一致;逐条核过 dev 笔记里三处等价论证。
**这次评了 `is` 比较**(第十五轮 tester 没评):"现在是对的,不打回,建议以后改用 `==`"。撞上一次晋升闸,补 DECISIONS ## W4 后通过。

## 结算

report:完成 4、交接 14、认领 4、打回 14% (1/7,脚本判偏低)、协议开销 0、未判定 0、死锁 0、异议 0、决策/完成 4/4。21 个提交,全部由两个会话的协议命令产生,**人类 0 个**。
**人类介入 0 次**;用量中断 1 次(429,原样重发,无重复交接);W17 捷径 1 次。
**`.pair/scratch/` 被两个会话用了六个文件**(ref.py、fuzz.py、trunc_ref.py、w3_mut.py、slugify_before_w4.py 与 __pycache__)—— 第八轮引入以来第一次真正被用上。
转义被写文件工具解掉 4 次,全在评审与笔记里;测试文件里 0 次(都用 chr 常量)。
