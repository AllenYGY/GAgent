from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.routers.chat_routes import (
    StructuredChatAgent,
    _save_chat_message,
    plan_decomposer_service,
    plan_executor_service,
)
from app.services.plans.plan_session import PlanSession
from app.services.foundation.settings import get_settings

from .judge_agent import JudgeAgent
from .models import (
    ActionSpec,
    AlignmentIssue,
    ChatAgentTurn,
    JudgeVerdict,
    SimulationRunState,
    SimulatedTurn,
    SimulatedUserTurn,
)
from .sim_user_agent import SimulatedUserAgent

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data" / "simulation_runs"
_SNAPSHOT_DIR = Path(os.getenv("SIMULATION_RUN_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))


def _preview(text: Optional[str], limit: int = 120) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class SimulationOrchestrator:
    """Coordinates simulated user, chat agent, and judge to produce turns."""

    def __init__(
        self,
        *,
        plan_session: Optional[PlanSession] = None,
        sim_user_agent: Optional[SimulatedUserAgent] = None,
        judge_agent: Optional[JudgeAgent] = None,
    ) -> None:
        self.plan_session = plan_session or PlanSession()
        # Feature flag for tool usage; default allow
        self.plan_session.allow_web_search = getattr(self.plan_session, "allow_web_search", True)
        self.plan_session.allow_rerun_task = getattr(self.plan_session, "allow_rerun_task", True)
        self.plan_session.allow_graph_rag = getattr(self.plan_session, "allow_graph_rag", True)
        self.plan_session.allow_show_tasks = getattr(self.plan_session, "allow_show_tasks", False)
        self.sim_user_agent = sim_user_agent or SimulatedUserAgent(plan_session=self.plan_session)
        self.judge_agent = judge_agent or JudgeAgent()
        settings = get_settings()
        self._default_goal = getattr(
            settings,
            "sim_default_goal",
            "Refine the currently bound plan to better achieve the user's objectives.",
        )

    def _ensure_plan_binding(self, plan_id: Optional[int]) -> None:
        if plan_id is None:
            self.plan_session.detach()
            return
        if self.plan_session.plan_id == plan_id and self.plan_session.current_tree() is not None:
            return
        try:
            self.plan_session.bind(plan_id)
        except Exception as exc:
            logger.error("Failed to bind plan session to %s: %s", plan_id, exc)
            raise

    def _resolve_goal(self, goal: Optional[str]) -> str:
        text = (goal or "").strip()
        return text or self._default_goal

    def _capture_plan_outline(self) -> str:
        try:
            return self.plan_session.outline()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to capture plan outline: %s", exc)
            return "(plan outline unavailable)"

    def _export_plan_snapshot(
        self, *, run_id: str, turn_index: int, outline: str
    ) -> None:
        if not run_id:
            return
        try:
            _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{run_id}_turn_{turn_index:02d}_plan_outline.txt"
            path = _SNAPSHOT_DIR / filename
            header = [
                f"Simulation run: {run_id}",
                f"Turn index    : {turn_index}",
                "",
                "Plan outline snapshot:",
                "",
            ]
            content = "\n".join(header) + outline.rstrip() + "\n"
            path.write_text(content, encoding="utf-8")
            logger.info(
                "Saved plan outline snapshot for run %s turn %s to %s",
                run_id,
                turn_index,
                path,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to export plan outline snapshot for run %s turn %s: %s",
                run_id,
                turn_index,
                exc,
            )

    def _build_history(self, state: SimulationRunState) -> List[dict]:
        history: List[dict] = []
        for turn in state.turns:
            history.append(
                {
                    "role": "user",
                    "content": turn.simulated_user.message,
                }
            )
            history.append(
                {
                    "role": "assistant",
                    "content": turn.chat_agent.reply,
                }
            )
        return history[-StructuredChatAgent.MAX_HISTORY :]

    async def _run_chat_agent(
        self, message: str, state: SimulationRunState
    ):
        history = self._build_history(state)
        session = PlanSession(repo=self.plan_session.repo, plan_id=self.plan_session.plan_id)
        if session.plan_id is not None:
            session.refresh()
        extra_context = {
            "simulation_max_actions": state.config.max_actions_per_turn,
            "enable_execute_actions": state.config.enable_execute_actions,
            "allow_web_search": state.config.allow_web_search,
            "allow_rerun_task": state.config.allow_rerun_task,
            "allow_graph_rag": state.config.allow_graph_rag,
            "allow_show_tasks": state.config.allow_show_tasks,
        }
        agent = StructuredChatAgent(
            plan_session=session,
            history=history,
            session_id=state.config.session_id,
            extra_context=extra_context,
            plan_decomposer=plan_decomposer_service,
            plan_executor=plan_executor_service,
        )
        result = await agent.handle(message)
        if self.plan_session.plan_id is not None:
            try:
                self.plan_session.refresh()
            except Exception:  # pragma: no cover - best effort refresh
                logger.debug("Failed to refresh shared plan session after execution.")
        actions = []
        for step in result.steps:
            action = step.action
            actions.append(
                ActionSpec(
                    kind=action.kind,
                    name=action.name,
                    parameters=dict(action.parameters or {}),
                    blocking=action.blocking,
                    order=action.order,
                    success=step.success,
                    result_message=step.message,
                )
            )
        turn = ChatAgentTurn(
            reply=result.reply,
            actions=actions,
            raw_response=result.model_dump(),
        )
        return result, turn

    def _record_simulation_messages(
        self,
        *,
        state: SimulationRunState,
        turn_index: int,
        goal: Optional[str],
        simulated_user: SimulatedUserTurn,
        agent_result: Any,
        chat_turn: ChatAgentTurn,
        judge_verdict: Optional[JudgeVerdict],
    ) -> tuple[Optional[int], Optional[int]]:
        """Persist simulated user and assistant messages via the standard chat pipeline."""
        session_id = state.config.session_id
        if not session_id:
            logger.debug(
                "Simulation run %s has no session_id; skipping chat message persistence",
                state.run_id,
            )
            return None, None

        desired_action_payload = (
            simulated_user.desired_action.model_dump(exclude_none=True)
            if simulated_user.desired_action
            else None
        )
        judge_payload = (
            judge_verdict.model_dump(exclude_none=True) if judge_verdict else None
        )
        plan_id = state.config.plan_id

        def _clean(metadata: Dict[str, Any]) -> Dict[str, Any]:
            return {key: value for key, value in metadata.items() if value is not None}

        user_metadata: Dict[str, Any] = {
            "simulation": True,
            "simulation_role": "simulated_user",
            "simulation_run_id": state.run_id,
            "simulation_turn_index": turn_index,
            "simulation_goal": goal,
            "simulation_desired_action": desired_action_payload,
        }
        if plan_id is not None:
            user_metadata["plan_id"] = plan_id

        user_message_id = _save_chat_message(
            session_id,
            "user",
            simulated_user.message,
            _clean(user_metadata),
        )

        step_payloads: List[Dict[str, Any]] = []
        for idx, step in enumerate(getattr(agent_result, "steps", []) or [], start=1):
            if hasattr(step, "action_payload"):
                payload = step.action_payload  # type: ignore[attr-defined]
            else:
                action = getattr(step, "action", None)
                payload = {
                    "kind": getattr(action, "kind", None),
                    "name": getattr(action, "name", None),
                    "parameters": getattr(action, "parameters", None),
                    "order": getattr(action, "order", idx),
                    "blocking": getattr(action, "blocking", True),
                    "success": getattr(step, "success", None),
                    "message": getattr(step, "message", None),
                    "details": getattr(step, "details", {}),
                }
            step_payloads.append(payload)
        actions_payload = (
            step_payloads
            if step_payloads
            else [action.model_dump(exclude_none=True) for action in chat_turn.actions]
        )
        raw_actions: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []
        for step in getattr(agent_result, "steps", []) or []:
            action = getattr(step, "action", None)
            if hasattr(action, "model_dump"):
                try:
                    raw_actions.append(action.model_dump())
                except Exception:  # pragma: no cover - defensive
                    raw_actions.append(
                        {"kind": getattr(action, "kind", None), "name": getattr(action, "name", None)}
                    )
            if getattr(action, "kind", None) == "tool_operation":
                details = getattr(step, "details", {}) or {}
                tool_results.append(
                    {
                        "name": getattr(action, "name", None),
                        "summary": details.get("summary"),
                        "parameters": details.get("parameters"),
                        "result": details.get("result"),
                    }
                )
        tool_results = [
            entry
            for entry in tool_results
            if isinstance(entry.get("result"), dict)
        ]

        assistant_metadata: Dict[str, Any] = {
            "intent": getattr(agent_result, "primary_intent", None),
            "success": getattr(agent_result, "success", None),
            "errors": getattr(agent_result, "errors", []),
            "plan_id": getattr(agent_result, "bound_plan_id", plan_id),
            "plan_outline": getattr(agent_result, "plan_outline", None),
            "plan_persisted": getattr(agent_result, "plan_persisted", None),
            "status": "completed",
            "raw_actions": raw_actions,
            "actions_summary": getattr(agent_result, "actions_summary", None),
            "tool_results": tool_results or None,
            "simulation": True,
            "simulation_role": "chat_agent",
            "simulation_run_id": state.run_id,
            "simulation_turn_index": turn_index,
            "simulation_goal": goal,
            "simulation_actions": actions_payload,
            "simulation_judge": judge_payload,
            "simulation_desired_action": desired_action_payload,
            "simulation_user_message_id": user_message_id,
        }
        if plan_id is not None and assistant_metadata.get("plan_id") is None:
            assistant_metadata["plan_id"] = plan_id
        if step_payloads:
            assistant_metadata["actions"] = step_payloads
            assistant_metadata["action_list"] = step_payloads
        job_id = getattr(agent_result, "job_id", None)
        job_type = getattr(agent_result, "job_type", None) or "chat_action"
        if job_id:
            assistant_metadata["job_id"] = job_id
            assistant_metadata["job_type"] = job_type
            assistant_metadata["job_status"] = (
                "completed"
                if getattr(agent_result, "success", None)
                else (
                    "failed"
                    if getattr(agent_result, "success", None) is False
                    else None
                )
            )

        assistant_message_id = _save_chat_message(
            session_id,
            "assistant",
            chat_turn.reply,
            _clean(assistant_metadata),
        )

        return user_message_id, assistant_message_id

    def _compose_chat_message(
        self,
        base_message: str,
        state: SimulationRunState,
        desired_action: Optional[ActionSpec] = None,
    ) -> str:
        pending_feedback = [issue for issue in state.alignment_issues if not issue.delivered]
        sections = [base_message]
        if desired_action is not None and desired_action.parameters:
            try:
                params = desired_action.parameters or {}
                extra_lines: List[str] = []
                instr = params.get("instruction")
                if isinstance(instr, str) and instr.strip():
                    if instr.strip() not in base_message:
                        extra_lines.append(f"Instruction detail: {instr.strip()}")
                parent_id = params.get("parent_id")
                if parent_id is not None and str(parent_id) not in base_message:
                    extra_lines.append(f"Parent task id: {parent_id}")
                if extra_lines:
                    sections.append("\n".join(extra_lines))
            except Exception:
                pass
        feedback_lines = [
            f"- Turn {issue.turn_index}: {issue.reason.strip()}"
            for issue in pending_feedback
        ]
        for issue in pending_feedback:
            issue.delivered = True
        if feedback_lines:
            feedback_block = "\n".join(feedback_lines)
            sections.append("Judge feedback to address in this turn:\n" + feedback_block)
        return "\n\n".join(sections)

    async def run_turn(self, state: SimulationRunState) -> SimulatedTurn:
        """Run a single simulation turn and update state."""
        self._ensure_plan_binding(state.config.plan_id)
        try:
            if self.plan_session.plan_id is not None:
                self.plan_session.refresh()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to refresh plan session before turn: %s", exc)

        turn_index = len(state.turns) + 1
        outline_snapshot = self._capture_plan_outline()
        self._export_plan_snapshot(
            run_id=state.run_id,
            turn_index=turn_index,
            outline=outline_snapshot,
        )

        goal = self._resolve_goal(state.config.improvement_goal)
        # propagate tool flags to plan_session (used by sim user)
        self.plan_session.allow_web_search = state.config.allow_web_search
        self.plan_session.allow_rerun_task = state.config.allow_rerun_task
        self.plan_session.allow_graph_rag = state.config.allow_graph_rag
        self.plan_session.allow_show_tasks = state.config.allow_show_tasks

        simulated_user_output = await self.sim_user_agent.generate_turn(
            improvement_goal=goal,
            previous_turns=state.turns,
            max_actions=state.config.max_actions_per_turn,
            allow_execute_actions=state.config.enable_execute_actions,
        )
        logger.info(
            "Simulation run %s turn %s user message: %s",
            state.run_id,
            turn_index,
            _preview(simulated_user_output.message),
        )
        delivered_message = self._compose_chat_message(
            simulated_user_output.message,
            state,
            simulated_user_output.desired_action,
        )
        simulated_user_output.message = delivered_message
        agent_result, chat_turn = await self._run_chat_agent(
            delivered_message, state
        )
        for idx, step in enumerate(agent_result.steps, start=1):
            logger.info(
                "Simulation run %s turn %s action %s/%s success=%s",
                state.run_id,
                turn_index,
                step.action.kind,
                step.action.name,
                step.success,
            )

        plan_outline = self.plan_session.outline()

        judge_verdict = await self.judge_agent.evaluate(
            plan_outline=plan_outline,
            improvement_goal=goal,
            simulated_user_action=simulated_user_output.desired_action,
            chat_turn=chat_turn,
        )
        logger.info(
            "Simulation run %s turn %s judge=%s",
            state.run_id,
            turn_index,
            judge_verdict.alignment,
        )
        if judge_verdict.alignment == "misaligned":
            issue = AlignmentIssue(
                turn_index=turn_index,
                reason=judge_verdict.explanation,
            )
            state.alignment_issues.append(issue)

        state.config.improvement_goal = goal

        user_msg_id: Optional[int] = None
        assistant_msg_id: Optional[int] = None
        try:
            user_msg_id, assistant_msg_id = self._record_simulation_messages(
                state=state,
                turn_index=turn_index,
                goal=goal,
                simulated_user=simulated_user_output,
                agent_result=agent_result,
                chat_turn=chat_turn,
                judge_verdict=judge_verdict,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Simulation run %s turn %s failed to persist chat transcript: %s",
                state.run_id,
                len(state.turns) + 1,
                exc,
            )

        turn = SimulatedTurn(
            index=turn_index,
            simulated_user=simulated_user_output,
            chat_agent=chat_turn,
            judge=judge_verdict,
            goal=goal,
            simulated_user_message_id=user_msg_id,
            chat_agent_message_id=assistant_msg_id,
        )

        state.append_turn(turn)
        return turn
