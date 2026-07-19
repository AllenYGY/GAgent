# 8-Shard LightRAG Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the existing `graph_rag` tool through the locally tunneled 8-shard LightRAG gateway using the recommended retrieval parameters while preserving all existing consumers.

**Architecture:** Keep the external protocol change at the GraphRAG adapter boundary. Configuration supplies stable retrieval defaults, the HTTP service calls `/health` and `/query`, and the service normalizes LightRAG's `response/references/metadata` into the existing `backend/mode/response/trace` result contract.

**Tech Stack:** Python 3, `httpx`, dataclass-based environment configuration, pytest/pytest-asyncio, Bash pipeline scripts.

---

### Task 1: Lock The New Gateway Contract With Tests

**Files:**
- Modify: `test/tools/test_graph_rag_tool.py`

- [x] **Step 1: Replace the success fixture with the LightRAG response contract**

Use a response containing `response`, `references`, and `metadata.query_mode`. Assert that the request targets `/query` and contains exactly `query`, `mode`, `top_k`, `max_chunks`, and `max_references` with values `mix`, `2`, `24`, and `32`.

- [x] **Step 2: Add assertions for normalized evidence**

Assert the public tool result retains `backend == "lightrag_8_shard"`, the returned answer under `response`, and both gateway `references` and `metadata` under `trace`.

- [x] **Step 3: Update health and error cases**

Assert health uses `/health`, preserves `shards_total` and `shards_ok`, and maps HTTP 403 to `invalid_api_key`. Clear the three new retrieval environment variables in the autouse fixture.

- [x] **Step 4: Run tests and verify RED**

Run: `pytest -q test/tools/test_graph_rag_tool.py`

Expected: failures showing the old `/api/query` and `/api/health` paths, the old response parser, missing `mix`, and missing request defaults.

### Task 2: Implement Configuration And Protocol Normalization

**Files:**
- Modify: `app/config/rag_config.py`
- Modify: `tool_box/tools_impl/graph_rag/service.py`
- Modify: `tool_box/tools_impl/graph_rag/__init__.py`
- Modify: `.env.example`

- [x] **Step 1: Add retrieval settings**

Extend `GraphRAGSettings` with integer defaults `top_k=2`, `max_chunks=24`, and `max_references=32`. Read them from `GRAPH_RAG_TOP_K`, `GRAPH_RAG_MAX_CHUNKS`, and `GRAPH_RAG_MAX_REFERENCES`, clamping each to at least 1.

- [x] **Step 2: Adapt the HTTP service**

Change health to `GET /health` and query to `POST /query`. Send the recommended settings in the JSON body, accept 401 and 403 as invalid API keys, and normalize the response as:

```python
return {
    "backend": "lightrag_8_shard",
    "mode": str(metadata.get("query_mode") or mode),
    "response": response_text,
    "trace": {"references": references, "metadata": metadata},
}
```

Reject a successful HTTP response without a non-empty string `response` as `request_error`.

- [x] **Step 3: Update the tool mode and cache contract**

Allow `mix` and `bypass`, make `mix` the handler/schema default, and include `top_k`, `max_chunks`, and `max_references` in the cache parameters.

- [x] **Step 4: Document environment defaults**

Add the three `GRAPH_RAG_*` variables with recommended values to `.env.example`.

- [x] **Step 5: Run focused tests and verify GREEN**

Run: `pytest -q test/tools/test_graph_rag_tool.py`

Expected: all tests pass.

### Task 3: Use Mix Across Plan Enrichment And Smoke Testing

**Files:**
- Modify: `scripts/pipeline/run_plan_graph_rag_enrich.sh`
- Modify: `scripts/pipeline/plan_enrichment_pipeline.py`
- Modify: `app/services/plans/plan_decomposer.py`
- Modify: `app/routers/chat_routes.py`
- Modify: `test/run_graph_rag_multirag_smoke.py`
- Modify: `.env`

- [x] **Step 1: Change omitted-mode defaults to mix**

Replace GraphRAG-specific fallback values of `hybrid` with `mix` in the tool-facing chat route, plan decomposer, enrichment pipeline, runner, and smoke test. Retain explicit `hybrid` support.

- [x] **Step 2: Configure the local runtime**

Set `MULTIRAG_BASE_URL=http://127.0.0.1:9660` in `.env`, use the provided gateway API key there, and add the recommended retrieval settings. Do not place the key in tracked example files or logs.

- [x] **Step 3: Run plan integration tests**

Run: `pytest -q test/test_plan_decomposer.py test/test_plan_enrichment_pipeline.py test/test_structured_agent_actions.py`

Expected: all tests pass, including explicit legacy `hybrid` cases.

### Task 4: Verify The Complete Adapter

**Files:**
- Verify only

- [x] **Step 1: Run static syntax validation**

Run: `python -m compileall -q app/config/rag_config.py tool_box/tools_impl/graph_rag scripts/pipeline/plan_enrichment_pipeline.py test/run_graph_rag_multirag_smoke.py`

Expected: exit code 0.

- [x] **Step 2: Run the focused regression suite**

Run: `pytest -q test/tools/test_graph_rag_tool.py test/test_plan_decomposer.py test/test_plan_enrichment_pipeline.py test/test_structured_agent_actions.py`

Expected: all tests pass.

- [x] **Step 3: Probe the tunneled service**

Run: `python test/run_graph_rag_multirag_smoke.py --mode mix --query "what is BACTERIOPHAGE"`

Expected: health reports 8 total and 8 healthy shards, and `graph_rag.success` is true with a non-empty response. If port 9660 is not listening, report the missing SSH tunnel as the only runtime blocker rather than changing application code.

- [x] **Step 4: Inspect the final diff**

Run: `git diff --check` and `git diff --stat`.

Expected: no whitespace errors and only the scoped adapter, defaults, tests, environment example, and plan files are changed by this task.
