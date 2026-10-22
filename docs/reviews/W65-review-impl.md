# W65 — review-impl(tester)

结论:**打回(changes)**,一处:decline 补计撞上死锁闸时,提交信息不是死锁闸的原样,`report` 数不到这次死锁。

## 要改的

`.agents/skills/pair-protocol/scripts/pair.py:3107` 的提交信息是 `chore(pair): 拒绝代办 R1,工作项 W1 打回 3 次,触发死锁闸`。`report` 认死锁靠
`DEADLOCK_SUBJECT_RE`(`pair.py:3239`,`^chore\(pair\): 工作项 \S+ 打回 \d+ 次,触发死锁闸$`,行首锚定)—— 这一条对不上。
实测(harness 临时仓库 + 你的 `pair.py`):计数先置 2 → request → 带着代办异议 → tester decline → 状态里计数 3、`deadlock_hits` 有一条、`whose-turn` 是 `stop`,
而 `report` 的"死锁工作项占比"是 `0% (0/1)`。契约写的是"补加后到死锁上限,照死锁闸原样处理";第十二轮 ⑤ 修过的正是"死锁提交的主题要能被 report 认出来"这件事。

这一次既是一次拒绝代办、又是一次死锁,`report` 两边都要数到。形状由你定,比如:
- 主题用死锁闸原样的那一句,拒绝代办记在正文里,`report` 的被拒数另认这一行;或
- 主题保持现状,`DEADLOCK_SUBJECT_RE` 放宽成也认 `拒绝代办 R<n>,工作项 … 触发死锁闸`。
`mutation_check.py` 有一条锚在 `        if DEADLOCK_SUBJECT_RE.match(subject):` 这一行上,改正则本身不影响它;改这一行的话我这边要重新锚。

**这一格要有用例守**(我的用例只查了计数、留痕与 `whose-turn`,没查 `report`)。请你改完之后在 review-test 以"缺这条用例"打回,我照 W17 捷径补:
同一个场景跑 `report`,"死锁工作项占比"的分子是 1、"代办被拒率"的分子也是 1。

## 查过的地方

- 三条命令共用 `_request_turn`:先查篡改(还原并拒绝)、再查回合;`_find_request` 先认被请求方、再认还开着。归属与回合分开拦 —— 我 `TestOwnership` 那三条对得上。
- request:只在 spec / impl;路径先认冻结、再认归自己、再认归对方,其余算孤儿 —— 冻结与孤儿一起交人类,归自己让直接改;`base` 取当时 HEAD;窄提交状态文件。
- fulfill:`_changed_since` 是 `base` 到工作区的差异加未跟踪,只看请求的那些路径;记账不执行。decline:理由非空,被带过的补计。
- 交接:"发给自己的开着"放在 W50 那道之后、抓改动之前,完成时任何开着都拒;`HANDOFF_INVARIANTS` 加了 `request-closed`,§4 同步。
- 计数:`is_dispute`(只在 impl)且自己发出、还开着的代办 → 不加、标 `carried`、正文一行;没有代办的异议照旧。`claim` 清空。
- `status` 只给被请求方列;`report` 两行按主题前缀数(`办完代办` 不会被数成发出)。文档 `rules.md`(不得用于表达分歧)、`SKILL.md`、`protocol-spec.md` §4 与 §8、
  `command-reference.md`、`architecture.md`、`troubleshooting.md`、两份 README、路线图 P1-13/P1-14 都跟上。全套 798 绿,我的 30 条全绿。

## 没覆盖的

- 锚点等你改完再登记(候选我看过,`if verdict == "changes" and not carried:`、`if r.get("carried"):`、`if r.get("to") != me:`、`if not _changed_since(...)`、`if waiting:` 各只一处)。
