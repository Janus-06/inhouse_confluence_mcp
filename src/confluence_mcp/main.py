from __future__ import annotations

import os
from pathlib import Path

from .audit import AuditLogger
from .config import Settings
from .confluence_client import ConfluenceClient
from .mcp_server import McpServer
from .policy import PolicyEngine
from .tools import ToolRegistry


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
            continue
        key, value = striped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    audit = AuditLogger(settings.audit_log_path)
    client = ConfluenceClient(settings)
    policy = PolicyEngine(settings)
    registry = ToolRegistry(settings=settings, client=client, policy=policy, audit=audit)
    server = McpServer(registry)
    server.run()


if __name__ == "__main__":
    main()
