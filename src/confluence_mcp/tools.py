from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .audit import AuditLogger
from .config import Settings
from .confluence_client import ConfluenceClient, ConfluenceError
from .policy import PolicyEngine, PolicyError

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


@dataclass
class ToolRegistry:
    settings: Settings
    client: ConfluenceClient
    policy: PolicyEngine
    audit: AuditLogger

    def build_tools(self) -> dict[str, ToolDefinition]:
        tools = {
            "confluence_search_cql": ToolDefinition(
                name="confluence_search_cql",
                description="Search Confluence content using CQL.",
                input_schema={
                    "type": "object",
                    "required": ["cql"],
                    "properties": {
                        "cql": {"type": "string"},
                        "limit": {"type": "integer"},
                        "start": {"type": "integer"},
                        "cursor": {"type": "string"},
                        "expand": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=self._search_cql,
            ),
            "confluence_get_content": ToolDefinition(
                name="confluence_get_content",
                description="Get a Confluence content item by id.",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "expand": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=self._get_content,
            ),
            "confluence_get_labels": ToolDefinition(
                name="confluence_get_labels",
                description="List labels for a content item.",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}, "start": {"type": "integer"}},
                },
                handler=self._get_labels,
            ),
            "confluence_get_children": ToolDefinition(
                name="confluence_get_children",
                description="List child pages for a content item.",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}, "start": {"type": "integer"}},
                },
                handler=self._get_children,
            ),
            "confluence_get_attachments": ToolDefinition(
                name="confluence_get_attachments",
                description="List attachments for a content item.",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}, "start": {"type": "integer"}},
                },
                handler=self._get_attachments,
            ),
            "confluence_get_comments": ToolDefinition(
                name="confluence_get_comments",
                description="List comments for a content item.",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}, "start": {"type": "integer"}},
                },
                handler=self._get_comments,
            ),
            "confluence_scan_content": ToolDefinition(
                name="confluence_scan_content",
                description="Scan Confluence content for indexing.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spaceKey": {"type": "string"},
                        "limit": {"type": "integer"},
                        "cursor": {"type": "string"},
                    },
                },
                handler=self._scan_content,
            ),
            "confluence_create_page": ToolDefinition(
                name="confluence_create_page",
                description="Create a Confluence page in an allowed space.",
                input_schema={
                    "type": "object",
                    "required": ["spaceKey", "title", "bodyStorage"],
                    "properties": {
                        "spaceKey": {"type": "string"},
                        "title": {"type": "string"},
                        "bodyStorage": {"type": "string"},
                        "parentId": {"type": "string"},
                    },
                },
                handler=self._create_page,
            ),
            "confluence_update_page": ToolDefinition(
                name="confluence_update_page",
                description="Update a Confluence page with version checks.",
                input_schema={
                    "type": "object",
                    "required": ["id", "title", "bodyStorage"],
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "bodyStorage": {"type": "string"},
                        "expectedVersion": {"type": "integer"},
                        "minorEdit": {"type": "boolean"},
                        "versionMessage": {"type": "string"},
                    },
                },
                handler=self._update_page,
            ),
            "confluence_add_label": ToolDefinition(
                name="confluence_add_label",
                description="Add labels to a Confluence content item.",
                input_schema={
                    "type": "object",
                    "required": ["id", "labels"],
                    "properties": {
                        "id": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=self._add_label,
            ),
            "confluence_add_comment": ToolDefinition(
                name="confluence_add_comment",
                description="Add a comment to a Confluence page.",
                input_schema={
                    "type": "object",
                    "required": ["id", "bodyStorage"],
                    "properties": {
                        "id": {"type": "string"},
                        "bodyStorage": {"type": "string"},
                        "parentCommentId": {"type": "string"},
                    },
                },
                handler=self._add_comment,
            ),
        }

        if self.settings.experimental_likes:
            tools["confluence_get_likes"] = ToolDefinition(
                name="confluence_get_likes",
                description="Get likes for a Confluence page (experimental).",
                input_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
                handler=self._get_likes,
            )

        return tools

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self.build_tools().values()
        ]

    def call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        tools = self.build_tools()
        if name not in tools:
            raise PolicyError(f"unknown tool: {name}")

        trace_id = f"cfx-{uuid.uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)
        try:
            result = tools[name].handler(args)
            duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            envelope = self._envelope(trace_id=trace_id, data=result)
            self.audit.log(
                {
                    "tool": name,
                    "status": "ok",
                    "latencyMs": duration_ms,
                    "traceId": trace_id,
                }
            )
            return envelope
        except (PolicyError, ConfluenceError, ValueError, KeyError) as exc:
            duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            retryable = bool(getattr(exc, "retryable", False))
            code = getattr(exc, "status_code", None)
            error_data = {
                "error": {
                    "code": str(code) if code is not None else "tool_error",
                    "message": str(exc),
                    "retryable": retryable,
                }
            }
            self.audit.log(
                {
                    "tool": name,
                    "status": "error",
                    "latencyMs": duration_ms,
                    "traceId": trace_id,
                    "error": str(exc),
                    "retryable": retryable,
                }
            )
            return self._envelope(trace_id=trace_id, data=error_data, is_error=True)

    def _envelope(self, *, trace_id: str, data: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
        return {
            "traceId": trace_id,
            "sourceSystem": "confluence",
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "isError": is_error,
            **data,
        }

    def _search_cql(self, args: dict[str, Any]) -> dict[str, Any]:
        cql = str(args["cql"])
        limit = self.policy.enforce_limit(args.get("limit"))
        expands = self.policy.enforce_expand(args.get("expand"))
        response = self.client.search_cql(
            cql=cql,
            limit=limit,
            start=args.get("start"),
            cursor=args.get("cursor"),
            expands=expands,
        )
        items = [self._content_brief(x) for x in response.get("results", [])]
        return {
            "items": items,
            "pageInfo": {
                "start": response.get("start"),
                "limit": response.get("limit"),
                "size": response.get("size"),
                "next": ((response.get("_links") or {}).get("next")),
            },
        }

    def _get_content(self, args: dict[str, Any]) -> dict[str, Any]:
        expands = self.policy.enforce_expand(args.get("expand"))
        content = self.client.get_content(content_id=str(args["id"]), expands=expands)
        space_key = ((content.get("space") or {}).get("key"))
        self.policy.enforce_single_space_access(space_key)
        return {"item": self._content_full(content)}

    def _get_labels(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = self.policy.enforce_limit(args.get("limit"))
        response = self.client.get_labels(content_id=str(args["id"]), start=args.get("start"), limit=limit)
        labels = [
            {
                "id": x.get("id"),
                "name": x.get("name"),
                "prefix": x.get("prefix"),
            }
            for x in response.get("results", [])
        ]
        return {"items": labels, "size": response.get("size")}

    def _get_children(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = self.policy.enforce_limit(args.get("limit"))
        response = self.client.get_children(content_id=str(args["id"]), start=args.get("start"), limit=limit)
        return {"items": [self._content_brief(x) for x in response.get("results", [])], "size": response.get("size")}

    def _get_attachments(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = self.policy.enforce_limit(args.get("limit"))
        response = self.client.get_attachments(content_id=str(args["id"]), start=args.get("start"), limit=limit)
        filtered = self.policy.enforce_attachment_constraints(response.get("results", []))
        items = [
            {
                "id": x.get("id"),
                "title": x.get("title"),
                "mediaType": (x.get("metadata") or {}).get("mediaType"),
                "fileSize": (x.get("extensions") or {}).get("fileSize"),
                "download": ((x.get("_links") or {}).get("download")),
            }
            for x in filtered
        ]
        return {"items": items, "size": len(items)}

    def _get_comments(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = self.policy.enforce_limit(args.get("limit"))
        response = self.client.get_comments(content_id=str(args["id"]), start=args.get("start"), limit=limit)
        items = [
            {
                "id": x.get("id"),
                "title": x.get("title"),
                "version": ((x.get("version") or {}).get("number")),
                "body": (((x.get("body") or {}).get("storage") or {}).get("value")),
            }
            for x in response.get("results", [])
        ]
        return {"items": items, "size": response.get("size")}

    def _scan_content(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = self.policy.enforce_limit(args.get("limit"))
        space_key = self.policy.enforce_single_space_access(args.get("spaceKey"))
        response = self.client.scan_content(limit=limit, cursor=args.get("cursor"), space_key=space_key)
        return {
            "items": [self._content_brief(x) for x in response.get("results", [])],
            "pageInfo": {
                "cursor": response.get("cursor"),
                "nextCursor": response.get("nextCursor"),
                "size": response.get("size"),
            },
        }

    def _get_likes(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.experimental_likes:
            raise PolicyError("likes tool is disabled")
        response = self.client.get_likes(content_id=str(args["id"]))
        return {"likes": response}

    def _create_page(self, args: dict[str, Any]) -> dict[str, Any]:
        self.policy.enforce_write_enabled()
        space_key = self.policy.enforce_single_space_access(str(args["spaceKey"]))
        body = self.policy.enforce_body_size(str(args["bodyStorage"]))
        created = self.client.create_page(
            space_key=space_key or "",
            title=str(args["title"]),
            body_storage=body,
            parent_id=args.get("parentId"),
        )
        return {"item": self._content_brief(created)}

    def _update_page(self, args: dict[str, Any]) -> dict[str, Any]:
        self.policy.enforce_write_enabled()
        body = self.policy.enforce_body_size(str(args["bodyStorage"]))
        updated = self.client.update_page(
            content_id=str(args["id"]),
            title=str(args["title"]),
            body_storage=body,
            expected_version=args.get("expectedVersion"),
            minor_edit=bool(args.get("minorEdit", True)),
            version_message=args.get("versionMessage"),
        )
        return {"item": self._content_brief(updated)}

    def _add_label(self, args: dict[str, Any]) -> dict[str, Any]:
        self.policy.enforce_write_enabled()
        labels = [str(x).strip() for x in args.get("labels", []) if str(x).strip()]
        if not labels:
            raise PolicyError("labels must not be empty")
        response = self.client.add_labels(content_id=str(args["id"]), labels=labels)
        return {"result": response}

    def _add_comment(self, args: dict[str, Any]) -> dict[str, Any]:
        self.policy.enforce_write_enabled()
        body = self.policy.enforce_body_size(str(args["bodyStorage"]))
        comment = self.client.add_comment(
            content_id=str(args["id"]),
            body_storage=body,
            parent_comment_id=args.get("parentCommentId"),
        )
        return {"item": self._content_brief(comment)}

    def _content_brief(self, x: dict[str, Any]) -> dict[str, Any]:
        links = x.get("_links") or {}
        return {
            "id": x.get("id"),
            "type": x.get("type"),
            "title": x.get("title"),
            "spaceKey": ((x.get("space") or {}).get("key")),
            "version": ((x.get("version") or {}).get("number")),
            "webUrl": self._web_url(links),
            "apiUrl": links.get("self"),
        }

    def _content_full(self, x: dict[str, Any]) -> dict[str, Any]:
        brief = self._content_brief(x)
        brief["bodyStorage"] = (((x.get("body") or {}).get("storage") or {}).get("value"))
        brief["bodyView"] = (((x.get("body") or {}).get("view") or {}).get("value"))
        brief["history"] = x.get("history")
        brief["lastUpdated"] = x.get("lastUpdated")
        return brief

    def _web_url(self, links: dict[str, Any]) -> str | None:
        base = links.get("base") or self.settings.base_url
        if links.get("webui"):
            return f"{base}{links['webui']}"
        return None
