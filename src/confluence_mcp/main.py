from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

from .audit import AuditLogger
from .config import Settings
from .confluence_client import ConfluenceClient, ConfluenceError
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


def bootstrap_allowed_spaces(settings: Settings, client: ConfluenceClient, audit: AuditLogger) -> Settings:
    if settings.allowed_spaces:
        return settings
    if not settings.auto_discover_spaces:
        return settings

    try:
        discovered = set(client.list_all_space_keys())
    except ConfluenceError as exc:
        print(f"[confluence-mcp] failed to auto-discover spaces: {exc}", file=sys.stderr)
        return settings

    discovered = {s for s in discovered if s not in settings.denied_spaces}
    if not discovered:
        print("[confluence-mcp] auto-discovered 0 allowed spaces; keeping current policy", file=sys.stderr)
        return settings

    sorted_spaces = sorted(discovered)
    print(f"[confluence-mcp] auto-discovered {len(sorted_spaces)} spaces", file=sys.stderr)
    audit.log(
        {
            "tool": "bootstrap_spaces",
            "status": "ok",
            "count": len(sorted_spaces),
            "spaces": sorted_spaces,
        }
    )
    return replace(settings, allowed_spaces=set(sorted_spaces))


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    audit = AuditLogger(settings.audit_log_path)
    client = ConfluenceClient(settings)
    settings = bootstrap_allowed_spaces(settings, client, audit)
    policy = PolicyEngine(settings)
    registry = ToolRegistry(settings=settings, client=client, policy=policy, audit=audit)
    server = McpServer(registry)
    server.run()


if __name__ == "__main__":
    main()
