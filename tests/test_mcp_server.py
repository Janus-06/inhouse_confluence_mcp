import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from confluence_mcp.mcp_server import McpServer


class StubRegistry:
    def __init__(self) -> None:
        self.calls = []

    def has_tool(self, name: str) -> bool:
        return name == "ok_tool"

    def list_tools(self):
        return [{"name": "ok_tool", "description": "", "inputSchema": {"type": "object"}}]

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name != "ok_tool":
            raise KeyError("unknown tool")
        if "bad" in arguments:
            raise ValueError("bad argument")
        return {"isError": False, "ok": True}


class McpServerTests(unittest.TestCase):
    def test_tools_list_rejected_before_initialize(self):
        server = McpServer(registry=StubRegistry())
        resp = server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        self.assertEqual(resp["error"]["code"], -32002)

    def test_unknown_tool_returns_jsonrpc_error(self):
        server = McpServer(registry=StubRegistry(), initialized=True)
        resp = server._handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "nope", "arguments": {}},
            }
        )
        self.assertEqual(resp["error"]["code"], -32602)

    def test_tools_call_invalid_arguments_type(self):
        server = McpServer(registry=StubRegistry(), initialized=True)
        resp = server._handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ok_tool", "arguments": "bad"},
            }
        )
        self.assertEqual(resp["error"]["code"], -32602)

    def test_batch_mixed_requests(self):
        server = McpServer(registry=StubRegistry())
        response = server._dispatch_message(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            ]
        )
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 2)
        self.assertIn("result", response[1])


if __name__ == "__main__":
    unittest.main()
