from __future__ import annotations

from types import SimpleNamespace

from app.repository.plan_repository import PlanRepository
from scripts.pipeline.plan_enrichment_pipeline import _run_enrichment


class DummyDecomposer:
    def __init__(self) -> None:
        self.run_plan_calls = []
        self.graph_rag_calls = []

    def run_plan(self, *args, **kwargs):
        self.run_plan_calls.append((args, kwargs))
        return SimpleNamespace(
            processed_nodes=[1],
            created_tasks=[],
            failed_nodes=[],
            stats={"enriched_nodes": 1, "llm_calls": 1, "graph_rag_calls": 0},
        )

    def enrich_plan_with_shared_graph_rag(self, *args, **kwargs):
        self.graph_rag_calls.append((args, kwargs))
        return SimpleNamespace(
            processed_nodes=[1],
            created_tasks=[],
            failed_nodes=[],
            stats={"enriched_nodes": 1, "llm_calls": 1, "graph_rag_calls": 1},
        )


def test_run_enrichment_dispatches_to_graph_rag_with_warning(
    plan_repo: PlanRepository,
    capsys,
):
    plan = plan_repo.create_plan("Imported web plan")
    root = plan_repo.create_task(plan.id, name="Root", instruction="Refine host prediction")
    assert root.id is not None

    decomposer = DummyDecomposer()

    result = _run_enrichment(
        decomposer=decomposer,
        repo=plan_repo,
        plan_id=plan.id,
        mode="graph_rag_enrich",
        max_depth=2,
        node_budget=5,
        allow_web_search=True,
        allow_graph_rag=True,
        graph_rag_mode="hybrid",
    )

    captured = capsys.readouterr()
    assert "does not appear to include prior web enrichment context" in captured.err
    assert len(decomposer.graph_rag_calls) == 1
    assert decomposer.run_plan_calls == []
    assert result.stats["graph_rag_calls"] == 1

    args, kwargs = decomposer.graph_rag_calls[0]
    assert args == (plan.id,)
    assert kwargs == {
        "max_depth": 2,
        "node_budget": 5,
        "graph_rag_mode": "hybrid",
    }


def test_run_enrichment_dispatches_to_web_enrich_without_graph_rag(
    plan_repo: PlanRepository,
):
    plan = plan_repo.create_plan("Imported web plan")
    plan_repo.create_task(plan.id, name="Root", instruction="Refine host prediction")

    decomposer = DummyDecomposer()

    result = _run_enrichment(
        decomposer=decomposer,
        repo=plan_repo,
        plan_id=plan.id,
        mode="web_enrich",
        max_depth=3,
        node_budget=8,
        allow_web_search=False,
        allow_graph_rag=True,
        graph_rag_mode="hybrid",
    )

    assert decomposer.graph_rag_calls == []
    assert len(decomposer.run_plan_calls) == 1
    assert result.stats["graph_rag_calls"] == 0

    args, kwargs = decomposer.run_plan_calls[0]
    assert args == (plan.id,)
    assert kwargs == {
        "max_depth": 3,
        "node_budget": 8,
        "allow_web_search": False,
        "web_enrich_only": True,
    }

