# W68 review-test(dev)

裁决: changes

## 我检查了什么

- `tests/conformance/test_v1_ratify.py` 20 条与契约「提案的签字与人类批准」及补充 ㉒ 逐项对上:
  - sign 取最后一个块的哈希、随交接提交,五种拒绝;
  - ratify 通过时契约按 diff 改、记批准行、主题与正文对、只提交契约与提案、两方校验失效;status 列待批准;讨论阶段里批准之后照常 resume;
  - ratify 的各种拒绝,每条都核对 PLAN、契约、提案逐字节不变、提交数不变。
- 提议改动用真的 `git diff` 造;"应用不上"那条用 `difflib` 造,理由写在用例里(`git diff` 比的是索引,造出来的总能应用),对。
- ㉒ 那条 `--checked` 另起一行伪造 `role=dev` 的场景写得准:tester 自己那行先正当提交,伪造的只有 dev 那一行,拦住它的只能是"只认第一行"。
- review-impl 登记的八个变异点里,七个被抓到。

## 打回原因:登记的变异点「批准_角色从正文任意一行取」是等价变异

- `tests/conformance/mutation_check.py:1307` 把 `.agents/skills/pair-protocol/scripts/pair.py:3471` 的 `first` 换成整段正文。
- `FIRST_LINE_ROLE_RE.search` 取的是第一个匹配,仍然是第一行的 `role=tester`,行为没变,所以存活。
- 我 impl 时自己的探针也是这么写弱的(交接正文里说过)。
- 按 review-impl 的约定由这里打回:请把这个变异点改成能代表"任意一行都认"的写法,比如取**最后一个** `role=`,让 ㉒ 那条用例红。实现不用改。
