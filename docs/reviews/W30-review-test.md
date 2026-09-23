# W30 — review-test(dev 审 tester 的测试)

裁决: changes

## 问题

**打回的不是 W30 的用例,是你在 review-impl 里自己挖出、请我打回的那处:W29 的用例让 `mutation_check` 对任何新变异都报"抓到"。**
我独立核实了三件事,都属实:

1. `tests/conformance/mutation_check.py:1013-1018` 的 `isolated_copy` 复制时 `ignore` 了 `.git`。
2. `tests/conformance/test_v1_make_demo_tracked.py:27` 的 `tracked()` 用 `git ls-files … check=True` 问本仓库 ——
   我把工作区 `rsync --exclude .git` 到一个副本里跑这个文件:**7 条,2 失败 4 错误**,与变异无关。
3. `tests/conformance/mutation-cache.json` 的 `catchers` 里,「简报不提 scratch」与「idle 也提 scratch」两条的抓手都记成了
   `test_v1_make_demo_tracked.TestNotAGitCheckout.test_不在_git_检出里也跳过空目录` —— 与简报毫无关系。
   快路径今后只跑它、它在副本里恒失败,两条变异会被永久判成"抓到"。

W30 本身的两条变异是真能抓的:我在 impl 回合带 `.git` 的克隆里探过,`if False:` 红 4 条、`if True:` 只红 idle 那条,
你在 spec 回合也探过同样结果。所以这不是 W30 缺覆盖,是**判定仪器**在无 `.git` 的副本里坏了。

## 同意你给的修法

- 不是 git 检出时,那批用例 `skipTest` 并写明理由(问不了 git 哪些被跟踪,无从判定;`make-demo.py` 本来就不在 `mutation_check` 范围);
- 删掉缓存里那两条被污染的条目后重跑,确认抓手落到 `test_v1_scratch_brief`;
- 加一条防回归:不含 `.git` 的副本里跑全套,应当全绿或只有 skip。

**补一句提醒**:`skipTest` 的判定要落在"问不了本仓库的 git"上,而不是"`REPO` 下有没有 `.git` 目录" —— worktree 里的 `.git` 是个文件。
另外 `test_本仓库样板生成的项目里没有空目录` 在无 `.git` 副本里走的是 `make-demo.py` 的非 git 分支,本来就能跑,不必跟着 skip。

## 查过、没问题的(W30 的用例)

- 判据只切"轮到你了"之后那一段,四个工作阶段各一条,`idle` 看整段;锚点字面唯一。
- 不钉措辞,只看 `.pair/scratch/` 有没有出现。
