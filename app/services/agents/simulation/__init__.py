"""
Simulation agents package.

Provides helpers to run the Simulated User Mode loop entirely in memory.
"""

from .models import (  # noqa: F401
    ActionSpec,
    ChatAgentTurn,
    JudgeVerdict,
    SimulationRunConfig,
    SimulationRunState,
    SimulationStatus,
    SimulatedTurn,
)
from .prompts import (  # noqa: F401
    build_judge_prompt,
    build_simulated_user_prompt,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_SIM_USER_MODEL,
)
from .sim_user_agent import SimulatedUserAgent  # noqa: F401
from .judge_agent import JudgeAgent  # noqa: F401

__all__ = [
    "ActionSpec",
    "ChatAgentTurn",
    "JudgeVerdict",
    "SimulationRunConfig",
    "SimulationRunState",
    "SimulationStatus",
    "SimulatedTurn",
    "SimulatedUserAgent",
    "JudgeAgent",
    "build_simulated_user_prompt",
    "build_judge_prompt",
    "DEFAULT_SIM_USER_MODEL",
    "DEFAULT_JUDGE_MODEL",
    "SimulationOrchestrator",
    "SimulationRegistry",
]


def __getattr__(name):
    if name == "SimulationOrchestrator":
        from .orchestrator import SimulationOrchestrator  # pragma: no cover - lazy import

        return SimulationOrchestrator
    if name == "SimulationRegistry":
        from .runtime import SimulationRegistry  # pragma: no cover - lazy import

        return SimulationRegistry
    raise AttributeError(f"module 'app.services.agents.simulation' has no attribute {name!r}")


def __dir__():  # pragma: no cover - module metadata
    return sorted(globals().keys() | set(__all__))
