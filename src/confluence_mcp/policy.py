from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


class PolicyError(ValueError):
    pass


@dataclass
class PolicyEngine:
    settings: Settings

    def enforce_limit(self, value: int | None) -> int:
        if value is None:
            return self.settings.default_limit
        if value <= 0:
            raise PolicyError("limit must be > 0")
        if value > self.settings.max_limit:
            return self.settings.max_limit
        return value

    def enforce_expand(self, expands: list[str] | None) -> list[str]:
        if not expands:
            return []
        if not self.settings.allowed_expands:
            return expands
        blocked = [x for x in expands if x not in self.settings.allowed_expands]
        if blocked:
            raise PolicyError(f"expand values are not allowed: {', '.join(blocked)}")
        return expands

    def enforce_space_access(self, spaces: list[str] | None) -> list[str]:
        if not spaces:
            return []
        denied = [s for s in spaces if s in self.settings.denied_spaces]
        if denied:
            raise PolicyError(f"spaces denied by policy: {', '.join(denied)}")
        if self.settings.allowed_spaces:
            blocked = [s for s in spaces if s not in self.settings.allowed_spaces]
            if blocked:
                raise PolicyError(f"spaces not in allowlist: {', '.join(blocked)}")
        return spaces

    def enforce_single_space_access(self, space: str | None) -> str | None:
        if not space:
            return space
        self.enforce_space_access([space])
        return space

    def enforce_write_enabled(self) -> None:
        if not self.settings.write_enabled:
            raise PolicyError("write tools are disabled by policy")

    def enforce_body_size(self, body: str) -> str:
        if len(body) > self.settings.max_body_chars:
            raise PolicyError(
                f"body too large: {len(body)} chars (max {self.settings.max_body_chars})"
            )
        return body

    def enforce_attachment_constraints(self, items: list[dict]) -> list[dict]:
        if len(items) > self.settings.max_attachment_count:
            items = items[: self.settings.max_attachment_count]
        if not self.settings.allowed_attachment_mime:
            return items
        filtered = []
        for item in items:
            media_type = (item.get("metadata") or {}).get("mediaType")
            file_size = ((item.get("extensions") or {}).get("fileSize") or 0)
            if media_type and media_type not in self.settings.allowed_attachment_mime:
                continue
            if file_size and file_size > self.settings.max_attachment_bytes:
                continue
            filtered.append(item)
        return filtered
