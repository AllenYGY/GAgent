# Bulk Plan Generation Plan

## Goal
- Provide an automated way to create many plans (N topics) without manual UI interaction.
- Use the existing chat-based plan_operation APIs so no new backend routes are required.
- Capture outputs (plan IDs, trees, logs) for experiment tracking and reruns.

## High-Level Flow
1. Read topics/goals from an input file (text, CSV, or JSON lines).
2. For each topic, send a `/chat/message` request that forces the agent to call `plan_operation.create_plan`.
3. Parse the response to capture the new `plan_id`.
4. Optionally fetch `/plans/{plan_id}/tree` for archival.
5. Log success/failure per topic and support retries/resume.

## Script Structure (`scripts/bulk_generate_plans.py`)
- **CLI arguments**
  - `--input PATH` (supports `.txt`, `.csv`, `.jsonl`).
  - `--base-url`, `--api-key` (if needed), `--concurrency` (default 8).
  - `--prompt-template PATH` to override the default message.
  - `--dump-dir DIR` to store chat responses/plan trees.
  - `--resume-from CSV` to skip already completed rows.
- **Config loader**
  - Normalizes each entry into `{title, goal, metadata}` objects.
  - Allows optional owner/description fields (passed to plan metadata).

## Prompting Strategy
- System message (fixed in script):  
  `"You are the planning agent. For every request you MUST call plan_operation.create_plan exactly once and auto-decompose the root task."`
- User template:  
  ```
  Topic: "<title>"
  Goal: <goal or title>
  Requirements:
  - Generate a detailed execution plan with actionable tasks.
  - Call plan_operation.create_plan once, report the plan ID.
  - Keep free-form text short; rely on tool output.
  ```
- `context.plan_title` set to `title` so the repository stores readable names.

## HTTP Layer
- Use `httpx.AsyncClient` with keep-alive and ~60s timeout.
- Payload mirrors `web-ui/src/api/chat.ts`:  
  ```json
  {
    "message": "<rendered prompt>",
    "mode": "assistant",
    "history": [],
    "session_id": "bulk_<timestamp>_<idx>",
    "context": {
      "plan_title": "<title>",
      "metadata": {"bulk_run_id": "..."}
    }
  }
  ```
- After response, inspect `payload.metadata.plan_id`, `details.plan_id`, or `raw_actions` to find the numeric id; fallback to `/plans` diff if missing.
- Optional follow-up call: `GET /plans/{plan_id}/tree` and persist JSON.

## Concurrency & Reliability
- Use `asyncio` with a semaphore sized by `--concurrency`.
- Per topic task:
  1. Acquire semaphore.
  2. Send chat request; retry on 429/5xx using exponential backoff (`max_retries`, jitter).
  3. If LLM refuses to create a plan, resend once with a stricter template.
- Maintain thread-safe log (CSV/JSONL) with columns: `topic, plan_id, status, retries, error, session_id`.
- Emit a `failed_topics.jsonl` for reruns. `--resume-from` merges previous successes.

## Output Artifacts
- Default `bulk_plans.csv`.
- If `--dump-dir` is set:
  - `responses/<session>.json` (raw chat payload).
  - `plans/plan_<id>.json` (full plan tree).
  - Optional Markdown outlines for quick review.

## Validation Steps
- `--dry-run` mode for 2–3 topics with `--concurrency 1`.
- Post-run verification script:
  - Iterate `plan_id`s and call `/plans/{id}/execution/summary` and `/plans/{id}/tree`.
  - Report missing/failed IDs.
- Spot-check `docs/plans` or dashboards as needed.

## Next Actions
1. Scaffold the script, argument parsing, and async client.
2. Implement prompt rendering + response parsing utilities.
3. Build logging/output helpers.
4. Dry-run in dev env, adjust prompt.
5. Execute full batch, monitor backend logs/resources.
6. Document usage in `README` or `docs/experiments`.

## Current Implementation
- Script: `scripts/bulk_generate_plans.py`
- Example:
  ```bash
  python3 scripts/bulk_generate_plans.py \
    --input topics.txt \
    --base-url http://localhost:9000 \
    --concurrency 6 \
    --dump-dir bulk_artifacts
  ```
- Outputs a CSV (`bulk_plans.csv` by default) plus optional JSON dumps under `--dump-dir`.

## Direct Plan Generation (New)
为了绕过 `/chat/message` 的异步流程，我们还需要一个“直接创建+拆解”的脚本，调用后端现有的 Repository 和 Decomposer：

1. **脚本位置**：新增 `scripts/direct_plan_generator.py`（或扩展现有脚本），读取与批量版相同的输入格式。
2. **初始化**：在脚本中引用 `PlanRepository` 与 `PlanDecomposer`，加载 `get_decomposer_settings()`，并确保 `sys.path` 指向仓库根目录。
3. **创建计划**：对每个 topic 调用 `repo.create_plan(...)`，再用 `repo.create_task(...)` 创建根任务并写入详细 instruction（例如 `goal + description`）。
4. **同步拆解**：使用 `decomposer.decompose_node(plan_id, root_id, expand_depth, node_budget)` 直接生成子任务；如需多层可对新节点继续调用同一方法。
5. **输出**：将 `plan_id`、`DecompositionResult`（包含 created_tasks、stopped_reason 等）打印或写入 JSON，必要时 `repo.get_plan_tree(plan_id).model_dump()` 落盘。
6. **扩展**：可支持并发（注意 SQLite 连接限制）、自定义拆解深度/预算、或在生成完毕后调用 Plan Executor。
7. **目标**：这样批量脚本即可在后端“同步”产出完整计划树，不依赖 LLM prompt 或异步 job 状态。
