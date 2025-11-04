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

    async def generate_turn(self, *, improvement_goal, previous_turns):
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
