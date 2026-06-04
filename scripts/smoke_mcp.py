#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "claude_bridge" / "server.py"


def main() -> int:
    proc = subprocess.Popen(
        ["python3", str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def send(message: dict[str, object]) -> dict[str, object]:
        assert proc.stdin is not None
        assert proc.stdout is not None
        raw = json.dumps(message).encode("utf-8")
        proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8"))
        proc.stdin.write(raw)
        proc.stdin.flush()

        header = b""
        while b"\r\n\r\n" not in header:
            chunk = proc.stdout.read(1)
            if not chunk:
                raise RuntimeError("MCP server returned no response")
            header += chunk
        head = header.split(b"\r\n\r\n", 1)[0].decode("utf-8")
        length = 0
        for line in head.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
        body = proc.stdout.read(length)
        return json.loads(body.decode("utf-8"))

    send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "1"},
            },
        }
    )
    response = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    expected = {"ask_claude", "reset_claude_thread"}
    if names != expected:
        raise RuntimeError(f"Unexpected tools: {sorted(names)}")
    proc.terminate()
    proc.wait(timeout=5)
    print("MCP smoke test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
