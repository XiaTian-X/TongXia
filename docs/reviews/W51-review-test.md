# W51 review-test(dev)

裁决: approve

## 我检查了什么

- `tests/conformance/test_v1_make_demo_git_fail.py` 7 条:假 git(sh 脚本,指定那一步打固定文字退 128,其余转给真 git)让 `init`/`add`/`commit` 各自失败,
  断言非 0、无 `Traceback`、git 原话在输出里、按 ASCII 词边界点名这一步;commit 失败给出 `user.email` 与 `commit.gpgsign`;目录留着;init 失败不点名 commit;前提对照组。
- 词边界的判法排除了 `commit.gpgsign`(带点)—— 否则修好之后的原因文字会替"点名 commit"作答,这条设计对。
- 隔离副本里另探两个:退回 `check=True` → 四条"点名+原话"红;所有步骤都给 commit 的提示 → 只红"init 失败时不说是 commit"。连同 tester 笔记里的四个探针,六种写错法都被抓。
- 全套 628 绿;假 git 在 CI 的 Linux/macOS 上可用(用例在 Windows 或没有 git 时 skip)。

## 未覆盖

- review-impl 打回的那处(两条出路互相抵消)是文案逻辑,没有用例守;靠两边各自手工走过一遍"就地做完"。
- stdout 那一路的原话(钩子打在标准输出)没有用例:假 git 只往 stderr 打。
