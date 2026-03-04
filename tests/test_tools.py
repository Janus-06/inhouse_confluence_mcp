import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from confluence_mcp.audit import AuditLogger
from confluence_mcp.config import Settings
from confluence_mcp.policy import PolicyEngine
from confluence_mcp.tools import ToolRegistry


class DummyClient:
    pass


class ToolRegistryTests(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            base_url="https://confluence.example.com",
            context_path="",
            auth_mode="pat",
            pat="token",
            username="",
            password="",
            write_enabled=False,
            experimental_likes=False,
            default_limit=25,
            max_limit=100,
            max_body_chars=1000,
            request_timeout_ms=10000,
            max_retries=1,
            auto_discover_spaces=True,
            discover_spaces_limit=200,
            allowed_spaces={"DEVOPS"},
            denied_spaces={"HR"},
            allowed_expands={"body.storage", "version"},
            allowed_attachment_mime=set(),
            max_attachment_bytes=1024,
            max_attachment_count=10,
            audit_log_path=Path("logs/test_audit.jsonl"),
        )

    def test_list_tools_contains_core_tools(self):
        settings = self._settings()
        registry = ToolRegistry(
            settings=settings,
            client=DummyClient(),
            policy=PolicyEngine(settings),
            audit=AuditLogger(settings.audit_log_path),
        )
        names = [t["name"] for t in registry.list_tools()]
        self.assertIn("confluence_list_spaces", names)
        self.assertIn("confluence_search_cql", names)
        self.assertIn("confluence_get_content", names)
        self.assertNotIn("confluence_get_likes", names)


if __name__ == "__main__":
    unittest.main()
