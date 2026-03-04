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

READ_TOOLS = {
    "confluence_search_cql",
    "confluence_get_content",
    "confluence_get_labels",
    "confluence_get_children",
    "confluence_get_attachments",
    "confluence_get_comments",
    "confluence_scan_content",
}
WRITE_TOOLS = {
    "confluence_create_page",
    "confluence_update_page",
    "confluence_add_label",
    "confluence_add_comment",
}
SPACE_TOOLS = {"confluence_list_spaces"}
LIKES_TOOL = {"confluence_get_likes"}


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
            continue
        key, value = striped.split("=", 1)
        key = key.strip().lstrip("\ufeff")
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


def _probe_ok(err: ConfluenceError) -> bool:
    # 404 means endpoint is reachable but the resource may not exist.
    if err.status_code == 404:
        return True
    return False


def bootstrap_enabled_tools(settings: Settings, client: ConfluenceClient, audit: AuditLogger) -> set[str]:
    enabled = set(READ_TOOLS | WRITE_TOOLS | SPACE_TOOLS)
    if settings.experimental_likes:
        enabled |= LIKES_TOOL

    if not _parse_bool_env("TOOL_PROBE_ON_STARTUP", True):
        if not settings.experimental_likes:
            enabled -= LIKES_TOOL
        if not settings.write_enabled:
            enabled -= WRITE_TOOLS
        return enabled

    probe_space_api = _parse_bool_env("SPACE_PROBE_ON_STARTUP", True)

    # space_api_ok: /rest/api/space availability (controls list_spaces tool)
    # declared_space_ok: whether user-declared ALLOWED_SPACES should be trusted
    space_api_ok = False
    declared_space_ok = bool(settings.allowed_spaces)
    read_ok = False
    likes_ok = False

    if probe_space_api:
        try:
            client.list_spaces(limit=1, start=0)
            space_api_ok = True
        except ConfluenceError as exc:
            space_api_ok = _probe_ok(exc)
    else:
        # When disabled, trust ALLOWED_SPACES for policy but keep list_spaces hidden.
        declared_space_ok = bool(settings.allowed_spaces)

    try:
        client.search_cql(cql="type=page order by id asc", limit=1)
        read_ok = True
    except ConfluenceError as exc:
        read_ok = _probe_ok(exc)

    if settings.experimental_likes:
        try:
            client.get_likes(content_id="0")
            likes_ok = True
        except ConfluenceError as exc:
            likes_ok = _probe_ok(exc)

    # list_spaces depends on /rest/api/space
    if not space_api_ok:
        enabled -= SPACE_TOOLS

    # Content read/write tools depend on /rest/api/content
    if not read_ok:
        enabled -= READ_TOOLS
        enabled -= WRITE_TOOLS

    if not likes_ok:
        enabled -= LIKES_TOOL
    if not settings.write_enabled:
        enabled -= WRITE_TOOLS

    audit.log(
        {
            "tool": "bootstrap_tool_probe",
            "status": "ok",
            "spaceApi": space_api_ok,
            "spaceProbeEnabled": probe_space_api,
            "declaredSpaceTrusted": declared_space_ok,
            "readApi": read_ok,
            "likesApi": likes_ok if settings.experimental_likes else None,
            "enabledTools": sorted(enabled),
        }
    )

    print(
        f"[confluence-mcp] tool probe spaceApi={space_api_ok} read={read_ok} "
        f"likes={likes_ok if settings.experimental_likes else 'off'} "
        f"spaceProbeEnabled={probe_space_api} declaredSpaceTrusted={declared_space_ok}; "
        f"enabled={len(enabled)}",
        file=sys.stderr,
    )
    return enabled


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    audit = AuditLogger(settings.audit_log_path)
    client = ConfluenceClient(settings)
    settings = bootstrap_allowed_spaces(settings, client, audit)
    policy = PolicyEngine(settings)
    enabled_tools = bootstrap_enabled_tools(settings, client, audit)
    registry = ToolRegistry(
        settings=settings,
        client=client,
        policy=policy,
        audit=audit,
        enabled_tools=enabled_tools,
    )
    server = McpServer(registry)
    server.run()


if __name__ == "__main__":
    main()
