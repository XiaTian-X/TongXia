# W23 review-test(dev 审 tester 的测试)

裁决: **approve**。

## 查过的

- `init` 写的 `.gitignore` 含 `.pair/scratch/`;本仓库 `.gitignore` 也有(样板项目那份由既有的 `test_gitignore_跟得上_GITIGNORE_LINES` 守)。
- **harness 的 `.gitignore` 是手写两行,用例先以人类身份把 `GITIGNORE_LINES` 原样追加** —— 手加 `.pair/scratch/` 的话用例就与实现无关。你开工前审查就指出了,这里照做了。
- 评审回合与 impl 回合写副本:放行、不进提交(`git_paths` 整路径判)。
- `verify-setup` 那条**换成 Go 的 glob 布局**,让副本里的 `.go` 本来会命中角色路径;并配一条"仓库里真源码照样被列出"的对照组 ——
  默认布局下 `.pair/scratch/` 不在任何角色路径里,那条会恒绿。
- 我 impl 回合的探针(`GITIGNORE_LINES` 去掉那一行)红 4 条,锚点 `+5/-0` 纯追加、字面一致。

## 未覆盖(不构成打回)

- 文档里那条示范命令没有用例 —— 我 impl 回合在一个最小项目上实测过。
- "误把实现路径加进 `.gitignore` 协议就看不见"这一面写进了决策记录(`## W23 —`),不在本项修。
