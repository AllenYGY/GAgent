from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.repository.plan_repository import PlanRepository
from app.services.llm.structured_response import LLMAction
from app.services.plans.action_schema import normalize_action
from app.services.plans.plan_decomposer import PlanDecomposer
from app.services.plans.plan_models import PlanTree

logger = logging.getLogger(__name__)


PHASE_ORDER: Dict[str, int] = {
    "create_task": 0,
    "update_task": 0,
    "update_task_instruction": 0,
    "move_task": 0,
    "decompose_task": 1,
    "delete_task": 2,
}


@dataclass
class ActionExecutionResult:
    action: LLMAction
    success: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    rejected: bool = False


class ActionExecutor:
    """Execute task_operation actions against a plan with local safety checks."""

    def __init__(
        self,
        *,
        repo: Optional[PlanRepository] = None,
        plan_decomposer: Optional[PlanDecomposer] = None,
    ) -> None:
        self._repo = repo or PlanRepository()
        self._plan_decomposer = plan_decomposer

    def apply_actions(
        self,
        plan_id: int,
        actions: Sequence[LLMAction],
        *,
        allowlist: Optional[Set[str]] = None,
        allow_delete_subtree: bool = False,
        require_delete_subtree_flag: bool = True,
        allow_delete_root: bool = False,
        enforce_dependency_check: bool = True,
        allow_decompose_web_search: bool = False,
    ) -> List[ActionExecutionResult]:
        tree = self._repo.get_plan_tree(plan_id)
        results: List[ActionExecutionResult] = []
        pending: List[Tuple[int, LLMAction]] = []

        for index, action in enumerate(actions):
            if action.kind != "task_operation":
                results.append(
                    self._reject(action, "Only task_operation actions are supported.")
                )
                continue
            if allowlist is not None and action.name not in allowlist:
                results.append(
                    self._reject(
                        action, f"Action '{action.name}' is not in the allowlist."
                    )
                )
                continue
            pending.append((index, action))

        pending.sort(
            key=lambda item: (
                PHASE_ORDER.get(item[1].name, 99),
                item[1].order,
                item[0],
            )
        )

        for _, action in pending:
            try:
                raw_params = self._normalize_params(action)
                params = normalize_action(action.kind, action.name, raw_params)
                result = self._execute_action(
                    plan_id,
                    tree,
                    action,
                    params,
                    allow_delete_subtree=allow_delete_subtree,
                    require_delete_subtree_flag=require_delete_subtree_flag,
                    allow_delete_root=allow_delete_root,
                    enforce_dependency_check=enforce_dependency_check,
                    allow_decompose_web_search=allow_decompose_web_search,
                )
            except Exception as exc:
                message = f"{action.name} failed: {exc}"
                logger.warning("Action %s failed: %s", action.name, exc)
                result = ActionExecutionResult(
                    action=action,
                    success=False,
                    message=message,
                    details={"error": str(exc)},
                )
            results.append(result)
            if result.success and action.name in PHASE_ORDER:
                tree = self._repo.get_plan_tree(plan_id)

        return results

    @staticmethod
    def _reject(action: LLMAction, reason: str) -> ActionExecutionResult:
        return ActionExecutionResult(
            action=action,
            success=False,
            message=reason,
            details={"reason": reason},
            rejected=True,
        )

    @staticmethod
    def _normalize_params(action: LLMAction) -> Dict[str, Any]:
        params = dict(action.parameters or {})
        if action.name == "create_task" and "name" not in params:
            for alt in ("task_name", "title"):
                if params.get(alt):
                    params["name"] = params[alt]
                    break
        return params

    @staticmethod
    def _normalize_dependencies(raw: Any) -> Optional[List[int]]:
        if raw is None or not isinstance(raw, list):
            return None
        deps: List[int] = []
        for item in raw:
            try:
                deps.append(int(item))
            except (TypeError, ValueError):
                continue
        return deps or None

    @staticmethod
    def _coerce_int(value: Any, field: str) -> int:
        if value is None:
            raise ValueError(f"{field} is missing or empty.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be an integer; received {value!r}") from exc

    @staticmethod
    def _descendants(tree: PlanTree, node_id: int) -> Set[int]:
        descendants: Set[int] = set()
        stack = list(tree.children_ids(node_id))
        while stack:
            current = stack.pop()
            if current in descendants:
                continue
            descendants.add(current)
            stack.extend(tree.children_ids(current))
        return descendants

    @staticmethod
    def _find_dependents(tree: PlanTree, task_id: int) -> List[int]:
        dependents: List[int] = []
        for node in tree.iter_nodes():
            if task_id in (node.dependencies or []):
                dependents.append(node.id)
        return dependents

    def _execute_action(
        self,
        plan_id: int,
        tree: PlanTree,
        action: LLMAction,
        params: Dict[str, Any],
        *,
        allow_delete_subtree: bool,
        require_delete_subtree_flag: bool,
        allow_delete_root: bool,
        enforce_dependency_check: bool,
        allow_decompose_web_search: bool,
    ) -> ActionExecutionResult:
        if action.name == "create_task":
            name = params.get("name")
            if not name:
                raise ValueError("create_task requires a name.")
            instruction = params.get("instruction")
            parent_id = params.get("parent_id")
            metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
            dependencies = self._normalize_dependencies(params.get("dependencies"))

            position_value = params.get("position")
            anchor_task_id = params.get("anchor_task_id")
            anchor_position = params.get("anchor_position")
            insert_before = params.get("insert_before")
            insert_after = params.get("insert_after")

            position, anchor_task_id, anchor_position = self._resolve_create_position(
                tree,
                parent_id,
                position_value,
                anchor_task_id,
                anchor_position,
                insert_before,
                insert_after,
            )

            node = self._repo.create_task(
                plan_id,
                name=name,
                instruction=instruction,
                parent_id=parent_id,
                metadata=metadata,
                dependencies=dependencies,
                position=position,
                anchor_task_id=anchor_task_id,
                anchor_position=anchor_position,
            )
            return ActionExecutionResult(
                action=action,
                success=True,
                message=f"Created task [{node.id}] {node.name}.",
                details={"task": node.model_dump()},
            )

        if action.name == "update_task":
            task_id = self._coerce_int(params.get("task_id"), "task_id")
            name = params.get("name")
            instruction = params.get("instruction")
            metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
            dependencies = self._normalize_dependencies(params.get("dependencies"))
            if all(v is None for v in [name, instruction, metadata, dependencies]):
                raise ValueError(
                    "update_task requires at least one of name, instruction, metadata, or dependencies."
                )
            node = self._repo.update_task(
                plan_id,
                task_id,
                name=name,
                instruction=instruction,
                metadata=metadata,
                dependencies=dependencies,
            )
            return ActionExecutionResult(
                action=action,
                success=True,
                message=f"Task [{node.id}] information has been updated.",
                details={"task": node.model_dump()},
            )

        if action.name == "update_task_instruction":
            task_id = self._coerce_int(params.get("task_id"), "task_id")
            instruction = params.get("instruction")
            if not instruction:
                raise ValueError("update_task_instruction requires an instruction.")
            existing = tree.nodes.get(task_id)
            if (
                existing
                and (existing.instruction or "").strip() == str(instruction).strip()
            ):
                return ActionExecutionResult(
                    action=action,
                    success=True,
                    message=(
                        f"Task [{task_id}] instruction is already up to date; no change applied."
                    ),
                    details={"task": existing.model_dump(), "no_change": True},
                )
            node = self._repo.update_task(
                plan_id,
                task_id,
                instruction=instruction,
            )
            return ActionExecutionResult(
                action=action,
                success=True,
                message=f"Task [{node.id}] instructions have been updated.",
                details={"task": node.model_dump()},
            )

        if action.name == "move_task":
            task_id = self._coerce_int(params.get("task_id"), "task_id")
            new_parent_id = params.get("new_parent_id")
            new_position = params.get("new_position")

            if new_parent_id is not None:
                if new_parent_id == task_id:
                    return self._reject(action, "move_task cannot set parent to itself.")
                descendants = self._descendants(tree, task_id)
                if new_parent_id in descendants:
                    return self._reject(
                        action,
                        "move_task would create a cycle by moving a node under its descendant.",
                    )

            node = self._repo.move_task(
                plan_id,
                task_id,
                new_parent_id=new_parent_id,
                new_position=new_position,
            )
            return ActionExecutionResult(
                action=action,
                success=True,
                message=f"Task [{node.id}] has been moved to a new position.",
                details={"task": node.model_dump()},
            )

        if action.name == "delete_task":
            task_id = self._coerce_int(params.get("task_id"), "task_id")
            if not allow_delete_root and task_id in tree.root_node_ids():
                return self._reject(action, "delete_task is not allowed on root nodes.")

            if enforce_dependency_check:
                dependents = self._find_dependents(tree, task_id)
                if dependents:
                    return self._reject(
                        action,
                        f"delete_task is blocked; dependent tasks exist: {dependents}.",
                    )

            has_children = bool(tree.children_ids(task_id))
            allow_subtree_flag = bool(action.metadata.get("allow_delete_subtree"))
            if has_children:
                if not allow_delete_subtree:
                    return self._reject(
                        action,
                        "delete_task is blocked; task has children and subtree deletion is not allowed.",
                    )
                if require_delete_subtree_flag and not allow_subtree_flag:
                    return self._reject(
                        action,
                        "delete_task is blocked; missing metadata.allow_delete_subtree for subtree deletion.",
                    )

            self._repo.delete_task(plan_id, task_id)
            return ActionExecutionResult(
                action=action,
                success=True,
                message=f"Task [{task_id}] and its subtasks have been deleted.",
                details={"task_id": task_id},
            )

        if action.name == "decompose_task":
            decomposer = self._plan_decomposer or PlanDecomposer(repo=self._repo)
            settings = getattr(decomposer, "settings", None)
            if settings is not None and getattr(settings, "model", None) is None:
                return self._reject(
                    action,
                    "decompose_task is unavailable; no decomposition model configured.",
                )

            expand_depth = params.get("expand_depth")
            node_budget = params.get("node_budget")
            allow_existing_children = params.get("allow_existing_children")
            allow_web_search = params.get("allow_web_search")
            if not allow_decompose_web_search:
                allow_web_search = False

            task_id = params.get("task_id")
            if task_id is None:
                result = decomposer.run_plan(
                    plan_id,
                    max_depth=expand_depth,
                    node_budget=node_budget,
                    allow_web_search=allow_web_search,
                )
            else:
                result = decomposer.decompose_node(
                    plan_id,
                    self._coerce_int(task_id, "task_id"),
                    expand_depth=expand_depth,
                    node_budget=node_budget,
                    allow_existing_children=allow_existing_children,
                    allow_web_search=allow_web_search,
                )

            created_count = len(result.created_tasks)
            message = (
                f"Generated {created_count} subtasks."
                if created_count
                else "No new subtasks were generated."
            )
            if result.stopped_reason:
                message += f" Stop reason: {result.stopped_reason}."
            details = {
                "plan_id": plan_id,
                "mode": result.mode,
                "processed_nodes": result.processed_nodes,
                "created": [node.model_dump() for node in result.created_tasks],
                "failed_nodes": result.failed_nodes,
                "stopped_reason": result.stopped_reason,
                "stats": result.stats,
            }
            return ActionExecutionResult(
                action=action,
                success=True,
                message=message,
                details=details,
            )

        return self._reject(action, f"Unsupported task action: {action.name}")

    def _resolve_create_position(
        self,
        tree: PlanTree,
        parent_id: Optional[int],
        position_value: Any,
        anchor_task_id: Any,
        anchor_position: Any,
        insert_before: Any,
        insert_after: Any,
    ) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        position: Optional[int] = None
        if anchor_task_id is not None:
            anchor_task_id = self._coerce_int(anchor_task_id, "anchor_task_id")
        if anchor_position is not None and not isinstance(anchor_position, str):
            raise ValueError("anchor_position must be a string.")
        if isinstance(anchor_position, str):
            anchor_position = anchor_position.strip().lower() or None

        if position_value is not None:
            if isinstance(position_value, str):
                position_str = position_value.strip()
                if position_str:
                    parts = position_str.split(":", 1)
                    keyword = parts[0].strip().lower()
                    if keyword in {"before", "after"}:
                        if len(parts) < 2 or not parts[1].strip():
                            raise ValueError(
                                "position must follow the format 'before:<task_id>' or 'after:<task_id>'."
                            )
                        candidate_id = self._coerce_int(parts[1].strip(), "position")
                        if anchor_task_id is not None and anchor_task_id != candidate_id:
                            raise ValueError(
                                "anchor_task_id does not match the task referenced in position."
                            )
                        if anchor_position is not None and anchor_position != keyword:
                            raise ValueError(
                                "anchor_position does not match the pattern specified in position."
                            )
                        anchor_task_id = candidate_id
                        anchor_position = keyword
                    elif keyword in {"first_child", "last_child"}:
                        if anchor_position is not None and anchor_position != keyword:
                            raise ValueError(
                                "anchor_position does not match the pattern specified in position."
                            )
                        anchor_position = keyword
                    else:
                        position = self._coerce_int(position_str, "position")
                else:
                    position = None
            else:
                position = self._coerce_int(position_value, "position")

        if position is not None and position < 0:
            raise ValueError("position cannot be negative.")

        insert_before_id = (
            self._coerce_int(insert_before, "insert_before")
            if insert_before is not None
            else None
        )
        insert_after_id = (
            self._coerce_int(insert_after, "insert_after")
            if insert_after is not None
            else None
        )

        siblings_parent_key = parent_id if parent_id is not None else None
        siblings = tree.children_ids(siblings_parent_key)

        if insert_before_id is not None and insert_after_id is not None:
            if insert_before_id == insert_after_id:
                raise ValueError(
                    "insert_before and insert_after cannot point to the same task."
                )
            if insert_after_id not in siblings or insert_before_id not in siblings:
                raise ValueError(
                    "insert_before / The task referenced by insert_after does not belong to the target parent node."
                )
            after_idx = siblings.index(insert_after_id)
            before_idx = siblings.index(insert_before_id)
            if after_idx > before_idx:
                raise ValueError("insert_after must appear before insert_before.")
            if anchor_task_id is not None and anchor_task_id not in {
                insert_after_id,
                insert_before_id,
            }:
                raise ValueError(
                    "anchor_task_id is inconsistent with insert_before/insert_after."
                )
            anchor_task_id = insert_after_id
            anchor_position = "after"
        else:
            if insert_before_id is not None:
                if anchor_task_id is not None and anchor_task_id != insert_before_id:
                    raise ValueError(
                        "anchor_task_id points to a different task than insert_before."
                    )
                if insert_before_id not in siblings:
                    raise ValueError(
                        "The task referenced by insert_before does not belong to the target parent node."
                    )
                anchor_task_id = insert_before_id
                anchor_position = "before"
            if insert_after_id is not None:
                if anchor_task_id is not None and anchor_task_id != insert_after_id:
                    raise ValueError(
                        "anchor_task_id points to a different task than insert_after."
                    )
                if insert_after_id not in siblings:
                    raise ValueError(
                        "The task referenced by insert_after does not belong to the target parent node."
                    )
                anchor_task_id = insert_after_id
                anchor_position = "after"

        if anchor_position is not None:
            valid_anchor_positions = {"before", "after", "first_child", "last_child"}
            if anchor_position not in valid_anchor_positions:
                raise ValueError(
                    "Invalid anchor_position; only before, after, first_child, last_child are supported."
                )

        return position, anchor_task_id, anchor_position
