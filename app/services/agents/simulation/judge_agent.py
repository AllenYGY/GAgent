from __future__ import annotations

import json
import logging
import os
from pathlib import Path
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
        self.top_k: Optional[int] = getattr(settings, "sim_judge_top_k", None)

    async def evaluate(
        self,
        *,
        plan_outline: str,
        improvement_goal: Optional[str],
        simulated_user_action: Optional[ActionSpec],
        chat_turn: ChatAgentTurn,
        run_id: Optional[str] = None,
        turn_index: Optional[int] = None,
    ) -> JudgeVerdict:
        prompt = build_judge_prompt(
            plan_outline=plan_outline,
            improvement_goal=improvement_goal,
            simulated_user_action=simulated_user_action,
            chat_agent_turn=chat_turn,
        )
        self._save_prompt(run_id=run_id, turn_index=turn_index, prompt=prompt)
        logger.debug("Judge prompt:\n%s", prompt)
        chat_kwargs = {"model": self.model}
        if self.top_k is not None:
            chat_kwargs["top_k"] = self.top_k
        response = await self.llm_service.chat_async(prompt, **chat_kwargs)
        logger.debug("Judge raw response: %s", response)

        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            logger.error("Judge response is not valid JSON: %s", exc)
            raise

        score_value = payload.get("alignment_score")
        score: Optional[int] = None
        if isinstance(score_value, (int, float)):
            score = 1 if int(score_value) == 1 else 0

        alignment = payload.get("alignment", "").strip().lower()
        if score is not None:
            alignment = "misaligned" if score == 1 else "aligned"
        if alignment not in {"aligned", "misaligned", "unclear"}:
            alignment = "unclear"

        explanation = (payload.get("reason") or payload.get("explanation") or "").strip() or "No explanation provided."
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
            score=score,
            raw_response=payload,
        )

    def _save_prompt(self, *, run_id: Optional[str], turn_index: Optional[int], prompt: str) -> None:
        """Persist the prompt sent to the judge model for debugging/analysis."""
        if not run_id or turn_index is None:
            return
        try:
            settings = get_settings()
            base_dir = Path(
                os.getenv(
                    "JUDGE_PROMPT_OUTPUT_DIR",
                    getattr(
                        settings,
                        "judge_prompt_output_dir",
                        Path(__file__).resolve().parents[3]
                        / "data"
                        / "judge_prompts",
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
                "Judge prompt:",
                "",
            ]
            content = "\n".join(header) + prompt.strip() + "\n"
            path.write_text(content, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to save judge prompt: %s", exc)
