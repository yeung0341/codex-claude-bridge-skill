#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SKILL_HOME="${CODEX_SKILL_HOME:-$HOME/.agents/skills}"

rm -rf "$SKILL_HOME/claude"
rm -rf "$CODEX_HOME/claude-bridge"

echo "Removed claude skill and bridge files."
echo "Remove the [mcp_servers.claude_bridge] block from $CODEX_HOME/config.toml if you want to fully remove the MCP entry."
