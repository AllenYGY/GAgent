from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.llm import LLMClient
from app.repository.plan_repository import PlanRepository
from app.services.llm.llm_service import LLMService
from app.services.llm.structured_response import LLMAction, LLMStructuredResponse, schema_as_json
from app.services.plans.action_catalog import build_action_catalog
from app.services.plans.action_executor import ActionExecutionResult, ActionExecutor
from app.services.plans.plan_models import PlanTree

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefactorLLMConfig:
    provider: Optional[str] = None
    model: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None


@dataclass
class RefactorRunResult:
    plan_id: int
    actions: List[LLMAction]
    results: List[ActionExecutionResult]
    dropped_count: int = 0


class PlanRefactorPromptBuilder:
    """Build the refactor prompt for structured plan actions."""

    def build(
        self,
        plan: PlanTree,
        *,
        allowlist: Sequence[str],
        max_actions: int,
        allow_delete_subtree: bool,
        allow_decompose_web_search: bool,
    ) -> str:
        outline = plan.to_outline(max_depth=6, max_nodes=200)
        allowlist_str = ", ".join(allowlist)
        delete_subtree_rule = (
            "If a task has children, you may delete it only when metadata.allow_delete_subtree=true."
            if allow_delete_subtree
            else "Do NOT delete tasks that have children."
        )
        decompose_rule = (
            "decompose_task may use web search."
            if allow_decompose_web_search
            else "decompose_task must NOT use web search (allow_web_search=false)."
        )

        catalog = build_action_catalog(
            plan_bound=True,
            allow_execute=False,
            allow_web_search=False,
            allow_graph_rag=False,
            allow_springer_nature=False,
            allow_rerun_task=False,
            allow_show_tasks=False,
        )

        prompt_lines = [
            "You are a plan refactor assistant. Improve plan structure using ACTIONs.",
            "Only return valid JSON that matches LLMStructuredResponse.",
            "Do NOT output Markdown or explanations.",
            "",
            "=== RULES ===",
            f"- Allowed task_operation actions: {allowlist_str}.",
            "- update_task_instruction is NOT allowed; use update_task instead.",
            "- delete_task requires metadata.reason and metadata.evidence (list).",
            "- Deletion is a last resort; prefer update/move whenever possible.",
            "- IMPORTANT: If any task depends on the target task, deletion is NOT allowed.",
            f"- {delete_subtree_rule}",
            f"- {decompose_rule}",
            f"- Limit total actions to <= {max_actions}.",
            "",
            "=== PLAN OUTLINE ===",
            outline or "(empty plan)",
            "",
            "=== ACTION CATALOG ===",
            catalog,
            "",
            "=== RESPONSE FORMAT ===",
            schema_as_json(indent=2),
        ]
        return "\n".join(prompt_lines)


class PlanRefactorLLMService:
    """LLM service for refactor prompts returning LLMStructuredResponse."""

    def __init__(
        self,
        *,
        llm: Optional[LLMService] = None,
        config: Optional[RefactorLLMConfig] = None,
    ) -> None:
        cfg = config or RefactorLLMConfig()
        self._model = cfg.model
        if llm is not None:
            self._llm = llm
        else:
            client: Optional[LLMClient] = None
            if any((cfg.provider, cfg.api_url, cfg.api_key, cfg.model)):
                client = LLMClient(
                    provider=cfg.provider,
                    api_key=cfg.api_key,
                    url=cfg.api_url,
                    model=cfg.model,
                )
            self._llm = LLMService(client)

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> LLMStructuredResponse:
        kwargs: Dict[str, Any] = {}
        chosen_model = model or self._model
        if chosen_model:
            kwargs["model"] = chosen_model
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = self._llm.chat(prompt, **kwargs)
        cleaned = _strip_code_fences(response)
        return LLMStructuredResponse.model_validate_json(cleaned)


class PlanRefactor:
    """Run an LLM refactor stage and execute resulting task actions."""

    def __init__(
        self,
        *,
        repo: Optional[PlanRepository] = None,
        llm_service: Optional[PlanRefactorLLMService] = None,
        action_executor: Optional[ActionExecutor] = None,
        prompt_builder: Optional[PlanRefactorPromptBuilder] = None,
        llm_config: Optional[RefactorLLMConfig] = None,
    ) -> None:
        self._repo = repo or PlanRepository()
        self._llm = llm_service or PlanRefactorLLMService(config=llm_config)
        self._action_executor = action_executor or ActionExecutor(repo=self._repo)
        self._prompt_builder = prompt_builder or PlanRefactorPromptBuilder()
        self._llm_config = llm_config or RefactorLLMConfig()

    def run(
        self,
        plan_id: int,
        *,
        allowlist: Sequence[str],
        max_actions: int = 25,
        allow_delete_subtree: bool = False,
        allow_decompose_web_search: bool = False,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        log_dir: Optional[Path] = None,
    ) -> RefactorRunResult:
        tree = self._repo.get_plan_tree(plan_id)
        prompt = self._prompt_builder.build(
            tree,
            allowlist=allowlist,
            max_actions=max_actions,
            allow_delete_subtree=allow_delete_subtree,
            allow_decompose_web_search=allow_decompose_web_search,
        )
        structured = self._llm.generate(
            prompt,
            model=model if model is not None else self._llm_config.model,
            temperature=temperature
            if temperature is not None
            else self._llm_config.temperature,
        )

        actions, dropped = self._filter_actions(
            structured.sorted_actions(),
            allowlist=set(allowlist),
            max_actions=max_actions,
        )

        results = self._action_executor.apply_actions(
            plan_id,
            actions,
            allowlist=set(allowlist),
            allow_delete_subtree=allow_delete_subtree,
            allow_decompose_web_search=allow_decompose_web_search,
        )

        self._write_log(plan_id, actions, results, dropped, log_dir=log_dir)

        return RefactorRunResult(
            plan_id=plan_id,
            actions=actions,
            results=results,
            dropped_count=len(dropped),
        )

    def _filter_actions(
        self,
        actions: Iterable[LLMAction],
        *,
        allowlist: Set[str],
        max_actions: int,
    ) -> Tuple[List[LLMAction], List[Dict[str, Any]]]:
        selected: List[LLMAction] = []
        dropped: List[Dict[str, Any]] = []
        for action in actions:
            if action.kind != "task_operation":
                dropped.append(self._drop_record(action, "Only task_operation actions are allowed."))
                continue
            if action.name not in allowlist:
                dropped.append(
                    self._drop_record(
                        action, f"Action '{action.name}' is not in the allowlist."
                    )
                )
                continue
            if action.name == "delete_task" and not self._has_delete_metadata(action):
                dropped.append(
                    self._drop_record(
                        action,
                        "delete_task requires metadata.reason and metadata.evidence.",
                    )
                )
                continue
            selected.append(action)

        if max_actions and len(selected) > max_actions:
            overflow = selected[max_actions:]
            for action in overflow:
                dropped.append(
                    self._drop_record(action, "Exceeded max_actions limit; action dropped.")
                )
            selected = selected[:max_actions]

        return selected, dropped

    @staticmethod
    def _has_delete_metadata(action: LLMAction) -> bool:
        meta = action.metadata or {}
        reason = meta.get("reason")
        evidence = meta.get("evidence")
        if not isinstance(reason, str) or not reason.strip():
            return False
        if not isinstance(evidence, list) or not evidence:
            return False
        return True

    @staticmethod
    def _drop_record(action: LLMAction, reason: str) -> Dict[str, Any]:
        return {
            "action": action.model_dump(),
            "status": "dropped",
            "reason": reason,
        }

    def _write_log(
        self,
        plan_id: int,
        actions: List[LLMAction],
        results: List[ActionExecutionResult],
        dropped: List[Dict[str, Any]],
        *,
        log_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        log_root = log_dir
        if log_root is None:
            env_dir = os.getenv("REFACTOR_LOG_DIR")
            log_root = Path(env_dir) if env_dir else Path("results/refactor_logs")
        log_root.mkdir(parents=True, exist_ok=True)
        log_path = log_root / f"plan_{plan_id}_refactor_actions.jsonl"

        timestamp = time.time()
        entries: List[Dict[str, Any]] = []
        for record in dropped:
            entry = dict(record)
            entry.update({"plan_id": plan_id, "timestamp": timestamp})
            entries.append(entry)
        for result in results:
            entries.append(
                {
                    "plan_id": plan_id,
                    "timestamp": timestamp,
                    "action": result.action.model_dump(),
                    "status": "success" if result.success else "failed",
                    "rejected": result.rejected,
                    "message": result.message,
                    "details": result.details,
                }
            )

        if not entries:
            return None

        with log_path.open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

        return log_path


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        while lines and lines[0].startswith("```"):
            lines.pop(0)
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        cleaned = "\n".join(lines).strip()
    return cleaned
