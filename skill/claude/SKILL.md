---
name: claude
description: Use when the user explicitly asks to consult Claude, says to use the claude skill, wants Claude's second opinion, or wants Claude to make the final judgment while Codex executes locally.
---

# Claude

Use this skill only on explicit request.

## Workflow

1. Gather any local context that is already cheap and relevant.
2. Prefer `mcp__claude_bridge.ask_claude` when it is available:
   - `prompt`: the user's current request
   - `mode`: `final`
   - `include_codex_history`: `true`
   - `codex_execution_context`: a short summary of relevant local findings when useful
3. If the MCP tool is not exposed in the current session, use the CLI fallback:

```bash
python3 ~/.codex/claude-bridge/server.py --self-test --thread-id manual-claude-skill --prompt-stdin --mode final
```

Pass the user's request on stdin. Use a stable thread id when one is known.

4. Treat Claude's answer as the recommendation to execute unless it conflicts with an explicit user instruction or is impossible in the current environment.
5. Execute locally in Codex and report the result.

## Notes

- The bridge preserves mapped Claude conversation history for each Codex thread when a thread id is available.
- If the user asks for a clean Claude conversation, call `mcp__claude_bridge.reset_claude_thread` first.
- If Claude is unavailable, say that Claude was unavailable for this turn and continue normally.
