# W14 review-test(dev 审 tester 的测试)

裁决: **changes**。两处缺口,都在隔离克隆里做成了"正确实现下绿、只在对应变异下红"的
候选用例再说话;不是措辞问题,是**契约里的一个分支没有任何用例接得住**。

判据全部碰的是既有前缀与契约给的三个行标签,判定行一个字没碰 —— 没有变更探测器,
这一点我查过、没问题。

---

## 问题一:`--basis` 只守了"不生效时不写",没守"生效时要写"

`tests/conformance/test_v1_effective.py:104-125` 的 `TestBasisOnlyWhenRewrite` 只有
纯追加那一条(断言**不**出现「改写依据」)。契约 `docs/pair-run/CONTRACT.md:749`
写的是"**在它实际生效时**才写进提交正文",两个方向都是本节内容。

实测(完整克隆,只注入这一个变异,跑全套):

| 变异 | 全套红几条 |
|---|---|
| `if args.basis and ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):` → `if False:` | **0** |
| 同样把另外四个旗标改成从不写 | 各 1–3 条(`test_boundaries` / `test_v1_docreason` / `test_v1_frozen` / `test_v1_memory` 早就钉着正向) |

五个旗标里只有 `--basis` 的正向没有任何既有用例 —— W8 的用例只看拒绝与放行,不看正文。
W14 之前 `if args.basis:` 是无条件的,缺口不显;W14 把它挂上了三个条件,
"条件写错成永远不成立"就成了一个真实的错误方向。

**候选形状**(已在克隆里验过:正确实现绿、只有这个变异红):同一个 setUp,
把路线图"第一条"那一行**改写**而非追加,带 `--doc-reason` 与 `--basis docs/DECISIONS.md`,
断言交接被接受、正文里有「改写依据」。

## 问题二:`test_不在完成那一次时不留痕` 分不出"看不看 DONE"

`tests/conformance/test_v1_effective.py:68-70`:spec 交接带 `--no-decision`,
但**没有写笔记**。笔记为空时 `len(note) >= MIN_NOTE_PROMOTE_CHARS` 已经不成立,
"不在完成那一次"这个条件有没有都一样 —— 用例名说它守的那个条件,它守不住。

实测:`no_decision_is_read` 里
`if not memory_on(cfg) or target != "DONE":` → `if not memory_on(cfg):`,**全套 0 条红**。

和你自己在 spec 回合抓到的 `assertIn("0% (0/2)")` 同一个形状:判据被另一个条件先满足了。

**候选形状**(已验:正确实现绿、只有这个变异红):spec 交接之前先写一份
`LONG_NOTE` 到 `docs/notes/W1.md`(不沉淀成决策),其余不变。这样笔记够长、没沉淀,
唯一挡住旗标的就是"不在完成那一次"。

---

## 我这边的账

这两个变异**也不在我 impl 笔记的探针表里** —— 我只探了"恒写"的方向,
`no_decision_is_read` 也只探了 `settled`。所以这不是你漏看了我点名的东西,
是两边都没想到的方向。修完之后建议把这两个也登记(连同那 11 个):

- `("--basis 从不写", "    if args.basis and ROADMAP_REL in touched_docs and has_rewrite(root, ROADMAP_REL):", "    if False:")`
  —— 注意它和"`--basis` 恒写"是同一行 old,两个变异要么合写要么挑一个
- `("--no-decision 在非完成时也生效", '    if not memory_on(cfg) or target != "DONE":', "    if not memory_on(cfg):")`

登记不是打回理由;这次退回 spec 你能顺手做,也可以照原计划留到 W15。

## 查过、没问题的

- **判据不碰措辞**:五个前缀都是既有文案、既有用例早钉着;`report` 三个标签是契约字面;
  `num()` 用 `标签\s*:?\s*(\d+)`,我的实现写 `推进交付的回合       103` 也能取到。
- **其余三个旗标的正向**:`--allow-deletion` / `--doc-reason` / `--contract-change` /
  `--no-decision` 改成从不写,各有 1–3 条既有或新用例红(见上表)。
- **`test_完成时脚本自己勾选_PLAN_不算承重文件改动`**:确实打"按提交内容判"的实现。
- **`report` 八条**:两数之和、空转计 1、评审/承重文件/异议不算、旧提交单独计数
  而新提交不算 —— 我 impl 回合那 11 个探针里的 7 个就是被这些接住的,不重复论证。
- **`test_v1_report.py` 那两处**:锚到 `--no-decision` 那一行的正则,不会被
  `--contract-change` 那一行的 `0% (0/2)` 蒙过去。

## 未覆盖(不构成打回)

- **`memory_on` 那一半条件接不住,但我认为不用补。** 记忆关闭时笔记目录不是共享路径,
  评审回合写不进笔记(实测被写权限边界拒:"这个文件不属于任何角色"),
  晋升闸在那个配置下结构上走不到。要构造得让人类预先提交一份笔记,
  换来的只是守一个几乎不可达的组合。记在这里,不要求。
- 你在 review-impl 里记的 ① 自由文本伪造判定行、② 历史声明污染,我同意不在本项修。
