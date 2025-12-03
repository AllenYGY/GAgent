from __future__ import annotations

import pytest

from app.services.agents.simulation.models import (
    ActionSpec,
    ChatAgentTurn,
    JudgeVerdict,
    SimulationRunConfig,
    SimulationRunState,
    SimulatedUserTurn,
)
from app.services.agents.simulation.orchestrator import SimulationOrchestrator
from app.services.plans.plan_session import PlanSession
from app.services.foundation.settings import get_settings


class StubSimulatedUser:
    def __init__(self, plan_session: PlanSession) -> None:
        self.plan_session = plan_session

    async def generate_turn(self, *, improvement_goal, previous_turns, **kwargs):
        return SimulatedUserTurn(
            message="Simulated user message",
            desired_action=ActionSpec(kind="plan_operation", name="create_plan", parameters={"title": "Demo"}),
            raw_response={"user_message": "Simulated user message"},
        )


class StubJudge:
    async def evaluate(self, **kwargs):
        return JudgeVerdict(
            alignment="aligned",
            explanation="Actions align.",
            confidence=0.9,
            raw_response={"alignment": "aligned"},
        )


@pytest.mark.asyncio
async def test_orchestrator_run_turn(monkeypatch):
    plan_session = PlanSession()
    sim_user = StubSimulatedUser(plan_session)
    judge = StubJudge()
    orchestrator = SimulationOrchestrator(
        plan_session=plan_session,
        sim_user_agent=sim_user,  # type: ignore[arg-type]
        judge_agent=judge,  # type: ignore[arg-type]
    )

    class FakeStep:
        def __init__(self) -> None:
            self.action = ActionSpec(
                kind="plan_operation",
                name="create_plan",
                parameters={"title": "Demo"},
            )
            self.success = True
            self.message = "Action executed"

    class FakeResult:
        def __init__(self) -> None:
            self.reply = "Assistant reply"
            self.steps = [FakeStep()]

        def model_dump(self):
            return {"llm_reply": self.reply, "steps": [step.message for step in self.steps]}

    async def fake_chat(self, message: str, state: SimulationRunState):
        result = FakeResult()
        turn = ChatAgentTurn(
            reply=result.reply,
            actions=[
                ActionSpec(
                    kind="plan_operation",
                    name="create_plan",
                    parameters={"title": "Demo"},
                    success=True,
                    result_message="Action executed",
                )
            ],
            raw_response={"llm_reply": result.reply},
        )
        return result, turn

    monkeypatch.setattr(
        SimulationOrchestrator,
        "_run_chat_agent",
        fake_chat,
        raising=False,
    )

    snapshots: list[dict] = []

    monkeypatch.setattr(
        SimulationOrchestrator,
        "_export_plan_snapshot",
        lambda self, **kwargs: snapshots.append(kwargs),
        raising=False,
    )

    state = SimulationRunState(run_id="test-run", config=SimulationRunConfig(max_turns=3))
    turn = await orchestrator.run_turn(state)

    default_goal = getattr(
        get_settings(),
        "sim_default_goal",
        "Refine the currently bound plan to better achieve the user's objectives.",
    )

    assert turn.index == 1
    assert len(state.turns) == 1
    assert turn.judge is not None
    assert turn.judge.alignment == "aligned"
    assert state.config.improvement_goal == default_goal
    assert turn.goal == default_goal
    assert turn.chat_agent.actions[0].success is True
    assert turn.chat_agent.actions[0].result_message == "Action executed"
    assert turn.simulated_user_message_id is None
    assert turn.chat_agent_message_id is None
    assert snapshots and snapshots[0]["run_id"] == "test-run"


@pytest.mark.asyncio
async def test_orchestrator_persists_chat_messages(monkeypatch):
    plan_session = PlanSession()
    sim_user = StubSimulatedUser(plan_session)
    judge = StubJudge()
    orchestrator = SimulationOrchestrator(
        plan_session=plan_session,
        sim_user_agent=sim_user,  # type: ignore[arg-type]
        judge_agent=judge,  # type: ignore[arg-type]
    )

    class FakeStep:
        def __init__(self) -> None:
            self.action = ActionSpec(
                kind="plan_operation",
                name="create_plan",
                parameters={"title": "Demo"},
            )
            self.success = True
            self.message = "Action executed"
            self.details = {
                "summary": "Created demo plan",
                "parameters": {"title": "Demo"},
                "result": {"id": 123},
            }

    class FakeResult:
        def __init__(self) -> None:
            self.reply = "Assistant reply"
            self.steps = [FakeStep()]
            self.actions_summary = [
                {
                    "order": 1,
                    "kind": "plan_operation",
                    "name": "create_plan",
                    "success": True,
                    "message": "Action executed",
                }
            ]
            self.success = True
            self.errors = []
            self.bound_plan_id = 7
            self.plan_outline = "Outline"
            self.plan_persisted = True
            self.primary_intent = "create_plan"
            self.job_id = None
            self.job_type = None

        def model_dump(self):
            return {"reply": self.reply}

    async def fake_chat(self, message: str, state: SimulationRunState):
        result = FakeResult()
        turn = ChatAgentTurn(
            reply=result.reply,
            actions=[
                ActionSpec(
                    kind="plan_operation",
                    name="create_plan",
                    parameters={"title": "Demo"},
                    success=True,
                    result_message="Action executed",
                )
            ],
            raw_response={"llm_reply": result.reply},
        )
        return result, turn

    monkeypatch.setattr(
        SimulationOrchestrator,
        "_run_chat_agent",
        fake_chat,
        raising=False,
    )

    message_calls = []
    snapshots: list[dict] = []

    def fake_save(session_id, role, content, metadata):
        message_calls.append((session_id, role, content, metadata))
        return 101 if role == "user" else 202

    monkeypatch.setattr(
        "app.services.agents.simulation.orchestrator._save_chat_message",
        fake_save,
    )

    monkeypatch.setattr(
        SimulationOrchestrator,
        "_export_plan_snapshot",
        lambda self, **kwargs: snapshots.append(kwargs),
        raising=False,
    )

    state = SimulationRunState(
        run_id="persist-run",
        config=SimulationRunConfig(max_turns=1, session_id="session-1"),
    )
    turn = await orchestrator.run_turn(state)

    assert turn.simulated_user_message_id == 101
    assert turn.chat_agent_message_id == 202
    assert len(message_calls) == 2

    user_call = message_calls[0]
    assistant_call = message_calls[1]

    assert user_call[1] == "user"
    assert assistant_call[1] == "assistant"

    user_metadata = user_call[3]
    assert user_metadata["simulation"] is True
    assert user_metadata["simulation_role"] == "simulated_user"
    assert user_metadata["simulation_run_id"] == state.run_id
    assert user_metadata["simulation_turn_index"] == 1
    assert "simulation_desired_action" in user_metadata

    assistant_metadata = assistant_call[3]
    assert assistant_metadata["simulation"] is True
    assert assistant_metadata["simulation_role"] == "chat_agent"
    assert assistant_metadata["simulation_run_id"] == state.run_id
    assert assistant_metadata["simulation_turn_index"] == 1
    assert assistant_metadata["simulation_user_message_id"] == 101
    assert isinstance(assistant_metadata["simulation_actions"], list)
    assert assistant_metadata["simulation_judge"]["alignment"] == "aligned"
    assert snapshots and snapshots[0]["run_id"] == "persist-run"
