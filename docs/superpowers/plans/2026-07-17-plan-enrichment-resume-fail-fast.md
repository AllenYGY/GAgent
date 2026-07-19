# Plan Enrichment Resume And RAG Fail-Fast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resume LightRAG enrichment from completed plan JSON checkpoints and terminate immediately when the tunneled 8-shard RAG service fails.

**Architecture:** The pipeline filters input files against validated same-name output checkpoints, imports only pending plans into a fresh attempt database, health-checks the gateway before every plan, and atomically dumps each plan immediately after success. The shell runner creates timestamped attempt databases while reusing the canonical output directory across restarts.

**Tech Stack:** Python, pytest, SQLite plan repositories, httpx-backed LightRAG health service, Bash, GNU screen.

---

### Task 1: Define Checkpoint And Fatal-RAG Behavior

**Files:**
- Modify: `test/test_plan_enrichment_pipeline.py`

- [ ] Add tests proving a valid `lightrag_8_shard` output is complete, malformed or old-backend output is pending, and atomic dump uses the source filename.
- [ ] Add tests proving `graph_rag_failed` and `graph_rag_empty` results raise a fatal pipeline exception.
- [ ] Add tests proving health validation requires success plus exactly 8/8 healthy shards.
- [ ] Run `python -m pytest -q test/test_plan_enrichment_pipeline.py` and confirm the new tests fail against the current pipeline.

### Task 2: Implement Plan-Level Resume And Fail-Fast

**Files:**
- Modify: `scripts/pipeline/plan_enrichment_pipeline.py`

- [ ] Add checkpoint validation and pending-file filtering helpers.
- [ ] Make `dump_plan_json` accept a source filename and atomically replace the checkpoint through a sibling `.tmp` file.
- [ ] Add strict uncached LightRAG health validation before every pending plan.
- [ ] Convert GraphRAG failed/empty stop reasons into a fatal exception and re-raise that exception from the processing loop.
- [ ] Dump each successful plan immediately and remove the end-of-batch dump loop.
- [ ] Run `python -m pytest -q test/test_plan_enrichment_pipeline.py test/tools/test_graph_rag_tool.py` and confirm all tests pass.

### Task 3: Create Fresh Attempt Databases Per Restart

**Files:**
- Modify: `scripts/pipeline/run_plan_graph_rag_enrich.sh`

- [ ] Set `ENRICH_RESUME=true`, `ENRICH_GRAPH_RAG_BACKEND=lightrag_8_shard`, and `PYTHONUNBUFFERED=1`.
- [ ] Generate one timestamped attempt id per shell launch and export `DB_ROOT=<experiment-root>/attempt_<id>` for each model.
- [ ] Log the experiment root, attempt database, checkpoint directory, and resume settings without printing credentials.
- [ ] Run `bash -n scripts/pipeline/run_plan_graph_rag_enrich.sh` and verify both input directories still contain 200 plans.

### Task 4: Verify And Restart

**Files:**
- Verify only

- [ ] Run the focused pipeline, GraphRAG, and plan decomposer tests.
- [ ] Run Python compile validation and `git diff --check` on changed files.
- [ ] Remove only the incomplete new LightRAG experiment directories created before checkpoint support.
- [ ] Start the runner in a detached screen session with a persistent log.
- [ ] Verify the screen session, Python child process, 8/8 health response, first successful `/query`, and creation of the first same-name checkpoint.
