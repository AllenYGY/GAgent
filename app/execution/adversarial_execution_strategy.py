"""
Adversarial Execution Strategy (deprecated).

The original adversarial evaluation flow depends on evaluation modules that are
no longer available. This wrapper preserves the public API but executes tasks
using the base executor without adversarial scoring.
"""

import logging
from typing import Any, Dict, Optional

from ..interfaces import TaskRepository
from ..models import TaskExecutionResult
from .base_executor import BaseTaskExecutor

logger = logging.getLogger(__name__)


class AdversarialExecutionStrategy:
    """Execution strategy wrapper without adversarial evaluation."""

    def __init__(self, repo: Optional[TaskRepository] = None):
        self.base_executor = BaseTaskExecutor(repo)

    def execute(
        self,
        task,
        max_iterations: int = 3,
        max_rounds: int = 3,
        quality_threshold: float = 0.8,
        improvement_threshold: float = 0.1,
        use_context: bool = False,
        context_options: Optional[Dict[str, Any]] = None,
        evaluation_config: Optional[Any] = None,
    ) -> TaskExecutionResult:
        logger.info("Adversarial evaluation disabled; running base execution.")
        return self.base_executor.execute_legacy_task(
            task,
            use_context=use_context,
            context_options=context_options,
        )
