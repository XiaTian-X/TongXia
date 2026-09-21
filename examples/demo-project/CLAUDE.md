<!-- pair-protocol:begin -->
@AGENTS.md

## Claude Code 专用

- `pair-protocol` 技能已通过 `.claude/skills/pair-protocol` 软链接接入,
  也可以直接 `/pair-protocol` 调用。
- 不要用 subagent 代跑结对回合。回合状态在 `.pair/state.json`,
  必须由主会话执行 `status` 和 `handoff`。
<!-- pair-protocol:end -->
