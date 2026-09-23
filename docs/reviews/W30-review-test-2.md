# W30 — review-test 第二次(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

- **skip 判的是"问得了本仓库的 git"**:`repo_is_git_checkout()` 用 `rev-parse --show-toplevel` 且要求等于 `REPO`,
  与 `make-demo.py` 的判定同一个口径,不看 `.git` 目录(照我上次的提醒,worktree 里 `.git` 是文件)。
  副本若落在别的 git 仓库里(比如 `.pair/scratch/`)也会 skip,不会去问外层仓库。
- **防回归真能红**:隔离克隆里把 `setUp` 的 skip 换成 `pass`,外层这个文件只红 `test_没有_git_的副本里只有_skip` 一条 ——
  它输出里夹着的 6 个 ERROR 是它子进程里那份副本的,正是它要揭发的东西。干净时这个文件在克隆里全绿。
- **全套在无 `.git` 的副本里**:我把工作区 `rsync --exclude .git` 到仓库外的临时目录跑 `run.py`,**528 条全绿** ——
  上次那 7 条 2 失败 4 错误没了,`mutation_check` 判定变异的环境恢复正常。
- **缓存清理干净**:`catchers` 里「简报不提 scratch」→ `test_v1_scratch_brief…test_impl`,「idle 也提 scratch」→
  `…test_idle_整段输出都不含`;整份缓存里再没有任何以 `test_v1_make_demo_tracked` 为抓手的条目。
- `TestRealDemoHasNoEmptyDirs` 没跟着 skip,走 make-demo 的非 git 分支照跑。
- 走了 W17 捷径,只动 `tests/`、缓存与记忆层;**决策**:`docs/pair-run/DECISIONS.md` 已有 `## W30`。

## 未覆盖

- 防回归只守这一个文件。今后别的用例若也在无 `.git` 副本里恒失败,同样会让 `mutation_check` 假判"抓到",
  没有东西会先发现 —— 除非有人像这次一样注意到抓手与变异毫不相干。一条"无 `.git` 副本里全套只许绿或 skip"的全局守卫
  能挡住整类,但每次要复制整个仓库、跑全套,代价大,不在本项。值得进路线图。
- `mutation_check` 本身不校验"抓手是否与变异相关",这是那次假判能潜伏的根本原因,同上。
