"""Shared ACTION schema and normalization utilities."""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


Schema = Dict[str, Dict[str, type]]


# Minimal schema for actions we expose. Keys are (kind, name).
ACTION_SCHEMAS: Dict[Tuple[str, str], Schema] = {
    ("tool_operation", "web_search"): {"required": {"query": str}, "optional": {"provider": str, "max_results": int}},
    ("tool_operation", "graph_rag"): {
        "required": {"query": str},
        "optional": {
            "top_k": int,
            "hops": int,
            "return_subgraph": bool,
            "focus_entities": str,
        },
    },

    ("plan_operation", "create_plan"): {"required": {"title": str}, "optional": {"description": str}},
    ("plan_operation", "list_plans"): {"required": {}, "optional": {}},
    ("plan_operation", "delete_plan"): {"required": {"plan_id": int}, "optional": {}},
    ("plan_operation", "execute_plan"): {"required": {}, "optional": {}},

    ("task_operation", "create_task"): {
        "required": {"name": str},
        "optional": {
            "parent_id": int,
            "instruction": str,
            "metadata": dict,
            "dependencies": list,
            "anchor_task_id": int,
            "anchor_position": str,
            "position": str,
            "insert_before": int,
            "insert_after": int,
        },
    },
    ("task_operation", "update_task"): {
        "required": {"task_id": int},
        "optional": {"name": str, "instruction": str, "metadata": dict, "dependencies": list},
    },
    ("task_operation", "update_task_instruction"): {"required": {"task_id": int, "instruction": str}, "optional": {}},
    ("task_operation", "move_task"): {"required": {"task_id": int}, "optional": {"new_parent_id": int, "new_position": int}},
    ("task_operation", "delete_task"): {"required": {"task_id": int}, "optional": {}},
    ("task_operation", "decompose_task"): {
        "required": {},
        "optional": {
            "task_id": int,
            "expand_depth": int,
            "node_budget": int,
            "allow_existing_children": bool,
            "allow_web_search": bool,
        },
    },
    ("task_operation", "show_tasks"): {"required": {}, "optional": {}},
    ("task_operation", "query_status"): {"required": {}, "optional": {}},
    ("task_operation", "rerun_task"): {"required": {"task_id": int}, "optional": {}},
}


def _coerce(value: Any, target_type: type) -> Any:
    if value is None:
        return None
    try:
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            if isinstance(value, str):
                return value.lower() in {"true", "1", "yes", "y"}
            return bool(value)
        if target_type is str:
            return str(value)
    except Exception:
        raise
    return value


def normalize_action(kind: str, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize action parameters against the shared schema.

    - Ensures required params exist and are cast to expected types.
    - Drops params not declared in the schema.
    - Raises ValueError on missing required fields or coercion failures.
    """

    schema = ACTION_SCHEMAS.get((kind, name))
    if schema is None:
        raise ValueError(f"Unsupported action: {kind}/{name}")

    required = schema.get("required", {})
    optional = schema.get("optional", {})
    normalized: Dict[str, Any] = {}

    # Required fields
    for field, typ in required.items():
        if field not in params:
            raise ValueError(f"Missing required parameter '{field}' for action {kind}/{name}")
        try:
            normalized[field] = _coerce(params[field], typ)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid type for '{field}' in action {kind}/{name}: {exc}") from exc

    # Optional fields
    for field, typ in optional.items():
        if field in params:
            try:
                normalized[field] = _coerce(params[field], typ)
            except Exception as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid type for '{field}' in action {kind}/{name}: {exc}") from exc

    # Warn about dropped params
    for extra_key in params.keys() - required.keys() - optional.keys():
        logger.debug("Dropping unsupported param '%s' for action %s/%s", extra_key, kind, name)

    return normalized
