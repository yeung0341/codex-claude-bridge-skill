# Codex Claude Bridge Skill

[![test](https://github.com/yeung0341/codex-claude-bridge-skill/actions/workflows/test.yml/badge.svg)](https://github.com/yeung0341/codex-claude-bridge-skill/actions/workflows/test.yml)

Use Claude Code as an on-demand second opinion inside Codex.

This project packages a small Codex skill plus an MCP bridge server. When you ask for the `claude` skill, Codex can send the current request and relevant Codex thread history to Claude Code, then execute locally based on Claude's recommendation.

## Why

- Consult Claude only when you ask for it.
- Keep Codex as the executor and Claude as the reviewer or decision partner.
- Reuse the same mapped Claude session per Codex thread.
- Avoid sending obvious API keys and bearer tokens by redacting common secret patterns.
- Fall back to a local CLI path when a Codex session has not exposed the MCP tool.

## Install

Prerequisites:

- Codex desktop or CLI with MCP support.
- Claude Code CLI installed and authenticated.
- Python 3.10 or newer.

Run:

```bash
git clone https://github.com/yeung0341/codex-claude-bridge-skill.git
cd codex-claude-bridge-skill
bash install.sh
```

Restart Codex after installation so the new skill and MCP server are loaded.

## Usage

In Codex:

```text
$claude review this implementation plan and tell me what to do next
```

or:

```text
Use the claude skill to inspect this error, then follow Claude's recommendation.
```

If the MCP tool is not exposed in an older Codex session, the skill includes a CLI fallback:

```bash
printf '%s' 'Review this request' | \
  python3 ~/.codex/claude-bridge/server.py --self-test --thread-id manual-claude-skill --prompt-stdin --mode final
```

## What Gets Installed

- `~/.agents/skills/claude/SKILL.md`
- `~/.agents/skills/claude/agents/openai.yaml`
- `~/.codex/claude-bridge/server.py`
- A `claude_bridge` MCP server entry in `~/.codex/config.toml`

No API keys are stored by this project. Claude authentication stays with your existing Claude Code CLI setup.

## Verify

```bash
python3 ~/.codex/claude-bridge/server.py --self-test \
  --thread-id install-check \
  --prompt "Reply with: bridge ok" \
  --mode final \
  --no-history
```

You should receive a JSON response with `"ok": true`.

## Repository Topics

Recommended GitHub topics:

```text
codex
claude
claude-code
mcp
skill
ai-agents
developer-tools
```

## Security

The bridge redacts common `sk-*`, `tp-*`, and `Bearer ...` token patterns before sending prompts to Claude. This is a safety net, not a replacement for normal secret hygiene. Do not intentionally paste credentials into prompts.

## License

MIT
