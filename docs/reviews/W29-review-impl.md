# W29 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `tracked_demo_files`:`--show-toplevel` 解析后等于 `REPO`(模块顶部已 `resolve()`)才用 `ls-files -z`;
  没有 `.git` 或上级是别的仓库时返回 None —— 与 spec 回合补的契约一致。
- `copy_demo`:只复制文件与链接,空目录自然不出现;非 git 路径打一行说明;被跟踪但工作区删掉的跳过(按工作区为准,合理)。
  技能目录与软链接照旧。本仓库那个真实的空 `tests/conformance/` 留着,git 路径不发它,用例绿。
- 样板契约组合符规则:实测 `NFC("क़")` 是 U+0915 + U+093C;全部 `M` 类字符 `isalnum()` 都为假(0 个例外),
  "组合符 `isalnum()` 为假"成立。"紧跟保留字符后面的保留、连续几个都保留、其余丢弃"与 `slugify("́a") == "a"`、
  `slugify("a-́b") == "a-b"`、`q́` 原样一致;与"先按原字符判定再小写化"(İ)不冲突;单独一个组合符
  没有 `isalnum()` 为真的字符,照旧 `ValueError`,错误表不用改。
- 例子写成转义、正文不留天城文字符(`grep` 0 处):条目 27 那一类的正确应对。
- `make-demo.py` 不在 `mutation_check` 范围,无锚点可登记;`test_v1_make_demo_tracked` 与 `test_v1_shipped` 全绿。

## 没覆盖的

- 样板契约措辞没有用例守(样板里没有实现)。
- 技能目录照旧整目录复制,本仓库跑过测试后的 `__pycache__/` 会跟着发出去;生成项目的 `.gitignore` 忽略它,契约写了照旧。
