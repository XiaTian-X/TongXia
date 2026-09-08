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
