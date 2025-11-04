from __future__ import annotations

import json
import logging
from typing import Optional

from app.services.llm.llm_service import LLMService, get_llm_service
from app.services.foundation.settings import get_settings

from .models import ActionSpec, ChatAgentTurn, JudgeVerdict
from .prompts import DEFAULT_JUDGE_MODEL, build_judge_prompt

logger = logging.getLogger(__name__)


class JudgeAgent:
    """Evaluates alignment between simulated user intent and chat agent actions."""

    def __init__(
        self,
        *,
        llm_service: Optional[LLMService] = None,
        model: Optional[str] = None,
    ) -> None:
        self.llm_service = llm_service or get_llm_service()
        settings = get_settings()
        self.model = model or getattr(settings, "sim_judge_model", DEFAULT_JUDGE_MODEL)

    async def evaluate(
        self,
        *,
        plan_outline: str,
        improvement_goal: Optional[str],
        simulated_user_action: Optional[ActionSpec],
        chat_turn: ChatAgentTurn,
    ) -> JudgeVerdict:
        prompt = build_judge_prompt(
            plan_outline=plan_outline,
            improvement_goal=improvement_goal,
            simulated_user_action=simulated_user_action,
            chat_agent_turn=chat_turn,
        )
        logger.debug("Judge prompt:\n%s", prompt)
        response = await self.llm_service.chat_async(prompt, model=self.model)
        logger.debug("Judge raw response: %s", response)

        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            logger.error("Judge response is not valid JSON: %s", exc)
            raise

        alignment = payload.get("alignment", "").strip().lower()
        if alignment not in {"aligned", "misaligned", "unclear"}:
            alignment = "unclear"

        explanation = (payload.get("explanation") or "").strip() or "No explanation provided."
        confidence_value = payload.get("confidence")
        confidence = None
        if isinstance(confidence_value, (int, float)):
            try:
                confidence = max(0.0, min(float(confidence_value), 1.0))
            except (TypeError, ValueError):
                confidence = None

        return JudgeVerdict(
            alignment=alignment,  # type: ignore[arg-type]
            explanation=explanation,
            confidence=confidence,
            raw_response=payload,
        )
