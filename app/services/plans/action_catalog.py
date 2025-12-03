from __future__ import annotations

from typing import List


def build_action_catalog(
    plan_bound: bool,
    *,
    allow_execute: bool = True,
    allow_web_search: bool = True,
    allow_rerun_task: bool = True,
    allow_graph_rag: bool = True,
    allow_show_tasks: bool = False,
) -> str:
    """Return the shared ACTION catalog description used across agents."""

    base_actions: List[str] = ["- system_operation: help"]
    if allow_web_search:
        base_actions.append(
            "- tool_operation: web_search (use for live web information; requires `query`, optional provider/max_results)"
        )
    if allow_graph_rag:
        base_actions.append(
            "- tool_operation: graph_rag (query the phage-host knowledge graph; requires `query`, optional top_k/hops/return_subgraph/focus_entities)"
        )
    if plan_bound:
        task_ops = [
            "create_task",
            "update_task",
            "update_task_instruction",
            "move_task",
            "delete_task",
            "decompose_task",
            "query_status",
        ]
        if allow_show_tasks:
            task_ops.append("show_tasks")
        if allow_rerun_task:
            task_ops.append("rerun_task")
        plan_actions: List[str] = [
            "- plan_operation: create_plan, list_plans{} delete_plan".format(
                ", execute_plan," if allow_execute else ","
            ),
            f"- task_operation: {', '.join(task_ops)}",
            "- context_request: request_subgraph (request additional task context; this response must not include other actions)",
        ]
    else:
        plan_actions = [
            "- plan_operation: create_plan  # only when the user explicitly asks to create a plan",
            "- plan_operation: list_plans  # list candidates; do not execute or mutate tasks while unbound",
        ]
    return "\n".join(base_actions + plan_actions)
