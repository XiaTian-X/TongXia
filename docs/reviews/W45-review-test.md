# W45 review-test(dev)

裁决: approve

## 我检查了什么

- `mutation_check.py` 的改动:抽出 `precheck_passes(rc, fails)`,`main` 的 `--no-baseline` 那一处由 `rc != 0 or fails` 改为 `not precheck_passes(rc, fails)` —— 逻辑等价,行为不变。
- `tests/conformance/test_mutation_precheck.py` 9 条对契约三层:真值表四格(含"退出码 0 但抓到 FAIL 行不放行")+ `main` 调用它;源码断言三条;`isolated_copy` 行为一条。
- 源码断言会不会被注释或文档字符串蒙过:`precheck_no_baseline` 的文档字符串提到 `PAIR_MUTATION_RUN` 但没有 `="1"`,`isolated_copy(` 只出现在调用处 —— 断言落在真代码上。
- 隔离副本(`git archive`)逐个改坏 `mutation_check.py`:挪到真实仓库、去掉变量、忽略不含 `.git`、只看退出码、只看失败集、`main` 不用判定 —— 六个各只红对应一条。
- 全套 608 绿。

## 未覆盖

- "忽略不含 `.git`"在没有 `.git` 的环境里只靠源码断言抓;行为断言"副本里没有 `.git`"在那里恒真(tester 笔记里也记了,见决策 W45)。
- `isolated_copy` 还排除 `*.pyc` 与 `.DS_Store`,没钉(契约只点名 `.git` 与 `__pycache__`)。
- 抽函数让缓存基线指纹失配,完成时的全量会重跑基线 —— 契约写明的成本。
