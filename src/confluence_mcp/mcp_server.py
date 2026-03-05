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
    initialized: bool = False

    def run(self) -> None:
        while True:
            try:
                message = self._read_message()
            except json.JSONDecodeError as exc:
                self._write_message(self._error(None, -32700, f"Parse error: {exc}"))
                continue

            if message is None:
                return

            response = self._dispatch_message(message)
            if response is not None:
                self._write_message(response)

    def _dispatch_message(self, message: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
        if isinstance(message, list):
            if not message:
                return self._error(None, -32600, "Invalid Request")
            responses: list[dict[str, Any]] = []
            for item in message:
                if not isinstance(item, dict):
                    responses.append(self._error(None, -32600, "Invalid Request"))
                    continue
                if "id" in item:
                    responses.append(self._handle_request(item))
                else:
                    self._handle_notification(item)
            return responses or None

        if not isinstance(message, dict):
            return self._error(None, -32600, "Invalid Request")

        if "id" not in message:
            self._handle_notification(message)
            return None

        return self._handle_request(message)

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method == "notifications/initialized":
            self.initialized = True

    def _handle_request(self, message: dict[str, Any]) -> dict[str, Any]:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if not isinstance(method, str):
            return self._error(request_id, -32600, "Invalid Request: method must be a string")

        if method == "initialize":
            self.initialized = True
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "inhouse-confluence-mcp", "version": "0.1.0"},
            }
            return self._result(request_id, result)

        if method in {"tools/list", "tools/call"} and not self.initialized:
            return self._error(request_id, -32002, "Server not initialized")

        if method == "ping":
            return self._result(request_id, {})

        if method == "tools/list":
            result = {"tools": self.registry.list_tools()}
            return self._result(request_id, result)

        if method == "tools/call":
            if not isinstance(params, dict):
                return self._error(request_id, -32602, "Invalid params: params must be an object")

            tool_name = params.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                return self._error(request_id, -32602, "Invalid params: name must be a non-empty string")

            if not self._registry_has_tool(tool_name):
                return self._error(request_id, -32602, f"Unknown tool: {tool_name}")

            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                return self._error(request_id, -32602, "Invalid params: arguments must be an object")

            try:
                payload = self.registry.call(tool_name, arguments)
            except (KeyError, ValueError, TypeError) as exc:
                return self._error(request_id, -32602, f"Invalid params: {exc}")
            except Exception as exc:  # pragma: no cover
                return self._error(request_id, -32000, str(exc))

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

    def _registry_has_tool(self, name: str) -> bool:
        has_tool = getattr(self.registry, "has_tool", None)
        if callable(has_tool):
            return bool(has_tool(name))
        return any(t.get("name") == name for t in self.registry.list_tools())

    def _result(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _read_message(self) -> dict[str, Any] | list[Any] | None:
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

    def _write_message(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
