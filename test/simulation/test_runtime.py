from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.agents.simulation.models import (
    ActionSpec,
    ChatAgentTurn,
    JudgeVerdict,
    SimulationRunConfig,
    SimulationRunState,
    SimulatedTurn,
    SimulatedUserTurn,
)
from app.services.agents.simulation.orchestrator import SimulationOrchestrator
from app.services.agents.simulation.runtime import SimulationRegistry


class FakeOrchestrator(SimulationOrchestrator):
    def __init__(self) -> None:
        self.invocations = 0

    async def run_turn(self, state: SimulationRunState):
        self.invocations += 1
        turn = SimulatedTurn(
            index=len(state.turns) + 1,
            simulated_user=SimulatedUserTurn(
                message=f"Turn {self.invocations}",
                desired_action=ActionSpec(
                    kind="plan_operation",
                    name="noop",
                    parameters={"timestamp": datetime.now(timezone.utc)},
                ),
            ),
            chat_agent=ChatAgentTurn(
                reply="Assistant",
                actions=[
                    ActionSpec(
                        kind="plan_operation",
                        name="noop",
                        parameters={"executed_at": datetime.now(timezone.utc)},
                    )
                ],
            ),
            judge=JudgeVerdict(alignment="aligned", explanation="ok"),
        )
        state.append_turn(turn)
        return turn


@pytest.mark.asyncio
async def test_registry_advance_and_finish():
    orchestrator = FakeOrchestrator()
    registry = SimulationRegistry(lambda: orchestrator)
    state = await registry.create_run(SimulationRunConfig(max_turns=2))
    assert state.status == "idle"

    updated = await registry.advance_run(state.run_id)
    assert updated.status == "idle"
    assert len(updated.turns) == 1

    updated = await registry.advance_run(state.run_id)
    assert updated.status == "finished"
    assert len(updated.turns) == 2

    # Further advances should not affect state
    updated = await registry.advance_run(state.run_id)
    assert updated.status == "finished"
    assert len(updated.turns) == 2


@pytest.mark.asyncio
async def test_persisted_run_uses_utc_timestamps(tmp_path, monkeypatch):
    from app.services.agents.simulation import runtime

    orchestrator = FakeOrchestrator()
    registry = SimulationRegistry(lambda: orchestrator)

    monkeypatch.setattr(runtime, "_OUTPUT_DIR", tmp_path)

    state = await registry.create_run(SimulationRunConfig(max_turns=1))
    await registry.advance_run(state.run_id)

    output_path = tmp_path / f"{state.run_id}.json"
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["created_at"].endswith("Z")
    assert payload["updated_at"].endswith("Z")
    for turn in payload["turns"]:
        assert turn["created_at"].endswith("Z")
        parsed = datetime.fromisoformat(turn["created_at"].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert "simulated_user_message_id" in turn
        assert "chat_agent_message_id" in turn
