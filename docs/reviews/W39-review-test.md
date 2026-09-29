# W39 — review-test(dev 审 tester 的测试)

裁决: changes

## 问题

**`only` 那一支没有用例守 —— 去掉它,4 条全绿。**

契约「审查结论里新写的组合符也要提示」的「行为」写明与 W37 用同一个**判定**;你在开工前审查里提醒过,
`combining_in_new_lines` 默认按 `shared_paths` 与记忆层过滤路径,某个项目的 `shared_paths` 不含 `docs/reviews` 时,
审查结论会被滤掉、提示静默消失。实现为此加了 `only=report_rel`。

隔离克隆(impl 回合,`.pair/scratch/w39`,用完删掉)里把 `, only=report_rel)` 去掉 —— 走默认的路径过滤 ——
`tests/conformance/test_v1_combining_setup_report.py` 4 条**全绿**:harness 的 `shared_paths` 是 `docs/reviews`,正好含结论所在的目录。
我在内存里核过:`shared_paths` 设成 `docs/other` 时,不传 `only` 返回空、传了能点名 —— 实现对,但没有用例守。你在 review-impl 里也请我打回。

**候选形状**:`TestNewReport` 旁边加一组,`config = {"require_setup_verification": True, "shared_paths": [<不含 docs/reviews 的目录>]}`,
其余照 `test_新写的结论里的组合符_点名文件_行号_码位` 写,断言点名文件与 `U+0301`。正确实现绿、去掉 `only` 红。
改 `shared_paths` 时注意 `verify-setup` 的其他检查(共享目录存在、与角色路径不重叠)不要因此先红 —— 那样这条会因为别的原因变红,测不到 `only`。

## 查过、没问题的

| 注入(impl 回合,隔离克隆) | 红 |
|---|---|
| 拆掉结论提示 | 新写的、追加补记的 —— 2 条 |
| 去掉 `only`(走 `shared_paths` 过滤) | **0 条**(即上面的问题) |

- 追加补记那条钉住了补记所在行的行号 —— W37 打回过的同一个缺口,这次一开始就补上了。
- 对照组写的是 `U+0301` 这几个 ASCII 字符;旧行里的组合符不提示。
- 组合符全用 `chr(0x...)` 常量,测试源码里 0 个裸组合符。
