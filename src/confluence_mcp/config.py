from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value.strip())


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    base_url: str
    context_path: str
    auth_mode: str
    pat: str
    username: str
    password: str

    write_enabled: bool
    experimental_likes: bool

    default_limit: int
    max_limit: int
    max_body_chars: int
    request_timeout_ms: int
    max_retries: int
    auto_discover_spaces: bool
    discover_spaces_limit: int

    allowed_spaces: set[str]
    denied_spaces: set[str]
    allowed_expands: set[str]
    allowed_attachment_mime: set[str]
    max_attachment_bytes: int
    max_attachment_count: int

    audit_log_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.getenv("CONFLUENCE_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise ValueError("CONFLUENCE_BASE_URL is required")

        context_path = os.getenv("CONFLUENCE_CONTEXT_PATH", "").strip().strip("/")
        auth_mode = os.getenv("CONFLUENCE_AUTH_MODE", "pat").strip().lower()

        return cls(
            base_url=base_url,
            context_path=context_path,
            auth_mode=auth_mode,
            pat=os.getenv("CONFLUENCE_PAT", "").strip(),
            username=os.getenv("CONFLUENCE_USERNAME", "").strip(),
            password=os.getenv("CONFLUENCE_PASSWORD", "").strip(),
            write_enabled=_parse_bool(os.getenv("WRITE_ENABLED"), False),
            experimental_likes=_parse_bool(os.getenv("EXPERIMENTAL_LIKES"), False),
            default_limit=_parse_int(os.getenv("DEFAULT_LIMIT"), 25),
            max_limit=_parse_int(os.getenv("MAX_LIMIT"), 100),
            max_body_chars=_parse_int(os.getenv("MAX_BODY_CHARS"), 20000),
            request_timeout_ms=_parse_int(os.getenv("REQUEST_TIMEOUT_MS"), 10000),
            max_retries=_parse_int(os.getenv("MAX_RETRIES"), 2),
            auto_discover_spaces=_parse_bool(os.getenv("AUTO_DISCOVER_SPACES"), True),
            discover_spaces_limit=_parse_int(os.getenv("DISCOVER_SPACES_LIMIT"), 200),
            allowed_spaces=set(_parse_csv(os.getenv("ALLOWED_SPACES"))),
            denied_spaces=set(_parse_csv(os.getenv("DENIED_SPACES"))),
            allowed_expands=set(_parse_csv(os.getenv("ALLOWED_EXPANDS"))),
            allowed_attachment_mime=set(_parse_csv(os.getenv("ALLOWED_ATTACHMENT_MIME"))),
            max_attachment_bytes=_parse_int(os.getenv("MAX_ATTACHMENT_BYTES"), 10 * 1024 * 1024),
            max_attachment_count=_parse_int(os.getenv("MAX_ATTACHMENT_COUNT"), 20),
            audit_log_path=Path(os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl")),
        )
