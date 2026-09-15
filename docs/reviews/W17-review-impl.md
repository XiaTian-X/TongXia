# W17 review-impl(tester 审 dev 的实现)

裁决: **approve**。实现对上契约(含我在 spec 回合带声明补的"契约自 review-impl approve 之后没变过")。
**这是 W16 落地后第一个在 review-impl 当场登记锚点的工作项** —— 你点名的六个我已经只追加进 `MUTATIONS`,
没有欠到下一项。

## 一、逐段对契约

| 契约 | 实现 | |
|---|---|---|
| review-test 打回后 spec 以绿结束 → review-test | `rebound_shortcut` 为真时把 `target` 从 impl 改写成 review-test | ✅ |
| 红 / 来源不是 review-test / 这一回合改了规划或契约 → impl | 三个 `return False`,承重文件复用 `changed_named_frozen`(按改动判) | ✅ |
| 契约自 review-impl approve 之后变过 → impl | review-impl approve 时记 `reviewed_contract`(工作区 sha),捷径要求相等 | ✅ |
| 老状态没有记录 → 不走 | 两个新键默认 `None`;`None == sha` 不成立 | ✅ |
| 死锁计数不清零、评审文件名照旧 | 改写发生在死锁保护之前,`changes_count` 路径不动 | ✅ |
| `cover` / `refactor` 不变 | 只改写 `target == "impl"`,cover 的 spec 本来就去 review-test | ✅ |

位置:红绿判定之后、死锁保护之前 —— 与我在副本里写的参考实现同一处。状态表两行进了 `protocol-spec`
(`test_状态_schema_与代码双向一致` 要求),文档三处准确。

**你删掉的两个判定我同意是死重**:函数里另判"是 spec、没有裁决"(`rebound_from == "review-test"` 只在打回那一次写入、
下一次交接就清掉,而那下一次只能是 spec)、DONE 时清 `reviewed_contract`(下一项进 review-test 前必先经过它自己的
review-impl approve 重写)。**留下的两个等价变异不登记**,理由写在 `MUTATIONS` 那段注释里。

## 二、六个锚点:登记并实跑

只追加进 `tests/conformance/mutation_check.py`(`numstat` 28 行新增、0 行删除),`test_变异点仍能匹配到源码` 通过,
`mutation_check --only 捷径` **基线全绿、六个全被抓到**:

| 变异 | 第一个抓手 |
|---|---|
| 捷径不看 GREEN | 以红结束 |
| 捷径不看回弹来源 | `report` 两数之和那条(你说旧状态那条也红) |
| 捷径不看本回合承重文件改动 | 改了规划 |
| 捷径不比 review-impl 时的契约 | review-test 期间被人提交 |
| 捷径的契约在打回时才记 | review-test 期间被人提交 |
| 捷径从不生效 | 带了声明没真改(走捷径那四条之一) |

结果与我 spec 回合在副本里拆条件的表一致。

## 三、未覆盖(不构成打回)

- **异议那条**是被"没有记录"挡住的(异议发生在 review-impl approve 之前),不是被"看回弹来源"挡住的 ——
  spec 回合笔记里写过。来源那一道由旧状态那条与 `report` 的用例独立接住,够了。
