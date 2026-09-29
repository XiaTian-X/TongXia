# W39 review-test(第二次)

裁决: approve

## 我检查了什么

- 新增 `TestReportOutsideSharedPaths`(`tests/conformance/test_v1_combining_setup_report.py:74`):config 把 `shared_paths` 设成 `["docs/other"]`,新写的结论带 U+0301,断言 `verify-setup` 通过、输出点名 U+0301、结论路径之后出现补句那一行的行号。
- 隔离副本(`git archive HEAD`,无 `.git`)里把 `pair.py` 的 `, only=report_rel)` 换成 `)`:5 条里只红这一条,其余 4 条绿。失败信息显示 `verify-setup` 本身照常通过("契约审查结论已收到""开工前校验全部通过"都在),只是少了提示 —— 红在该红的地方,不是被共享目录存在、孤儿之类的其他检查先挡住。
- 复原后 5 条全绿;全套 571 绿(`tests/conformance/run.py`)。
- 新锚点 `, only=report_rel)` 在 `pair.py` 里恰好一处,`test_变异点仍能匹配到源码` 绿。
- 第一次 review-test 列过的其余几处(拆掉提示红 2、追加补记的行号钉住、对照组与旧行不提示)这次没动,照旧成立。

## 未覆盖

- `docs/other` 在 harness 里不存在,`verify-setup` 对不存在的共享目录目前不报错;若将来加上这条检查,这组用例会先红在别处,需要一并建目录。
- 结论文件被 `ignore_paths` 覆盖时的行为没测(`only` 目前也不看 `ignore_paths`,提示照出)—— 契约没规定,不算缺口。
