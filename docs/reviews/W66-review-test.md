# W66 review-test(dev)

裁决: changes

## 我检查了什么

- `tests/conformance/test_v1_proposals.py` 25 条加 `test_docs_consistency` 的 1 条,与契约「提案目录」及补充 ⑳ 逐项对上:
  - 四个阶段都可写;
  - 已提交的只能追加;
  - 四处不认它,用最强形状试,另有对照组放行;
  - `scope`、指纹、正文、默认关、`init`;
  - 五种重叠与三条对照。
- review-impl 登记的九个变异点里八个被抓到,与我 impl 回合在项目内 `.pair/scratch/` 放的 10 个探针一致。

## 打回原因:`inbox` 那一条断言区分不出提案原文出现在哪一段

- `tests/conformance/test_v1_proposals.py:161` 在 `inbox` 的整段输出里找提案原文。
- `inbox` 开头的 `git show` 本来就印出提案的 diff,原文在里面。拆掉 `prose_paths` 里的提案(你登记的 `提案_inbox_不摆出`),这条照样绿。
- 契约要的是摆进 `.agents/skills/pair-protocol/scripts/pair.py:3164` 那一段"对方这一回合写给你的",那一段才是对方必读的散文区。
- 请把断言收窄到那一段:从那一行切到下一个 `===` 为止。这是 review-impl 里约定由这里打回的,实现不用改。

## 未覆盖(不阻断)

- 提案目录用 glob 模式(如 `docs/*/proposals`)时,"只能追加"只认字面目录。契约写的是"直接位于某个提案目录下",用例都用的是字面目录。
