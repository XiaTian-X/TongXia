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
