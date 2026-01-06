"""
Multi-Expert Execution Strategy (deprecated).

The original multi-expert evaluation depends on evaluation modules that are no
longer available. This wrapper keeps the API but executes tasks once without
expert evaluation.
"""

import logging
from typing import Any, Dict, Optional

from ..interfaces import TaskRepository
from ..models import TaskExecutionResult
from .base_executor import BaseTaskExecutor

logger = logging.getLogger(__name__)


class MultiExpertExecutionStrategy:
    """Execution strategy wrapper without multi-expert evaluation."""

    def __init__(self, repo: Optional[TaskRepository] = None):
        self.base_executor = BaseTaskExecutor(repo)

    def execute(
        self,
        task,
        max_iterations: int = 3,
        quality_threshold: float = 0.8,
        experts: Optional[list] = None,
        use_context: bool = False,
        context_options: Optional[Dict[str, Any]] = None,
        evaluation_config: Optional[Any] = None,
    ) -> TaskExecutionResult:
        logger.info("Multi-expert evaluation disabled; running base execution.")
        return self.base_executor.execute_legacy_task(
            task,
            use_context=use_context,
            context_options=context_options,
        )
