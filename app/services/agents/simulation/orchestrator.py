from __future__ import annotations

import logging
from typing import List, Optional

from app.routers.chat_routes import StructuredChatAgent
from app.services.plans.plan_session import PlanSession
from app.services.foundation.settings import get_settings

from .judge_agent import JudgeAgent
from .models import ActionSpec, ChatAgentTurn, SimulationRunState, SimulatedTurn
from .sim_user_agent import SimulatedUserAgent

logger = logging.getLogger(__name__)


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
        agent = StructuredChatAgent(
            plan_session=session,
            history=history,
            session_id=state.config.session_id,
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

    async def run_turn(self, state: SimulationRunState) -> SimulatedTurn:
        """Run a single simulation turn and update state."""
        self._ensure_plan_binding(state.config.plan_id)

        goal = self._resolve_goal(state.config.improvement_goal)

        simulated_user_output = await self.sim_user_agent.generate_turn(
            improvement_goal=goal,
            previous_turns=state.turns,
        )
        logger.info(
            "Simulation run %s turn %s user message: %s",
            state.run_id,
            len(state.turns) + 1,
            _preview(simulated_user_output.message),
        )
        agent_result, chat_turn = await self._run_chat_agent(
            simulated_user_output.message, state
        )
        for idx, step in enumerate(agent_result.steps, start=1):
            logger.info(
                "Simulation run %s turn %s action %s/%s success=%s",
                state.run_id,
                len(state.turns) + 1,
                step.action.kind,
                step.action.name,
                step.success,
            )

        plan_outline = self.plan_session.outline(max_depth=4, max_nodes=80)

        judge_verdict = await self.judge_agent.evaluate(
            plan_outline=plan_outline,
            improvement_goal=goal,
            simulated_user_action=simulated_user_output.desired_action,
            chat_turn=chat_turn,
        )
        logger.info(
            "Simulation run %s turn %s judge=%s",
            state.run_id,
            len(state.turns) + 1,
            judge_verdict.alignment,
        )

        state.config.improvement_goal = goal
        turn = SimulatedTurn(
            index=len(state.turns) + 1,
            simulated_user=simulated_user_output,
            chat_agent=chat_turn,
            judge=judge_verdict,
            goal=goal,
        )
        state.append_turn(turn)
        return turn
