# Troubleshooting

## Codex sees the skill but not the MCP tool

Restart Codex after running `./install.sh`. MCP tools are commonly loaded when a Codex session starts, so old sessions may not expose `mcp__claude_bridge.ask_claude`.

The skill includes a fallback:

```bash
printf '%s' 'Test Claude bridge' | \
  python3 ~/.codex/claude-bridge/server.py --self-test --thread-id manual-test --prompt-stdin --mode final --no-history
```

## Claude CLI is not found

Set `CLAUDE_BRIDGE_CLAUDE_BIN` in the MCP config entry, or rerun the installer after making `claude` available on your shell `PATH`.

## Claude resume fails

The bridge retries without resuming when a mapped Claude session id fails. You can also reset the mapped thread with `mcp__claude_bridge.reset_claude_thread`.

## Codex history is missing

History sync depends on Codex session files under `~/.codex/sessions` and `~/.codex/archived_sessions`. If those files are unavailable, the bridge still sends the current prompt.
