# 项目规划（冻结 — agent 只读）

> 由人类维护。工作项完成时由脚本勾选,那是脚本的权限,不是 agent 的。

## 目标

把 `status` 每回合给 agent 看的内容落盘到 `.pair/.last-brief.md`,
让人类事后能查"这一回合它到底看到了什么"。**零协议语义变更,纯可观测性。**

来源:`docs/improvements.md` 的 P1-4。

## 工作项

- [x] **W1** [feature] — 轮到自己时写出简报头部,且不影响后续交接
  - 验收标准:轮到自己时 `.pair/.last-brief.md` 存在,含契约规定的四行头部
    (角色 / 工作项 / 阶段 / 测试),取值形态与契约一致;写过之后再跑 `handoff`
    不因这个文件被拒
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘

- [ ] **W2** [feature] — 记忆段落入简报,非自己回合时不写不清空
  - 验收标准:有笔记或相干决策时,记忆段落与终端所见逐字一致;没有时整段省略
    而头部四行仍在;不是自己回合时跑 `status` 既不创建该文件、也不改动已有内容
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘

- [ ] **W3** [feature] — 写不成时不阻断,以及新项目里被忽略
  - 验收标准:写入抛 `OSError` 时 `status` 退出码不变、其余输出不受影响,
    标准输出出现一行 `[简报]` 开头的警告;全新项目跑完 `init` 后
    `.gitignore` 含这个文件
  - 对应契约:`docs/pair-run/CONTRACT.md` → status 简报落盘
