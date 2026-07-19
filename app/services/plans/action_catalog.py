from __future__ import annotations

from typing import List


def build_action_catalog(
    plan_bound: bool,
    *,
    allow_execute: bool = True,
    allow_web_search: bool = True,
    allow_rerun_task: bool = True,
    allow_graph_rag: bool = True,
    allow_springer_nature: bool = True,
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
            "- tool_operation: graph_rag (query the 8-shard LightRAG knowledge backend; requires `query`, optional `mode`).\n"
            "  mode can be `hybrid` (default, best general choice), `local` (entity-focused local context), "
            "`global` (higher-level global summary), or `naive` (plain retrieval).\n"
            "  Only send `query` and `mode`; do NOT generate `top_k`, `hops`, `return_subgraph`, or `focus_entities`."
        )
    if allow_springer_nature:
        base_actions.append(
            "- tool_operation: springer_nature (search Springer Nature; requires `api` and `q`).\n"
            "  api selects dataset: `meta` (Meta API, default) or `openaccess` (Open Access metadata). "
            "OA full-text (/openaccess/jats) is not supported.\n"
            "  q uses `field:argument` constraints + boolean logic. Constraints include: `doi:`, `title:`, `name:`, "
            "`orgname:`, `journal:`, `book:`, `subject:`, `discipline:`, `keyword:`, `language:`, `pub:`, `year:`, "
            "`onlinedate:`, `onlinedatefrom:`/`onlinedateto:`, `date:`/`datefrom:`/`dateto:`, "
            "`dateloaded:`/`dateloaded(from/to):`, `country:`, `issn:`, `isbn:`, `journalid:`, "
            "`topicalcollection:`, `issue:`, `issuetype:`, `volume:`, `bookdoi:`, `orcid:`, `grid:`, "
            "`type:(Book|Journal)`, `journalonlinefirst:true`, `openaccess:true`, `free:true`, "
            "`ContainsElements:`, `Exclude:Bibliography`, `latest issue`, `earliest issue`.\n"
            "  Some constraints are Meta-only (e.g., `discipline:`, `topicalcollection:`, `issuetype`, "
            "`latest issue`, `earliest issue`, `free:true`, `openaccess:true`). Keep `openaccess` queries simple.\n"
            "  Basic-plan only: do NOT use `sort:` or NEAR/n. AND/OR/NOT are allowed; use quoted phrases and "
            "parentheses for grouping when needed (e.g., `orgname:\"University of Calgary\"`).\n"
            "  For “latest” requests, prefer `year:` or `onlinedate:` filters.\n"
            "  Pagination: `p` page size (default 10), `s` start (default 1); use `fetch_all` only when needed."
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
