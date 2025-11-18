from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SimulationStatus = Literal["idle", "running", "finished", "cancelled", "error"]


def utcnow() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ActionSpec(BaseModel):
    """Simplified action schema shared by simulated and chat agents."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    blocking: bool = True
    order: Optional[int] = None
    success: Optional[bool] = None
    result_message: Optional[str] = None

    @field_validator("kind", "name")
    def _not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must be a non-empty string")
        return value.strip()


class SimulatedUserTurn(BaseModel):
    """Result returned by the simulated user agent."""

    message: str
    desired_action: Optional[ActionSpec] = None
    raw_response: Optional[Dict[str, Any]] = None


class ChatAgentTurn(BaseModel):
    """Subset of data returned from StructuredChatAgent."""

    reply: str
    actions: list[ActionSpec] = Field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


class JudgeVerdict(BaseModel):
    """Assessment returned by the judge agent."""

    alignment: Literal["aligned", "misaligned", "unclear"]
    explanation: str
    confidence: Optional[float] = None
    score: Optional[int] = Field(default=None, ge=0, le=1)
    raw_response: Optional[Dict[str, Any]] = None


class AlignmentIssue(BaseModel):
    """Tracks judge feedback for misaligned turns."""

    turn_index: int
    reason: str
    delivered: bool = False


class SimulatedTurn(BaseModel):
    """Single turn captured during simulation."""

    index: int
    simulated_user: SimulatedUserTurn
    chat_agent: ChatAgentTurn
    judge: Optional[JudgeVerdict] = None
    goal: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    simulated_user_message_id: Optional[int] = None
    chat_agent_message_id: Optional[int] = None


class SimulationRunConfig(BaseModel):
    """Configuration used when starting a simulation."""

    session_id: Optional[str] = None
    plan_id: Optional[int] = None
    improvement_goal: Optional[str] = None
    max_turns: int = Field(default=5, ge=1)
    auto_advance: bool = True
    max_actions_per_turn: int = Field(default=2, ge=1, le=2)
    enable_execute_actions: bool = False


class SimulationRunState(BaseModel):
    """In-memory state for a simulation run."""

    run_id: str
    status: SimulationStatus = "idle"
    config: SimulationRunConfig
    turns: list[SimulatedTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    error: Optional[str] = None
    alignment_issues: list[AlignmentIssue] = Field(default_factory=list)

    def append_turn(self, turn: SimulatedTurn) -> None:
        self.turns.append(turn)
        self.updated_at = utcnow()

    @property
    def remaining_turns(self) -> int:
        return max(self.config.max_turns - len(self.turns), 0)

    def finish(self, status: SimulationStatus) -> None:
        if status not in {"finished", "cancelled", "error"}:
            raise ValueError("finish() requires a terminal status")
        self.status = status
        self.updated_at = utcnow()

    def mark_running(self) -> None:
        self.status = "running"
        self.updated_at = utcnow()
