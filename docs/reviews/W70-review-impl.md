# W70 — review-impl(tester)

结论:**通过**。

## 查过的地方

- 分级放在写权限边界之前:带了 `--contract-change` 时,本回合改动里有 `plan_file`,或有 `contract_file` 且 `has_rewrite`(相对 HEAD 有删除行)→ `die`,
  点名这些文件、给出正式通道(撤回 → 写成提案里的 diff → 双方各在本人回合 `sign` → 人类 `PAIR_ROLE=human … ratify`)。`die` 在提交之前,什么都不落盘、工作区不动。
- 纯追加(插在中间也只有新增行)不进 `tiered`,照旧走依据检查、当场留决策、正文 `契约变更(已声明):`。
- 不带声明:冻结那一项对 `plan_file` / `contract_file` 补一句"追加可带 --contract-change;改写或改 PLAN 走提案签字与 ratify"。DONE 时脚本勾选 PLAN 在抓改动之后,不经这道。
- `ENFORCEMENTS` 加 `contract-change-tier`;追加 ADR-025(ADR-001 到 024 原文指纹不变,W56 那几条照绿);两份 README 的 ADR 计数改为 25;
  `rules.md`、`command-reference.md`、`architecture.md`、`troubleshooting.md`、路线图 P1-9 ✅ 跟上。全套绿。

## 变异点

登记四个(锚点各只出现一次),`--only "分级_"` 全部被抓到:PLAN 不拒、改写不拒、纯追加也拒、冻结文案不指向批准。基线全绿。

## 没覆盖的

- `has_rewrite` 认"有删除行":把一行末尾补几个字也算改写(diff 里是一删一加)—— 契约的口径就是这样,写「补充」要另起一段;rules 里已写明。

---

# W70 — review-impl 第二次(tester)

结论:**通过**。

- 本回合 `pair.py` 没动,只有状态文件;空转判定"是",如实。回合进 impl 是第三十二轮 W59 ⑱(与第三十四轮 W61 一并算消失的用例)的设计行为:
  上一次完成的全量判出两条"不再跑的用例",那是本项 spec 回合有意的改名(`test_v1_frozen`、`test_v1_rebound_shortcut` 各一条),⑱ 认不出"有意",照样不走 W17 捷径。
- 我这边的改动(注销等价变异、删缓存里那一条)已在上一个 spec 回合提交,`test_变异点仍能匹配到源码` 与缓存一致性那两条绿。

## 一处观察(不阻断,建议登记)

⑱ 把"消失的用例"一律当成实现弄坏的,而 tester 在 spec 回合**有意改名**的用例也会消失 —— 这一次因此多绕了 impl 与 review-impl 两个回合。
改名不经 `--allow-deletion`(那只认删文件或删用例),所以 tester 没有地方声明。建议完成后登记成路线图开放条目,交人类排期;不在本项里改。
