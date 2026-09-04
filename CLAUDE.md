<!-- pair-protocol:begin -->
@AGENTS.md

## Claude Code 专用

- `pair-protocol` 技能已通过 `.claude/skills/pair-protocol` 软链接接入,
  也可以直接 `/pair-protocol` 调用。
- 不要用 subagent 代跑结对回合。回合状态在 `.pair/state.json`,
  必须由主会话执行 `status` 和 `handoff`。
- 本轮用 `.pair/enforcer.py`(钉住的副本),不是 skill 里的 `pair.py`;
  每条命令带 `PAIR_ROLE=` 前缀。理由见 AGENTS.md。
<!-- pair-protocol:end -->
