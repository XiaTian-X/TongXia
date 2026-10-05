# W48 review-test(dev)

裁决: approve

## 我检查了什么

- `symbol_ref_scope`:被 git 跟踪的 `.md` 减 `shared_paths`、`ignore_paths` 与记忆层,路径匹配用 `pair.py` 的 `matches_any` —— 与 `normative_docs` 同口径,不另写枚举。
  `NORMATIVE` 保留给别的用例,符号检查改扫新范围。
- 端到端(本地 `git clone` 出来的副本,有 `.git`):往 `references/brownfield.md` 写一处不存在的符号 → `test_规范文档里没有行号形式的引用` 红;
  同一句写进 `docs/pair-run/notes/W48.md` → 绿;**把测试文件换回 W48 之前的版本**、坏引用照样写进 `brownfield.md` → 绿 —— 新范围确实多守住了原来漏掉的那批。
- 问不了 git 时返回 None、整组 skip(你补的 ⑬):查过变异缓存,没有任何变异的抓手是这组用例,隔离副本里 skip 不会让哪个变异变成存活。
  CI 与本地都是 git 检出,这组照常跑。
- 新增 4 条:范围含枚举外文档、不含记忆层与评审目录、新纳入文档的坏引用被检出、非 git 目录返回 None。
- 全套绿。

## 未覆盖

- 只扫被跟踪的 `.md`:本回合新写、还没提交的文档要等提交之后才进范围(`normative_docs` 按改动那一批算,两者在这一点上不同,对仓库一致性检查是合适的)。
- 在 `mutation_check` 的隔离副本里这组 skip —— 那里文档不会被改动,不损失防护;但那是靠"变异只改 `pair.py`"这个前提。
