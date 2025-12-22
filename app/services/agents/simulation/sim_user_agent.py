from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

from app.services.llm.llm_service import LLMService, get_llm_service
from app.services.plans.action_catalog import build_action_catalog
from app.services.plans.action_schema import normalize_action
from app.services.plans.plan_session import PlanSession
from app.services.foundation.settings import get_settings

from .models import ActionSpec, SimulatedTurn, SimulatedUserTurn
from .prompts import DEFAULT_SIM_USER_MODEL, build_simulated_user_prompt

logger = logging.getLogger(__name__)


class SimulatedUserAgent:
    """Agent that simulates a user interacting with the chat assistant."""

    def __init__(
        self,
        *,
        plan_session: Optional[PlanSession] = None,
        llm_service: Optional[LLMService] = None,
        model: Optional[str] = None,
    ) -> None:
        self.plan_session = plan_session or PlanSession()
        self.llm_service = llm_service or get_llm_service()
        settings = get_settings()
        self.model = model or getattr(settings, "sim_user_model", DEFAULT_SIM_USER_MODEL)
        self.top_k: Optional[int] = getattr(settings, "sim_user_top_k", None)

    def _plan_outline(self) -> str:
        try:
            return self.plan_session.outline()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to produce plan outline: %s", exc)
            return "(plan outline unavailable)"

    async def generate_turn(
        self,
        *,
        improvement_goal: Optional[str],
        previous_turns: Iterable[SimulatedTurn],
        max_actions: int = 2,
        allow_execute_actions: bool = True,
        run_id: Optional[str] = None,
        turn_index: Optional[int] = None,
    ) -> SimulatedUserTurn:
        """Generate the next simulated user message and desired action."""
        allow_web_search = getattr(self.plan_session, "allow_web_search", True)
        allow_rerun_task = getattr(self.plan_session, "allow_rerun_task", True)
        allow_graph_rag = getattr(self.plan_session, "allow_graph_rag", True)
        allow_show_tasks = getattr(self.plan_session, "allow_show_tasks", False)
        action_catalog = build_action_catalog(
            self.plan_session.plan_id is not None,
            allow_execute=allow_execute_actions,
            allow_web_search=allow_web_search,
            allow_rerun_task=allow_rerun_task,
            allow_graph_rag=allow_graph_rag,
            allow_show_tasks=allow_show_tasks,
        )
        base_prompt = build_simulated_user_prompt(
            plan_outline=self._plan_outline(),
            improvement_goal=improvement_goal,
            previous_turns=previous_turns,
            action_catalog=action_catalog,
            max_actions=max_actions,
        )

        chat_kwargs = {"model": self.model, "temperature": 0.3}
        if self.top_k is not None:
            chat_kwargs["top_k"] = self.top_k

        payload = None
        action = None
        message = ""
        last_response = ""

        for attempt in range(2):
            prompt = base_prompt
            if attempt == 1:
                prompt = (
                    base_prompt
                    + "\n\nSystem note: Your last suggestion repeated an earlier request. "
                    "Generate a different ACTION not already proposed in prior turns; avoid repeating the same task updates/creates."
                )
            if attempt == 0:
                self._save_prompt(run_id=run_id, turn_index=turn_index, prompt=prompt)
            logger.debug("Simulated user prompt (attempt %s):\n%s", attempt + 1, prompt)
            response = await self.llm_service.chat_async(
                prompt,
                **chat_kwargs,
            )
            last_response = response
            logger.debug("Simulated user raw response (attempt %s): %s", attempt + 1, response)

            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                logger.error("Simulated user response is not valid JSON: %s", exc)
                raise

            message = (payload.get("user_message") or "").strip()
            if not message:
                raise ValueError("Simulated user response missing 'user_message'")

            action_payload = payload.get("desired_action")
            action = None
            if isinstance(action_payload, dict):
                try:
                    normalized_params = normalize_action(
                        action_payload.get("kind", ""), action_payload.get("name", ""), action_payload.get("parameters", {}) or {}
                    )
                    action = ActionSpec(
                        kind=action_payload.get("kind", ""),
                        name=action_payload.get("name", ""),
                        parameters=normalized_params,
                        blocking=action_payload.get("blocking", True),
                        order=action_payload.get("order"),
                    )
                except Exception as exc:
                    logger.warning("Failed to parse desired_action: %s", exc)

            pre_dedupe = action
            # Post-process to avoid duplicate creates when an equivalent task already exists
            try:
                action = self._dedupe_create(action)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Deduplication check failed, leaving action unchanged: %s", exc)
            else:
                if action and pre_dedupe and (
                    action.kind != pre_dedupe.kind
                    or action.name != pre_dedupe.name
                    or action.parameters != pre_dedupe.parameters
                ):
                    # If we rewrote the intent, rewrite the user_message to match.
                    if (
                        action.kind == "task_operation"
                        and action.name == "update_task_instruction"
                        and isinstance(action.parameters, dict)
                    ):
                        task_id = action.parameters.get("task_id")
                        instr = action.parameters.get("instruction") or ""
                        message = (
                            f"I want to update existing task [{task_id}] to refine its instruction: {instr}"
                            if task_id
                            else f"I want to update an existing task to refine its instruction: {instr}"
                        )
                    else:
                        # Generic fallback: restate the normalized action
                        message = (
                            f"I want to perform {action.kind}/{action.name} with parameters {json.dumps(action.parameters, ensure_ascii=False)}"
                        )

            if action is None:
                break
            if not self._is_duplicate_action(action, previous_turns):
                break
            if attempt == 0:
                logger.info(
                    "Sim user detected duplicate action; retrying with anti-repeat hint (attempt %s)",
                    attempt + 1,
                )
                # Try again with anti-repeat hint on second loop iteration
                action = None
                continue
            # On final attempt, accept even if duplicate to avoid returning empty
            logger.info("Sim user duplicate action persisted after retry; returning as-is.")
            break

        return SimulatedUserTurn(
            message=message,
            desired_action=action,
            raw_response=payload or {"user_message": message, "raw": last_response},
        )

    def _save_prompt(self, *, run_id: Optional[str], turn_index: Optional[int], prompt: str) -> None:
        """Persist the prompt sent to the simulated user model for debugging/analysis."""
        if not run_id or turn_index is None:
            return
        try:
            settings = get_settings()
            base_dir = Path(
                os.getenv(
                    "SIM_USER_PROMPT_OUTPUT_DIR",
                    getattr(
                        settings,
                        "sim_prompt_output_dir",
                        Path(__file__).resolve().parents[3]
                        / "data"
                        / "simulation_prompts",
                    ),
                )
            )
            run_dir = Path(base_dir) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            filename = f"turn_{turn_index:02d}_prompt.txt"
            path = run_dir / filename
            header = [
                f"Simulation run: {run_id}",
                f"Turn index    : {turn_index}",
                "",
                "Simulated user prompt:",
                "",
            ]
            content = "\n".join(header) + prompt.strip() + "\n"
            path.write_text(content, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to save simulated user prompt: %s", exc)

    def _dedupe_create(self, action: Optional[ActionSpec]) -> Optional[ActionSpec]:
        """If a create_task targets an existing sibling with same name, convert to update."""
        if action is None:
            return None
        if not (
            action.kind == "task_operation"
            and action.name == "create_task"
            and isinstance(action.parameters, dict)
        ):
            return action
        params = action.parameters
        parent_id = params.get("parent_id")
        raw_name = params.get("name")
        if not raw_name:
            return action
        name_norm = str(raw_name).strip().lower()
        tree = self.plan_session.current_tree() or self.plan_session.refresh()
        if tree is None:
            return action
        for node in tree.nodes.values():
            node_name_norm = (node.name or "").strip().lower()
            if node.parent_id == parent_id and node_name_norm == name_norm:
                instr = params.get("instruction")
                new_params = {"task_id": node.id}
                if instr:
                    new_params["instruction"] = instr
                logger.info(
                    "Sim user dedup: convert create_task -> update_task_instruction on existing node %s",
                    node.id,
                )
                return ActionSpec(
                    kind="task_operation",
                    name="update_task_instruction",
                    parameters=new_params,
                    blocking=action.blocking,
                    order=action.order,
                )
        return action

    def _is_duplicate_action(
        self, action: ActionSpec, previous_turns: Iterable[SimulatedTurn]
    ) -> bool:
        """Detect whether the proposed action matches any prior simulated user action."""
        if action is None:
            return False
        try:
            current = {
                "kind": action.kind,
                "name": action.name,
                "parameters": action.parameters or {},
            }
            for turn in previous_turns:
                prev = turn.simulated_user.desired_action
                if prev is None:
                    continue
                prev_obj = {
                    "kind": prev.kind,
                    "name": prev.name,
                    "parameters": prev.parameters or {},
                }
                if current == prev_obj:
                    return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Duplicate action check failed: %s", exc)
            return False
        return False
