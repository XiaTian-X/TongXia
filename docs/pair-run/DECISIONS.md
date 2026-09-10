# 决策记录（追加式 — 只能往后加，不能改已有条目）

> 两个 agent 不共享对话，也不共享各自厂商的记忆。这份文件是它们唯一
> 累积起来的共同结论，`pair.py status` 会在相关回合把它读给双方听。
>
> **只记事实和裁决，不记推理过程。** 记忆层是让下一回合不必从零重新推导，
> 不是让两边想到一块去 —— 共享推理会让两份产出趋同，合起来少一道验收。
> 所以下面故意没有"分析"字段。
>
> 强制写入的时刻只有三个:同一工作项第二次被打回、契约在工作项期间被改过、
> 工作项完成时笔记里还有没沉淀的东西。其余时候想写就写。
>
> 格式如下，四个字段缺一不可，单条不得超过 1500 字符（超了 handoff 会拒绝
> —— 这条结论此后每次 status 都会被读一遍，长了就没人读）:

    ## W1 — 用毫秒时间戳而不是 ISO 字符串做排序键

    - 理由: ISO 字符串在跨时区输入下排序结果和真实先后不一致，
      W1 的验收标准直接依赖排序
    - 已否决: 存 ISO 再解析后排序 —— 每次读都要解析，且解析失败没有兜底路径
    - 影响路径: `src/timeline.py`, `tests/test_timeline.py`

`影响路径` 是检索键:今后谁要动这些路径，`status` 会自动把这条结论摆到他面前。
所以路径要写准，写全。

---

## SETUP — 契约由人类授权定稿,但未经人类逐条通读

- 理由: 人类的分工是定方向与指挥,不逐条过规划("只要能够保证完成既定目标我就不再过问")。所以 `docs/pair-run/CONTRACT.md` 两个小节的 `依据: 人类定稿` 记的是**授权定稿**,不是**逐条通读**。这两者在协议里长得一样,但证明力不同 —— 契约含糊是唯一会致命的失败模式,而那道防线现在只剩双方的开工前审查(setup-verification),没有人类这一层兜底。写下来是为了让后面任何一次"契约其实没说清楚"的事故能追到根因,而不是去怪某一方没读懂。
- 已否决: 让 agent 自己改契约来补漏 —— 直接撞冻结文件那条,而它存在的理由正是契约漂移。契约要改仍然走变更流程,那一步仍然需要人类落笔,这一条没有放宽它。
- 影响路径: `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `docs/reviews/setup-verification.md`

## SETUP — 契约定稿这一次由 dev 代人类执行,人类是决定者

- 理由: `docs/reviews/setup-verification.md` 提的歧义②(「没有记忆内容」的判据)必须人类落笔,tester 在笔记里也判为唯一的阻断项。人类看过逐字 diff 并两次明确指示由 dev 代为执行。**改动内容与 dev 在对话里公示的 diff 逐字一致,可核对**:补丁脚本留在会话的临时目录,内容同本次提交的 diff。写下这条是因为协议规定 agent 不得改契约,而 tester 无法从仓库里分辨这次改动是人类定稿还是 dev 迁就自己的实现 —— 那正是冻结文件买来的信任,这一次它没有了,由本条替代。
- 已否决: 由 dev 直接改而不留痕 —— 那会让契约的 `依据: 人类定稿` 变成不可核对的断言,下一次谁都可以照此办理,冻结文件就名存实亡。也否掉了坚持不改、让人类自己敲 —— 人类已两次指示,再推回去是拿规则条文挡掉它自己要保护的那个决定。
- 影响路径: `docs/pair-run/CONTRACT.md`, `docs/reviews/setup-verification.md`, `docs/pair-run/notes/W2.md`

## W2 — 行号绊线跨越角色边界,本轮双方各撞一次

- 理由: `test_docs_consistency.py` 的 `CITED_LINE_COUNTS` 钉的是被引文件的**行数快照**,而被引文件横跨两个角色:`pair.py` 归 dev,`mutation_check.py` 和这个常量本身归 tester。任一方改自己的文件,失配都出现在**对方**路径里,自己无权修。本轮双向各撞一次:dev 改实现→常量失配、它改不了;tester 换变异点锚点→`docs/improvements.md` 三处引用失配、tester 改不了。绊线是单人维护视角下设计的,没有预见角色切分。临时解法是通过异议/评审互相把核准过的数字递过去,代价是每个 impl 回合都要多一次往返。另有一处更糟:`INSTALL.md` 在仓库根,不属于任何角色,双方都改不了,只能靠人类。
- 已否决: 把改动压成行数不变来绕过绊线 —— 那是拿代码和文档去迁就一条检查,评审该打回的正是这种东西。也否决了直接把 `pair.py` 从 `CITED_LINE_COUNTS` 里摘掉 —— 那要动 tester 的文件、且超出 W2 范围,属于人类排期的事,不在这一轮顺手做。
- 影响路径: `tests/conformance/test_docs_consistency.py`, `tests/conformance/mutation_check.py`, `docs/improvements.md`, `INSTALL.md`

## W2 — 「靠评审读代码核对」不算防护,该补测试的要补测试

- 理由: 契约定稿时加的「status 提前收尾时简报同样没有记忆段落」这一条,实现里靠 `all_done` 守卫满足,但零测试。把守卫拿掉,279 条一条不红 —— 契约被违反而红绿一声不吭。tester 在 spec 笔记里点名了这个坑并承诺"在 review-impl 回合按同一次取值核对",它也确实核对了、实现也确实对。但评审是一次性的,防护是持续的:下一个动 `cmd_status` 的人把守卫改回去,没有任何东西会响。dogfood-run-1 的第二次打回是同一个形状(「打回换来的修复没有测试守着」),这是本项目第二次撞它。
- 已否决: 以「W2 的验收标准里没有这一情形」为由不补 —— 定稿后的契约把「没有记忆内容」收窄成两条路径(idle、status 提前收尾),验收标准的「没有时整段省略」两条都涵盖。也否掉了 approve 之后开新工作项补 —— 跨工作项补测试会让 W2 带着一个不设防的契约条款完成,这条在 run-1 里已经论证过一次。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_brief.py`

## W2 — 「评审时读过代码」不算防护,契约的每条可观测要求都要有测试

- 理由: review-test 打回一次,证据是跑出来的:把 `pair.py` 里 `mem = ("" if all_done or me != owner …)` 的 `all_done` 守卫拿掉,279 条全绿 —— 契约「`status` 提前结束时……简报同样没有记忆段落」当时零测试守着。tester 在 spec 笔记里点名过这个坑,又在 review-impl 回合实测核过一次,判定"已核对"就放行了。**那是一次性的**:下一个重构 `cmd_status` 的人不会被一次评审拦住,而红绿会一声不吭。已补 `test_status_提前收尾时简报也没有记忆段落`(拿掉守卫时 280 条里唯一变红的一条)与变异点「拆掉简报的提前收尾守卫」。**造这类用例的关键是场景要能区分** —— W1 的 `test_工作项全部完成时仍然写` 用 idle 空仓库,`memory_brief` 本来就返回空串,守卫在不在都一样;要先 claim 出工作项并写笔记,让"正常情况下终端会注入"成立,再把 PLAN 勾完。
- 已否决: 以"验收标准里没有这一情形"为由不写 —— 定稿后的契约把「没有记忆内容」收窄成两条路径(idle、提前收尾),验收标准的"没有时"两条都包含。也否决了以"评审已核对"替代用例:评审是一次性的,防护是持续的。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_brief.py`, `tests/conformance/mutation_check.py`

## W2 — 行号引用的续引形式对 grep 隐形,「逐条核对」抓不全

- 理由: 绊线红的时候只说"行数变了,逐条核对每一处引用"。本轮 tester 按文件名 grep 列出三处 `mutation_check.py:<行号>`,实际有五处 —— 漏掉的两处是同一行里省略文件名的**续引**(形如 ``​`mutation_check.py:596` 的 X 与 `:466` 的 Y``)。按 `mutation_check.py:` grep 抓不到 ``​`:466`​``。这不是谁不仔细:绊线要求的"逐条"没有定义边界,而人和 grep 都会把续引读成上下文而不是引用。
- 已否决: 禁止续引形式、要求每处都写全文件名 —— 那会让同一行里出现三四次相同的文件名,可读性代价大于收益,而且没有任何东西强制得了它。也否掉了让绊线自己列出全部引用 —— 它现在就会列(`test_被引文件的行数没变过` 的失败输出里有),但列的是**它自己解析出来的**那些,解析器同样按文件名匹配,漏的是同一批。
- 影响路径: `tests/conformance/test_docs_consistency.py`, `docs/improvements.md`, `docs/contributing.md`

## W3 — 跨边界常量第二次挡住 impl 回合;根因是 33 个"孤儿路径",不是冻结文件

- 理由: 同一结构问题第二次让 dev 交不出 GREEN,这次卡住两处:`CITED_LINE_COUNTS`(tester 路径)与 `examples/demo-project/.gitignore`(**谁都够不着**)。按 `.pair/config.json` 的 roles 对 `git ls-files` 实算过一次:**冻结路径 6 个**(PLAN、CONTRACT、`.pair/*`、`.claude` —— 刻意设计),而**不属于任何角色、也没被冻结的"孤儿"有 33 个**,含 `README.md`、`INSTALL.md`、`pyproject.toml`、`cli/pair_bootstrap/__init__.py` 与整个 `examples/`。本轮全部三次卡顿(`INSTALL.md`、`examples/.gitignore`、`improvements.md` 行号)**都出自孤儿,没有一次出自冻结**。所以症结不是"文档只许人类改",是 roles 配置压根没覆盖全仓,而缺口只在第 N 个回合突然发作。
- 已否决: 放宽 `test_gitignore_跟得上_GITIGNORE_LINES` 或 `CITED_LINE_COUNTS` 让它别红 —— 拿测试迁就归属问题,两条检查本身都是对的。也否决了在本轮顺手改 roles 配置:`.pair/` 是冻结路径,agent 改不了,且扩大范围是人类的决定。
- 影响路径: `.pair/config.json`, `tests/conformance/test_docs_consistency.py`, `tests/conformance/test_v1_shipped.py`, `examples/`, `INSTALL.md`

## W3 — 协议强制 dev 跑的验证命令,产出落在 tester 的独占路径里

- 理由: `contributing.md` 写死"改动强制逻辑后两个都要跑",而 `mutation_check.py` 跑完会刷新 `tests/conformance/mutation-cache.json` 的基线指纹 —— 那是 `tests/conformance/**`,tester 的独占路径。dev 照纪律跑完,`handoff` 立刻判越界:「dev 在 impl 阶段只能写 …」。撤销缓存改动才能交接,于是 dev 每次跑变异检查都要顺手 `git checkout` 一次,而缓存的意义(快路径)对 dev 这一侧实际是废的。这是本轮同一类问题的**第三个形态**:前两个是孤儿路径(W3 决策条目)与行号绊线(W2 决策条目),这一个不同 —— 它不是"谁都够不着",是**协议要求你做的事本身会越界**。
- 已否决: 让 dev 别跑变异检查 —— 那等于让"改了强制逻辑要跑两个"这条纪律对 dev 永久失效,而 dev 正是唯一会改强制逻辑的角色。也否决了把 `mutation-cache.json` 加进 `ignore_paths` —— 边界检查会整个跳过它,tester 对它的改动也就不再受任何约束,拿掉一条真防护去换一次方便。
- 影响路径: `tests/conformance/mutation-cache.json`, `tests/conformance/mutation_check.py`, `.pair/config.json`, `docs/contributing.md`

## W3 — 脚手架把 stdout 与 stderr 拼在一起,契约里"标准输出"那半句因此不设防

- 理由: 契约「写入失败时的 status」写明"**标准输出**多出恰好一行"。但 `harness.py:189-190` 的 `Result.text` 返回 `self.out + self.err`,而两条用例用的都是 `.text` —— 把实现里的 `print` 换成 `sys.stderr.write`,284 条全绿。这不是用例写坏,是**脚手架的默认取值抹掉了契约要区分的那个维度**:`.text` 用起来最顺手,于是所有人默认用它,而任何"这句话打到哪条流"的契约条款都会自动失去防护。流的选择不是细节 —— 有的 harness 折叠或不展示 stderr,警告落在那里等于没警告,而这一节的全部意义就是"写不出来要被看见"。
- 已否决: 让 `Result.text` 不再拼接、只返回 stdout —— 全仓大量用例用 `.text` 做宽松断言(`assertIn` 拒绝理由等),改默认值会把它们一起打散,是拿一次修复去换一批误伤。正确的做法是在**需要区分流**的用例里显式用 `.out` / `.err`,`Result` 已经分开存好了。
- 影响路径: `tests/conformance/harness.py`, `tests/conformance/test_v1_brief.py`, `.agents/skills/pair-protocol/scripts/pair.py`

## W3 — 验证命令的副作用落在谁的路径是随机的,两个方向都会卡住对方

- 理由: 上一条只记了 dev 方向(跑 `mutation_check.py` 刷新 `mutation-cache.json`,落进 tester 独占路径而被判越界)。**反方向同样成立,而且更隐蔽:** tester 在**只读评审回合**跑同一条命令复验,缓存改动留在工作区,下一个回合 dev 的 `handoff` 做 `git add -A`,边界检查照样把它算到 dev 头上、拒绝交接 —— 而 dev 完全不知道那个改动是谁造成的,拒绝文案还会引导它去"撤销"。本轮 review-impl 真的撞上了一次,靠 tester 主动 `git checkout` 还原才没有卡死对方的完成回合。**还有一处时序值得记:** `full_test_cmd` 在 `pair.py:1787` 跑,位置在 `git commit`(`:1782`)**之后**,所以工作项完成那一次跑出来的缓存改动进不了该次提交,必然以脏工作区的形态留给下一个人。
- 已否决: 让评审回合别跑验证命令 —— 评审要求"证据是跑出来的",不跑就退回读代码,而这一轮两次打回都证明读代码不够。也否决了在评审回合顺手提交缓存:只读评审回合的可写路径里没有 `tests/`,提交它本身就是越界。
- 影响路径: `tests/conformance/mutation-cache.json`, `.pair/config.json`, `.agents/skills/pair-protocol/scripts/pair.py`

## W3 — 截断路径零测试:这是 W2 的遗留缺口,趁协议停转前把它落进记录

- 理由: 契约「简报的记忆段落」有一条「**截断**」:注入内容若已被截断(`MAX_NOTE_INJECT_CHARS` / `MAX_DECISION_INJECT_CHARS` / 决策条数上限),简报写的是**截断之后**的那份。全仓 grep 不到任何用例碰这三个常量。当前实现下它是**结构性成立**的(简报与终端拿的是同一个 `mem` 值),所以不是缺陷 —— 但"结构性成立"正是 W2 那条决策记录说的"靠评审读代码核对不算防护":换一条取值路径就没了。之所以现在写进来:它是 W2 的遗留,双方都同意不塞进 W3(不在 W3 的验收标准与契约小节里,规则 5 也不允许),tester 报给了人类,但**报告不落文件就活不过这一轮** —— W3 通过后 PLAN 全部勾选、协议停止轮转,两份工作项笔记随之作废,而决策记录会被 `status` 按影响路径推给下一个动这些文件的人。
- 已否决: 硬塞进 W3 的验收范围 —— 会让工作项范围含糊,而"要不要扩大范围"是人类的决定;这一条 tester 在 spec 笔记里论证过,我同意。也否决了只留在 `--uncovered` 与聊天报告里 —— 那正是这次要防的失效方式。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_brief.py`, `docs/pair-run/CONTRACT.md`

## SETUP — 33 个孤儿路径的划归,以及它推翻的一条旧决策

- 理由: 第三轮开工前把不属于任何角色的 33 个文件划给了 dev(仓库根的 6 份 md、各家入口文件、`cli/`、`pyproject.toml`、`examples/`、根 `.gitignore`),并把 `tests/conformance/mutation-cache.json` 放进 `ignore_paths`。实测划归后**孤儿 0、角色重叠 0**。这是 W6 的硬前置:它要迁移的引用有几处在 `INSTALL.md` 与 `README.md`,那两份此前谁都改不了。顺带删掉了 `roles.dev` 里的 `!docs/DECISIONS.md` —— 它排除的文件已不存在(`decisions_file` 早已是 `docs/pair-run/DECISIONS.md`,而那条路径不被 `docs/*.md` 匹配),是旧配置残留;删后实测 `decisions_file` 仍不被 dev 匹配。
- 已否决: 把这些路径划进 `shared_paths` —— 那个键被五处逻辑依赖(`dispute-evidence` 强制点、评审文件命名、打回的位置引用、异议举证、`verify-setup` 的记忆层检查),并进去会让"写了一份提案/文档"被算成"异议落到纸面"。也**推翻了 `## W3 — 协议强制 dev 跑的验证命令…` 那条里对 `ignore_paths` 的否决**:它当时的理由是"tester 对缓存的改动不再受任何约束,拿掉一条真防护"。复查认为那条防护并不存在 —— 提议中的留痕防不住伪造,而缓存另有基线指纹保护;`ignore_paths` 的 `continue` 落在角色与阶段判断之前,本就是为副产物设计的位置。
- 影响路径: `.pair/config.json`, `pyproject.toml`, `.gitignore`, `examples/`, `cli/`, `tests/conformance/mutation-cache.json`

## SETUP — 第三轮契约由 dev 代笔定稿，人类授权，双方结论都已到齐

- 理由: 契约头写着"变更需双方同意后由人类修改",本次是**人类明确授权 dev 代笔**("你来审查规划一下")。九处改动全部来自两份独立的开工前审查结论:tester(`0472b88`)五处、dev 五处、其中两处独立撞上(行内代码豁免会让 W6 恒真、`improvements.md` 的口径)。**唯一的分歧被证伪**:tester 认为孤儿的两个定义会让共享路径误报,实测 `writable_paths` 里 `shared` 对每个阶段都在 `allowed` 中,共享文件永远进不了 `violations`,后果不可达 —— 措辞仍按 tester 说的统一了,但不是阻断级。九处里 tester 独有 1 处(符号重名 `Class.method`),dev 独有 4 处(记忆层必然是孤儿、`artifact_paths` 残留、末尾"请撤销"那句、路径粒度与区间形式)。
- 已否决: 让人类逐条落笔 —— 九处里没有一处是双方分歧,人类的角色是裁决冲突不是当打字员,而每轮开工都要人类手抄契约正是 P1-9 要消灭的东西。也否决了 dev 只改契约不改 PLAN:W4/W6 的验收标准逐字复述了被改的那几条(排除集、旧形式、豁免范围),只改一边就是给下一轮埋一个两份规格打架。
- 影响路径: `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `docs/reviews/setup-verification.md`

## SETUP — 开工前校验的报告路径对两个角色是同一个文件名，dev 因此覆盖了 tester 的结论

- 理由: `SETUP_REPORT_REL` 是**全局唯一的固定文件名**,两个角色的开工前结论写同一份文件。dev 的 `verify-setup` 在后台跑的那两分钟里 tester 提交了自己的结论(`0472b88`),dev 没看见就整份覆盖(`2ff494f`),之后从 git 逐字节还原、两份并存(`e935350`)。**没有内容丢失,但这是一次真的越写。** 对照:`docs/reviews/` 下所有别的文件都带 `<ID>-<阶段>` 前缀,由 `check_review_names` 强制并检查,唯独这一份不受管。它和本轮 W4 是同一类东西 —— **边界的缺口只在真撞上的那一刻才发作**,这次撞上的是 dev 自己。
- 已否决: 现在就改成 `setup-verification-<角色>.md` —— 不在本轮 PLAN 里,而"要不要扩大范围"是人类的决定;`verify-setup` 读的是固定路径,改它要同时动 `SETUP_REPORT_REL` 与文案,属于新工作项。也否决了只在聊天里报一句:上一条 W3 决策刚记过"报告不落文件就活不过这一轮"。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/reviews/setup-verification.md`, `docs/improvements.md`

## W6 — 「模块级赋值算符号」这条契约条款的防护挂在一处文档引用上，改写那句话就会静默拆掉它

- 理由: `TestSymbolReferences` 的 10 条作弊场景里没有一条喂模块级赋值。实测:删掉 `_symbol_index` 里的 `ast.Assign` 分支,只有 `test_规范文档里没有行号形式的引用` 变红 —— 而它之所以红,是因为 W6 迁移时恰好把 `docs/improvements.md` 的一处引用写成了 `tests/conformance/mutation_check.py#MAX_CACHED`。那份文件在 dev 路径:任何一次改写那句话都会让这条契约条款回到零覆盖,而且**不会有任何东西红**。契约「引用形式」写明符号可以是「模块级赋值的名字」,所以这是有契约、无独立用例的状态。dev 在两轮 review-test 里都把它写进 `--uncovered`,tester 两轮都没补 —— 双方都不认为它够打回,但它也不该随工作项笔记一起作废。补法是一行:`self._one("见 `…/mutation_check.py#MAX_CACHED`") == []`。
- 已否决: 拿它做第三次打回 —— 契约没要求每条条款都有独立用例,而现状确实有覆盖,为凑打回而打回本身就是失真(评审阶段的文案点名禁止)。也否决了 dev 在 `improvements.md` 里给那处引用加"别删"的注释 —— 靠注释保护一条测试覆盖,是把防护建在下一个人读不读注释上,比现状更弱。
- 影响路径: `tests/conformance/test_docs_consistency.py`, `docs/improvements.md`

## W6 — 决策记录本身不在符号引用的扫描范围内，而它是唯一跨轮次的长期资产

- 理由: W6 的检查按契约只扫 `NORMATIVE`(SKILL.md、rules.md、README、INSTALL、`docs/*.md`)。`docs/reviews/` 与工作项笔记不在其中,那是对的 —— 它们一次性、随工作项作废。但 `docs/pair-run/DECISIONS.md` 不同:**它每次 `status` 都被注入给两个 agent**,是跨轮次唯一的长期资产,却同样不被扫描。实测它现在带着 `mutation_check.py:596`、`harness.py:189-190`、`pair.py:1787` 等行号引用,其中 `mutation_check.py:596` **已经是错的**(596 是 `run_baseline`,那条决策说的是 `precheck_no_baseline`)—— 正是 W6 笔记里追出来的那次漂移,它在决策记录里还留着一份没修。也就是说:被反复读给未来 agent 的那份材料,恰恰是防护最弱的一份。
- 已否决: 在 W6 里顺手把 `decisions_file` 加进扫描范围 —— 契约「边界」逐字写的是"只管规范性文档(与现有一致性检查的口径相同)",扩大范围要改契约,是人类的决定;而且记忆层能否承受"符号改名就变红"要单独想清楚(决策记录记的是当时的判断,和运行报告同类,可能该走 `@<sha>` 豁免而不是符号)。也否决了 dev 在评审回合顺手修那处 596 —— 决策记录是追加式的,改写既有条目正是它禁止的。
- 影响路径: `docs/pair-run/DECISIONS.md`, `tests/conformance/test_docs_consistency.py`, `docs/pair-run/CONTRACT.md`

## W4 — 断言里拿整份输出做 assertIn，会被表头里的总数满足：这一轮两条契约都栽在同一个形状上

- 理由: 契约「孤儿清单」的输出条款要求"再补一行说明还剩多少个(总数减 10,**不是总数**)",括号是人类定稿时专门加的。守它的断言两版都写成对整份输出的 `assertIn`:第一版 `assertIn("5")`(总数 15 含 5),第二版 `assertIn("2")`(总数 12 含 2)—— **两版都恒真**。变异证明:把 `render_path_listing` 里补剩余数那两行整段删掉(等于该条款完全不实现),全套 301 条**全绿**;打印总数而不是剩余数的错误实现同样能过。根因是**总数与剩余数天然共用数字**(12/2、15/5),而表头按契约必须含总数 —— 所以任何"在整份输出里找那个数字"的写法都必然被表头满足。正确判据要限定到行:存在一行含剩余数、不含总数、且不是被列出的路径。同一形状本轮出现过第二次:W6 的 `test_区间形式也被拒且按起始行给建议` 用一个起止落在同一符号里的区间,声称守"取起始行"却守不住。两次都不是断言写错,是**取样范围比被断言的性质大**。
- 已否决: 把用例的孤儿个数改成 20(剩余 10、总数 20,`"10"` 不是 `"20"` 的子串)—— 能让 `assertIn` 重新有效,但下一个改数字的人不知道为什么必须是 20,判据藏在算术里而不是写在代码里,等于把同一个坑留给下一次。也否决了断言实现方的具体措辞(如 `assertIn("还有 2 个没列出")`)—— 契约只规定"补一行说明还剩多少个",没规定措辞,钉措辞就是断言契约没写的东西(规则 4)。
- 影响路径: `tests/conformance/test_v1_paths.py`, `tests/conformance/test_docs_consistency.py`, `.agents/skills/pair-protocol/scripts/pair.py`

## W4 — 交出用例前必须自己注入一个"合理的错误实现"确认它会红

- 理由: 第三轮 tester 在 spec 回合**三次**交出没有区分力的用例,三次都由 dev 跑变异发现:① W6 的区间用例起止落在同一符号里,取起始行还是结束行都一样;② W4 的三条负向断言在功能未实现时恒真,加的第一版前提断言 `assertIn("AGENTS.md")` 也恒真(`verify-setup` 因入口文件检查本来就会提到它);③ W4 的剩余数断言 `assertIn("2", r.text)` 恒真 —— 首行"12 个孤儿"里就含 `2`,把补剩余数那一行整段删掉,301 条一条都不红。**三次是同一个形状:用例看起来在测,其实测不到。** 根因是"我验证过这个场景能触发那条分支"被当成了"这条断言能区分对错"——触发不等于区分。**判据**:交出用例前,自己把实现改成一个**合理的错误写法**(不是随便改坏),确认该用例变红;负向断言另加一条前提断言,且前提用的关键词必须**只有目标功能才会产生**。
- 已否决: 靠评审回合发现 —— 评审是一次性的、防护是持续的(W2 决策已记),而且这三次全是评审发现的,说明这条路已经在超载。也否决了"写完跑一遍看是红的就行":①③ 在功能未实现时**本来就红**,红不等于有区分力,只有注入错误实现才分得出。
- 影响路径: `tests/conformance/`, `docs/pair-run/notes/`

## W4 — 新防护的变异点要在 spec 回合和用例一起补,不能留给"后续"

- 理由: 五步纪律第 3 步(在 `MUTATIONS` 里补变异点)落在 tester 的路径,而 tester 通常是在**只读评审回合**才发现它缺了 —— 那时写不了 `tests/`。W3 时的处理是写进笔记并注明"建议归进后续的 cover 工作项",**而笔记随工作项作废,那个后续从没发生**。实测:`pair.py` 里 W3 的两条(写简报失败的 `OSError` 降级、`BRIEF_REL` 进 `GITIGNORE_LINES`)与 W4 的三条(孤儿清单、`ignore_paths` 覆盖清单、越界文案区分有无孤儿)**五条防护,71 个变异点里一个都没有**。缺口在累积,而每一轮都把它推给下一轮。**判据**:tester 在 **spec 回合**写用例时就同时补变异点 —— 那是唯一既能写 `tests/`、又知道这条防护该怎么拆掉的时刻。dev 在 impl 回合发现缺了,走 `request` 或异议把它递回来。
- 已否决: 继续记进工作项笔记 —— 笔记随工作项作废,W3 那次就是这么丢的;这条同 W6 那次行号漂移的教训同源(把待办写进将要作废的地方 = 没写)。也否决了让 dev 补 —— `mutation_check.py` 在 tester 独占路径,它写不了,这正是问题的来源而不是解法。
- 影响路径: `tests/conformance/mutation_check.py`, `.agents/skills/pair-protocol/scripts/pair.py`

## W4 — ignore_paths 既是孤儿判据的排除项、又是另一段清单的来源，而"不能同时出现在两段里"没有用例

- 理由: 契约把 `ignore_paths` 同时用在两处:孤儿判据里它是**排除项**(命中就不算孤儿),覆盖清单里它是**来源**(命中就要列出来)。两处的语义是相反的 —— 一段说"没人能写",一段说"人人都能写"。变异证明:把 `is_orphan` 里那句 `if matches_any(path, cfg["ignore_paths"]): return False` 去掉,`test_v1_paths` 10 条**一条都不红**,而输出里 `build/缓存.json` 同时出现在两段警告中,孤儿表头还自己写着"也不在 ignore_paths 里"。`TestIgnorePathsListing` 只断言它出现在"不受边界保护"那一段,没断言它**不在**孤儿清单里。补法一行:断言该文件在整份输出里只出现一次。同一节还有第二处不对称:契约要求 `ignore_paths` 清单"同样超过 10 个只列前 10 行",孤儿那一侧有 `TestOrphanTruncation` 守着,这一侧把 limit 调成 10000 也全绿。
- 已否决: 拿这两条做第三次打回 —— `DEADLOCK_LIMIT = 3`,第三次 `handoff changes` 会停转并要求人类裁决,而这里没有分歧(前两次打回 tester 都受理了、改法也对)。死锁闸守的是"两个 agent 谈不拢",不是"还能再补两条用例";拿一个双方不会有争议的补充去触发它,是把闸用歪,而且会把一个非冲突推到人类面前。也否决了只写进 `--uncovered` 就算完 —— 那只在提交正文里,而这两条值得活过 W4。前两次打回是另一个种类:断言**声称**守着契约却守不住(区间用例起止同符号、剩余数断言被表头满足),那比没有用例更坏,必须打回。
- 影响路径: `tests/conformance/test_v1_paths.py`, `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`

## SETUP — 第四轮的规划与契约由 tester 代笔,人类授权;并修了两处契约自漂

- 理由: 人类要求"审查计划和契约"、随后授权"可以,开始吧"。经过与第三轮 dev 代笔定稿同一形态,记在这里供对方核对。**改了三处**:①修契约头部两处自漂 —— 它写着"第三轮…三节写在最后面"和"三节的共同点",而实际只有两节,原因是开工前复查判定「副产物路径」是过度设计并删掉了它,却没同步头部;**这一处是 tester 自己造成的**,而这一轮的主题恰恰是"文档与代码的关系"。②契约新增第四轮两节(文档改动要带理由、冻结文件改成强制留痕),弱版本的代价逐条写进了契约正文。③PLAN 新增 W7/W8/W9。**W7 是 `cover` 不是 `feature`** —— 它补的三条测试与五个变异点针对的功能已经实现,`feature` 的 spec 回合强制 RED,写成 feature 会当场卡死。
- 已否决: 把第三轮的欠账留给"以后" —— 本轮刚立的决策写着"待办写进将要作废的地方等于没写",W3 的变异点缺口就是这么丢的,所以直接进 PLAN。也否决了 tester 直接改 `.pair/config.json` 把 PLAN/CONTRACT 移出冻结:那是"谁能写什么"的决定,契约的「不做」明写脚本与 agent 都不碰,留给人类在开工前做(已写进 PLAN 目标段)。
- 影响路径: `docs/pair-run/PLAN.md`, `docs/pair-run/CONTRACT.md`, `.pair/config.json`

## SETUP — 第四轮的计划与契约由 dev 代笔修订，人类授权；六处审查发现 + 第三轮三条欠账的取舍

- 理由: 人类看过审查结论后说"结合上一轮总结的问题,开始规划修改本轮",授权 dev 落笔。改了六处审查发现:①契约里「规范性文档」有两个外延(差 5 份文件,含本轮要解冻的 PLAN 与 CONTRACT)——新增「术语」一节把两个范围**改成两个名字**(规范性文档 / 扫描范围)并写明差集,而不是统一它们,因为符号引用检查的行为已经落地,改口径等于让已交付的实现不合规;②开工前"移出 frozen_paths 并划归角色"与"移出后会变成孤儿"不能同时成立,拆成有顺序的三步;③划归若写成 `docs/pair-run/**` 会命中 `notes_dir` 与 `decisions_file`、`verify-setup` 直接失败,实测后把逐份写的安全形式写进计划;④W9 落地后两份文件的标题("冻结 — agent 只读")会变成假的,补进验收标准;⑤新增「判据取回合开始时的工作区,不是提交内容」——`tick_plan_item` 在边界校验之后写 `PLAN.md`,按提交判会让每次完成工作项的交接都被要求 `--doc-reason`;⑥W7 的第四项跨到「简报的降级与忽略」那一节,而脚本只读第一行 `对应契约`。另把第三轮的教训写成一条本轮纪律:每条新增拒绝分支要给出"拆掉它会红"的变异证据,因为第三轮同一个失效形状(取样范围比被断言的性质大)出现了三次。
- 已否决: 把开放条目 12、13、14 一并塞进本轮 —— 13(报告路径不分角色)实测改动面是 `pair.py` 6 处 + 文档 7 处 + 测试 33 处、跨两个角色,单独就是一个工作项,而本轮已有三项;本轮改用一条散文临时办法(第二个跑 `verify-setup` 的一方先读再追加)并写明它只是临时办法。12 绕开成本≈0,和 13 同一个函数,一起排下轮。14 是机械迁移,且 W8 落地后改那 66 处本身就要带 `--doc-reason`,顺序上更适合放在 W8 之后。也否决了把「五步纪律无人能独立执行」(开放条目 15)单列成工作项 —— 本轮新增两条拒绝分支,那条纪律正好在关键路径上,所以并进 W8 的验收,并用 W8 自己新增的 `--doc-reason` 走第一个真实用例。
- 影响路径: `docs/pair-run/PLAN.md`, `docs/pair-run/CONTRACT.md`, `docs/contributing.md`, `.pair/config.json`

## W9 — 划归角色那条路是死的，改成「两份文件仍冻结、按配置键点名开一个带声明的口子」

- 理由: 第一版契约写"`PLAN`/`CONTRACT` 从 `frozen_paths` 移出、划归某个角色"。实算三条路全堵:①`docs/pair-run/PLAN.md` **不匹配任何现有角色模式**(`dev` 只有 `docs/*.md`,不含子目录),移出后立刻变成孤儿;②划归给某一方,**另一方就永远改不了契约**,而契约变更本该双方都能发起 —— P1-9 的目的只实现一半;③并进 `shared_paths` 会污染五处依赖(异议举证、评审文件命名、打回的位置引用、范围豁免、记忆层隔离检查),"改了契约"会被算成"异议落到纸面"。改成:两份文件**仍留在 `frozen_paths`**,`handoff` 的冻结拒绝分支加一个豁免,**按 `plan_file` / `contract_file` 两个配置键点名**放行(需 `--contract-change`)。配置一个字不用改,双方都能写,没有孤儿。**豁免必须按键名点名而不是"带旗标就能改冻结路径"** —— `frozen_paths` 里还有 `.pair`,而 `.pair/enforcer.py` 是本轮的裁判,一个旗标能改判官这条防护就整个塌了。
- 已否决: 新增第三个路径类别(双方可写、要带声明)—— 那是通用解,而且和 P0-7 推迟的 `artifact_paths`、P0-5 会需要的 `proposal_paths` 是同一类问题的三个实例,**值得一起设计,不该在本轮各造一个**;本轮走最小可行,不新增配置键。也否决了继续用"复用已有的契约变过必留决策":那条的触发点是 `target == "DONE"`,拿 `claim` 时的 `contract_sha` 比对 —— 它**确实能在工作项完成时抓到中途的契约变更**(自审第一版说"根本走不到"是说过头了,已更正),但抓不到改动发生的那一刻,而且 `idle` 期间改契约(`contract_sha` 为 `None`)一次都不触发。W9 自己加一条,与既有那条并存。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `.pair/config.json`

## W8 — 「规范性文档」改成闭合定义：枚举实算漏掉 13 份，含全部入口文件

- 理由: 第一版把范围写成枚举(`docs/` 下的 `.md` + `README` + `INSTALL` + skill 的 `references/` 与 `SKILL.md`)。按"所有被跟踪的 `.md` 减去记忆层与评审目录"这个闭合定义实算,枚举**漏掉 13 份**,其中包括 `AGENTS.md`、`CLAUDE.md`、`CONVENTIONS.md`、`GEMINI.md`、`.github/copilot-instructions.md` —— **正是告诉每个 agent"这是结对项目"的那批入口文件**,也正是 ADR-022 那次 sweep 漏掉过的同一批。W4 刚用 33 个孤儿证明了枚举会漏,同一轮里不该再造一个枚举。闭合定义下当前 64 份被跟踪 `.md` 有 35 份在范围内,含 `examples/` 下的样板文档(它们是分发物,改了同样该有理由)。另外把 `--basis` 从"只要求非空"改成"必须指向仓库里真实存在的路径"(判据复用 `handoff changes` 的位置引用检查):两个旗标若都只查非空,效果**完全一样**,叠着只是多打一行字;要求指向产物之后一个是"为什么"、一个是"凭什么",而后者可被对方点开核对。
- 已否决: 在闭合定义里再排除 `examples/` —— 每加一条排除就重新打开"会漏"的口子,而样板文档是随包分发的,改它本来就该留理由。也否决了直接取消 `--basis` 只留 `--doc-reason` —— 那会把"路线图的改写要有依据"(P1-15②)整条丢掉,而它是本轮的来源之一。
- 影响路径: `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `.agents/skills/pair-protocol/scripts/pair.py`
## SETUP — 裁判副本必须逐字节等于 pair.py，重钉时刻由 DONE 定义；契约四处修订由 tester 代笔，人类授权

- 理由: 开工前审查实跑发现两条阻断:①本轮裁判 `.pair/enforcer.py` 与 `pair.py` 差 100 行,`grep -c orphan` 一边 8 处一边 **0 处** —— W4 上一轮验收通过的孤儿清单**整整一轮都不在裁判里**,而 W8/W9 要加的旗标直接 `unrecognized arguments`,两条验收标准无人能执行;②只在冻结分支开豁免不够,实算 `writable_paths` 两份文件在**五个阶段全部不在 `allowed` 里**,豁免完照样被拒、且会被 W4 判成孤儿。**判据**:不变量取"逐字节相等,例外窗口是一个工作项",`claim` 校验 + `DONE` 自动重钉(全绿即证据),推论是**同一个工作项里不能既加旗标又用旗标** —— W8/W9 里做不到的那两条据此摘出去,W11 承接。**另定:`verify-setup --drafter other` 挪到定稿之前** —— 它有效(本轮六条全是它挖的),只是发生得太晚,前三轮每轮都在定稿后返工,换个顺序零成本。
- 已否决: 拿 `ENFORCEMENTS` / `HANDOFF_INVARIANTS` 注册表比对当护栏 —— 实算两边都是 14 条与 16 条、**差集为空**,而两文件差 100 行,这个断言恒真,会全绿地放过上面那一整轮。也否决了取消钉住改回 `pair.py` 当裁判:本轮给 `handoff` 加两条拒绝分支,改坏就两边都动不了,钉住的副本正是这件事的保险。还否决了「契约每条行为附一行实测」:契约小节属低频档、加得起,但会退化成套话,而挪前的独立审查已经覆盖了它的目的。
- 影响路径: `.pair/enforcer.py`, `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `.agents/skills/pair-protocol/scripts/pair.py`

## SETUP — 第四轮契约与计划的第三次修订：两节对同一件事给了相反规矩，W11 的类型会在 claim 被硬拦

- 理由: 审 `fe04625` 时查出四处。①**A 段与 B 段矛盾**:「路线图与计划的改写要有依据」说改动落在 `improvements.md`/`PLAN.md`/`CONTRACT.md` 上时"纯追加只要 `--doc-reason`",而 W9 那一节对后两份是**无条件**要求 `--contract-change`、不带就在写权限边界直接拒。B 在更早的一步生效,所以 A 的那半句对这两份文件**不可达** —— 照 A 写用例会写出"往 `PLAN.md` 追加、只给 `--doc-reason` 应当通过"这样一条必然失败的断言。已把 A 段收窄到只管 `improvements.md`,`--basis` 因此也只作用于它。②**重钉的位置只钉了一头**:契约只说"边界校验之后",而实测边界校验与 `git add -A` 相隔两百多行,落在 `add` 之后重钉过的 `.pair/enforcer.py` 会留在工作区没进提交,下一个回合对方被冻结判定拦住、而那个改动不是它做的、撤销又会把重钉撤掉 —— 没有出路。已补"而且在 `git add -A` 之前"。③**W11 `[refactor]` 会在 `claim` 被硬拦**:`refactor` 的保护测试要求是硬闸,而改两句 markdown 标题不存在能保护它的测试,拒绝文案给的出路(先开 `[cover]`)也走不通;改成 `[feature]` —— 它本来就可测,对两句标题做一条文档一致性断言,与 `POSITION_ENTRIES` 那批定位绊线同形。④PLAN 里 W9 的验收还留着契约刚撤回的"`idle` 期间一次都不触发"那半句,已同步。
- 已否决: 把 A 段的追加/改写分叉也套到 `PLAN.md`/`CONTRACT.md` 上(即让 W9 只在"有改写"时要 `--contract-change`)—— 那会让"往契约里追加一节"不留任何声明,而追加一节和改写一节对下游的影响一样大;冻结这两份文件买来的信任正是"改了必有人知道"。也否决了给 W11 声明一个形式上的保护测试路径来满足 `refactor` 的硬闸 —— 那是拿声明去迁就类型检查,而类型本来就选错了。
- 影响路径: `docs/pair-run/CONTRACT.md`, `docs/pair-run/PLAN.md`, `docs/reviews/setup-verification.md`
## SETUP — 更正:ENFORCEMENTS 是 30 条不是 14 条，上一条 SETUP 里那个数字是错的

- 理由: 上一条 `SETUP`(裁判副本同步不变量)的「已否决」里写着"实算两边都是 14 条与 16 条",**14 是错的,实测 30**。错法:用 `awk '/^ENFORCEMENTS = /,/^\)/'` 框范围,而 `ENFORCEMENTS` 是**拼接式**定义,范围在中间那个 `)` 提前收口,只数到前 14 条。正确做法是 `importlib` 导入模块后 `len()`。`HANDOFF_INVARIANTS` 16 条是对的。**结论不受影响** —— "注册表比对当护栏是恒真的"这个判断靠的是**差集为空**,而两边差集确实为空、文件却差 122 行。按追加式更正,不改上一条。
- 已否决: 直接改上一条里那个数字 —— `DECISIONS.md` 是追加式,悄悄改数字正是这一轮在防的东西;而且错的**测量手法**本身值得留在记录里,它和 W6 那次行号漂移、和本轮被 dev 挑出的"改了一半的规矩"是同一族。
- 影响路径: `docs/pair-run/DECISIONS.md`

## W10 — 「记录写成什么样」在这一项里不是风格问题：断言只查子串会放过一个断成两行的重钉记录

- 理由: 契约「裁判副本的同步」要求 DONE 重钉时把新 sha 写进提交正文,而那一行是裁判被换掉之后**唯一的纸面记录**。`test_重钉的_sha_进提交正文` 断言的是 `sha[:7] in body` —— 整份正文含 sha 前 7 位即可。变异实测:拿掉 `repin_judge` 的 `.strip()`,正文断成两行(sha 行尾断开、右括号单独一行),**11 条一条都不红**。tester 在 review-impl 里靠读代码发现了这个缺陷,并主动记下"我的用例一条都抓不到,这是我的问题",还点名请 dev 在 review-test 用实测决定要不要打回。正确判据是**结构**不是措辞:正文里存在**一行**同时含 `JUDGE_REL` 与完整 sha —— 这样不碰措辞,也不撞规则 4。
- 已否决: 拿"`and green` 去掉之后 11 条全绿"一起打回 —— 核实后收回:`FLOWS` 里 `review-test`(以及 refactor 的 `review-impl`)期望都是 GREEN,不绿在红绿不变量那一步就 die,`green` 在 `target == "DONE"` 处**不可能为假**,那是结构性冗余而不是无人看守的条款;变异存活但不可达,不核实就报会变成一次假打回,而假打回和点头一样失真。也否决了要求 tester 为"`hash-object` 失败时仍留痕"造注入点 —— 用例跑的是子进程,把 git 弄坏会让整条链一起塌,强行造测试的代价大于它守住的东西;那条改由代码注释与评审记录守着,已写进本条。
- 影响路径: `tests/conformance/test_v1_judge.py`, `.agents/skills/pair-protocol/scripts/pair.py`

## W10 — 临时变异脚本会变成死代码而安静全绿：变异测试自己的失效模式，和它要检测的东西一模一样

- 理由: tester 在 spec 回合写的变异脚本,在 dev 的实现落地之后**六条全报 OK** —— 锚点是"当时那份实现"的字面源码片段,实现一变 `str.replace` 什么都没替换掉,而脚本不报错。**它安静地全绿,和它要检测的失效模式完全同形。** 仓库里 `test_变异点仍能匹配到源码` 守的是同一件事(`MUTATIONS` 的 `count(old) == 1`),但只管登记在册的变异点,管不到评审回合临时写的一次性脚本 —— 而 W10 这一轮两个角色一共跑了十几次临时变异,全部没有这层保护。ADR-018 把"把实现改坏看有没有测试会红"确立为本项目发现问题的主要手段,那么这个手段自己的失效模式就是一等问题。最省事的修法:临时脚本在替换之后断言内容确实变了(`before != after`),两行。
- 已否决: 要求把所有临时变异都登记进 `MUTATIONS` —— 那会让每一次评审探查都变成一次跨角色的文件改动(`mutation_check.py` 在 tester 独占路径),而临时变异的价值正在于随手可跑;开放条目 15 已经记了这条边界。也否决了本回合就写进 `docs/improvements.md` —— review-test 是只读评审,`docs/*.md` 不在可写路径里,硬写会被边界拦住;先落决策记录,等下一个能写文档的回合搬过去。
- 影响路径: `tests/conformance/mutation_check.py`, `docs/contributing.md`, `docs/improvements.md`

## W10 — 两条测不了或没规定的缺口，明确不作为打回理由

- 理由: 两条都在 W10 的评审里查实,都不构成偏离契约。①**`if repinned is not None:` 退回真值判断抓不到**:它只在 `git hash-object` 失败时才有区别,而用例跑的是子进程,脚手架里没有干净的注入点 —— 把 git 弄坏会让整条链一起塌。dev 在两轮评审里都明确要求 tester **不要为它造注入点**,代价大于它守住的东西;这条不变量("动作发生了必须有记录")靠 `repin_judge` 里那段注释与两份评审记录守着。②**正本缺失而副本存在时校验静默通过**:`judge_pair` 在 `PROG_HINT` 不存在时返回 `(None, None)`,`judge_in_sync` 因此为真。契约只写了"副本存在时必须相等",没写正本缺失怎么办 —— 不算偏离,但那恰恰是"有人把正本删了"的形状,而协议一个字都不说。
- 已否决: 拿这两条做第三次打回 —— `DEADLOCK_LIMIT = 3`,第三次 `handoff changes` 会停转并要求人类裁决,而这里没有分歧:①是双方都同意测不了,②是 tester 自己先记下来、dev 同意不作为理由。死锁闸守的是"两个 agent 谈不拢",拿共识去触发它是把闸用歪。也否决了只写进 `--uncovered` 就算完 —— 那只在提交正文里,而这两条值得活过 W10。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_judge.py`, `docs/pair-run/CONTRACT.md`
## W10 — 预告过、写进了 --uncovered、对方读到了，然后照样发生了：「某一步之前必须做完」这类事在协议里没有家

- 理由: tester 在 W10 的 `review-impl` 第三轮里实测发现副本停在 `899b0fa` 之前(`cmp` 差在 line 505,`507` 行仍是没 `.strip()` 的那版),并预告了确定的后果:**DONE 由这个旧副本执行,会把断成两行的记录写进 W10 自己的完成提交**。这条写进了 `--uncovered`、写进了评审文件、也进了提交正文,dev 在 `inbox` 里必然读到。**然后它照样发生了** —— `0e037ca` 的正文第 4-5 行就是那条断开的记录。修掉这个缺陷的工作项,把这个缺陷写进了自己的完成提交,而且是重钉唯一的纸面记录。**根因不是谁疏忽:`--uncovered` 是一条记录,不是一道闸;而这件事的形状是「在 X 之前必须做完 Y」,协议里没有任何一个位置承载它** —— 笔记随工作项作废、`--uncovered` 只在提交正文里、决策记录要到下一次 `status` 才被念,而那时 DONE 已经过去了。判据:凡是"某一步之前必须做完"的事,只有两种正当归宿 —— 变成那一步的一道拒绝分支,或者停下来交给人类;写进任何一份会被读到但不会拦人的材料,等于没写。
- 已否决: 当时就用第三次 `handoff changes` 把它逼停 —— `changes_count` 已到 2,`DEADLOCK_LIMIT = 3`,那会触发死锁闸并要求人类裁决,而这里没有分歧,是把闸用歪(同本轮另一条已记的判断)。也否决了事后改写历史把那条记录修正 —— 提交记录是这个项目唯一的通信总线,改写它比留一条难看的记录坏得多;这条记录反而是本条决策最好的物证。也否决了把它记进 W10 的笔记 —— 笔记随工作项作废,而 W10 已经 DONE,那等于不记。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`, `docs/improvements.md`

## W7 — 「超出验收标准的四个变异点」判不超范围：那份枚举写在 W10 存在之前

- 理由: W7 的验收标准 ④ 写的是"`MUTATIONS` 补上五个变异点 —— W3 的两条与 W4 的三条",而 tester 补了十个(那五个 + "剩余数打成总数" + W10 的四个),并主动交出裁决权("判超范围就打回我")。dev 判**不超**,三条理由:①**那份枚举写在 W10 存在之前** —— W10 是本轮开工后新插进 PLAN 的工作项,插进去时没有回头改 W7 的 ④,拿过期枚举当上限本身就是本轮已经栽过两次的形状(「规范性文档」枚举漏 13 份、「术语」那节的"差 5 份"是旧定义下的数);②**W10 那一轮双方已就此议定** —— 记在 W10 的笔记与 review-impl 评审里:变异点的锚点是 `pair.py` 的字面源码,spec 回合实现还不存在,写死锚点就是断言实现细节,当时的结论就是"归进 W7";拒收等于把一个已议定的缺口再推给下一轮;③**代价为零、收益可验证** —— 只动 tester 独占的 `mutation_check.py`,不碰产品代码,81/81 全部被抓,`test_变异点仍能匹配到源码` 绿说明四个锚点都唯一。dev 独立注入四个变异复验了三条缺口,其中前两条在第三轮是存活的。
- 已否决: 按 PLAN 字面打回并要求拆掉那四个 —— 那是拿一份过期的枚举去否决一件双方事先议定、且已验证有效的工作,而它的唯一收益是"程序上好看"。**但这不构成"以后可以顺手扩范围"的先例**:成立靠的是"双方事先议定"这一条,不是"顺手补了对大家都好";请人类下次改 PLAN 时把 ④ 从"五个"改成"W3、W4、W10 三项的全部"。也否决了只在评审记录里写而不留决策 —— 评审记录随工作项沉底,而"枚举写在新工作项之前因而过期"这个形状本轮已出现三次,值得跨轮次留痕。
- 影响路径: `docs/pair-run/PLAN.md`, `tests/conformance/mutation_check.py`

## W8 — 「规范性文档」的闭合定义没说 ignore_paths 与协议日志算不算，实现按类比豁免了

- 理由: 契约的闭合定义是"所有 `.md`,除去记忆层(`notes_dir` / `decisions_file`)与评审目录(`shared_paths`)",**没有提 `ignore_paths`,也没有提协议自己写的日志**。dev 实现时按写权限边界那一处的类比,把这两类一并豁免了。核实两类的实际影响:①协议日志里只有 `.pair/.last-brief.md` 是 `.md`,而它进了 `.gitignore`、在 `git status` 里从不出现 —— 这半条豁免是死代码,无害也无用;②`ignore_paths` 里的 `.md`(副产物)要不要理由,契约确实没说,dev 认为不该要(副产物本来就不受边界保护),但那是实现方的判断。变异掉这条豁免,15 条用例一条都不红 —— 因为契约没写,tester 无从断言。
- 已否决: 拿它打回 tester —— 契约没写的东西不该由用例来钉(规则 4),这是实现比契约宽,不是测试漏了。也否决了 dev 自己把豁免删掉以"贴合契约字面" —— 那会让 `ignore_paths` 下的副产物 `.md` 突然要求理由,而副产物连写权限边界都不受,两处口径会更不一致。正确出路是人类在下次改契约时补一句:要么写明豁免,要么写明不豁免。
- 影响路径: `docs/pair-run/CONTRACT.md`, `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_docreason.py`

## W8 — 路线图写死成 docs/improvements.md，`--basis` 对所有下游项目永不触发

- 理由: 契约「路线图与计划的改写要有依据」把路线图写死成 `docs/improvements.md`,而这个协议是**随包分发的 skill**。任何下游项目都没有这个文件,于是 `--basis` 那半条强制对它们**永远不触发** —— 它只在本仓库有效。tester 在 spec 回合提出,dev 同意。有先例(`SETUP_REPORT_REL` 也写死),但两者性质不同:评审结论是**协议自己产出的产物**,路线图是**项目自己的文档**;而 `plan_file` / `contract_file` / `notes_dir` / `decisions_file` 全都是配置键,唯独它不是 —— 这个不对称本身就是信号。建议加 `roadmap_file` 配置键,缺省 `docs/improvements.md`。
- 已否决: 本轮顺手加这个键 —— 契约是冻结文件,而且加配置键要同时动 `load_config` 的默认值、`verify-setup` 的路径自洽检查、以及 W8 那 15 条用例的 `config`,是一个完整工作项而不是顺手改;本轮已有 W9、W11 未做。也否决了照 `SETUP_REPORT_REL` 的先例就此认下 —— 那个先例指向的是协议产物,拿它论证项目文档也该写死,是把两类不同的东西并成一类。
- 影响路径: `.pair/config.json`, `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`, `tests/conformance/test_v1_docreason.py`

## W8 — feature 流程里 tester 只有一个可写回合，而回到它的两条边都由 dev 发起

- 理由: 实算 `FLOWS["feature"]`:tester 唯一可写的阶段是 `spec`(`review-impl` 是只读评审,`tests/` 与 `mutation_check.py` 都不在它的可写路径里)。回到 `spec` 的边只有两条 —— `('impl', 'changes')` 与 `('review-test', 'changes')` —— **两条都由 dev 发起**;tester 自己那次打回(`review-impl changes`)去的是 `impl`,是 dev 的回合。于是:**在一个 feature 工作项里,tester 补测试或补变异点的机会完全由 dev 决定。** 这和五步纪律的第 3 步(补 `MUTATIONS` 变异点)撞在一起:变异锚点是 `pair.py` 的字面源码,实现没落地时任何锚点都失配,所以第 3 步只能在实现之后 —— 而那时 tester 已经没有可写回合了。W8 这一轮它之所以补上了,是因为 dev 为**别的两条缺口**打了回、把阶段退回 `spec`,tester 顺带补的。**那是运气,不是机制。**
- 已否决: 让 dev 为了给 tester 腾一个可写回合而打回 —— 那是制造一次打回,评审阶段的文案点名禁止,而且会污染打回率这个指标(`report` 拿它当"互相点头"的观测量)。也否决了把 `review-impl` 改成可写 —— 只读是它的全部意义:评审回合能改测试,就没有什么能阻止评审方把测试改成迁就实现的样子。正确出路写进了 `docs/contributing.md` 的分角色纪律:dev 交实现时点名欠账;若到 `review-test` 都没有正当的打回理由,**dev 必须在 approve 之前把欠账写进决策记录**;或者单开一个 `[cover]` 工作项(第三轮 W7 的做法)。
- 影响路径: `docs/contributing.md`, `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/mutation_check.py`

## W8 — `--doc-reason` 少了 `.strip()`：一个空格就能满足「强制留痕」，而留下的痕是空的

- 理由: 实测在临时仓库跑真实 `handoff`:`--doc-reason "   "` 退出码 **0**,提交正文里那一行渲染成 `文档改动理由:` —— **git 剥掉尾随空白,留痕与没写一模一样**。契约对这个旗标的原话是"不是放行,是强制留痕",现在两头都不成立。根因是判据写成 `not args.doc_reason`,而同一份文件里既有的同类旗标(`--checked` / `--uncovered`)用的是 `not (val or "").strip()` —— **少了 `.strip()`,与仓库既有口径不一致**。tester 上一轮补的 `test_理由是空字符串不算数` 只钉了 `""`,一个空格就绕过去。缺陷在实现,不在用例;但 feature 流程里 tester 唯一可写的阶段是 `spec`,所以必须由 dev 打回才能补上这条用例 —— 这正是本工作项另一条决策记的那个结构问题的第二次实例。
- 已否决: dev 在 `review-test` 直接 approve 再自己找机会补 `.strip()` —— review-test 只读,改不了实现;而下一个可写回合要到下一个工作项,那时这条防护已经以"一个空格就能满足"的形态上线了。也否决了顺带要求补 `--basis "   "` 的用例 —— 实测空白串会被第二道 `basis_points_at_file` 拒掉(`"   ".split()` 是空列表),那条用例会是恒真的,而恒真的用例比没有更坏。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/test_v1_docreason.py`, `tests/conformance/mutation_check.py`
## W8 — 判空少一个 strip 的洞不止 --doc-reason 一个：--allow-deletion 三个空格就能悄悄删掉已有测试

- 理由: W8 修的是 `--doc-reason` 的判空(`not args.doc_reason` → `not (args.doc_reason or "").strip()`),根因是 **git 会剥掉尾随空白**,所以"三个空格"和"没写"在提交正文里长得一模一样 —— 留痕和没留一样,而门开了。实测发现**同一行形状在 `pair.py:1863` 的 `--allow-deletion` 上还开着**:`handoff "删了 W1 的用例" --allow-deletion "   "` 退出码 **0**,正文那一行渲染成 `删除测试(已声明):` 后面什么都没有。**这一条比 --doc-reason 要紧**:它守的是删除已有测试,而同一段拒绝文案自己写着"测试是规格,删除它等于悄悄缩小验收范围"。`pair.py:943` 的 `--no-decision` 是同一行形状(未单独实测,看代码推的)。判据:凡是"强制留痕"类旗标,判空一律走 `not (val or "").strip()`,即 `--checked` / `--uncovered` 那一处的既有口径;补法是各一条空白用例 + 一个变异点,与 `--doc-reason` 完全同形。
- 已否决: 拿这两条打回 W8 的实现 —— 不是这次改出来的,也不在 W8 的契约小节里,拿范围外的旧缺陷打回是把打回当待办清单用。也否决了只写进 `--uncovered`:同一份记录里已经有一条判死过这种做法(预告过、写进 --uncovered、对方读到了,然后照样发生了),而 `--uncovered` 只在提交正文里,活不过这个工作项。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `tests/conformance/mutation_check.py`, `docs/improvements.md`

## W8 — 把变异点锚在「还不存在的实现」上，解开了五步纪律第 3 步的时机死结

- 理由: 第 3 步(补 `MUTATIONS` 变异点)的锚点是 `pair.py` 的字面源码片段,而 `test_变异点仍能匹配到源码` 要求 `count(old) == 1` —— 防护没写出来时任何锚点都失配,所以第 3 步只能在实现之后;但 feature 流程里 tester 唯一可写的阶段是 `spec`,回到它的两条边又都由 dev 发起。W8 最后一轮 tester 用了第三条路:**在 spec 回合就把锚点按"实现应该长什么样"写下来**(`(args.doc_reason or "").strip()`),让 `test_变异点仍能匹配到源码` 红着交给 dev,并在交接说明里写明"要换写法就在 review-test 打回我并给出你实际用的片段"。dev 按片段实现,锚点即刻匹配,不需要额外往返。**这把一个时序死结变成了一次普通的规格协商** —— 锚点从"事后追认的实现细节"变成"事前声明的接口",而 dev 有正常的异议通道可以推翻它。前提是那个片段本身有依据:这次的片段与同文件 `--checked` / `--uncovered` 的既有口径逐字一致,不是凭空指定实现。
- 已否决: 继续用原来那两条出路当唯一解 —— "dev 打回时顺带补"依赖运气(W8 这一轮确实是靠 dev 为别的缺口打回才补上的),"单开 `[cover]` 工作项"要多排一整项。也否决了把这条写进 W8 的实现 —— 它是流程纪律不是代码,该进 `docs/contributing.md` 的分角色那一节,由下一个能写文档的回合补。**顺带记一个操作坑**:重锚或重命名变异点时要同时删掉 `mutation-cache.json` 里的旧键,否则 `test_缓存里的条目名都在_MUTATIONS_里` 变红,而第一反应"跑 `mutation_check` 刷新缓存"是死路 —— 它要求基线全绿,而基线红的原因正是那条陈旧缓存。出路是按那条测试自己说的直接删键。
- 影响路径: `docs/contributing.md`, `tests/conformance/mutation_check.py`, `tests/conformance/mutation-cache.json`
## W9 — 带了 --contract-change 却没改承重文件时：不校验、不拒绝、照样进统计

- 理由: 实测 `handoff "什么承重文件都没改" --contract-change "这不是路径"` → **退出码 0**,提交正文里照样写下 `契约变更(已声明): 这不是路径`。根因:校验块的入口是 `if changed_named_frozen and args.contract_change:`,没改承重文件时 `changed_named_frozen` 为空,整块被跳过 —— **路径真实性那一道根本没跑**;而写正文那一段只看 `if args.contract_change:`,于是 `report` 的 `--contract-change` 那一行把它计成一次契约变更。契约把那一行定为"频率异常再收紧"的观测量,而**一个不改任何东西就能加一的计数器观测不了任何东西**。这和本工作项里另一条(report 那一行原来被分母推动)是同一个病:那一行到底有没有意义。判据:两条出路都行 —— 声明只在 `changed_named_frozen` 非空时才写进正文;或者反过来,空的时候直接拒绝("你没改承重文件,不要带这个旗标")。**契约没规定这种情况,所以不是偏离,要人类定一句。**
- 已否决: 在本轮补一条用例把它钉住 —— 契约没写这种情况该怎么办,钉哪一边都是断言契约没规定的东西(规则 4);先把事实记下来,等契约定了再补用例与变异点。也否决了只写进 `--uncovered`:同一份记录里已有一条判死过那种做法。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`

## W9 — 同一次契约变更被要求留两条决策，而第二条必然没有内容

- 理由: 实测:带 `--contract-change` 在 spec 回合改了契约并留了一条 `## W1 — …`,走到 DONE 那次交接**又被既有的 `contract-change-note` 拦下**("契约在这个工作项期间被改过,但决策记录里没有对应记录")。根因是那条算的是 `new_decision_entries` —— **按偏移量算"这一次交接里新追加的"**,spec 回合那条早就进了 HEAD,到 DONE 时不算新的。于是同一次契约变更要留两条同 id 的决策。**问题不是多写一条,是第二条必然没有内容**:tester 在脚手架里被迫写的那条叫"完成时再记一次同一件事"。而决策记录是**每次 `status` 都注入给两个 agent** 的长期资产 —— 强制产出空转条目,是在往那份材料里掺水,而掺水的代价由此后每一个回合承担。
- 已否决: 在 W9 里顺手改既有那条 —— 契约写的是两条"并存、互不替代",改它要动契约,超出 W9 的验收标准;而且既有那条守的性质(完成时发现契约变过却无人记录)是对的,要动的只是"什么算已记录"。也否决了让 tester 把这个交互写成断言 —— 把可疑行为焊进用例正是 cover 那套纪律点名要避免的,tester 只在脚手架里满足它并注明"这是交互不是规格",做法正确。**建议人类改成**:`contract-change-note` 认"本工作项内已有同 id 决策"(不限本回合新追加),而不是只认 `new_decision_entries`。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`, `docs/pair-run/DECISIONS.md`

## W9 — 「孤儿判据里排除 plan_file / contract_file」是死代码，那条验收标准写在旧设计下

- 理由: PLAN 的 W9 验收标准里有"孤儿判据里要排除 `plan_file` / `contract_file`"。实算 `is_orphan` 的判定顺序(角色 → 共享 → `ignore_paths` → **冻结** → 记忆层):W9 明确保留这两份文件在 `frozen_paths` 里,冻结那一道**已经**让它们 `is_orphan=False`。再加一条排除今天就是死代码,**为它写的任何用例都恒真**(今天就绿,和 W9 做没做无关)。所以 dev 没有实现它,tester 也没有为它写用例,双方在 spec/impl 两个回合各自独立得出同一结论。根因:这条验收标准是在 W9 还是"移出 `frozen_paths`、划归角色"的那一版设计下写的,换成"仍然冻结、按配置键开口子"之后就失效了 —— **设计换了,验收标准没跟着换**,和更早那次 `artifact_paths` 残留是同一类。
- 已否决: 照字面实现一条死代码以"满足验收标准" —— 那会往承重路径里加一段没有任何用例能覆盖的分支,而本轮反复在治的正是"看着有防护、实际恒真"。也否决了默不作声地跳过:验收标准是人类落的笔,agent 单方面判它不适用而不留痕,下一个人会以为它落地了。**建议人类在 PLAN 里划掉它,或注明"为将来解冻准备的冗余"。**
- 影响路径: `docs/pair-run/PLAN.md`, `.agents/skills/pair-protocol/scripts/pair.py`

## W9 — 「声明空转仍进统计」不是 W9 独有：`--no-decision` 是同一个形状，所以这是一条仓库级规则

- 理由: tester 记下 `--contract-change` 在没改承重文件时不校验、不拒绝、照样进 `report` 统计。查既有先例后发现**这不是 W9 引入的**:写正文那一段的既有写法就是 `if args.<旗标>: body += …` —— `--allow-deletion` 没删测试时照样写进正文(它不进统计,无害),而 **`--no-decision` 同样只看 `if args.no_decision:`,并且 `report` 的 `--no-decision` 那一行正是靠正文里那句话计数**。也就是说:随便一次交接带上 `--no-decision`,那个比率就涨一格,和有没有笔记要沉淀无关。**同一个病,已经在仓库里活了三轮。** 所以正确的出路不是在 W9 里单独修 `--contract-change`(那会让两个同类旗标口径不一致),而是定一条仓库级规则:**声明只在它实际生效时才写进提交正文**,或者反过来,带了不生效的声明就拒绝。
- 已否决: 在 W9 的实现里单独修 `--contract-change` —— 契约没规定这种情况,而且修一个不修另一个会制造新的不一致;tester 判"钉哪一边都是断言契约没写的东西"(规则 4)是对的,所以本轮不补用例也不补变异点。也否决了把它当成 W9 的缺陷记 —— 它是既有惯例的产物,记成 W9 的会让人去改 W9 而不是改惯例。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/CONTRACT.md`

## W9 — 「只认本回合新追加」不只是 contract-change-note 的毛病：笔记晋升闸同形，实测在同一个工作项里连撞两次

- 理由: 本工作项已经因为 `contract-change-note` 的"只认本回合新追加"被拦过一次(见同名 id 的另一条)。走到最后 `approve` 时**又被拦了一次**,这次是笔记晋升闸:"工作项 W9 要完成了,但它的笔记还没被处理"。而这一项的笔记**已经**在上一个 impl 回合沉淀成三条决策记录 —— 闸看不见,因为它同样用 `new_decision_entries` 按偏移量算"这一次交接里新追加的"。**同一个工作项、同一个根因、两条不同的强制,各发作一次。** 这把上一条的建议从"改 `contract-change-note`"扩大成一条通用判据:**这两处要问的都是"本工作项有没有被沉淀过",不是"这一回合有没有新写"。** 现状会逼出两类坏结果:要么写一条空转的重复条目(决策记录每次 `status` 都注入,掺水的代价此后每回合承担),要么用 `--no-decision` 声明"没有值得留的",而那句话在这里是假的 —— 有,而且已经留了。
- 已否决: 用 `--no-decision "已在上一回合沉淀"` 绕过 —— 那个旗标进 `report` 的指标,而本工作项另一条决策刚记下"声明空转仍进统计"是个真问题;拿一次不准确的声明去满足闸,正好是那条毛病的实例。也否决了把三条决策挪到本回合重写一遍以满足偏移量判据 —— 那是拿记录去迁就检查,而记录的时间戳本身是证据。**建议人类把两处的判据统一改成"本工作项内已有同 id 决策"(不限本回合)**;在那之前,正确做法是像本回合这样:发现闸拦住时,如果确有新事实就记新的(本条就是),没有才用 `--no-decision`。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/DECISIONS.md`, `docs/pair-run/CONTRACT.md`

## W11 — 两份承重文件的标题改写：把它们钉在脚本真的在做的那件事上，而不是钉在某种说法上

- 理由: W9 落地之后,`PLAN.md` 的「冻结 — agent 只读」与 `CONTRACT.md` 的「冻结 — agent 只读,变更需双方同意后由人类修改」**都是假的**:两个角色都可以落笔,只是要带 `--contract-change` 并当场留决策。而这两份是每个 agent 开工第一件事就要读的承重文件 —— 文档说的和脚本做的不一样,是这套机制最贵的失效模式。新标题不只是删掉那半句,而是**点名 `--contract-change`**:tester 的判据同时要求"开头不得出现『只读』"与"开头必须出现 `--contract-change`",两条缺一不可 —— 只查前者,删半句话就能过而不告诉人新规矩;只查后者,写成"冻结 — agent 只读,除非带 `--contract-change`"这种自相矛盾的句子也能过。这和 `ENFORCEMENTS ↔ architecture.md` 那条一致性检查是同一个手法:把文档钉在脚本真的在做的那件事上。契约那一段还写进了本轮的取舍(不要求对方签字,换来的观测量是 `report` 的契约变更频率)。
- 已否决: 顺手划掉 PLAN 里 W9 那条已被双方确认是死代码的验收标准(tester 在交接说明里建议过)—— **删一条验收标准正好是 W9 弱版本防不住的那个形状**:"两个 agent 都觉得它没用,于是把它去掉了"。理由再站得住也不该由 agent 单方面执行,所以改成**原文保留 + 标注事实 + 指向决策记录**,把裁决留给人类。也否决了只改标题不改下面那句导语:导语里"由人类维护""变更需双方同意后由人类修改"同样是假的,只改标题会留下一句更隐蔽的错话。
- 影响路径: `docs/pair-run/PLAN.md`, `docs/pair-run/CONTRACT.md`, `tests/conformance/test_docs_consistency.py`

## W11 — 检查窗口从写死的行数改成结构，代价是丢掉「标题里必须有旗标名」那一格，接受

- 理由: 原判据是 `HEAD_LINES = 3`,而 dev 在 W11 的实现里把两份承重文件的导语写长了(`PLAN.md` 标题+前导块 7 行、`CONTRACT.md` 18 行),窗口比它要守的那段话短 —— 契约那 18 行里 15 行不在检查范围内,而那 15 行正是最可能长出新错话的地方;实测把「除此之外 agent 只读」放进第 5 行,两条断言一条都不红。改成"窗口 = 标题行 + 紧随其后的前导引用块"之后,导语写多长都覆盖得住,到正文就停 —— 所以两份文件里 6 处**引用旧标题的历史引文**(`PLAN.md:194,195,209,210` / `CONTRACT.md:491,492`)不受影响,那些是 W9/W11 的验收标准与契约背景在记录当时的说法,改掉等于篡改记录。**代价是丢掉一格**:标题去掉 `--contract-change`、而导语仍提时,现在是绿的(三格实测确认)。接受它,因为这条断言要守的性质是"读的人知不知道现在怎么改它",标题与紧随的导语是同一个视觉块;**钉"必须在标题里"是钉位置不是钉性质**,而且会让一次合法重排(机制挪进导语、标题只留名字)误红,误红的检查最后都会被人删掉。下限由第三格兜住:整个前导块都不提那个旗标,仍然红(已实测)。
- 已否决: 保留 3 行窗口再单独加一条"标题必须含旗标名" —— 两条判据都盯同一段话,而位置那一条会随排版变动误红;本轮从头到尾在治的正是"判据比它声称守的性质更窄或更宽"。也否决了把窗口扩成整份文件:那 6 处历史引文会全部误红,而它们正是不该改的东西(和 W6 的 `@<sha>` 豁免同一个道理)。**给下一个人**:看到"标题里没有旗标名也能过"而想把那一格加回去之前,先读这条。
- 影响路径: `tests/conformance/test_docs_consistency.py`, `docs/pair-run/PLAN.md`, `docs/pair-run/CONTRACT.md`

## W11 — 「只认本回合新追加」在一轮里实测发作三次，最后一次挡着整轮收尾

- 理由: 本轮结束前把这个根因的完整证据攒齐:①W9 的 spec 回合,tester 带 `--contract-change` 改契约并留了决策,走到 `DONE` 又被 `contract-change-note` 拦(它算 `new_decision_entries`,spec 那条早进了 HEAD);②W9 的 `approve`,笔记晋升闸拦 dev,而笔记已在上一个 impl 回合沉淀成三条决策;③**本条 —— W11 的 `approve`,`contract-change-note` 再次拦下**:W11 期间改过契约(标题与导语),对应决策 `## W11 — 两份承重文件的标题改写…` 早已写在 impl 回合。**三次跨两条强制、两个工作项,而第三次挡着第四轮收尾** —— 也就是说,这个缺陷现在不只是噪音,它能让一轮结不了尾,除非有人写一条"为了过闸"的条目。两条强制要问的都是"**本工作项有没有被沉淀过**",而它们实际问的是"这一次交接有没有新写"。判据统一改成"本工作项内已有同 id 决策"即可,不必改别的。
- 已否决: 用 `--no-decision` 绕过 —— 那句话在这里是假的(有值得留的,而且已经留了),而且它进 `report` 的指标,和本轮记下的"声明空转仍进统计"叠在一起;dev 在 W9 的 approve 也拒绝过同样的做法。也否决了把已有的那条决策挪到本回合重写一遍以满足偏移量判据 —— 那是拿记录去迁就检查,而记录的时间戳本身是证据。**本条不是为了过闸而造的空转条目**:它记的是这一轮攒齐的完整发作次数与"挡着收尾"这个新事实,而那正是判断该不该改的依据。
- 影响路径: `.agents/skills/pair-protocol/scripts/pair.py`, `docs/pair-run/DECISIONS.md`, `docs/pair-run/CONTRACT.md`
