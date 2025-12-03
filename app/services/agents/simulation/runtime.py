from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, TYPE_CHECKING
from uuid import uuid4

from .models import SimulationRunConfig, SimulationRunState, utcnow

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .orchestrator import SimulationOrchestrator

import logging


logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data" / "simulation_runs"
_OUTPUT_DIR = Path(os.getenv("SIMULATION_RUN_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))
_DEFAULT_SESSION_DIR = Path(__file__).resolve().parents[3] / "data" / "simulation_sessions"
_SESSION_LOG_DIR = Path(
    os.getenv("SIMULATION_SESSION_OUTPUT_DIR", str(_DEFAULT_SESSION_DIR))
)


class SimulationRegistry:
    """In-memory registry that manages simulation runs."""

    def __init__(
        self,
        orchestrator_factory: Optional[Callable[[], "SimulationOrchestrator"]] = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._runs: Dict[str, SimulationRunState] = {}
        self._orchestrators: Dict[str, "SimulationOrchestrator"] = {}
        self._factory = orchestrator_factory or self._default_factory

    async def create_run(self, config: SimulationRunConfig) -> SimulationRunState:
        run_id = uuid4().hex
        run_state = SimulationRunState(run_id=run_id, config=config)
        orchestrator = self._factory()
        async with self._lock:
            self._runs[run_id] = run_state
            self._orchestrators[run_id] = orchestrator
        logger.info(
            "Simulation run %s created (plan_id=%s, max_turns=%s, auto_advance=%s)",
            run_id,
            config.plan_id,
            config.max_turns,
            config.auto_advance,
        )
        self._persist_run(run_state)
        return run_state

    def _default_factory(self) -> "SimulationOrchestrator":
        from .orchestrator import SimulationOrchestrator  # pragma: no cover - lazy import

        return SimulationOrchestrator()

    async def get_run(self, run_id: str) -> Optional[SimulationRunState]:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(self) -> Dict[str, SimulationRunState]:
        async with self._lock:
            return dict(self._runs)

    async def cancel_run(self, run_id: str) -> Optional[SimulationRunState]:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.finish("cancelled")
            logger.info(
                "Simulation run %s cancelled at %s turns", run_id, len(run.turns)
            )
            self._persist_run(run)
            return run

    async def delete_run(self, run_id: str) -> None:
        async with self._lock:
            self._runs.pop(run_id, None)
            self._orchestrators.pop(run_id, None)

    async def advance_run(self, run_id: str) -> SimulationRunState:
        async with self._lock:
            run = self._runs.get(run_id)
            orchestrator = self._orchestrators.get(run_id)
            if run is None or orchestrator is None:
                raise KeyError(f"Simulation run {run_id} not found")
            if run.status in {"finished", "cancelled", "error"}:
                logger.info(
                    "Simulation run %s advance skipped (status=%s)",
                    run_id,
                    run.status,
                )
                return run
            run.mark_running()

        try:
            turn = await orchestrator.run_turn(run)
        except Exception as exc:
            async with self._lock:
                run = self._runs.get(run_id)
                if run is not None:
                    run.error = str(exc)
                    run.finish("error")
                    logger.error(
                        "Simulation run %s errored after %s turns: %s",
                        run_id,
                        len(run.turns),
                        exc,
                    )
                raise

        async with self._lock:
            run = self._runs[run_id]
            # Stop early if this turn is misaligned
            if (
                turn.judge
                and turn.judge.alignment == "misaligned"
                and run.config.stop_on_misalignment
            ):
                run.finish("finished")
                logger.info(
                    "Simulation run %s stopped early due to misalignment at turn %s",
                    run_id,
                    len(run.turns),
                )
            if run.remaining_turns <= 0:
                run.finish("finished")
                logger.info(
                    "Simulation run %s finished (%s turns)", run_id, len(run.turns)
                )
            elif run.status == "running":
                run.status = "idle"
                run.updated_at = utcnow()
                logger.info(
                    "Simulation run %s advanced to turn %s (remaining=%s)",
                    run_id,
                    len(run.turns),
                    run.remaining_turns,
                )
            self._persist_run(run)
            return run

    async def auto_run(self, run_id: str) -> SimulationRunState:
        """Advance a run until depletion or error."""
        while True:
            async with self._lock:
                run = self._runs.get(run_id)
                orchestrator = self._orchestrators.get(run_id)
                if run is None or orchestrator is None:
                    raise KeyError(f"Simulation run {run_id} not found")
                if run.status in {"finished", "cancelled", "error"}:
                    self._persist_run(run)
                    return run
                if run.remaining_turns <= 0:
                    run.finish("finished")
                    logger.info(
                        "Simulation run %s auto-run completed (%s turns)",
                        run_id,
                        len(run.turns),
                    )
                    self._persist_run(run)
                    return run

            await self.advance_run(run_id)

    def _persist_run(self, run: SimulationRunState) -> None:
        try:
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = _OUTPUT_DIR / f"{run.run_id}.json"
            payload = run.model_dump()
            payload["remaining_turns"] = run.remaining_turns
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                )
            summary_path = _OUTPUT_DIR / f"{run.run_id}.txt"
            with summary_path.open("w", encoding="utf-8") as handle:
                handle.write(format_run_summary(run))
            logger.info(
                "Persisted simulation run %s (turns=%s) to %s",
                run.run_id,
                len(run.turns),
                output_path,
            )
            self._persist_session_log(run)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist simulation run %s: %s", run.run_id, exc)

    def _persist_session_log(self, run: SimulationRunState) -> None:
        session_id = run.config.session_id
        if not session_id:
            return
        try:
            _SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = _SESSION_LOG_DIR / f"{session_id}.json"
            turns_payload = []
            for turn in run.turns:
                turns_payload.append(
                    {
                        "index": turn.index,
                        "goal": turn.goal,
                        "simulated_user_message": turn.simulated_user.message,
                        "chat_reply": turn.chat_agent.reply,
                        "judge": turn.judge.model_dump() if turn.judge else None,
                        "simulated_user_message_id": turn.simulated_user_message_id,
                        "chat_agent_message_id": turn.chat_agent_message_id,
                    }
                )
            alignment_payload = [issue.model_dump() for issue in run.alignment_issues]
            payload = {
                "session_id": session_id,
                "run_id": run.run_id,
                "plan_id": run.config.plan_id,
                "status": run.status,
                "max_turns": run.config.max_turns,
                "remaining_turns": run.remaining_turns,
                "alignment_issues": alignment_payload,
                "turns": turns_payload,
            }
            with log_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                )
            logger.info(
                "Persisted session log for %s to %s",
                session_id,
                log_path,
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist session log for %s: %s",
                session_id,
                exc,
            )


def format_run_summary(run: SimulationRunState) -> str:
    lines = [
        f"Simulation Run {run.run_id}",
        f"Status       : {run.status}",
        f"Created at   : {_format_timestamp(run.created_at)}",
        f"Updated at   : {_format_timestamp(run.updated_at)}",
        f"Plan ID      : {run.config.plan_id}",
        f"Max turns    : {run.config.max_turns}",
        f"Auto advance : {run.config.auto_advance}",
        f"Action limit : {run.config.max_actions_per_turn} per turn",
        f"Execute plan : {run.config.enable_execute_actions}",
        "",
    ]
    if run.alignment_issues:
        lines.append("Misaligned turns:")
        for issue in run.alignment_issues:
            status = "delivered" if issue.delivered else "pending"
            lines.append(
                f"  - Turn {issue.turn_index} ({status}): {issue.reason}"
            )
    else:
        lines.append("Misaligned turns: (none)")
    lines.append("")
    if not run.turns:
        lines.append("No turns recorded.")
        return "\n".join(lines)

    for turn in run.turns:
        lines.append(f"Turn {turn.index}")
        lines.append("-" * 60)
        lines.append(f"Goal                : {turn.goal or '(none)'}")
        lines.append("Simulated user:")
        lines.append(turn.simulated_user.message.strip() or "(empty)")
        if turn.simulated_user.desired_action:
            lines.append(
                "Desired ACTION      : "
                f"{turn.simulated_user.desired_action.kind}/"
                f"{turn.simulated_user.desired_action.name}"
            )
            params = turn.simulated_user.desired_action.parameters or {}
            if params:
                lines.append(
                    "Desired parameters  : "
                    f"{json.dumps(params, ensure_ascii=False, default=_json_default)}"
                )
        lines.append("")
        lines.append("Chat agent reply:")
        lines.append(turn.chat_agent.reply.strip() or "(empty)")
        if turn.chat_agent.actions:
            lines.append("Chat agent actions :")
            for action in turn.chat_agent.actions:
                line = f"  - {action.kind}/{action.name}"
                params = action.parameters or {}
                if params:
                    encoded = json.dumps(
                        params,
                        ensure_ascii=False,
                        default=_json_default,
                    )
                    line += f" {encoded}"
                lines.append(line)
        lines.append("")
        lines.append(
            "User message ID     : "
            f"{turn.simulated_user_message_id if turn.simulated_user_message_id is not None else '(not saved)'}"
        )
        lines.append(
            "Assistant message ID: "
            f"{turn.chat_agent_message_id if turn.chat_agent_message_id is not None else '(not saved)'}"
        )
        if turn.judge:
            lines.append("")
            lines.append(
                f"Judge verdict       : {turn.judge.alignment}"
                + (
                    f" (confidence {turn.judge.confidence:.2f})"
                    if isinstance(turn.judge.confidence, (int, float))
                    else ""
                )
            )
            lines.append(f"Judge explanation   : {turn.judge.explanation}")
        lines.append("")
    return "\n".join(lines)


def _json_default(value):  # pragma: no cover - helper for json.dump
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return str(value)


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
