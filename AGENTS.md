<!-- pair-protocol:begin -->
# 本仓库正处于双 AI agent 结对开发模式

**在做任何事之前:**

1. 激活 `pair-protocol` 技能(位于 `.agents/skills/pair-protocol/`)。
   工具不自动激活的话,直接读 `.agents/skills/pair-protocol/SKILL.md` 并严格遵守。
2. 运行下面这条命令,确认你的角色和当前回合:

```
python3 .pair/enforcer.py status
```

在这两步完成之前,**不要读代码、不要修改任何文件。**

## 注意:这一轮的执行器是钉住的副本

协议命令一律用 `python3 .pair/enforcer.py <子命令>`,**不要**用
`.agents/skills/pair-protocol/scripts/pair.py` —— 后者是这次结对的**工作产物**,
正在被 dev 编辑。用它执行判定,改坏一次就再也起不来。

`.pair/` 是冻结路径,你改不了执行器,这是有意的。
理由记在 `docs/pair-run/DECISIONS.md` 第一条。

你不是单独在这个项目上工作。另一个 agent 正在负责你不负责的那一半,
擅自动手会破坏它的工作。
<!-- pair-protocol:end -->
