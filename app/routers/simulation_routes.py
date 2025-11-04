"""Simulation endpoints for the simulated user mode."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.services.foundation.settings import get_settings
from app.services.agents.simulation.runtime import SimulationRegistry, format_run_summary
from app.services.agents.simulation.models import SimulationRunConfig, SimulationRunState

from . import register_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _create_orchestrator():
    from app.services.agents.simulation.orchestrator import SimulationOrchestrator  # pragma: no cover - lazy import

    return SimulationOrchestrator()


simulation_registry = SimulationRegistry(_create_orchestrator)


class SimulationRunRequest(BaseModel):
    session_id: Optional[str] = None
    plan_id: Optional[int] = None
    max_turns: Optional[int] = Field(default=None, ge=1, le=20)
    auto_advance: bool = True


class SimulationAdvanceRequest(BaseModel):
    auto_continue: bool = False


def _serialize_state(state: SimulationRunState) -> Dict[str, Any]:
    payload = state.model_dump()
    payload["remaining_turns"] = state.remaining_turns
    return payload


@router.post("/run")
async def start_simulation(request: SimulationRunRequest) -> Dict[str, Any]:
    settings = get_settings()
    default_turns = getattr(settings, "sim_default_turns", 5)
    max_turn_cap = getattr(settings, "sim_max_turns", 10)
    requested_turns = request.max_turns or default_turns
    max_turns = min(max(requested_turns, 1), max_turn_cap)
    default_goal_text = getattr(
        settings,
        "sim_default_goal",
        "Refine the currently bound plan to better achieve the user's objectives.",
    )

    config = SimulationRunConfig(
        session_id=request.session_id,
        plan_id=request.plan_id,
        improvement_goal=default_goal_text,
        max_turns=max_turns,
        auto_advance=request.auto_advance,
    )
    state = await simulation_registry.create_run(config)

    if config.auto_advance:
        asyncio.create_task(_auto_run_background(state.run_id))

    return {"run": _serialize_state(state)}


async def _auto_run_background(run_id: str) -> None:
    try:
        await simulation_registry.auto_run(run_id)
    except Exception as exc:  # pragma: no cover - debug helper
        logger.exception("Auto simulation run %s failed: %s", run_id, exc)


@router.get("/run/{run_id}")
async def get_simulation(run_id: str) -> Dict[str, Any]:
    state = await simulation_registry.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return {"run": _serialize_state(state)}


@router.get("/run/{run_id}/export", response_class=PlainTextResponse)
async def export_simulation(run_id: str) -> PlainTextResponse:
    state = await simulation_registry.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return PlainTextResponse(format_run_summary(state))


@router.post("/run/{run_id}/advance")
async def advance_simulation(
    run_id: str,
    request: SimulationAdvanceRequest,
) -> Dict[str, Any]:
    state = await simulation_registry.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    if state.status in {"finished", "cancelled", "error"}:
        return {"run": _serialize_state(state)}

    updated_state = await simulation_registry.advance_run(run_id)

    if request.auto_continue and updated_state.status not in {"finished", "cancelled", "error"}:
        asyncio.create_task(_auto_run_background(run_id))

    return {"run": _serialize_state(updated_state)}


@router.post("/run/{run_id}/cancel")
async def cancel_simulation(run_id: str) -> Dict[str, Any]:
    state = await simulation_registry.cancel_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return {"run": _serialize_state(state)}


register_router(
    namespace="simulation",
    version="v1",
    path="/simulation",
    router=router,
    tags=["simulation"],
    description="APIs for running simulated user evaluations.",
)
