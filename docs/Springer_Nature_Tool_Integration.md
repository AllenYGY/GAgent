# Springer Nature Tool Integration

## Goals
- Add a single tool in `tool_box` that can call Meta and Open Access.
- Support two API keys (Meta and Open Access only).
- Keep the query string (`q`) syntax intact; only strip unsupported modifiers
  (e.g., `sort:`) for basic-plan safety.
- Avoid blocking the event loop when the wrapper runs sync HTTP calls.

## Purpose and Scope
- `meta`: search Springer Nature versioned metadata (Meta API v2).
- `openaccess`: search Open Access metadata (OA API).
- OA full-text endpoint (`/openaccess/jats`) is not wired in this tool yet.
- Metadata API is deprecated and intentionally not supported.
- No semantic rewriting: the tool forwards `q` as-is except for removing
  unsupported modifiers like `sort:`/`NEAR/n` in basic-plan mode.

## Configuration
Environment variables:
- `SPRINGER_META_API_KEY` for Meta
- `SPRINGER_OPENACCESS_API_KEY` for Open Access

Add `app/config/springer_config.py`:
- Define `SpringerSettings` with the keys above.
- Expose `get_springer_settings()` (cached).
- Export from `app/config/__init__.py`.

## Tool Interface
Tool name: `springer_nature`

Parameters (summary):
```json
{
  "api": "meta | openaccess",
  "q": "query string",
  "p": 10,
  "s": 1,
  "fetch_all": false,
  "is_premium": false,
  "api_key": "optional override"
}
```

Parameter details:
- `api`: API family to query. Default is `meta`.
- `q`: full query string. Required. Uses Springer Nature query syntax.
- `p`: page size. Defaults to 10.
- `s`: start position. Defaults to 1.
- `fetch_all`: paginate through all pages. Use with caution.
- `is_premium`: currently ignored (basic-plan only).
- `api_key`: optional override for Meta/Open Access.

Behavior:
- Pick key by `api`:
  - `meta` -> `SPRINGER_META_API_KEY`
  - `openaccess` -> `SPRINGER_OPENACCESS_API_KEY`
- Use `asyncio.to_thread(...)` to call the sync wrapper.
- Standardize error payloads with `success`, `error`, and `code`.
- Basic-plan only: strip `sort:` and `NEAR/n` before requests. If normalization changes the
  query, return `fallback_reason="basic_plan_simplified"` plus `original_query`.
  Boolean operators (`AND`/`OR`/`NOT`) are preserved.
- If a 403 persists, retry after removing field constraints and return
  `fallback_reason="field_constraints_removed"` plus `original_query`.

## Return Structure
Meta/Open Access:
```json
{
  "api": "meta",
  "query": "keyword:\"cancer\"",
  "success": true,
  "records": [],
  "record_count": 0
}
```

Error response:
```json
{
  "api": "meta",
  "query": "keyword:\"cancer\"",
  "success": false,
  "error": "403 Client Error: Forbidden",
  "code": "request_error"
}
```

Error codes:
- `missing_query`
- `invalid_request`
- `invalid_api_key`
- `rate_limit`
- `request_error`
- `unexpected_error`

## Query Syntax Notes
The `q` parameter supports query constraints, not extra request parameters.

Common constraints (Meta, Open Access):
- `doi:`, `subject:`, `keyword:`, `language:`, `pub:`
- `year:`, `onlinedate:`, `datefrom/dateto:`, `dateloaded:`
- `country:`, `isbn:`, `issn:`, `journalid:`, `issue`, `volume`
- `type:(Book|Journal)`, `orcid:`, `grid:`, `bookdoi:`
- `journalonlinefirst:true`, `ContainsElements:`, `Exclude:Bibliography`
- "contains" constraints: `title:`, `orgname:`, `journal:`, `book:`, `name:`

Differences:
- Not supported in Open Access: `discipline:`, `topicalcollection:`,
  `issuetype`, `latest issue`, `earliest issue`, `free:true`
- `openaccess:true` is for Meta v2, not Open Access
- `excludeElements` only applies to Open Access

Multi-word values must be quoted:
```
orgname:"University of Calgary"
```

Reference: https://dev.springernature.com/docs/supported-query-params/

## Implementation Steps
1. Add `springernature-api-client` to `requirements.txt`.
2. Add `app/config/springer_config.py` and export it in `app/config/__init__.py`.
3. Add `tool_box/tools_impl/springer_nature.py` with the async handler.
4. Export tool in `tool_box/tools_impl/__init__.py`.
5. Register tool in `tool_box/integration.py`.
6. Add examples to the docstring and tool schema.

## Example Usage
```python
await execute_tool(
    "springer_nature",
    api="meta",
    q='keyword:"cancer" year:2023',
    p=20,
    s=1,
)
```

```python
await execute_tool(
    "springer_nature",
    api="openaccess",
    q='keyword:"cancer" year:2023',
)
```

```python
await execute_tool(
    "springer_nature",
    api="meta",
    q='orgname:"University of Calgary"',
)
```

## Testing
- Add `test/tools/test_springer_nature_tool.py`.
- Mock the wrapper classes and verify:
  - Key selection by `api`
  - Query validation and error mapping
  - Sort fallback behavior (non-premium)
