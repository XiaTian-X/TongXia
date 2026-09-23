# W31 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `GITIGNORE_LINES` 照定死的两行;样板 `.gitignore` 跟上三行,本仓库补 `Thumbs.db`、`desktop.ini`。
- `_orphan_note`:按 `PurePosixPath(path).name` 认,`docs/.DS_Store` 算;系统文件只打"加进 `.gitignore`",不再同时说"需要人类划归"
  —— 两个出口并列会让人不知道做哪件,同意。普通孤儿那一句原样;没往 `if violations:` 与 `lines =` 之间插东西(既有锚点)。
- 系统文件落在**别的角色路径**下(不是孤儿,比如 dev 在 impl 碰到 `tests/.DS_Store`)也会打这一句:那时出口同样是 `.gitignore`,合理。
- 锚点「越界文案不认系统文件」字面唯一,已追加登记,被抓;「gitignore 不含 .DS_Store」照旧被抓;匹配源码那条通过。

## 没覆盖的 / 提醒

- **`OS_FILES` 按"不含 `/` 也不含 `*`"从 `GITIGNORE_LINES` 里筛**:今天恰好正是那三项,但把"被忽略的裸文件名"当成"操作系统写的"是
  两件事 —— 今后 `GITIGNORE_LINES` 加一个 `.env` 之类的裸文件名,它会被说成"操作系统写的文件"。没有用例守这个语义。
  不打回(今天行为正确、与契约一致),建议进路线图或在那行注释里写明新增裸文件名时要改这里。
- 路线图 40(落在自己路径下被静默提交)已登记。
