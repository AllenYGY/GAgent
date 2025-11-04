from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from app.services.llm.llm_service import LLMService, get_llm_service
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

    def _plan_outline(self) -> str:
        try:
            return self.plan_session.outline(max_depth=4, max_nodes=80)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to produce plan outline: %s", exc)
            return "(plan outline unavailable)"

    async def generate_turn(
        self,
        *,
        improvement_goal: Optional[str],
        previous_turns: Iterable[SimulatedTurn],
    ) -> SimulatedUserTurn:
        """Generate the next simulated user message and desired action."""
        prompt = build_simulated_user_prompt(
            plan_outline=self._plan_outline(),
            improvement_goal=improvement_goal,
            previous_turns=previous_turns,
        )
        logger.debug("Simulated user prompt:\n%s", prompt)
        response = await self.llm_service.chat_async(prompt, model=self.model)
        logger.debug("Simulated user raw response: %s", response)

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
                action = ActionSpec(**action_payload)
            except Exception as exc:
                logger.warning("Failed to parse desired_action: %s", exc)

        return SimulatedUserTurn(
            message=message,
            desired_action=action,
            raw_response=payload,
        )
