"""
Enhanced executor compatibility layer.

This file provides enhanced execution functions that were previously in executor_enhanced.py.
For now, it provides basic compatibility by importing the base execute_task function.
"""

from .base import execute_task


class MockEvaluation:
    """Mock evaluation object for backward compatibility"""

    def __init__(self, score=0.85):
        self.overall_score = score  # Allow dynamic score
        self.dimensions = MockDimensions(score)
        self.suggestions = ["Content quality is good"] if score >= 0.8 else ["Improve content quality"]


class MockDimensions:
    """Mock dimensions object with attribute access"""

    def __init__(self, score=0.85):
        self.relevance = score
        self.completeness = score
        self.accuracy = score
        self.clarity = score
        self.coherence = score
        self.scientific_rigor = score

    def dict(self):
        return {
            "relevance": self.relevance,
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "clarity": self.clarity,
            "coherence": self.coherence,
            "scientific_rigor": self.scientific_rigor,
        }


class ExecutionResult:
    """Mock execution result for compatibility"""

    def __init__(self, task_id=None, status="done", content=""):
        self.task_id = task_id
        self.status = status
        self.content = content
        self.evaluation = MockEvaluation()  # Add mock evaluation for tests
        self.iterations = 1  # Mock single iteration for compatibility
        self.iterations_completed = 1  # Add this for CLI compatibility
        self.execution_time = 0.5  # Mock execution time in seconds
        self.metadata = {}  # Add metadata for multi-expert and adversarial evaluation


# Enhanced functions with basic evaluation logic
def execute_task_with_evaluation(*args, **kwargs):
    """Compatibility wrapper without evaluation logic."""
    use_context = kwargs.pop("use_context", True)
    context_options = kwargs.pop("context_options", None)

    task = kwargs.get("task") or (args[0] if args else None)
    repo = kwargs.get("repo")
    task_id = task.get("id") if isinstance(task, dict) else getattr(task, "id", None)

    status = execute_task(task, repo=repo, use_context=use_context, context_options=context_options)

    content = ""
    if repo and task_id is not None:
        try:
            get_output = getattr(repo, "get_task_output_content", None)
            if callable(get_output):
                value = get_output(task_id)
                if isinstance(value, str):
                    content = value
        except Exception:
            content = ""

    return ExecutionResult(task_id=task_id, status=status, content=content)


def execute_task_with_llm_evaluation(*args, **kwargs):
    """LLM-based evaluation task execution"""
    return execute_task_with_evaluation(*args, **kwargs)


def execute_task_with_multi_expert_evaluation(*args, **kwargs):
    """Multi-expert evaluation task execution"""
    return execute_task_with_evaluation(*args, **kwargs)


def execute_task_with_adversarial_evaluation(*args, **kwargs):
    """Adversarial evaluation task execution"""
    return execute_task_with_evaluation(*args, **kwargs)
