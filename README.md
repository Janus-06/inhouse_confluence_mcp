# inhouse_confluence_mcp

In-house Confluence (Data Center/Server) MCP server implementation.
Default mode is read-only, and write tools are controlled by policy.

## Tools
- `confluence_list_spaces`
- `confluence_search_cql`
- `confluence_get_content`
- `confluence_get_labels`
- `confluence_get_children`
- `confluence_get_attachments`
- `confluence_get_comments`
- `confluence_scan_content`
- `confluence_get_likes` (experimental, off by default)
- `confluence_create_page` (write, off by default)
- `confluence_update_page` (write, off by default)
- `confluence_add_label` (write, off by default)
- `confluence_add_comment` (write, off by default)

## Quick Start
1. Copy `.env.example` to `.env`
2. Set required values:
- `CONFLUENCE_BASE_URL`
- `CONFLUENCE_AUTH_MODE` (`pat` or `basic`)
- `CONFLUENCE_PAT` or `CONFLUENCE_USERNAME`/`CONFLUENCE_PASSWORD`

3. Install and run:
```powershell
python -m pip install -e .
confluence-mcp
```

Or:
```powershell
python -m confluence_mcp.main
```

## Space Auto-Discovery
- If `ALLOWED_SPACES` is empty and `AUTO_DISCOVER_SPACES=true`, the server auto-loads all available space keys on startup.
- Spaces in `DENIED_SPACES` are always excluded.
- To generate a ready-to-copy env line manually:
```powershell
confluence-mcp-sync-spaces
```
- Output file: `logs/spaces_discovered.json`

## Recommended Settings
- Keep `WRITE_ENABLED=false` initially
- Configure `DENIED_SPACES` for sensitive spaces
- Keep `EXPERIMENTAL_LIKES=false` unless needed

## Logs
- Audit log path: `AUDIT_LOG_PATH` (default: `logs/audit.jsonl`)
- Fields: timestamp, tool, status, latencyMs, traceId, error

## Tests
```powershell
python -m unittest discover -s tests -v
```
