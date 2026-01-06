"""
Evaluation Orchestrator (deprecated).

The original evaluation coordination depends on evaluation modules that are no
longer available. This wrapper keeps the API but executes tasks once without
iterative evaluation.
"""

import logging
from typing import Any, Dict, Optional

from ..interfaces import TaskRepository
from ..models import TaskExecutionResult
from .base_executor import BaseTaskExecutor

logger = logging.getLogger(__name__)


class EvaluationOrchestrator:
    """Orchestrates task execution without evaluation."""

    def __init__(self, repo: Optional[TaskRepository] = None):
        self.base_executor = BaseTaskExecutor(repo)

    def execute_with_evaluation(
        self,
        task,
        max_iterations: int = 3,
        quality_threshold: float = 0.8,
        evaluation_config: Optional[Any] = None,
        use_context: bool = False,
        context_options: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        logger.info("Evaluation loop disabled; running base execution.")
        return self.base_executor.execute_legacy_task(
            task,
            use_context=use_context,
            context_options=context_options,
        )
