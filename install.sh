#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SKILL_HOME="${CODEX_SKILL_HOME:-$HOME/.agents/skills}"
BRIDGE_HOME="$CODEX_HOME/claude-bridge"
CONFIG_FILE="$CODEX_HOME/config.toml"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

CLAUDE_BIN_PATH="${CLAUDE_BRIDGE_CLAUDE_BIN:-}"
if [ -z "$CLAUDE_BIN_PATH" ]; then
  CLAUDE_BIN_PATH="$(command -v claude || true)"
fi
if [ -z "$CLAUDE_BIN_PATH" ]; then
  CLAUDE_BIN_PATH="claude"
fi

mkdir -p "$BRIDGE_HOME" "$SKILL_HOME/claude/agents" "$CODEX_HOME"
cp "$ROOT_DIR/mcp/claude_bridge/server.py" "$BRIDGE_HOME/server.py"
cp "$ROOT_DIR/skill/claude/SKILL.md" "$SKILL_HOME/claude/SKILL.md"
cp "$ROOT_DIR/skill/claude/agents/openai.yaml" "$SKILL_HOME/claude/agents/openai.yaml"
chmod 700 "$BRIDGE_HOME/server.py"

touch "$CONFIG_FILE"

if grep -q '^\[mcp_servers\.claude_bridge\]' "$CONFIG_FILE"; then
  echo "claude_bridge MCP entry already exists in $CONFIG_FILE"
else
  cat >>"$CONFIG_FILE" <<EOF

[mcp_servers.claude_bridge]
command = "python3"
args = ["$BRIDGE_HOME/server.py"]
startup_timeout_sec = 120

[mcp_servers.claude_bridge.env]
CODEX_HOME = "$CODEX_HOME"
CLAUDE_BRIDGE_CLAUDE_BIN = "$CLAUDE_BIN_PATH"
EOF
  echo "Added claude_bridge MCP entry to $CONFIG_FILE"
fi

python3 -m py_compile "$BRIDGE_HOME/server.py"

echo "Installed claude skill to $SKILL_HOME/claude"
echo "Installed bridge server to $BRIDGE_HOME/server.py"
echo "Restart Codex to load the new skill and MCP server."
