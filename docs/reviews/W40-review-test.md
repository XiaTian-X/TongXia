# W40 review-test(dev)

裁决: changes

## 问题

1. **只比主版本的自检能过全部用例** —— `tests/conformance/test_v1_run_env.py:51` 的假 `python3` 报 `2.7`,与本机差的是主版本。
   把 `tests/conformance/run.py:160` 的 `if theirs != mine:` 换成只比主版本(`theirs.split('.')[0] != mine.split('.')[0]`),5 条全绿。
   而立项的起因正是主版本相同、次版本不同(3.9 / 3.12 对 3.14),契约写的是"主.次版本相同"。
   请在 :51 旁加一条:假 `python3` 报与本机**同主版本、不同次版本**的号(例如本机 `3.N` 时报 `3.N+1`,用 `sys.version_info` 现算),
   断言非 0、点名两个版本、没有汇总行。
2. **"PATH 上找不到 `python3`"那一支没有用例** —— `tests/conformance/run.py:154` 换成 `return []`,5 条全绿。
   这是我在开工前审查里提的读法、你照着实现了,但没钉住。可以把 PATH 设成一个空的临时目录(`run.py` 本身用 `sys.executable` 绝对路径起,
   不受影响),断言非 0、输出含"找不到"、没有汇总行。

## 我检查了什么(其余都成立)

在隔离副本(`git archive`,无 `.git`)里逐个改坏 `run.py` 跑 `test_v1_run_env`:
- 去掉版本比较 → 红 1(版本不同那条);去掉 pytest 检查 → 红 1(`-S` 那条);有问题也返回 0 → 红 2;不自检 → 红 2;
  自检挪到 `--list` 之前 → `--list` 那条红。
- 用例只选 `test_mutation_tooling` 跑 `run.py`,自检漏拦也不会递归跑全套 —— 属实。
- `-S` 起同一解释器模拟"缺 pytest":venv 与 Homebrew 的 site-packages 都被跳过,CI 上 `pip install` 装进的也是 site-packages,成立。
- 失败说明指向的 `docs/contributing.md「两条必跑的命令」`已存在。
