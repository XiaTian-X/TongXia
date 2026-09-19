# W23 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `GITIGNORE_LINES` 末尾加 `.pair/scratch/`,注释说明不另写判定的理由;与我参考实现一致。
- 本仓库与样板项目的 `.gitignore` 各加一行 —— `test_gitignore_跟得上_GITIGNORE_LINES` 与我那条本仓库数据检查都绿。
- `rules.md` 新小节:单进程临时替换的示范里,替换发生在 `discover` 导入测试模块之前,测试里 `from src import slugify`
  拿到的是替换后的对象,成立;"替换测试导入的那个名字"那半句补得对。编译缓存与 `\uXXXX` 两句照契约写进。
- 锚点「gitignore 不含 scratch」字面唯一,已追加登记;`--only scratch` caught,匹配源码那条通过。

## 没覆盖的

- 自定义测试命令会不会扫进 `.pair/scratch/` 里副本的测试文件(harness 的 Go 假命令 `glob('**/*_test.go')` 就会):
  `rules.md` 没提,不写成用例,记在我 spec 笔记里,可以留给路线图。
