from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.repository.plan_repository import PlanRepository
from scripts.pipeline import plan_enrichment_pipeline as pipeline

DEFAULT_GRAPH_RAG_MODE = pipeline.DEFAULT_GRAPH_RAG_MODE
_run_enrichment = pipeline._run_enrichment


class DummyDecomposer:
    def __init__(self, *, stopped_reason=None) -> None:
        self.run_plan_calls = []
        self.graph_rag_calls = []
        self.stopped_reason = stopped_reason

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
            stopped_reason=self.stopped_reason,
            stats={"enriched_nodes": 1, "llm_calls": 1, "graph_rag_calls": 1},
        )


def test_graph_rag_enrichment_defaults_to_mix():
    assert DEFAULT_GRAPH_RAG_MODE == "mix"
    assert pipeline.DEFAULT_GRAPH_RAG_BACKEND == "lightrag_8_shard"


def test_completed_checkpoint_requires_expected_graph_rag_backend(tmp_path):
    checkpoint = tmp_path / "plan_1.json"
    checkpoint.write_text(
        json.dumps({
            "nodes": {
                "1": {
                    "context_meta": {
                            "graph_rag": {"backend": "lightrag_8_shard"}
                    }
                }
            }
        }),
        encoding="utf-8",
    )

    assert pipeline._is_completed_graph_rag_checkpoint(checkpoint, "lightrag_8_shard") is True
    assert pipeline._is_completed_graph_rag_checkpoint(checkpoint, "multirag") is False

    checkpoint.write_text("{broken", encoding="utf-8")
    assert pipeline._is_completed_graph_rag_checkpoint(checkpoint, "lightrag_8_shard") is False


def test_pending_plan_files_skip_only_valid_checkpoints(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    files = [input_dir / "plan_1.json", input_dir / "plan_2.json"]
    for path in files:
        path.write_text("{}", encoding="utf-8")
    (output_dir / "plan_1.json").write_text(
        json.dumps({
            "nodes": {
                "1": {
                    "context_meta": {
                            "graph_rag": {"backend": "lightrag_8_shard"}
                    }
                }
            }
        }),
        encoding="utf-8",
    )

    pending = pipeline._pending_plan_files(
        files,
        output_dir=output_dir,
        resume=True,
        expected_backend="lightrag_8_shard",
    )

    assert pending == [files[1]]


def test_dump_plan_json_uses_source_name_and_atomic_replace(
    tmp_path,
    plan_repo: PlanRepository,
):
    plan = plan_repo.create_plan("Checkpoint plan")
    plan_repo.create_task(plan.id, name="Root", instruction="Run analysis")

    output_path = pipeline.dump_plan_json(
        plan_repo,
        plan.id,
        tmp_path,
        filename="plan_77.json",
    )

    assert output_path == tmp_path / "plan_77.json"
    assert output_path.exists()
    assert not (tmp_path / "plan_77.json.tmp").exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["id"] == 77
    assert {node["plan_id"] for node in payload["nodes"].values()} == {77}


@pytest.mark.parametrize("stopped_reason", ["graph_rag_failed", "graph_rag_empty"])
def test_run_enrichment_raises_on_fatal_graph_rag_result(
    stopped_reason,
    plan_repo: PlanRepository,
):
    plan = plan_repo.create_plan("Imported web plan")
    plan_repo.create_task(plan.id, name="Root", instruction="Refine host prediction")

    with pytest.raises(pipeline.GraphRAGUnavailableError, match=stopped_reason):
        _run_enrichment(
            decomposer=DummyDecomposer(stopped_reason=stopped_reason),
            repo=plan_repo,
            plan_id=plan.id,
            mode="graph_rag_enrich",
            max_depth=2,
            node_budget=5,
            allow_web_search=True,
            allow_graph_rag=True,
            graph_rag_mode="mix",
        )


def test_validate_graph_rag_health_requires_all_eight_shards():
    pipeline._validate_graph_rag_health({
        "success": True,
        "status": "healthy",
        "shards_total": 8,
        "shards_ok": 8,
    })

    with pytest.raises(pipeline.GraphRAGUnavailableError, match="7/8"):
        pipeline._validate_graph_rag_health({
            "success": True,
            "status": "degraded",
            "shards_total": 8,
            "shards_ok": 7,
        })


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
