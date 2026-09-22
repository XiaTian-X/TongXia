<!-- pair-protocol:begin -->
@AGENTS.md

## Claude Code 专用

- `pair-protocol` 技能已通过 `.claude/skills/pair-protocol` 软链接接入,
  也可以直接 `/pair-protocol` 调用。
- 一个角色的回合由这个角色自己的会话从头跑到尾(`status`、`handoff` 都是),
  不要转手给别的 agent 或会话去跑 —— 回合状态在 `.pair/state.json`,
  转手之后谁做的、做到哪一步就对不上了。**你本身就是这个角色唯一的会话时
  (不论你是怎么被启动的,包括被派出来的 subagent),这条不针对你。**
- 用 `.pair/enforcer.py`(钉住的副本),不是 skill 里的 `pair.py`;
  副本必须逐字节等于正本(`claim` 校验、`DONE` 自动重钉),细节见 AGENTS.md;
  每条命令带 `PAIR_ROLE=` 前缀。理由见 AGENTS.md。
<!-- pair-protocol:end -->
