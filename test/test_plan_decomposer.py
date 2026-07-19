from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Iterable, List, Optional

from app.config.decomposer_config import DecomposerSettings
from app.repository.plan_repository import PlanRepository
from app.services.llm.decomposer_service import (
    DecompositionResponse,
    PlanDecomposerLLMService,
)
from app.services.plans.plan_decomposer import PlanDecomposer


def _make_response(
    *,
    target: Optional[int],
    mode: str,
    should_stop: bool,
    reason: Optional[str],
    children: List[dict],
) -> DecompositionResponse:
    return DecompositionResponse(
        target_node_id=target,
        mode=mode,
        should_stop=should_stop,
        reason=reason,
        children_raw=children,
    )


class StubDecomposerLLM(PlanDecomposerLLMService):
    def __init__(
        self,
        responses: Iterable[DecompositionResponse],
        *,
        enrich_responses: Optional[Iterable[Any]] = None,
    ) -> None:
        self._responses = iter(responses)
        self._enrich_responses = iter(enrich_responses or [])
        self.prompts: List[str] = []
        self.enrich_prompts: List[str] = []

    def generate(self, prompt: str) -> DecompositionResponse:
        self.prompts.append(prompt)
        try:
            return next(self._responses)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise AssertionError("No more stub responses available") from exc

    def enrich_node(self, prompt: str) -> str:
        self.enrich_prompts.append(prompt)
        try:
            response = next(self._enrich_responses)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise AssertionError("No more stub enrich responses available") from exc
        if isinstance(response, Exception):
            raise response
        return str(response)


def _settings(**overrides) -> DecomposerSettings:
    base = DecomposerSettings(
        max_depth=3,
        max_children=6,
        total_node_budget=20,
        model="stub-model",
        auto_on_create=True,
        stop_on_empty=True,
        retry_limit=0,
        allow_existing_children=False,
    )
    return replace(base, **overrides)


def test_run_plan_creates_root_tasks(plan_repo: PlanRepository):
    responses = [
        _make_response(
            target=None,
            mode="plan_bfs",
            should_stop=False,
            reason=None,
            children=[
                {"name": "Task Alpha", "instruction": "Do alpha work", "leaf": False},
                {"name": "Task Beta", "instruction": "Do beta work", "leaf": True},
            ],
        ),
        _make_response(
            target=1,
            mode="plan_bfs",
            should_stop=True,
            reason="depth limit",
            children=[],
        ),
    ]
    stub_llm = StubDecomposerLLM(responses)
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )
    plan = plan_repo.create_plan("Demo Plan", description="Stub plan")

    result = decomposer.run_plan(plan.id, max_depth=2, node_budget=5)

    assert len(result.created_tasks) == 2
    assert [node.name for node in result.created_tasks] == ["Task Alpha", "Task Beta"]
    assert result.stopped_reason == "depth limit"
    assert result.stats["llm_calls"] == 2

    tree = plan_repo.get_plan_tree(plan.id)
    assert tree.node_count() == 2
    assert tree.root_node_ids()  # ensure tasks recorded as roots


def test_decompose_node_with_context(plan_repo: PlanRepository):
    plan = plan_repo.create_plan("Context Plan")
    root = plan_repo.create_task(plan.id, name="Root Task")
    responses = [
        _make_response(
            target=root.id,
            mode="single_node",
            should_stop=True,
            reason="node complete",
            children=[
                {
                    "name": "Write spec",
                    "instruction": "Draft a detailed specification",
                    "dependencies": [str(root.id)],
                    "leaf": True,
                    "context": {
                        "combined": "Spec summary",
                        "sections": [{"title": "Outline", "content": "..."}],
                        "meta": {"source": "llm"},
                    },
                }
            ],
        )
    ]
    stub_llm = StubDecomposerLLM(responses)
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )

    result = decomposer.decompose_node(plan.id, root.id, expand_depth=1)

    assert len(result.created_tasks) == 1
    child = result.created_tasks[0]
    assert child.parent_id == root.id
    assert child.context_combined == "Spec summary"
    assert child.context_meta.get("source") == "llm"
    assert child.dependencies == [root.id]


def test_decompose_node_skips_when_children_exist(plan_repo: PlanRepository):
    stub_llm = StubDecomposerLLM([])
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )
    plan = plan_repo.create_plan("Existing Children Plan")
    parent = plan_repo.create_task(plan.id, name="Parent")
    plan_repo.create_task(plan.id, name="Existing Child", parent_id=parent.id)

    result = decomposer.decompose_node(plan.id, parent.id, expand_depth=1)

    assert result.created_tasks == []
    assert result.processed_nodes == []
    assert result.stats["llm_calls"] == 0


def test_enrich_plan_with_shared_graph_rag_updates_instruction_and_context(
    monkeypatch, plan_repo: PlanRepository
):
    plan = plan_repo.create_plan("Phage host range", description="Design a validation workflow")
    root = plan_repo.create_task(plan.id, name="Root", instruction="Outline the workflow")
    child = plan_repo.create_task(
        plan.id,
        name="Child",
        parent_id=root.id,
        instruction="Collect benchmark datasets",
    )
    plan_repo.update_task(
        plan.id,
        root.id,
        context_sections=[{"title": "web_search", "content": "Existing web context"}],
        context_meta={"web_search": {"query": "phage host range workflow"}},
    )

    enrich_responses = [
        json.dumps(
            {
                "instruction": "Outline the workflow with receptor-binding evidence.",
                "context": {
                    "combined": "Why: receptor-binding proteins shape host range.",
                },
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "instruction": "Collect benchmark datasets and label receptor-binding proteins.",
                "context": {
                    "combined": "Why: GraphRAG highlights receptor-binding evidence.",
                },
            },
            ensure_ascii=False,
        ),
    ]
    stub_llm = StubDecomposerLLM([], enrich_responses=enrich_responses)
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )

    calls = []

    async def _fake_execute_tool(tool_name: str, **kwargs):
        calls.append((tool_name, kwargs))
        return {
            "success": True,
            "result": {
                "backend": "multirag",
                "mode": "hybrid",
                "response": "Receptor-binding proteins are central to host specificity.",
                "trace": {"final_path": "merged", "graph": "used"},
            },
        }

    monkeypatch.setattr(
        "app.services.plans.plan_decomposer.execute_tool",
        _fake_execute_tool,
    )

    result = decomposer.enrich_plan_with_shared_graph_rag(
        plan.id,
        max_depth=2,
        node_budget=10,
        graph_rag_mode="hybrid",
    )

    assert calls == [
        (
            "graph_rag",
            {
                "query": "Phage host range. Design a validation workflow",
                "mode": "hybrid",
            },
        )
    ]
    assert result.mode == "graph_rag_enrich"
    assert result.created_tasks == []
    assert result.failed_nodes == []
    assert result.stats["graph_rag_calls"] == 1
    assert result.stats["llm_calls"] == 2
    assert result.stats["enriched_nodes"] == 2

    tree = plan_repo.get_plan_tree(plan.id)
    assert tree.get_node(root.id).parent_id is None
    assert tree.get_node(child.id).parent_id == root.id
    assert (
        tree.get_node(root.id).instruction
        == "Outline the workflow with receptor-binding evidence."
    )
    assert (
        tree.get_node(child.id).instruction
        == "Collect benchmark datasets and label receptor-binding proteins."
    )
    root_sections = tree.get_node(root.id).context_sections
    assert any(sec.get("title") == "graph_rag" for sec in root_sections)
    assert tree.get_node(child.id).context_meta["graph_rag"]["mode"] == "hybrid"
    assert "SHARED GRAPHRAG CONTEXT" in stub_llm.enrich_prompts[0]


def test_enrich_plan_with_shared_graph_rag_falls_back_to_context_on_llm_failure(
    monkeypatch, plan_repo: PlanRepository
):
    plan = plan_repo.create_plan("Phage assembly")
    root = plan_repo.create_task(plan.id, name="Root", instruction="Assemble contigs")

    stub_llm = StubDecomposerLLM(
        [],
        enrich_responses=[RuntimeError("LLM unavailable")],
    )
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )

    async def _fake_execute_tool(tool_name: str, **kwargs):
        assert tool_name == "graph_rag"
        return {
            "success": True,
            "result": {
                "backend": "multirag",
                "mode": "local",
                "response": "Assembly quality depends on coverage and repeat resolution.",
                "trace": {"final_path": "graph_only"},
            },
        }

    monkeypatch.setattr(
        "app.services.plans.plan_decomposer.execute_tool",
        _fake_execute_tool,
    )

    result = decomposer.enrich_plan_with_shared_graph_rag(plan.id, graph_rag_mode="local")

    assert result.failed_nodes == [root.id]
    assert result.stats["graph_rag_calls"] == 1
    assert result.stats["llm_calls"] == 0
    assert result.stats["enriched_nodes"] == 1

    refreshed = plan_repo.get_node(plan.id, root.id)
    assert refreshed.instruction == "Assemble contigs"
    assert refreshed.context_meta["graph_rag"]["mode"] == "local"
    assert any(
        sec.get("title") == "graph_rag"
        for sec in refreshed.context_sections
    )


def test_enrich_plan_with_shared_graph_rag_stops_when_graph_call_fails(
    monkeypatch, plan_repo: PlanRepository
):
    plan = plan_repo.create_plan("Phage taxonomy")
    root = plan_repo.create_task(plan.id, name="Root", instruction="Classify genomes")

    stub_llm = StubDecomposerLLM([])
    decomposer = PlanDecomposer(
        repo=plan_repo,
        llm_service=stub_llm,
        settings=_settings(),
    )

    async def _fake_execute_tool(tool_name: str, **kwargs):
        assert tool_name == "graph_rag"
        return {"success": False, "error": "service unavailable", "code": "service_unavailable"}

    monkeypatch.setattr(
        "app.services.plans.plan_decomposer.execute_tool",
        _fake_execute_tool,
    )

    result = decomposer.enrich_plan_with_shared_graph_rag(plan.id)

    assert result.stopped_reason == "graph_rag_failed"
    assert result.processed_nodes == []
    assert result.stats["graph_rag_calls"] == 1
    assert result.stats["llm_calls"] == 0

    refreshed = plan_repo.get_node(plan.id, root.id)
    assert refreshed.context_meta == {}
    assert refreshed.context_sections == []
