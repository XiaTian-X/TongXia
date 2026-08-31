---
name: pair-protocol
description: 双 AI agent 结对编程协议。一个 agent 写测试、一个写实现,严格轮流交接并互相评审。当本仓库存在 .pair/ 目录、或你被告知处于结对开发模式、或环境变量 PAIR_ROLE 已设置时,必须激活本技能。涵盖回合调度、写权限边界、红绿不变量、评审裁决和契约变更流程。
license: MIT
compatibility: 需要 git 和 bash。适用于任何支持 Agent Skills 的编码 agent。
metadata:
  version: "1.0"
---

# 双 Agent 结对编程协议

本仓库由**两个 AI agent 结对开发**:一个只写测试,一个只写实现,严格轮流,
互相评审。你是其中之一。

你和对方**看不到彼此的对话**。唯一的通信渠道是 git 提交和 `docs/reviews/`
里的文件。任何你希望对方知道的事,都必须写进这两个地方。

## 第一件事

```
.agents/skills/pair-protocol/scripts/status
```

它会告诉你:你是谁、轮到谁、测试是红是绿、这一回合具体该做什么。
**跑它之前不要读代码、不要改任何文件。**

如果它说不是你的回合:跑 `scripts/inbox` 看对方做了什么,向人类报告在等谁,
然后**停下**。不要抢跑。

## 最后一件事

```
.agents/skills/pair-protocol/scripts/handoff "一句话说明你这回合做了什么"
```

评审回合必须带裁决:`handoff approve "理由"` 或 `handoff changes "问题清单"`。

`handoff` 会校验写权限边界和红绿不变量,**不合规直接拒绝提交**。
被拒时不要想办法绕过去——拒绝理由就是你要修的东西。

## 两个角色

| | `tester` | `dev` |
|---|---|---|
| 只能写 | `tests/` | `src/` |
| 绝对不碰 | `src/` | `tests/` |
| 职责 | 把 PLAN 里的工作项翻译成**会失败**的测试 | 让失败的测试变绿 |

角色由环境变量 `PAIR_ROLE` 决定,人类启动你时已设好。没设就停下来问人类。
实际路径边界以 `.pair/config` 为准,上表是默认值。

## 回合循环

```
spec (tester)  →  impl (dev)  →  review-impl (tester)  →  review-test (dev)  →  下一项
   写失败测试        最小实现至绿        审实现是否作弊          审测试是否过拟合
```

评审打回会退回对应阶段。同一工作项被打回 3 次,协议强制停止并交给人类。

## 六条硬性规则

这些不是建议。违反会被 `handoff` 拒绝,或被对方在评审时打回。
详细说明和判例见 [references/rules.md](references/rules.md)。

1. **不许碰对方的目录。** 认为对方写错了 → 写进 `docs/reviews/`,
   用 `handoff changes` 打回,由对方自己改。
2. **dev 不许改或删测试。** 一条都不行。测试是规格,不是障碍。
3. **dev 不许为通过测试而硬编码。** 针对测试输入特判、返回写死的期望值,
   都算作弊,评审时必须被打回。
4. **tester 只断言 `docs/CONTRACT.md` 里的可观测行为。** 禁止断言私有方法名、
   内部调用次数、日志内容——那会把测试变成变更探测器。
5. **tester 一回合只提一个(或一组紧密相关的)失败用例。** 不要一次砸一堆。
6. **评审必须给出具体裁决。** 禁止 "看起来不错" "LGTM" 这类空话,approve 也要
   写清楚你实际检查了什么。**你的价值就在于挑刺;互相点头等于这个项目白做。**

## 冻结文件

`docs/PLAN.md` 和 `docs/CONTRACT.md` 由人类维护,agent 一律只读。

实现到一半发现接口设计有问题是正常的,**不要硬着头皮实现一个错的契约**,
走 [references/rules.md](references/rules.md#契约变更流程) 里的变更流程。
