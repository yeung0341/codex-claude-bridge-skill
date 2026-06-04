#!/usr/bin/env python3

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
BRIDGE_HOME = CODEX_HOME / "claude-bridge"
STATE_PATH = BRIDGE_HOME / "state.json"
DEFAULT_CLAUDE_BIN = os.environ.get("CLAUDE_BRIDGE_CLAUDE_BIN") or shutil.which("claude") or "claude"
SERVER_NAME = "claude-bridge"
SERVER_VERSION = "0.1.0"

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9._-]{12,}\b"),
    re.compile(r"\btp-[A-Za-z0-9._-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b", re.IGNORECASE),
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(0).split("-")[0] + "-REDACTED", redacted)
    return redacted


def clip_text(text: str, max_chars: int = 2400) -> str:
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 15].rstrip() + "\n...[truncated]"


def extract_content_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"output_text", "input_text", "text"}:
            text = item.get("text") or item.get("output_text") or ""
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts).strip()


def find_thread_session_file(thread_id: str) -> str | None:
    patterns = [
        str(CODEX_HOME / "sessions" / "**" / f"*{thread_id}.jsonl"),
        str(CODEX_HOME / "archived_sessions" / "**" / f"*{thread_id}.jsonl"),
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern, recursive=True))
    if not candidates:
        return None
    candidates.sort(key=lambda path: Path(path).stat().st_mtime, reverse=True)
    return candidates[0]


def extract_codex_messages(thread_id: str) -> tuple[list[dict[str, str]], str | None]:
    session_file = find_thread_session_file(thread_id)
    if session_file is None:
        return [], None

    messages: list[dict[str, str]] = []
    with open(session_file, "r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "event_msg":
                payload = event.get("payload", {})
                if payload.get("type") == "user_message":
                    text = payload.get("message", "")
                    if isinstance(text, str) and text.strip():
                        messages.append({"role": "user", "text": text.strip()})
            elif event.get("type") == "response_item":
                payload = event.get("payload", {})
                if (
                    payload.get("type") == "message"
                    and payload.get("role") == "assistant"
                    and payload.get("phase") == "final_answer"
                ):
                    text = extract_content_text(payload.get("content"))
                    if text:
                        messages.append({"role": "assistant", "text": text})
    return messages, session_file


def save_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    BRIDGE_HOME.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=path.suffix, dir=str(BRIDGE_HOME))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"threads": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"threads": {}}
    if not isinstance(data, dict):
        return {"threads": {}}
    data.setdefault("threads", {})
    return data


def save_state(state: dict[str, Any]) -> None:
    save_json_atomic(STATE_PATH, state)


def compress_history(messages: list[dict[str, str]], max_history_messages: int) -> tuple[list[dict[str, str]], int]:
    if max_history_messages <= 0 or len(messages) <= max_history_messages:
        return messages, 0
    if max_history_messages <= 2:
        kept = messages[-max_history_messages:]
        return kept, len(messages) - len(kept)
    kept = messages[:2] + messages[-(max_history_messages - 2) :]
    return kept, len(messages) - len(kept)


def format_transcript(messages: list[dict[str, str]]) -> str:
    chunks: list[str] = []
    for item in messages:
        role = "USER" if item["role"] == "user" else "CODEX_FINAL"
        chunks.append(f"{role}:\n{clip_text(redact_secrets(item['text']))}")
    return "\n\n".join(chunks).strip()


def parse_claude_json(output: str) -> dict[str, Any]:
    text = output.strip()
    if not text:
        raise ValueError("Claude returned empty output")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Claude output was not valid JSON")


def run_claude(prompt: str, claude_session_id: str | None) -> dict[str, Any]:
    cmd = [
        DEFAULT_CLAUDE_BIN,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--tools",
        "",
    ]
    if claude_session_id:
        cmd[1:1] = ["-r", claude_session_id]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode == 0:
        return parse_claude_json(completed.stdout)

    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()
    raise RuntimeError(
        f"Claude CLI failed with exit code {completed.returncode}. "
        f"stdout={stdout[:600]} stderr={stderr[:600]}"
    )


def build_bridge_prompt(
    *,
    thread_id: str | None,
    mode: str,
    prompt: str,
    codex_execution_context: str,
    history_excerpt: list[dict[str, str]],
    omitted_history_count: int,
    unsynced_excerpt: list[dict[str, str]],
) -> str:
    sections = [
        "You are Claude Code acting as the decision authority for a Codex-to-Claude bridge.",
        "Codex will execute locally; your answer should tell Codex what conclusion to follow and what to do next.",
        "Do not ask to run tools or inspect files yourself. Assume Codex will perform any execution.",
        f"Bridge mode: {mode}.",
    ]

    if thread_id:
        sections.append(f"Codex thread id: {thread_id}")

    if history_excerpt:
        history_block = format_transcript(history_excerpt)
        if omitted_history_count > 0:
            history_block = f"[Omitted {omitted_history_count} older Codex messages]\n\n{history_block}"
        sections.append("Relevant prior Codex thread history:\n" + history_block)

    if unsynced_excerpt:
        sections.append("Recent Codex thread updates since the last Claude sync:\n" + format_transcript(unsynced_excerpt))

    if codex_execution_context.strip():
        sections.append("Codex execution context:\n" + clip_text(redact_secrets(codex_execution_context), 3200))

    sections.append("Current Codex request:\n" + clip_text(redact_secrets(prompt), 3200))
    sections.append(
        "Respond with exactly these sections:\n"
        "Decision:\n"
        "Reasoning:\n"
        "Execution:\n"
        "Checks:\n"
        "Keep it decisive and concrete."
    )
    return "\n\n".join(sections).strip()


def extract_thread_id(meta: Any, arguments: dict[str, Any]) -> str | None:
    if isinstance(arguments.get("codex_thread_id"), str) and arguments["codex_thread_id"].strip():
        return arguments["codex_thread_id"].strip()
    if not isinstance(meta, dict):
        return None
    if isinstance(meta.get("threadId"), str) and meta["threadId"].strip():
        return meta["threadId"].strip()
    turn_meta = meta.get("x-codex-turn-metadata", {})
    if isinstance(turn_meta, dict):
        if isinstance(turn_meta.get("thread_id"), str) and turn_meta["thread_id"].strip():
            return turn_meta["thread_id"].strip()
        if isinstance(turn_meta.get("session_id"), str) and turn_meta["session_id"].strip():
            return turn_meta["session_id"].strip()
    return None


def ask_claude(arguments: dict[str, Any], meta: dict[str, Any] | None) -> dict[str, Any]:
    prompt = arguments.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("`prompt` is required")

    mode = arguments.get("mode", "final")
    if mode not in {"final", "advice", "review"}:
        mode = "final"

    include_codex_history = bool(arguments.get("include_codex_history", True))
    force_new = bool(arguments.get("force_new_claude_session", False))
    max_history_messages = int(arguments.get("max_history_messages", 12) or 12)
    max_history_messages = max(0, min(max_history_messages, 80))
    codex_execution_context = arguments.get("codex_execution_context", "")
    if not isinstance(codex_execution_context, str):
        codex_execution_context = ""

    thread_id = extract_thread_id(meta, arguments)
    state = load_state()
    record = state.setdefault("threads", {}).get(thread_id or "", {}) if thread_id else {}

    all_messages: list[dict[str, str]] = []
    session_file = None
    if include_codex_history and thread_id:
        all_messages, session_file = extract_codex_messages(thread_id)

    synced_count = int(record.get("synced_message_count", 0) or 0) if thread_id else 0
    synced_count = min(synced_count, len(all_messages))
    unsynced = all_messages[synced_count:] if include_codex_history else []

    normalized_prompt = prompt.strip()
    if unsynced and unsynced[-1]["role"] == "user" and unsynced[-1]["text"].strip() == normalized_prompt:
        unsynced = unsynced[:-1]

    if thread_id and not record:
        prior_history = all_messages[:-1] if all_messages and all_messages[-1]["role"] == "user" else all_messages
        history_excerpt, omitted_history_count = compress_history(prior_history, max_history_messages)
        unsynced = []
    else:
        history_excerpt, omitted_history_count = [], 0
        if include_codex_history and unsynced:
            history_excerpt, omitted_history_count = compress_history(unsynced, max_history_messages)
            unsynced = []

    bridge_prompt = build_bridge_prompt(
        thread_id=thread_id,
        mode=mode,
        prompt=prompt,
        codex_execution_context=codex_execution_context,
        history_excerpt=history_excerpt,
        omitted_history_count=omitted_history_count,
        unsynced_excerpt=unsynced,
    )

    mapped_claude_session = None if force_new else record.get("claude_session_id")
    retry_without_resume = bool(mapped_claude_session)
    try:
        claude_result = run_claude(bridge_prompt, mapped_claude_session)
    except Exception:
        if not retry_without_resume:
            raise
        claude_result = run_claude(bridge_prompt, None)
        mapped_claude_session = None

    claude_session_id = claude_result.get("session_id")
    if thread_id and isinstance(claude_session_id, str) and claude_session_id.strip():
        state.setdefault("threads", {})[thread_id] = {
            "claude_session_id": claude_session_id.strip(),
            "session_file": session_file,
            "synced_message_count": len(all_messages),
            "last_prompt_at": now_iso(),
            "last_mode": mode,
        }
        save_state(state)

    return {
        "ok": True,
        "thread_id": thread_id,
        "claude_session_id": claude_session_id,
        "reused_claude_session": bool(mapped_claude_session),
        "session_file": session_file,
        "history_messages_seen": len(all_messages),
        "history_messages_backfilled": len(history_excerpt),
        "mode": mode,
        "decision": claude_result.get("result", ""),
        "raw": claude_result,
    }


def reset_claude_thread(arguments: dict[str, Any], meta: dict[str, Any] | None) -> dict[str, Any]:
    thread_id = extract_thread_id(meta, arguments)
    if not thread_id:
        raise ValueError("Unable to resolve Codex thread id")
    state = load_state()
    existed = thread_id in state.get("threads", {})
    if existed:
        del state["threads"][thread_id]
        save_state(state)
    return {"ok": True, "thread_id": thread_id, "reset": existed}


class StdioMCPServer:
    def __init__(self) -> None:
        self.protocol_version = "2024-11-05"

    def run(self) -> None:
        while True:
            message = self.read_message()
            if message is None:
                break
            self.handle_message(message)

    def read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in {b"\r\n", b"\n"}:
                break
            name, _, value = line.decode("utf-8").partition(":")
            headers[name.strip().lower()] = value.strip()

        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = sys.stdin.buffer.read(length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def send(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8"))
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    def respond(self, request_id: Any, result: Any) -> None:
        self.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def error(self, request_id: Any, code: int, message: str) -> None:
        self.send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params", {})
        if method == "initialize":
            requested = params.get("protocolVersion")
            if isinstance(requested, str) and requested.strip():
                self.protocol_version = requested.strip()
            self.respond(
                request_id,
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
            return
        if method == "notifications/initialized":
            return
        if method == "ping":
            self.respond(request_id, {})
            return
        if method == "tools/list":
            self.respond(
                request_id,
                {
                    "tools": [
                        {
                            "name": "ask_claude",
                            "description": "Consult Claude Code for the current Codex thread.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {"type": "string"},
                                    "mode": {"type": "string", "enum": ["final", "advice", "review"]},
                                    "include_codex_history": {"type": "boolean"},
                                    "force_new_claude_session": {"type": "boolean"},
                                    "max_history_messages": {"type": "integer"},
                                    "codex_execution_context": {"type": "string"},
                                    "codex_thread_id": {"type": "string"},
                                },
                                "required": ["prompt"],
                            },
                        },
                        {
                            "name": "reset_claude_thread",
                            "description": "Forget the mapped Claude session for the current Codex thread.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"codex_thread_id": {"type": "string"}},
                            },
                        },
                    ]
                },
            )
            return
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            meta = params.get("_meta")
            if not isinstance(arguments, dict):
                self.respond(
                    request_id,
                    {"content": [{"type": "text", "text": "Tool arguments must be an object"}], "isError": True},
                )
                return
            try:
                if tool_name == "ask_claude":
                    result = ask_claude(arguments, meta if isinstance(meta, dict) else None)
                elif tool_name == "reset_claude_thread":
                    result = reset_claude_thread(arguments, meta if isinstance(meta, dict) else None)
                else:
                    raise ValueError(f"Unknown tool: {tool_name}")
            except Exception as exc:
                self.respond(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)}],
                        "isError": True,
                    },
                )
                return

            self.respond(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            )
            return
        if request_id is not None:
            self.error(request_id, -32601, f"Method not found: {method}")


def read_prompt_from_args(args: argparse.Namespace) -> str | None:
    if args.prompt_stdin:
        return sys.stdin.read()
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as handle:
            return handle.read()
    return args.prompt


def run_self_test(args: argparse.Namespace) -> int:
    prompt = read_prompt_from_args(args)
    if not args.thread_id or not prompt:
        print("--self-test requires --thread-id and a prompt", file=sys.stderr)
        return 2
    result = ask_claude(
        {
            "prompt": prompt,
            "mode": args.mode,
            "include_codex_history": not args.no_history,
            "force_new_claude_session": args.force_new,
            "max_history_messages": args.max_history_messages,
            "codex_execution_context": args.codex_execution_context or "",
            "codex_thread_id": args.thread_id,
        },
        None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex to Claude Code bridge MCP server")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--thread-id")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--prompt-stdin", action="store_true")
    parser.add_argument("--mode", default="final")
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--force-new", action="store_true")
    parser.add_argument("--max-history-messages", type=int, default=12)
    parser.add_argument("--codex-execution-context")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test(args)

    StdioMCPServer().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
