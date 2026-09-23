# W29 — review-test 第二次(dev 审 tester 的测试)

裁决: approve

## 我检查了什么

- **上一次的缺口补上了**:隔离克隆(`.pair/scratch/w29`,用完删掉)里删掉 `make-demo.py` 的 toplevel 等于 REPO 那两行,
  现在恰好红新加的 `test_解压进别的_git_仓库里照样有样板文件` 一条;干净时两个文件全绿。
- **变体造得对**:外层仓库**提交过自己的文件**(`README.md`),mini TongXia 放在它的 `vendor/tongxia/` 下、没被提交 ——
  `rev-parse --show-toplevel` 会成功并指向外层,`ls-files -- examples/demo-project` 在那里列不出任何东西。
  这正是我上次实跑出"退出码 0、项目里没有样板文件"的那个形状;外层有提交也排除了"空仓库上 `ls-files` 行为不同"的干扰。
- **判据**:断言 `docs/PLAN.md` 与 `src/__init__.py` 存在 —— 都是被跟踪的样板文件,错误实现下两者都不在。
- 上一次查过的其余几条(整目录复制红 3 条、非 git 时建空目录红 1 条、对照组、只删一个目录可区分)不变。
- 走了 W17 捷径(`spec -> review-test`),只动了 `tests/`。
- **决策**:`docs/pair-run/DECISIONS.md` 已有 `## W29`。

## 未覆盖

- 外层仓库**恰好**跟踪了同路径的样板文件(用户把 TongXia 整个提交进了自己的项目)时,`ls-files` 会列出它们,
  但 toplevel 不等于 REPO,实现仍走"整目录复制、跳过空目录"那一支 —— 结果只是多带出未跟踪文件,不会少文件。
  契约没点这种情况,不要求。
- 技能目录照旧整目录复制(`__pycache__/` 会跟着发出去,生成项目的 `.gitignore` 忽略它),契约写了照旧。
