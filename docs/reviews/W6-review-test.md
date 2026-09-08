# W6 评审(dev 审 tester 的测试)

结论:**打回**。两处要改,一处是"用例声称守着某条契约、实际不守"。
证据都是跑出来的,不是读出来的。

---

## ① 「取起始行」这条契约没有被守住 —— 变异存活

`tests/conformance/test_docs_consistency.py:527`
(`TestSymbolReferences.test_区间形式也被拒且按起始行给建议`)

它的断言注释写着:

> `assertIn("cmd_init.put", bad[0], "应按**起始行**所在的最内层符号给建议")`

但它选的区间是 `pair.py:2375-2382`,而 **2375 和 2382 落在同一个符号里**:

```
起始行 2375 -> cmd_init.put
结束行 2382 -> cmd_init.put
```

所以这条用例**分不出取的是起始行还是结束行**。

**变异实验(在进程内替换 `check_symbol_refs`,不改文件):**

| | 结果 |
|---|---|
| 基线 | GREEN(10 条) |
| 把 `_enclosing_symbol(rel, a)` 改成 `_enclosing_symbol(rel, int(b) if b else a)` | **GREEN(10 条)** |

契约「旧形式被拒」写的是"取**起始行**所在的封闭符号",这是逐字写死的一条,
而它现在**一条用例都没守**。

**改法(实测可用):** 把区间换成 `pair.py:2375-2390`——

```
起始行 2375 -> cmd_init.put
结束行 2390 -> cmd_init
```

现有断言 `assertIn("cmd_init.put", bad[0])` 原样保留即可:取结束行会产出
`#cmd_init`,不含 `cmd_init.put`,变异立刻红。

---

## ② 这个文件直接跑的时候，10 条新用例全部被静默跳过

`tests/conformance/test_docs_consistency.py:459` 是
`if __name__ == "__main__": unittest.main()`,而
`:462` 才是 `class TestSymbolReferences`。

`unittest.main()` 在类定义**之前**执行,于是:

```
python3 tests/conformance/test_docs_consistency.py   ->  Ran 12 tests  OK
python3 -m unittest tests.conformance.test_docs_consistency -> Ran 22 tests  OK
```

`run.py` 走导入,门禁不受影响 —— 但**直接跑这个文件的人会看到一个绿的 OK,
而这一轮新增的 10 条一条都没跑**。这个仓库对"看着是绿的、其实什么都没验"
的东西一向当严重问题处理(`mutation_check.py#precheck_no_baseline` 那条闸
就是为同一个失效模式加的)。

**改法:** 把 `class TestSymbolReferences` 整体移到 `unittest.main()` 之前。

---

## 逐条核过、认为没问题的部分

**用变异确认过、真的被守住的:**

- **模块级赋值算符号** —— 从 `_symbol_index` 里删掉 `ast.Assign` 分支,
  `test_规范文档里没有行号形式的引用` 变红。**但只有它变红**,10 条作弊
  场景一条都没红(见下面「没覆盖到」)。

**读过、口径正确的:**

- **纯函数 `check_symbol_refs(text, where)` 的取舍是对的。** 9 条作弊场景
  直接喂字符串,不建临时文件树,10 条跑完 0.12 秒。绑死在"扫描 NORMATIVE"
  上的话,每条作弊场景都要造一份假文档树。
- **不要求反引号**(`_LINE_REF` / `_SYM_REF` 都不含反引号)—— 我同意。
  只认反引号会给旧引用留一个绕过口,而漏掉反引号的旧引用同样该被迁移。
- **`_blank_fences` 把围栏抹成空行而不是删掉**,行号保持不变。
- **两类豁免各有一条正向用例**,而且是**正反成对**的:
  `test_裸写重名符号被检出并列出候选`(红)对 `test_限定名可以消歧`(绿),
  `test_行内代码算引用`(红)对 `test_围栏代码块里的不算引用`(绿)。
  这一对正是契约里最危险那条(行内代码整类豁免会让检查恒真)的两面。
- **`test_历史快照豁免且不校验_sha` 用的是 `@deadbeef`** —— 一个不存在的
  sha,正好同时钉住"豁免"与"不校验"两件事,一条用例守两条契约。
- **删掉那两条旧测试(`--allow-deletion`)的理由成立。** 新检查覆盖了它们
  的全部职责,而旧绊线有一个已被实证走过的逃逸口(改数字变绿)。

**关于 `assertEqual(len(bad), 1)`:** 我一开始怀疑它过严(多报一条也算红),
但看下来是对的 —— 每个作弊场景只喂一处引用,数量本身就是断言的一部分,
不然"报了 3 条其中 1 条对"也会算通过。

---

## 没覆盖到（不构成打回，但请一并看一眼）

**模块级赋值只被真实文档那条用例间接守着。** 变异 B(删掉 `ast.Assign`)
只有 `test_规范文档里没有行号形式的引用` 变红,而它之所以红,是因为
**我这一轮刚好把 `improvements.md` 里一处引用写成了
`tests/conformance/mutation_check.py#MAX_CACHED`**。

也就是说:这条契约条款("符号可以是模块级赋值")的全部防护,取决于
**dev 的一份文档里恰好留着那一处引用**。我下一轮改写那句话,防护就没了,
而且不会有任何东西红。加一条 `self._one("见 `…/mutation_check.py#MAX_CACHED`")
== []` 就能把它钉死,成本一行。

我没把它算成打回理由:契约没有单独要求"模块级赋值要有独立用例",
而现状是**有覆盖**的,只是覆盖来源不稳。
