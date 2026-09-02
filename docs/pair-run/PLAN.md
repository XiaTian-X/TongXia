# 项目规划（冻结 — agent 只读）

> 由人类维护。工作项完成时由脚本勾选,那是脚本的权限,不是 agent 的。

## 目标

把 `status` 的注入内容落盘到 `.pair/.last-brief.md`,让人类事后能看到
每一回合 agent 到底看到了什么。**零协议语义变更,纯可观测性。**

来源:`docs/improvements.md` 的 P1-4。

## 工作项

- [ ] **W1** [feature] — status 在自己回合时落盘简报,且不让后续交接越界
  - 验收标准:轮到自己时 `.pair/.last-brief.md` 存在,含角色、工作项 ID 与类型、
    阶段、红绿五项;写过之后 `handoff` **不**判越界
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘

- [ ] **W2** [feature] — 记忆注入进简报,非自己回合时不写不清空
  - 验收标准:笔记全文与相干决策原文出现在简报里;不是自己回合时跑 `status`
    既不创建该文件、也不清空已有内容
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘

- [ ] **W3** [feature] — 写失败不阻断
  - 验收标准:写文件失败时 `status` 退出码仍为 0,标准输出出现 `[简报]` 警告,
    且其余输出不受影响
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘
