# W31 — review-test(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

隔离克隆(impl 回合,`.pair/scratch/w31`,用完删掉)里对 `test_v1_os_files` + `test_v1_shipped` 注入:

| 注入 | 红 |
|---|---|
| 认出系统文件那一行改 `if False:`(即你登记的「越界文案不认系统文件」) | 根目录、`docs/` 下、Windows 两种、同一次拒绝各说各的 —— 4 条 |
| 系统文件与普通孤儿都走系统文件那一句 | 对照组、同一次拒绝各说各的 —— 2 条 |
| 干净 | 无 |

- **判据只看那个文件自己那一段**:`block()` 取 `\n  <路径>\n` 之后连续的六空格缩进行,到下一个文件或空行为止 ——
  末尾的指引将来提到 `.gitignore` 不会替判据成立;`docs/.DS_Store` 与 `.DS_Store` 用 `re.escape` 分开取,不会互相命中。
- **对照组只差文件名**:同一位置、同样未跟踪的 `notes.txt`,它那一段不含 `.gitignore`、仍含"需要人类划归" ——
  两个方向的错误实现各被它抓住一次。
- **端到端那条走真实路径**:`adopt_gitignore` 让 harness 的 `.gitignore` 跟上 `GITIGNORE_LINES`,两个 `.DS_Store` 都不挡交接 ——
  守的是"机制本身生效",不只是文案。
- `init` 那条跑真 `init` 再按行比,不靠子串(`.DS_Store` 不会被 `.DS_Store.bak` 之类蒙过)。
- 锚点「越界文案不认系统文件」「gitignore 不含 .DS_Store」在 `pair.py` 里各恰好 1 次;重锚后的「gitignore 不含 scratch」照旧被抓。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W31`。

## 未覆盖

- **接受你在 review-impl 里的提醒**:`OS_FILES` 按"不含 `/` 也不含 `*`"从 `GITIGNORE_LINES` 里筛,今天恰好是那三项;
  今后加一个 `.env` 之类的裸文件名,它会被说成"操作系统写的文件"。没有用例守这个语义,我也同意不打回。
  修法是我的:下一次碰 `pair.py` 时把这三项在 `GITIGNORE_LINES` 里标出来(比如单独一个具名元组再拼进列表),
  筛选就不再靠形状猜 —— 但字面是你定死的、锚点在上面,改它要走带声明的契约变更。本回合只读、写不了 `docs/improvements.md`,完成后由下一个能写它的回合登记。
- 落在执行者自己路径下会被静默提交:路线图 40。
