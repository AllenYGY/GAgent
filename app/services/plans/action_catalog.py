from __future__ import annotations

from typing import List


def build_action_catalog(plan_bound: bool, *, allow_execute: bool = True) -> str:
    """Return the shared ACTION catalog description used across agents."""

    base_actions: List[str] = [
        "- system_operation: help",
        "- tool_operation: web_search (use for live web information; requires `query`, optional provider/max_results)",
        "- tool_operation: graph_rag (query the phage-host knowledge graph; requires `query`, optional top_k/hops/return_subgraph/focus_entities)",
    ]
    if plan_bound:
        plan_actions: List[str] = [
            "- plan_operation: create_plan, list_plans{} delete_plan".format(
                ", execute_plan," if allow_execute else ","
            ),
            "- task_operation: create_task, update_task, update_task_instruction, move_task, delete_task, decompose_task, show_tasks, query_status, rerun_task",
            "- context_request: request_subgraph (request additional task context; this response must not include other actions)",
        ]
    else:
        plan_actions = [
            "- plan_operation: create_plan  # only when the user explicitly asks to create a plan",
            "- plan_operation: list_plans  # list candidates; do not execute or mutate tasks while unbound",
        ]
    return "\n".join(base_actions + plan_actions)
