# W18 review-test(dev 审 tester 的测试)

裁决: **changes**。一处,你在 review-impl 已经同意:文案那条断言恒成立。

## 问题:`assertIn("W1-review-impl.md", r.text)` 不管实现怎样都成立

`tests/conformance/test_v1_review_immutable.py:37`。被改写的那份文件本身就叫
`docs/reviews/W1-review-impl.md`,而拒绝清单必然把**违规路径**打出来 —— 断言命中的是路径那一行,
不是"本回合该写的是 …"那一句。实测:把 `review_rewrite_hint` 里那整句删掉,**全套 434 条 0 红**。

契约「拒绝文案」要的是**给出本回合该写的文件名**,而这条用例守不住它。

**候选形状**:让"被改写的文件"和"本回合该写的文件"不同名 ——
在 review-impl 里先 `handoff changes` 打回一次(`changes_count` 变 1),简报算出的就是
`W1-review-impl-2.md`;再去改写已提交的 `W1-review-impl.md`,断言文案里出现 `-2`。
删掉那句时它会红。

**这是同一个形状的第三次**:你 spec 回合自己抓到两条(`replace` 空操作、先通过一次再改写导致状态字节相同),
这是第三条 —— 都是"另一样东西替判据成立了"。

## 查过、没问题的

- 其余九条:拒绝四条(评审回合改写、删整份、改名、dev 在 impl 改写)、放行四条(纯追加、新建、
  `ignore_paths`、子目录与非 `.md`)、`verify-setup` 一侧两条。判据不碰我起的函数名。
- **`verify-setup` 那条真的守住了"拒绝早于写状态"**:我把整块拒绝挪到 `save_state` **之后**重探,
  只有它红。(我第一次探错了位置,记在笔记里。)
- **六个锚点已在 review-impl 当场登记**:`+36/-0` 纯追加,字面与我笔记表一致,含"拒绝晚于写状态"那个 ——
  我给的表达方式(提前插一行 `save_state`)你采用了。
- W16 连续第三项在 review-impl 当场还清锚点。

## 顺带

你修完这条之后,如果只改 `tests/`、以 GREEN 结束、不碰契约,**W17 的捷径应该会把它直接送回 review-test**,
跳过 impl 与 review-impl —— 那将是捷径的第一个真实样本。留意 `handoff` 输出的下一阶段。
