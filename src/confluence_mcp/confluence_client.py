from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings


class ConfluenceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class ConfluenceClient:
    settings: Settings

    def _auth_headers(self) -> dict[str, str]:
        mode = self.settings.auth_mode
        if mode == "pat":
            if not self.settings.pat:
                raise ConfluenceError("CONFLUENCE_PAT is empty while auth mode is pat")
            return {"Authorization": f"Bearer {self.settings.pat}"}
        if mode == "basic":
            if not self.settings.username or not self.settings.password:
                raise ConfluenceError("username/password are required for basic auth")
            token = base64.b64encode(
                f"{self.settings.username}:{self.settings.password}".encode("utf-8")
            ).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        raise ConfluenceError(f"unsupported CONFLUENCE_AUTH_MODE: {mode}")

    def _build_url(self, path: str, query: dict[str, Any] | None = None) -> str:
        base = self.settings.base_url
        context = self.settings.context_path
        path = "/" + path.lstrip("/")
        if context:
            url = f"{base}/{context}{path}"
        else:
            url = f"{base}{path}"
        if query:
            query = {k: v for k, v in query.items() if v is not None and v != ""}
            encoded = urlencode(query, doseq=True)
            if encoded:
                url = f"{url}?{encoded}"
        return url

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        url = self._build_url(path, query)
        headers = {
            "Accept": "application/json",
            **self._auth_headers(),
        }
        body: bytes | None = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        timeout_s = self.settings.request_timeout_ms / 1000.0
        last_error: Exception | None = None

        for attempt in range(self.settings.max_retries + 1):
            try:
                request = Request(url=url, method=method, data=body, headers=headers)
                with urlopen(request, timeout=timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    if not raw:
                        return {}
                    return json.loads(raw)
            except HTTPError as exc:
                retryable = exc.code in {429, 500, 502, 503, 504}
                if retryable and attempt < self.settings.max_retries:
                    time.sleep(0.3 * (2**attempt))
                    continue
                detail = exc.read().decode("utf-8", errors="ignore")
                raise ConfluenceError(
                    f"Confluence HTTP {exc.code}: {detail[:500]}",
                    status_code=exc.code,
                    retryable=retryable,
                ) from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(0.3 * (2**attempt))
                    continue
                raise ConfluenceError(f"Confluence connection error: {exc}", retryable=True) from exc
            except json.JSONDecodeError as exc:
                raise ConfluenceError(f"invalid JSON response from Confluence: {exc}") from exc

        raise ConfluenceError(f"request failed: {last_error}")

    def search_cql(
        self,
        *,
        cql: str,
        limit: int,
        start: int | None = None,
        cursor: str | None = None,
        expands: list[str] | None = None,
    ) -> dict[str, Any]:
        query = {
            "cql": cql,
            "limit": limit,
            "start": start,
            "cursor": cursor,
            "expand": ",".join(expands or []),
        }
        return self._request("GET", "/rest/api/content/search", query=query)

    def get_content(self, *, content_id: str, expands: list[str] | None = None) -> dict[str, Any]:
        query = {"expand": ",".join(expands or [])}
        return self._request("GET", f"/rest/api/content/{content_id}", query=query)

    def get_labels(self, *, content_id: str, start: int | None = None, limit: int | None = None) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/content/{content_id}/label",
            query={"start": start, "limit": limit},
        )

    def get_children(self, *, content_id: str, start: int | None = None, limit: int | None = None) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/content/{content_id}/child/page",
            query={"start": start, "limit": limit},
        )

    def get_attachments(self, *, content_id: str, start: int | None = None, limit: int | None = None) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/content/{content_id}/child/attachment",
            query={"start": start, "limit": limit},
        )

    def get_comments(self, *, content_id: str, start: int | None = None, limit: int | None = None) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/content/{content_id}/child/comment",
            query={"start": start, "limit": limit},
        )

    def scan_content(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        space_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/rest/api/content/scan",
            query={"limit": limit, "cursor": cursor, "spaceKey": space_key},
        )

    def get_likes(self, *, content_id: str) -> dict[str, Any]:
        return self._request("GET", f"/rest/likes/1.0/content/{content_id}/likes")

    def create_page(
        self,
        *,
        space_key: str,
        title: str,
        body_storage: str,
        parent_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": str(parent_id)}]
        return self._request("POST", "/rest/api/content", payload=payload)

    def update_page(
        self,
        *,
        content_id: str,
        title: str,
        body_storage: str,
        expected_version: int | None,
        minor_edit: bool,
        version_message: str | None,
    ) -> dict[str, Any]:
        current = self.get_content(content_id=content_id, expands=["version", "space"])
        latest = int((current.get("version") or {}).get("number", 0))
        if expected_version is not None and expected_version != latest:
            raise ConfluenceError(
                f"version conflict: expected {expected_version}, current {latest}",
                status_code=409,
                retryable=False,
            )
        payload = {
            "id": str(content_id),
            "type": current.get("type", "page"),
            "title": title,
            "space": {"key": ((current.get("space") or {}).get("key"))},
            "version": {
                "number": latest + 1,
                "minorEdit": bool(minor_edit),
                "message": version_message or "",
            },
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        return self._request("PUT", f"/rest/api/content/{content_id}", payload=payload)

    def add_labels(self, *, content_id: str, labels: list[str]) -> dict[str, Any]:
        payload = [{"prefix": "global", "name": label} for label in labels]
        return self._request("POST", f"/rest/api/content/{content_id}/label", payload=payload)

    def add_comment(
        self,
        *,
        content_id: str,
        body_storage: str,
        parent_comment_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "comment",
            "container": {"id": str(content_id), "type": "page"},
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        if parent_comment_id:
            payload["ancestors"] = [{"id": str(parent_comment_id)}]
        return self._request("POST", "/rest/api/content", payload=payload)
