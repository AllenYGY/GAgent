# 8-Shard LightRAG Adapter Design

## Goal

Replace the existing MultiRAG HTTP service used by the public `graph_rag` tool with the locally tunneled 8-shard LightRAG gateway, without changing plan enrichment or other `graph_rag` consumers.

## Runtime Contract

- The application runs locally and reaches the gateway through an SSH tunnel at `http://127.0.0.1:9660`.
- Query authentication continues to use the `X-API-Key` header, with the secret supplied through the existing `MULTIRAG_API_KEY` environment variable.
- The default request uses `mode=mix`, `top_k=2`, `max_chunks=24`, and `max_references=32`.
- Health checks call `GET /health`; RAG queries call `POST /query`.

## Adapter Boundary

The protocol change stays inside `tool_box/tools_impl/graph_rag` and `app/config/rag_config.py`. The adapter converts the LightRAG response into the existing internal result shape:

```python
{
    "backend": "lightrag_8_shard",
    "mode": "mix",
    "response": "...",
    "trace": {
        "references": [...],
        "metadata": {...},
    },
}
```

Keeping this shape means `PlanDecomposer.enrich_plan_with_shared_graph_rag`, chat tool rendering, and the plan enrichment pipeline continue to consume `response` and `trace` unchanged.

## Configuration

Retain the existing `MULTIRAG_BASE_URL` and `MULTIRAG_API_KEY` names to minimize deployment changes. Add configurable defaults for `top_k`, `max_chunks`, and `max_references`. Include all request-affecting values in the in-memory cache key so different retrieval configurations cannot share stale results.

The plan enrichment runner defaults `ENRICH_GRAPH_RAG_MODE` to `mix`. The tool accepts all gateway modes: `mix`, `local`, `global`, `hybrid`, `naive`, and `bypass`.

## Error And Health Handling

- Map both HTTP 401 and 403 to `invalid_api_key`.
- Treat HTTP 422 as a request error and HTTP 5xx, including 502, as service unavailable.
- Preserve timeout and malformed-JSON handling.
- A health response is successful only for HTTP 200 with a JSON object. Preserve shard health fields such as `shards_total`, `shards_ok`, and `shards` for diagnostics.
- Preserve query `references` and `metadata` under the internal `trace` field so downstream context and logs retain shard evidence.

## Verification

Update the GraphRAG unit tests before implementation and confirm they fail against the old `/api/*` protocol. Cover the new paths, request defaults, response normalization, cache behavior, mode validation, 403 mapping, and health payload. Then run the focused GraphRAG tests and plan decomposer/enrichment tests. Use the smoke script against the SSH tunnel only after unit tests pass.

## Scope

No changes are required to the database import flow, `plan_enrichment_pipeline.py`, or the plan-level one-query/shared-context behavior. The SSH tunnel lifecycle remains external to the Python process.
