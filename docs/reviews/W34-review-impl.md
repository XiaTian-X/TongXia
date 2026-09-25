# W34 — review-impl(tester)

结论:**通过**。

## 查过的地方

- 字面与 spec 回合定死的一致:`OS_FILES` 元组在 `GITIGNORE_LINES` 之前,后者末行 `*OS_FILES`;按形状筛的那一行删掉,注释写明原因。
- `init` 写的 `.gitignore` 内容与顺序不变(三个系统文件仍在末尾、scratch 之后),W31/W23 的相关用例绿。
- `_orphan_note` 仍读 `OS_FILES`,名字没变。
- 三个锚点(scratch、`.DS_Store`、退回按形状筛)字面各匹配 1 处,`test_变异点仍能匹配到源码` 通过;本回合没有新锚点要登记。

## 没覆盖的

- 名单本身的内容(为什么是这三个)没有用例守 —— 契约写明不改名单。
