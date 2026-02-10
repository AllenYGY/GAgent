# Plan Refactor Actions Pipeline

## Goal
Add a post-enrichment refactor stage that can modify plan structure via LLM-generated ACTIONs.
The refactor stage must:
- Use LLMStructuredResponse (same schema as chat).
- Reuse ACTION execution logic (normalize_action + PlanRepository).
- Allow create/update/move/delete/decompose.
- Disallow update_task_instruction (update_task covers it).
- Enforce safe deletion (no dependent tasks; no subtree delete by default).
- Disallow web search inside decompose_task by default.

## Allowlist (final)
- create_task
- update_task
- move_task
- delete_task
- decompose_task

## Defaults (confirmed)
- delete_task: subtree deletion NOT allowed by default.
- decompose_task: web search NOT allowed by default.

## High-Level Flow
1) Import plan JSON into DB.
2) Web enrich-only (existing flow).
3) Refactor actions stage (new):
   - Build refactor prompt + action catalog.
   - LLM returns LLMStructuredResponse.
   - Filter actions by allowlist.
   - Execute actions with local safety checks.
4) Dump updated plan JSON.

## New Modules

### 1) app/services/plans/action_executor.py
Purpose: a shared ACTION executor for plan/task operations.

Responsibilities:
- Normalize params via action_schema.normalize_action.
- Filter actions via allowlist.
- Enforce local safety rules.
- Execute actions using PlanRepository / PlanDecomposer.
- Return structured results (success/failure + reason).

Execution order (avoid structural corruption):
- Phase A: create_task, update_task, move_task
- Phase B: decompose_task
- Phase C: delete_task

Safety rules (local hard checks):
- Reject delete_task on root nodes.
- Reject delete_task if other nodes depend on this task.
- Reject delete_task if node has children unless metadata.allow_delete_subtree=true.
- Reject move_task if it would create cycles.
- Drop update_task_instruction (not in allowlist).

### 2) app/services/plans/plan_refactor.py
Purpose: build prompt, call LLM, parse LLMStructuredResponse, and call ActionExecutor.

Prompt requirements:
- Output must be valid JSON and match LLMStructuredResponse.
- Only allow task_operation actions from allowlist.
- delete_task requires metadata.reason + metadata.evidence.
- Deletion is last resort; prefer update/move.
- IMPORTANT: If any task depends on the target task, deletion is NOT allowed. Resolve dependencies first (update/move) before delete.
- Innovation & Feasibility alignment: when updating/creating context, 尽可能在任务上下文中明确非显而易见的创新点、预期收益、可行性约束、资源需求、风险与缓解（仅在计划本身提供依据时补充，避免编造）。
- Limit total actions (e.g., <= 25).

Expected output format (example):
{
  "llm_reply": {"message": "short summary"},
  "actions": [
    {
      "kind": "task_operation",
      "name": "delete_task",
      "parameters": {"task_id": 42},
      "metadata": {
        "reason": "duplicate of task 38",
        "evidence": ["[42] ...", "[38] ..."],
        "allow_delete_subtree": false
      }
    }
  ]
}

## Pipeline Integration
File: scripts/pipeline/plan_enrichment_pipeline.py

After web_enrich_only, add optional refactor stage:
- if ENRICH_ENABLE_REFACTOR=true
  - plan_refactor.run(plan_id, allowlist, max_actions, allow_delete_subtree, allow_web_search_for_decompose)

Suggested env vars:
- ENRICH_ENABLE_REFACTOR=true|false
- REFACTOR_MAX_ACTIONS=25
- REFACTOR_ACTION_ALLOWLIST=create_task,update_task,move_task,delete_task,decompose_task
- REFACTOR_ALLOW_DELETE_SUBTREE=false
- REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH=false
- REFACTOR_MODEL / REFACTOR_PROVIDER / REFACTOR_TEMPERATURE

## Logging
- Write a JSONL file with each action, reason/evidence, and execution result.
- Include rejected actions with rejection reasons.

## Validation Checklist
- delete_task is rejected when a task has inbound dependencies.
- delete_task is rejected when a task has children unless allow_delete_subtree=true.
- update_task_instruction is dropped.
- decompose_task does not use web search when REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH=false.
- Action order is Phase A -> Phase B -> Phase C.
