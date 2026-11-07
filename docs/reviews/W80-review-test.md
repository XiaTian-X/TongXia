# W80 review-test —— 符号引用检查:被引文件插入无关行不会红

**裁决:通过(approve)。**

## 查过的地方

- **两条用例对应验收标准 ① ②**:
  - 临时被引文件里四类符号:模块级赋值、函数、嵌套函数、方法。每个定义上方各插 40 行注释、空行、别的函数,同一段引用零违规。
  - 先断言插行之前就通过,场景搭对了。
  - 对照组插行后改名,检出两条"不存在的符号"。
- **缓存陷阱处理对了**:`_symbol_index` 把缓存挂在函数属性 `_c` 上、按路径记(`test_docs_consistency.py#_symbol_index`)。
  - 用例每次改写都 `pop` 掉这个文件的缓存;
  - 用 `addCleanup` 撤掉 `PY_BY_REL` 的登记和缓存。
  - 不这样做,"插行后仍通过"会读到插行前的索引而恒真,对照组也会串到上一条的缓存。
- **不是变更探测器**:只断言违规条数与"不存在的符号"字样,不钉文案全文。插的无关行里有新函数,但不与被引符号同名,不引入重名。
- **验收标准 ③ 的读法**:不登记进 `mutation_check.py`,改为隔离副本探针。我同意。
  - `mutation_check` 只变异 `pair.py`(`tests/conformance/mutation_check.py#PAIR_PY`);
  - 被测的检查在 `test_docs_consistency.py` 里;
  - PLAN 里 W64 有同样的先例。
- **我自己复跑了一个探针**:让 `_symbol_index` 只收前 30 行的定义。在 `.pair/scratch/` 的副本里跑 `TestSymbolReferences`,新增的两条都红,另有两条已有用例也红。tester 表里另三个探针我没复跑。
- 不改 `pair.py`,不改检查本身(验收标准 ④)。

## 没覆盖到的

- 探针没有进 `mutation_check`,以后有人改检查时不会被自动复验。这是"检查住在测试文件里"的结构性局限,不是这一项能解决的。
- 路线图 P1-12 第 ② 项还没标 ✅:review-test 是 dev 的只读回合,写不了 `docs/improvements.md`。留给下一次开轮的提交补上。
