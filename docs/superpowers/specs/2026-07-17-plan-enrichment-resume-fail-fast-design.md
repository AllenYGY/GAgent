# Plan Enrichment Resume And RAG Fail-Fast Design

## Goal

Make long-running plan-level LightRAG enrichment resumable at plan granularity and stop immediately when the SSH-tunneled RAG service becomes unavailable.

## Checkpoint Contract

Each source `plan_N.json` has one canonical checkpoint at `ENRICH_OUTPUT_DIR/plan_N.json`. A checkpoint is complete only when it is valid JSON and at least one node contains `context_meta.graph_rag.backend == "lightrag_8_shard"`. Completed checkpoints are skipped before database import.

After a plan finishes successfully, the pipeline writes its JSON to a temporary sibling file and atomically replaces the canonical checkpoint. A process interruption can therefore leave either the previous complete checkpoint or no checkpoint, never a partially written JSON file.

An interrupted plan is rerun from its original `web_enriched_v2` source. Node-level partial database mutations are not reused.

## Attempt Databases

The shell runner treats each configured database path as an experiment root and creates a timestamped `attempt_*` database beneath it for every launch. Only pending source plans are imported into that attempt database. This avoids duplicate imports and avoids resuming from a database whose current plan may be partially rewritten.

## RAG Availability

Before each pending plan, the pipeline performs an uncached `GET /health` request. The plan starts only when the gateway reports HTTP success and `shards_ok == shards_total == 8`.

The pipeline also treats `graph_rag_failed` and `graph_rag_empty` enrichment results as fatal. Health failures, query timeouts, authentication failures, malformed responses, and shard failures terminate the Python process with a non-zero status. Because the shell runner uses `set -e`, the second model does not start after a RAG failure.

Node enrichment LLM fallback behavior remains unchanged because it is independent of RAG tunnel availability.

## Output And Progress

Progress logs report total inputs, completed checkpoints, and pending plans. Each successful plan immediately emits a checkpoint path. Restarting the same shell script after restoring the SSH tunnel processes only pending plans.

## Verification

Tests cover checkpoint validation, same-name atomic dumping, pending-file filtering, fatal GraphRAG result handling, and strict 8-shard health validation. Shell syntax and the focused Python test suite must pass before restarting the detached batch.
