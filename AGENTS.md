<!-- pair-protocol:begin -->
# 本仓库是双 AI agent 结对开发项目

**在做任何事之前:**

1. 激活 `pair-protocol` 技能(位于 `.agents/skills/pair-protocol/`)。
   如果你的工具不自动激活技能,直接读
   `.agents/skills/pair-protocol/SKILL.md` 并严格遵守。
2. 运行 `PAIR_ROLE=<你的角色> python3 .pair/enforcer.py status`,
   确认你的角色和当前回合。

**本轮两条特殊约定,和默认用法不同:**

- **执行器是 `.pair/enforcer.py`,不是 skill 里的 `pair.py`。** 本轮的工作项
  要改 `pair.py` 的 `cmd_status`,而 `status` 是每回合第一条命令 —— 拿正在
  被编辑的脚本当裁判,改坏一次就再也起不来,也分不清是协议在拦你还是你把
  协议拆了。`.pair/enforcer.py` 是钉住的副本,在冻结路径下,谁都改不了。
- **每条协议命令都要带 `PAIR_ROLE=` 前缀。** 这个仓库没有远端,分离工作
  副本那条路走不通,两个 agent 共用同一个目录,所以角色不能靠
  `.pair/whoami`(一个文件只能说一个角色)。人类会在你的第一条消息里告诉你
  是 `tester` 还是 `dev`,**从头到尾不要换**。

在这两步完成之前,**不要读代码、不要修改任何文件**。

你不是单独在这个项目上工作。另一个 agent 正在负责你不负责的那一半,
擅自动手会破坏它的工作。
<!-- pair-protocol:end -->
