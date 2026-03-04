import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from confluence_mcp.config import Settings
from confluence_mcp.policy import PolicyEngine, PolicyError


class PolicyTests(unittest.TestCase):
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
            allowed_spaces={"DEVOPS"},
            denied_spaces={"HR"},
            allowed_expands={"body.storage", "version"},
            allowed_attachment_mime=set(),
            max_attachment_bytes=1024,
            max_attachment_count=10,
            audit_log_path=Path("logs/test_audit.jsonl"),
        )

    def test_limit_clamped(self):
        policy = PolicyEngine(self._settings())
        self.assertEqual(policy.enforce_limit(1000), 100)

    def test_expand_denied(self):
        policy = PolicyEngine(self._settings())
        with self.assertRaises(PolicyError):
            policy.enforce_expand(["body.view"])

    def test_space_denied(self):
        policy = PolicyEngine(self._settings())
        with self.assertRaises(PolicyError):
            policy.enforce_space_access(["HR"])

    def test_write_disabled(self):
        policy = PolicyEngine(self._settings())
        with self.assertRaises(PolicyError):
            policy.enforce_write_enabled()


if __name__ == "__main__":
    unittest.main()
