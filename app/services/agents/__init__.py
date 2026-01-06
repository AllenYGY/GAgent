"""Agent-oriented service helpers."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .simulation import JudgeAgent, SimulatedUserAgent
    from .simulation.orchestrator import SimulationOrchestrator
    from .simulation.runtime import SimulationRegistry

__all__ = [
    "SimulationOrchestrator",
    "SimulationRegistry",
    "SimulatedUserAgent",
    "JudgeAgent",
]


def __getattr__(name):
    if name in {"SimulatedUserAgent", "JudgeAgent", "SimulationOrchestrator", "SimulationRegistry"}:
        from .simulation import (  # pragma: no cover - lazy import
            JudgeAgent,
            SimulatedUserAgent,
        )
        from .simulation.orchestrator import SimulationOrchestrator  # pragma: no cover - lazy import
        from .simulation.runtime import SimulationRegistry  # pragma: no cover - lazy import

        mapping = {
            "SimulatedUserAgent": SimulatedUserAgent,
            "JudgeAgent": JudgeAgent,
            "SimulationOrchestrator": SimulationOrchestrator,
            "SimulationRegistry": SimulationRegistry,
        }
        return mapping[name]
    raise AttributeError(f"module 'app.services.agents' has no attribute {name!r}")


def __dir__():  # pragma: no cover - module metadata helper
    return sorted(__all__)
