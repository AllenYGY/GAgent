from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from app.services.llm.llm_service import LLMService, get_llm_service
from app.llm import LLMClient
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
        settings = get_settings()
        if llm_service is not None:
            self.llm_service = llm_service
            self.model = model or getattr(settings, "sim_judge_model", DEFAULT_JUDGE_MODEL)
        else:
            judge_provider = os.getenv("SIM_JUDGE_PROVIDER")
            judge_api_key = os.getenv("SIM_JUDGE_API_KEY")
            judge_api_url = os.getenv("SIM_JUDGE_API_URL")
            judge_model = os.getenv("SIM_JUDGE_MODEL")
            if any([judge_provider, judge_api_key, judge_api_url, judge_model]):
                client = LLMClient(
                    provider=judge_provider,
                    api_key=judge_api_key,
                    url=judge_api_url,
                    model=judge_model or model,
                )
                self.llm_service = LLMService(client=client)
                self.model = judge_model or model or getattr(settings, "sim_judge_model", DEFAULT_JUDGE_MODEL)
            else:
                self.llm_service = get_llm_service()
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
        max_retries = int(os.getenv("SIM_JUDGE_JSON_RETRIES", "1"))
        attempt = 0
        response = ""
        payload: Optional[dict] = None
        while True:
            response = await self.llm_service.chat_async(prompt, **chat_kwargs)
            logger.debug("Judge raw response: %s", response)
            payload = self._parse_json_response(response)
            if payload is not None:
                break
            attempt += 1
            logger.warning(
                "Judge response is not valid JSON (attempt %s/%s).",
                attempt,
                max_retries,
            )
            if attempt > max_retries:
                payload = {
                    "alignment_score": 1,
                    "reason": "Judge returned invalid JSON after retries; marking as misaligned.",
                    "confidence": 0.0,
                }
                break
            prompt = (
                prompt
                + "\n\nREMINDER: Return ONLY a JSON object with keys alignment_score, reason, confidence. No extra text."
            )

        score_value = payload.get("alignment_score") if payload else None
        score: Optional[int] = None
        if isinstance(score_value, (int, float)):
            score = 1 if int(score_value) == 1 else 0

        alignment = (payload.get("alignment", "") if payload else "").strip().lower()
        if score is not None:
            alignment = "misaligned" if score == 1 else "aligned"
        if alignment not in {"aligned", "misaligned", "unclear"}:
            alignment = "unclear"

        explanation = (
            (payload.get("reason") or payload.get("explanation") or "").strip()
            if payload
            else ""
        ) or "No explanation provided."
        confidence_value = payload.get("confidence") if payload else None
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
            raw_response=payload or {"raw_response": response},
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

    @staticmethod
    def _parse_json_response(response: str) -> Optional[dict]:
        text = response.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Strip code fences if present.
        if text.startswith("```"):
            parts = re.split(r"```+", text)
            if len(parts) >= 2:
                text = parts[1].strip()
                if text.lower().startswith("json"):
                    text = text[4:].strip()
        # Extract the first JSON object-like span.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None
        return None
