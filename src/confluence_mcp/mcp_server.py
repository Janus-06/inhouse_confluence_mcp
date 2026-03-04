from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from .tools import ToolRegistry


JSONRPC_VERSION = "2.0"


@dataclass
class McpServer:
    registry: ToolRegistry

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            if "id" not in message:
                self._handle_notification(message)
                continue
            response = self._handle_request(message)
            self._write_message(response)

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method == "notifications/initialized":
            return

    def _handle_request(self, message: dict[str, Any]) -> dict[str, Any]:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "inhouse-confluence-mcp", "version": "0.1.0"},
                }
                return self._result(request_id, result)

            if method == "ping":
                return self._result(request_id, {})

            if method == "tools/list":
                result = {"tools": self.registry.list_tools()}
                return self._result(request_id, result)

            if method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments") or {}
                payload = self.registry.call(tool_name, arguments)
                result = {
                    "isError": bool(payload.get("isError", False)),
                    "structuredContent": payload,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ],
                }
                return self._result(request_id, result)

            return self._error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # pragma: no cover
            return self._error(request_id, -32000, str(exc))

    def _result(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _read_message(self) -> dict[str, Any] | None:
        content_length = None
        while True:
            line = sys.stdin.buffer.readline()
            if line == b"":
                return None
            if line in (b"\r\n", b"\n"):
                break
            if b":" not in line:
                continue
            key, value = line.decode("utf-8", errors="replace").split(":", 1)
            if key.lower().strip() == "content-length":
                content_length = int(value.strip())

        if content_length is None:
            return None

        body = sys.stdin.buffer.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def _write_message(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
