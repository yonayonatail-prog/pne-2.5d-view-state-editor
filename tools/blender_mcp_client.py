"""Minimal client for Blender's official local MCP bridge.

The Blender add-on accepts one null-terminated JSON request per TCP
connection and returns one null-terminated JSON response.
"""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=9876, type=int)
    parser.add_argument("--code-file", type=Path)
    parser.add_argument("--code")
    parser.add_argument("--timeout", default=120.0, type=float)
    parser.add_argument("--strict-json", action="store_true")
    args = parser.parse_args()

    if (args.code_file is None) == (args.code is None):
        parser.error("provide exactly one of --code-file or --code")

    code = (
        args.code_file.read_text(encoding="utf-8")
        if args.code_file is not None
        else args.code
    )
    payload = json.dumps(
        {"type": "execute", "code": code, "strict_json": args.strict_json},
        ensure_ascii=False,
    ).encode("utf-8") + b"\0"

    chunks: list[bytes] = []
    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        sock.sendall(payload)
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            if b"\0" in chunk:
                chunks.append(chunk.split(b"\0", 1)[0])
                break
            chunks.append(chunk)

    response = json.loads(b"".join(chunks).decode("utf-8"))
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
