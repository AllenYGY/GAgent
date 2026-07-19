# noqa: D401 - module-level documentation handled in docs/decompose_task_plan.md
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field

from ...config.decomposer_config import DecomposerSettings, get_decomposer_settings
from ...repository.plan_repository import PlanRepository
from ...utils import parse_json_obj, run_async
from .plan_models import PlanNode, PlanTree
from ..llm.decomposer_service import (
    DecompositionChild,
    PlanDecomposerLLMService,
)
from tool_box.integration import execute_tool

logger = logging.getLogger(__name__)


def _log_job(level: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    try:
        from .decomposition_jobs import log_job_event
    except Exception:  # pragma: no cover - defensive
        return
    log_job_event(level, message, metadata)


@dataclass
class QueueItem:
    node_id: Optional[int]
    relative_depth: int


class DecompositionResult(BaseModel):
    plan_id: int
    mode: str
    root_node_id: Optional[int] = None
    processed_nodes: List[Optional[int]] = Field(default_factory=list)
    created_tasks: List[PlanNode] = Field(default_factory=list)
    failed_nodes: List[Optional[int]] = Field(default_factory=list)
    stopped_reason: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)


class SearchDecision(BaseModel):
    use_search: bool = False
    query: Optional[str] = None


class DecompositionPromptBuilder:
    """Compose prompts for the decomposition LLM without sharing chat history."""

    SYSTEM_HEADER = (
        "You are a task planning assistant. You must return valid JSON that matches "
        "the provided schema. Decompose the target work item into direct child tasks only."
    )

    def build(
        self,
        *,
        plan: PlanTree,
        node: Optional[PlanNode],
        outline: str,
        web_context: Optional[str],
        mode: str,
        settings: DecomposerSettings,
        depth: int,
        max_depth: int,
    ) -> str:
        if node is None:
            node_title = plan.title
            node_instruction = plan.description or ""
            node_path = "/"
            node_children = []
        else:
            node_title = node.name
            node_instruction = node.instruction or ""
            node_path = node.path or f"/{node.id}"
            node_children = self._summarise_children(plan, node.id)

        constraints = {
            "mode": mode,
            "target_node_path": node_path,
            "current_depth": depth,
            "max_depth": max_depth,
            "min_children": settings.min_children,
            "max_children": settings.max_children,
            "stop_on_empty": settings.stop_on_empty,
        }

        prompt = [
            self.SYSTEM_HEADER,
            "\n=== PLAN OVERVIEW ===",
            outline or "(empty plan)",
        ]
        if web_context:
            prompt.extend(
                [
                    "\n=== WEB CONTEXT ===",
                    web_context,
                    "\n=== WEB CONTEXT RULES ===",
                    "- Use web context when it improves specificity (tools, versions, parameters, thresholds, data sources).",
                    "- Do not force web details into unrelated tasks.",
                    "- Summarize web info into executable details; do not paste long quotes.",
                    "- If web context is used, include a short 'web_search' entry in child.context.sections.",
                    "- If web context enables a non-obvious approach, capture it explicitly as innovation with expected benefit, feasibility constraints, resources, and risks/mitigations.",
                ]
            )
        prompt.extend(
            [
                "\n=== TARGET NODE ===",
                f"Name: {node_title}",
                f"Instruction: {node_instruction}",
                f"Existing children count: {len(node_children)}",
                *node_children,
                "\n=== CONSTRAINTS ===",
                self._format_constraints(constraints),
                "\n=== RESPONSE FORMAT ===",
                "{",
                '  "target_node_id": <int or null>,',
                '  "mode": "plan_bfs" | "single_node",',
                '  "should_stop": <true|false>,',
                '  "reason": "<optional string>",',
                '  "children": [',
                "    {",
                '      "name": "<task name>",',
                '      "instruction": "<execution details>",',
                '      "dependencies": [<int>],',
                '      "leaf": <true|false>,',
                '      "context": {',
                '         "combined": "<optional summary>",',
                '         "sections": [',
                '             {',
                '                 "title": "<section title>",',
                '                 "content": "<section details>"',
                '             }',
                '         ],',
                '         "meta": {',
                '             "<key>": "<value>"',
                '         }',
                "      }",
                "    }",
                "  ]",
                "}",
                "\nSTRICT REQUIREMENTS:",
                "- The entire response must be valid JSON (no comments, no trailing commas, no Markdown code fences).",
                "- `children` must be an array. Each child must include `name`, `instruction`, `dependencies`, `leaf`, and `context`.",
                "- `context.sections` must be an array of JSON objects, never strings. Every object must provide `title` and `content` keys.",
                "- Use empty arrays (`[]`) or empty objects (`{}`) when there is no data.",
                "- Do not invent additional top-level keys beyond this schema.",
                f"- Aim to produce between {settings.min_children} and {settings.max_children} well-scoped child tasks when the work warrants it.",
                f"- Returning fewer than {settings.min_children} children is acceptable only if the task is inherently small; explain via `reason` when doing so.",
                "- Where possible, include Innovation & Feasibility in child context (non-obvious idea, expected benefit, feasibility constraints, resource needs, risks/mitigation).",
                "\nOnly return JSON. Do not wrap the response in Markdown code fences.",
            ]
        )
        return "\n".join(prompt)

    def _summarise_children(self, plan: PlanTree, node_id: int) -> List[str]:
        summaries: List[str] = []
        for child_id in plan.children_ids(node_id):
            child = plan.nodes.get(child_id)
            if not child:
                continue
            instruction = (child.instruction or "").strip()
            if len(instruction) > 80:
                instruction = instruction[:77] + "..."
            summaries.append(f"- [{child.id}] {child.name} :: {instruction}")
        return summaries

    def _format_constraints(self, data: Dict[str, Any]) -> str:
        return "\n".join(f"- {key}: {value}" for key, value in data.items())


class PlanDecomposer:
    """High-level façade orchestrating BFS task decomposition."""

    SEARCH_DECISION_HEADER = (
        "You are a search decision assistant. Decide whether web search is required "
        "to decompose the target node into actionable subtasks. Return only JSON."
    )
    NODE_ENRICH_HEADER = (
        "You are a plan enrichment assistant. Use available retrieval context to improve an existing "
        "task node without changing the plan structure. Return only JSON."
    )

    def __init__(
        self,
        *,
        repo: Optional[PlanRepository] = None,
        llm_service: Optional[PlanDecomposerLLMService] = None,
        settings: Optional[DecomposerSettings] = None,
    ) -> None:
        self._repo = repo or PlanRepository()
        self._settings = settings or get_decomposer_settings()
        self._llm = llm_service or PlanDecomposerLLMService(settings=self._settings)
        self._prompt_builder = DecompositionPromptBuilder()

    @property
    def settings(self) -> DecomposerSettings:
        return self._settings

    def _build_search_decision_prompt(
        self,
        *,
        plan: PlanTree,
        node: Optional[PlanNode],
        outline: str,
        depth: int,
        max_depth: int,
        parent_web_context: Optional[str] = None,
        current_web_context: Optional[str] = None,
    ) -> str:
        if node is None:
            node_title = plan.title
            node_instruction = plan.description or ""
            node_path = "/"
            node_children: List[str] = []
        else:
            node_title = node.name
            node_instruction = node.instruction or ""
            node_path = node.path or f"/{node.id}"
            node_children = self._prompt_builder._summarise_children(plan, node.id)

        prompt = [
            self.SEARCH_DECISION_HEADER,
            "\n=== PLAN OVERVIEW ===",
            outline or "(empty plan)",
        ]
        if parent_web_context:
            prompt.extend(
                [
                    "\n=== PARENT WEB CONTEXT (SUMMARY) ===",
                    parent_web_context,
                ]
            )
        if current_web_context:
            prompt.extend(
                [
                    "\n=== CURRENT NODE WEB CONTEXT (SUMMARY) ===",
                    current_web_context,
                ]
            )
        prompt.extend(
            [
                "\n=== TARGET NODE ===",
                f"Name: {node_title}",
                f"Instruction: {node_instruction}",
                f"Path: {node_path}",
                f"Depth: {depth} (max {max_depth})",
                f"Existing children count: {len(node_children)}",
                *node_children,
                "\n=== RESPONSE FORMAT ===",
                "{",
                '  "use_search": <true|false>,',
                '  "query": "<string>"',
                "}",
                "\nSTRICT REQUIREMENTS:",
                "- Return only valid JSON (no Markdown, no extra keys).",
                "- Use search only if external info is needed to decompose the node.",
                "- Search is for gap-filling (missing tools/versions/parameters/metrics/thresholds/data sources), not repetition.",
                "- If parent/current web context already covers the needed details, set use_search=false.",
                "- If use_search is false, set query to an empty string.",
                "- Keep query concise (<= 120 characters).",
                "\nQUERY GUIDELINES (when use_search=true):",
                "- Query MUST include:",
                "  (1) target entity/domain,",
                "  (2) task type or method,",
                "  (3) at least one constraint (data type/platform/threshold/species),",
                "  (4) intended output (protocol/parameters/tool).",
                "- Prefer using concrete terms from node name/instruction.",
                "- Avoid generic queries (no single-word queries).",
                "- Aim for 4–8 keywords, compact but specific.",
            ]
        )
        return "\n".join(prompt)

    @staticmethod
    def _parse_search_decision(raw: Any) -> SearchDecision:
        text = "" if raw is None else str(raw)
        parsed = parse_json_obj(text)
        if not isinstance(parsed, dict):
            return SearchDecision(use_search=False, query=None)
        use_search = bool(parsed.get("use_search"))
        query_raw = parsed.get("query")
        query = str(query_raw).strip() if query_raw is not None else ""
        if not use_search or not query:
            return SearchDecision(use_search=False, query=None)
        if len(query) > 120:
            query = query[:120].strip()
        return SearchDecision(use_search=True, query=query)

    @staticmethod
    def _normalize_context_sections(
        raw_sections: Any,
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw_sections, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_sections, start=1):
            if item is None:
                continue
            if isinstance(item, dict):
                title = item.get("title")
                content = item.get("content")
                normalized.append(
                    {
                        "title": str(title).strip() if title is not None else f"Section {index}",
                        "content": str(content).strip() if content is not None else "",
                    }
                )
            else:
                normalized.append({"title": f"Section {index}", "content": str(item).strip()})
        return normalized

    @staticmethod
    def _format_web_context(
        payload: Dict[str, Any], *, query: Optional[str] = None
    ) -> Tuple[str, int, Optional[str]]:
        def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
            if not text:
                return None
            if "```json" in text:
                start = text.find("```json") + len("```json")
                end = text.find("```", start)
                if end != -1:
                    block = text[start:end].strip()
                else:
                    block = text[start:].strip()
            else:
                block = text.strip()
            if block.startswith("{") and block.endswith("}"):
                try:
                    return json.loads(block)
                except Exception:
                    return None
            return None

        summary_raw = str(payload.get("response") or payload.get("answer") or "").strip()
        parsed = _extract_json_block(summary_raw)
        summary = summary_raw
        reference_list: List[Dict[str, Any]] = []
        if isinstance(parsed, dict):
            answer = parsed.get("answer")
            if answer:
                summary = str(answer).strip()
            refs = parsed.get("references") or parsed.get("sources") or []
            if isinstance(refs, list):
                reference_list = [item for item in refs if isinstance(item, dict)]

        results = payload.get("results") or []
        if not isinstance(results, list):
            results = []
        if reference_list and not results:
            results = reference_list
        provider = payload.get("provider")

        lines: List[str] = []
        if query:
            lines.append(f"Query: {query}")
        if summary:
            lines.append("Key findings:")
            lines.append(f"- {summary}")
        if results:
            lines.append("Sources:")
            for item in results[:5]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "source").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                line = f"- {title}"
                if url:
                    line += f" | {url}"
                if snippet:
                    if len(snippet) > 200:
                        snippet = snippet[:197] + "..."
                    line += f" | {snippet}"
                lines.append(line)

        return "\n".join(lines).strip(), len(results), provider

    @staticmethod
    def _collect_node_web_context(node: Optional[PlanNode]) -> Optional[str]:
        if node is None:
            return None
        lines: List[str] = []
        for sec in node.context_sections or []:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title") or "").strip().lower()
            content = str(sec.get("content") or "").strip()
            if not content:
                continue
            if title.startswith("web"):
                lines.append(content)
        context = "\n\n".join(lines).strip()
        return context or None

    def _collect_parent_web_context(
        self, tree: PlanTree, node: Optional[PlanNode]
    ) -> Optional[str]:
        if node is None or node.parent_id is None:
            return None
        parent = tree.nodes.get(node.parent_id)
        return self._collect_node_web_context(parent)

    @staticmethod
    def _upsert_context_section(
        sections: List[Dict[str, Any]],
        *,
        title: str,
        content: str,
    ) -> List[Dict[str, Any]]:
        normalized = PlanDecomposer._normalize_context_sections(sections)
        target = title.strip().lower()
        result: List[Dict[str, Any]] = []
        inserted = False
        for section in normalized:
            current_title = str(section.get("title") or "").strip().lower()
            if current_title == target:
                if not inserted and content:
                    result.append({"title": title, "content": content})
                    inserted = True
                continue
            result.append(section)
        if not inserted and content:
            result.append({"title": title, "content": content})
        return result

    def _apply_web_context(
        self,
        *,
        plan_id: int,
        node: Optional[PlanNode],
        tree: PlanTree,
        context: str,
        query: str,
        provider: Optional[str],
        results_count: int,
    ) -> None:
        if node is None or not context:
            return
        sections = self._upsert_context_section(
            list(node.context_sections or []),
            title="web_search",
            content=context,
        )
        meta = dict(node.context_meta or {})
        meta["web_search"] = {
            "query": query,
            "provider": provider,
            "results_count": results_count,
        }
        updated = self._repo.update_task(
            plan_id,
            node.id,
            context_sections=sections,
            context_meta=meta,
        )
        tree.nodes[updated.id] = updated

    @staticmethod
    def _format_graph_rag_context(
        payload: Dict[str, Any], *, query: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            return "", {}

        response = str(result.get("response") or "").strip()
        trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
        mode = str(result.get("mode") or payload.get("mode") or "").strip()
        backend = str(result.get("backend") or "").strip()

        lines: List[str] = []
        if query:
            lines.append(f"Query: {query}")
        if response:
            lines.append("GraphRAG findings:")
            lines.append(f"- {response}")
        if trace:
            lines.append("Trace:")
            for key, value in list(trace.items())[:6]:
                if isinstance(value, (dict, list)):
                    rendered = json.dumps(value, ensure_ascii=False)
                else:
                    rendered = str(value)
                rendered = rendered.strip()
                if len(rendered) > 160:
                    rendered = rendered[:157] + "..."
                lines.append(f"- {key}: {rendered}")

        meta: Dict[str, Any] = {
            "query": query or "",
            "mode": mode or "",
            "backend": backend or "",
            "trace": trace,
        }
        return "\n".join(lines).strip(), meta

    @staticmethod
    def _build_plan_graph_rag_query(plan: PlanTree) -> str:
        def _clean(text: Optional[str]) -> str:
            return " ".join(str(text or "").split()).strip()

        parts: List[str] = []
        title = _clean(plan.title)
        if title:
            parts.append(title)

        description = _clean(plan.description)
        if description:
            parts.append(description)
        else:
            for root_id in plan.root_node_ids():
                root = plan.nodes.get(root_id)
                instruction = _clean(root.instruction if root else "")
                if instruction:
                    parts.append(instruction)
                    break

        query = ". ".join(part for part in parts if part)
        if len(query) > 400:
            query = query[:397].rstrip() + "..."
        return query or "plan graph enrichment"

    def _build_node_enrichment_prompt(
        self,
        *,
        plan: PlanTree,
        node: PlanNode,
        outline: str,
        parent_web_context: Optional[str],
        current_web_context: Optional[str],
        new_web_context: Optional[str],
        search_query: Optional[str],
        provider: Optional[str],
        results_count: Optional[int],
        shared_graph_rag_context: Optional[str] = None,
        graph_rag_query: Optional[str] = None,
        graph_rag_mode: Optional[str] = None,
        graph_rag_backend: Optional[str] = None,
    ) -> str:
        context_payload = {
            "combined": node.context_combined,
            "sections": node.context_sections or [],
            "meta": node.context_meta or {},
        }
        prompt = [
            self.NODE_ENRICH_HEADER,
            "\n=== PLAN OVERVIEW ===",
            outline or "(empty plan)",
        ]
        if parent_web_context:
            prompt.extend(
                [
                    "\n=== PARENT WEB CONTEXT ===",
                    parent_web_context,
                ]
            )
        if current_web_context:
            prompt.extend(
                [
                    "\n=== CURRENT NODE WEB CONTEXT ===",
                    current_web_context,
                ]
            )
        if new_web_context:
            prompt.extend(
                [
                    "\n=== NEW WEB CONTEXT ===",
                    new_web_context,
                ]
            )
        if shared_graph_rag_context:
            prompt.extend(
                [
                    "\n=== SHARED GRAPHRAG CONTEXT ===",
                    shared_graph_rag_context,
                ]
            )
        prompt.extend(
            [
                "\n=== TARGET NODE ===",
                f"ID: {node.id}",
                f"Name: {node.name}",
                f"Instruction: {node.instruction or ''}",
                f"Dependencies: {node.dependencies}",
                "\n=== EXISTING CONTEXT (JSON) ===",
                json.dumps(context_payload, ensure_ascii=False),
                "\n=== EXISTING METADATA (JSON) ===",
                json.dumps(node.metadata or {}, ensure_ascii=False),
                "\n=== OUTPUT FORMAT ===",
                "{",
                '  "name": "<string>",',
                '  "instruction": "<string>",',
                '  "metadata": { "<key>": "<value>" },',
                '  "dependencies": [<int>],',
                '  "context": {',
                '     "combined": "<string>",',
                '     "sections": [',
                '        { "title": "<string>", "content": "<string>" }',
                "     ],",
                '     "meta": { "<key>": "<value>" }',
                "  }",
                "}",
                "\nSTRICT REQUIREMENTS:",
                "- Return only valid JSON (no Markdown, no extra keys).",
                "- Only update these fields: name, instruction, metadata, dependencies, context.*",
                "- Do NOT add/remove nodes or change structure (id/parent/path/position/depth stay unchanged).",
                "- Use parent/current web context to avoid repeating the same facts.",
                "- New web context should fill gaps (tools/versions/parameters/metrics/thresholds/data sources).",
                "- If using new web context, include a 'web_search' section in context.sections.",
                "- Shared GraphRAG context provides plan-level domain facts and should be applied only when it helps this node.",
                "- If using GraphRAG context, include a 'graph_rag' section in context.sections.",
                "- Keep summaries concise; do not paste long quotes.",
                "- Instruction must remain a minimal executable unit; it may include up to 2 tightly coupled micro-actions only if they lead to one explicit output.",
                "- If the output artifact is missing, add it explicitly in the instruction (e.g., '... -> output: <file/table/model>').",
                "- Do NOT merge distinct phases (preprocess + train + evaluate) or multiple outputs/tools into one node.",
                "- context.combined MUST include: Why (rationale), Assumption/Constraint, and Metric/Validation (if available). Keep to 1–3 sentences.",
                "- Where possible, add Innovation & Feasibility details in context.combined or a dedicated context.sections entry: non-obvious idea, expected benefit, feasibility constraints, resource needs, risks/mitigation.",
                "- Prefer concrete parameters/metrics from available retrieval context; if unknown, say what is missing.",
                "- If a field does not need changes, return the original value.",
            ]
        )
        if search_query:
            prompt.append(f"\nSearch query: {search_query}")
        if provider:
            prompt.append(f"Search provider: {provider}")
        if results_count is not None:
            prompt.append(f"Search results count: {results_count}")
        if graph_rag_query:
            prompt.append(f"GraphRAG query: {graph_rag_query}")
        if graph_rag_mode:
            prompt.append(f"GraphRAG mode: {graph_rag_mode}")
        if graph_rag_backend:
            prompt.append(f"GraphRAG backend: {graph_rag_backend}")
        return "\n".join(prompt)

    def _parse_node_update(self, raw: Any) -> Dict[str, Any]:
        parsed = parse_json_obj("" if raw is None else str(raw))
        if not isinstance(parsed, dict):
            return {}
        update: Dict[str, Any] = {}

        if "name" in parsed and isinstance(parsed.get("name"), str):
            name = parsed.get("name", "").strip()
            if name:
                update["name"] = name
        if "instruction" in parsed and isinstance(parsed.get("instruction"), str):
            instruction = parsed.get("instruction", "").strip()
            if instruction:
                update["instruction"] = instruction

        if "metadata" in parsed and isinstance(parsed.get("metadata"), dict):
            update["metadata"] = parsed.get("metadata")
        if "dependencies" in parsed and isinstance(parsed.get("dependencies"), list):
            update["dependencies"] = parsed.get("dependencies")

        context = parsed.get("context") if isinstance(parsed.get("context"), dict) else {}
        if "context_combined" in parsed:
            context_combined = parsed.get("context_combined")
        else:
            context_combined = context.get("combined")
        if isinstance(context_combined, str) and context_combined.strip():
            update["context_combined"] = context_combined.strip()

        if "context_sections" in parsed:
            sections_raw = parsed.get("context_sections")
        else:
            sections_raw = context.get("sections")
        if sections_raw is not None:
            sections = self._normalize_context_sections(sections_raw)
            if sections:
                update["context_sections"] = sections

        if "context_meta" in parsed and isinstance(parsed.get("context_meta"), dict):
            update["context_meta"] = parsed.get("context_meta")
        else:
            if isinstance(context.get("meta"), dict) and context.get("meta"):
                update["context_meta"] = context.get("meta")

        return update

    def _apply_node_update(
        self,
        *,
        plan_id: int,
        node: PlanNode,
        tree: PlanTree,
        update: Dict[str, Any],
        web_context: Optional[str],
        query: Optional[str],
        provider: Optional[str],
        results_count: Optional[int],
        graph_rag_context: Optional[str] = None,
        graph_rag_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[PlanNode]:
        if not update and not web_context and not graph_rag_context:
            return None

        name = update.get("name") or node.name
        instruction = update.get("instruction") or node.instruction

        metadata = None
        if "metadata" in update and isinstance(update.get("metadata"), dict):
            merged = dict(node.metadata or {})
            merged.update(update.get("metadata") or {})
            metadata = merged

        deps = None
        if "dependencies" in update and isinstance(update.get("dependencies"), list):
            filtered: List[int] = []
            for value in update.get("dependencies") or []:
                try:
                    dep_id = int(value)
                except (TypeError, ValueError):
                    continue
                if dep_id == node.id:
                    continue
                if dep_id not in tree.nodes:
                    continue
                if dep_id not in filtered:
                    filtered.append(dep_id)
            deps = filtered
        if deps is not None and metadata is None:
            metadata = dict(node.metadata or {})

        context_combined = None
        if "context_combined" in update:
            context_combined = update.get("context_combined")

        sections = None
        meta = None

        if "context_sections" in update:
            sections = list(update.get("context_sections") or [])
        if "context_meta" in update and isinstance(update.get("context_meta"), dict):
            meta = dict(update.get("context_meta") or {})

        if web_context or graph_rag_context:
            if sections is None:
                sections = list(node.context_sections or [])
            meta = dict(node.context_meta or {})
            if "context_meta" in update and isinstance(update.get("context_meta"), dict):
                meta.update(update.get("context_meta") or {})
            if web_context:
                sections = self._upsert_context_section(
                    sections,
                    title="web_search",
                    content=web_context,
                )
                meta["web_search"] = {
                    "query": query,
                    "provider": provider,
                    "results_count": results_count or 0,
                }
            if graph_rag_context:
                sections = self._upsert_context_section(
                    sections,
                    title="graph_rag",
                    content=graph_rag_context,
                )
                meta["graph_rag"] = dict(graph_rag_meta or {})

        updated = self._repo.update_task(
            plan_id,
            node.id,
            name=name,
            instruction=instruction,
            metadata=metadata,
            dependencies=deps if deps is not None else None,
            context_combined=context_combined,
            context_sections=sections,
            context_meta=meta,
        )
        tree.nodes[updated.id] = updated
        return updated

    def enrich_plan_with_shared_graph_rag(
        self,
        plan_id: int,
        *,
        max_depth: Optional[int] = None,
        node_budget: Optional[int] = None,
        graph_rag_mode: str = "mix",
    ) -> DecompositionResult:
        tree = self._repo.get_plan_tree(plan_id)
        depth_limit = max_depth if max_depth is not None else self._settings.max_depth
        budget_limit = (
            node_budget if node_budget is not None else self._settings.total_node_budget
        )
        queue: Deque[QueueItem] = deque(
            QueueItem(node_id=root_id, relative_depth=0) for root_id in tree.root_node_ids()
        )
        root_reference = queue[0].node_id if queue else None

        if tree.is_empty():
            return DecompositionResult(
                plan_id=plan_id,
                mode="graph_rag_enrich",
                root_node_id=None,
                processed_nodes=[],
                created_tasks=[],
                failed_nodes=[],
                stopped_reason="empty_plan",
                stats={
                    "node_budget": budget_limit,
                    "consumed_budget": 0,
                    "queue_remaining": 0,
                    "llm_calls": 0,
                    "enriched_nodes": 0,
                    "graph_rag_calls": 0,
                },
            )

        graph_query = self._build_plan_graph_rag_query(tree)
        logger.info(
            "Running plan-level GraphRAG once for plan %s (mode=%s, query=%s)",
            plan_id,
            graph_rag_mode,
            graph_query,
        )
        graph_payload: Optional[Dict[str, Any]]
        try:
            graph_payload = run_async(
                execute_tool(
                    "graph_rag",
                    query=graph_query,
                    mode=graph_rag_mode,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Plan-level GraphRAG failed for plan %s: %s", plan_id, exc)
            graph_payload = {
                "success": False,
                "error": str(exc),
                "code": "unexpected_error",
            }

        if not isinstance(graph_payload, dict) or not graph_payload.get("success"):
            error = (
                graph_payload.get("error")
                if isinstance(graph_payload, dict)
                else "graph_rag returned an invalid payload"
            )
            return DecompositionResult(
                plan_id=plan_id,
                mode="graph_rag_enrich",
                root_node_id=root_reference,
                processed_nodes=[],
                created_tasks=[],
                failed_nodes=[],
                stopped_reason="graph_rag_failed",
                stats={
                    "node_budget": budget_limit,
                    "consumed_budget": 0,
                    "queue_remaining": len(queue),
                    "llm_calls": 0,
                    "enriched_nodes": 0,
                    "graph_rag_calls": 1,
                    "graph_rag_query": graph_query,
                    "graph_rag_mode": graph_rag_mode,
                    "graph_rag_error": error or "",
                },
            )

        shared_graph_context, graph_meta = self._format_graph_rag_context(
            graph_payload,
            query=graph_query,
        )
        if not shared_graph_context:
            return DecompositionResult(
                plan_id=plan_id,
                mode="graph_rag_enrich",
                root_node_id=root_reference,
                processed_nodes=[],
                created_tasks=[],
                failed_nodes=[],
                stopped_reason="graph_rag_empty",
                stats={
                    "node_budget": budget_limit,
                    "consumed_budget": 0,
                    "queue_remaining": len(queue),
                    "llm_calls": 0,
                    "enriched_nodes": 0,
                    "graph_rag_calls": 1,
                    "graph_rag_query": graph_query,
                    "graph_rag_mode": graph_rag_mode,
                },
            )

        processed: List[Optional[int]] = []
        failed: List[Optional[int]] = []
        llm_calls = 0
        enriched_nodes = 0
        budget_remaining = max(budget_limit, 0)
        outline_cache = tree.to_outline(max_depth=5, max_nodes=80)
        total_targets = self._count_enrich_targets(tree, queue, depth_limit)
        processed_count = 0
        stopped_reason: Optional[str] = None

        while queue and budget_remaining > 0:
            current = queue.popleft()
            if current.relative_depth > depth_limit:
                continue
            node = tree.nodes.get(current.node_id) if current.node_id else None
            if node is None:
                continue

            processed_count += 1
            logger.info(
                "GraphRAG enrich node %s/%s (plan=%s, id=%s, name=%s)",
                processed_count,
                total_targets or "?",
                plan_id,
                node.id,
                node.display_name(),
            )

            parent_web_context = self._collect_parent_web_context(tree, node)
            current_web_context = self._collect_node_web_context(node)
            enrich_prompt = self._build_node_enrichment_prompt(
                plan=tree,
                node=node,
                outline=outline_cache,
                parent_web_context=parent_web_context,
                current_web_context=current_web_context,
                new_web_context=None,
                search_query=None,
                provider=None,
                results_count=None,
                shared_graph_rag_context=shared_graph_context,
                graph_rag_query=graph_meta.get("query"),
                graph_rag_mode=graph_meta.get("mode"),
                graph_rag_backend=graph_meta.get("backend"),
            )

            try:
                raw_update = self._llm.enrich_node(enrich_prompt)
                update_payload = self._parse_node_update(raw_update)
                updated = self._apply_node_update(
                    plan_id=plan_id,
                    node=node,
                    tree=tree,
                    update=update_payload,
                    web_context=None,
                    query=None,
                    provider=None,
                    results_count=None,
                    graph_rag_context=shared_graph_context,
                    graph_rag_meta=graph_meta,
                )
                if updated:
                    enriched_nodes += 1
                    outline_cache = tree.to_outline(max_depth=5, max_nodes=80)
                llm_calls += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Shared GraphRAG node enrichment failed for node %s: %s",
                    node.id,
                    exc,
                )
                failed.append(node.id)
                fallback = self._apply_node_update(
                    plan_id=plan_id,
                    node=node,
                    tree=tree,
                    update={},
                    web_context=None,
                    query=None,
                    provider=None,
                    results_count=None,
                    graph_rag_context=shared_graph_context,
                    graph_rag_meta=graph_meta,
                )
                if fallback:
                    enriched_nodes += 1
                    outline_cache = tree.to_outline(max_depth=5, max_nodes=80)

            processed.append(node.id)
            budget_remaining -= 1
            if current.relative_depth < depth_limit:
                for child_id in tree.children_ids(node.id):
                    if budget_remaining <= 0:
                        break
                    queue.append(
                        QueueItem(
                            node_id=child_id,
                            relative_depth=current.relative_depth + 1,
                        )
                    )

        if budget_remaining <= 0:
            stopped_reason = "node_budget_exhausted"

        return DecompositionResult(
            plan_id=plan_id,
            mode="graph_rag_enrich",
            root_node_id=root_reference,
            processed_nodes=processed,
            created_tasks=[],
            failed_nodes=failed,
            stopped_reason=stopped_reason,
            stats={
                "node_budget": budget_limit,
                "consumed_budget": budget_limit - budget_remaining,
                "queue_remaining": len(queue),
                "llm_calls": llm_calls,
                "enriched_nodes": enriched_nodes,
                "graph_rag_calls": 1,
                "graph_rag_query": graph_query,
                "graph_rag_mode": graph_meta.get("mode") or graph_rag_mode,
                "graph_rag_backend": graph_meta.get("backend") or "",
            },
        )

    def _count_enrich_targets(
        self, tree: PlanTree, queue: Deque[QueueItem], max_depth: int
    ) -> int:
        seen: set[int] = set()
        work: Deque[QueueItem] = deque(queue)
        while work:
            current = work.popleft()
            if current.relative_depth > max_depth:
                continue
            node_id = current.node_id
            if node_id is None:
                continue
            if node_id in seen:
                continue
            seen.add(node_id)
            if current.relative_depth < max_depth:
                for child_id in tree.children_ids(node_id):
                    work.append(
                        QueueItem(
                            node_id=child_id,
                            relative_depth=current.relative_depth + 1,
                        )
                    )
        return len(seen)

    def run_plan(
        self,
        plan_id: int,
        *,
        max_depth: Optional[int] = None,
        node_budget: Optional[int] = None,
        allow_web_search: Optional[bool] = None,
        web_enrich_only: Optional[bool] = None,
    ) -> DecompositionResult:
        """Decompose an entire plan by traversing from the plan root."""
        tree = self._repo.get_plan_tree(plan_id)
        queue: Deque[QueueItem] = deque()
        enrich_only = bool(web_enrich_only)
        if tree.is_empty():
            if enrich_only:
                return DecompositionResult(
                    plan_id=plan_id,
                    mode="web_enrich_only",
                    root_node_id=None,
                    processed_nodes=[],
                    created_tasks=[],
                    failed_nodes=[],
                    stopped_reason="empty_plan",
                    stats={
                        "node_budget": node_budget or self._settings.total_node_budget,
                        "consumed_budget": 0,
                        "queue_remaining": 0,
                        "llm_calls": 0,
                    },
                )
            # Use None to represent virtual plan root so LLM can produce top-level tasks.
            queue.append(QueueItem(node_id=None, relative_depth=0))
        else:
            for root_id in tree.root_node_ids():
                queue.append(QueueItem(node_id=root_id, relative_depth=0))
        root_reference = queue[0].node_id if queue else None
        return self._process_queue(
            plan_id,
            tree=tree,
            mode="web_enrich_only" if enrich_only else "plan_bfs",
            queue=queue,
            max_depth=max_depth if max_depth is not None else self._settings.max_depth,
            node_budget=node_budget
            if node_budget is not None
            else self._settings.total_node_budget,
            root_reference=root_reference,
            allow_web_search=allow_web_search,
            override_allow_existing_children=True if enrich_only else None,
        )

    def decompose_node(
        self,
        plan_id: int,
        node_id: int,
        *,
        expand_depth: Optional[int] = 1,
        node_budget: Optional[int] = None,
        allow_existing_children: Optional[bool] = None,
        allow_web_search: Optional[bool] = None,
        web_enrich_only: Optional[bool] = None,
    ) -> DecompositionResult:
        """Decompose a specific node and optionally continue BFS under it."""
        tree = self._repo.get_plan_tree(plan_id)
        if node_id not in tree.nodes:
            raise ValueError(f"Task {node_id} not found in plan {plan_id}")
        depth_limit = (
            expand_depth if expand_depth is not None else self._settings.max_depth
        )
        enrich_only = bool(web_enrich_only)
        queue: Deque[QueueItem] = deque([QueueItem(node_id=node_id, relative_depth=0)])
        root_reference = node_id
        return self._process_queue(
            plan_id,
            tree=tree,
            mode="web_enrich_only" if enrich_only else "single_node",
            queue=queue,
            max_depth=depth_limit,
            node_budget=node_budget
            if node_budget is not None
            else self._settings.total_node_budget,
            root_reference=root_reference,
            allow_web_search=allow_web_search,
            override_allow_existing_children=True if enrich_only else allow_existing_children,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_queue(
        self,
        plan_id: int,
        *,
        tree: PlanTree,
        mode: str,
        queue: Deque[QueueItem],
        max_depth: int,
        node_budget: int,
        override_allow_existing_children: Optional[bool] = None,
        root_reference: Optional[int] = None,
        allow_web_search: Optional[bool] = None,
    ) -> DecompositionResult:
        processed: List[Optional[int]] = []
        created_nodes: List[PlanNode] = []
        failed: List[Optional[int]] = []
        outline_cache = tree.to_outline(max_depth=5, max_nodes=80)
        budget_remaining = max(node_budget, 0)
        llm_calls = 0
        stopped_reason: Optional[str] = None
        enrich_only = mode == "web_enrich_only"
        enriched_nodes = 0
        total_targets = (
            self._count_enrich_targets(tree, queue, max_depth) if enrich_only else 0
        )
        processed_count = 0

        if budget_remaining == 0:
            return DecompositionResult(
                plan_id=plan_id,
                mode=mode,
                root_node_id=root_reference,
                processed_nodes=processed,
                created_tasks=created_nodes,
                failed_nodes=failed,
                stopped_reason="node_budget_exhausted",
                stats={
                    "node_budget": node_budget,
                    "consumed_budget": 0,
                    "queue_remaining": len(queue),
                    "llm_calls": 0,
                },
            )
        allow_existing = (
            self._settings.allow_existing_children
            if override_allow_existing_children is None
            else override_allow_existing_children
        )
        effective_allow_web_search = (
            self._settings.enable_web_search
            if allow_web_search is None
            else allow_web_search
        )
        if enrich_only:
            allow_existing = True

        while queue and budget_remaining > 0:
            current = queue.popleft()
            if current.relative_depth > max_depth:
                continue

            node = tree.nodes.get(current.node_id) if current.node_id else None
            if enrich_only and node is None:
                continue
            if (
                not allow_existing
                and node is not None
                and tree.children_ids(node.id)
            ):
                logger.debug(
                    "Skip node %s because children already exist and allow_existing=False",
                    node.id,
                )
                _log_job(
                    "debug",
                    "Skipped node because it already has children",
                    {"node_id": node.id, "allow_existing_children": allow_existing},
                )
                continue

            _log_job(
                "info",
                "Preparing to decompose node",
                {
                    "node_id": current.node_id,
                    "depth": current.relative_depth,
                    "queue_remaining": len(queue),
                    "budget_remaining": budget_remaining,
                },
            )
            if enrich_only and node is not None:
                processed_count += 1
                logger.info(
                    "Enrich node %s/%s (id=%s, name=%s)",
                    processed_count,
                    total_targets or "?",
                    node.id,
                    node.display_name(),
                )
                _log_job(
                    "info",
                    "Enrich node progress",
                    {
                        "node_id": node.id,
                        "node_name": node.display_name(),
                        "index": processed_count,
                        "total": total_targets,
                    },
                )
            web_context: Optional[str] = None
            parent_web_context = self._collect_parent_web_context(tree, node)
            current_web_context = self._collect_node_web_context(node)
            if effective_allow_web_search and hasattr(self._llm, "decide_search"):
                decision_prompt = self._build_search_decision_prompt(
                    plan=tree,
                    node=node,
                    outline=outline_cache,
                    depth=current.relative_depth,
                    max_depth=max_depth,
                    parent_web_context=parent_web_context,
                    current_web_context=current_web_context,
                )
                try:
                    raw_decision = self._llm.decide_search(decision_prompt)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception(
                        "Search decision failed for node %s: %s",
                        current.node_id,
                        exc,
                    )
                    _log_job(
                        "error",
                        "Search decision LLM call failed",
                        {"node_id": current.node_id, "error": str(exc)},
                    )
                    raw_decision = ""

                decision = self._parse_search_decision(raw_decision)
                _log_job(
                    "info",
                    "Search decision evaluated",
                    {
                        "node_id": current.node_id,
                        "use_search": decision.use_search,
                        "query": decision.query or "",
                    },
                )
                provider = None
                results_count = 0
                if decision.use_search and decision.query:
                    try:
                        payload = run_async(
                            execute_tool(
                                "web_search",
                                query=decision.query,
                                max_results=5,
                            )
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception(
                            "Web search failed for node %s: %s",
                            current.node_id,
                            exc,
                        )
                        _log_job(
                            "error",
                            "Web search failed",
                            {"node_id": current.node_id, "error": str(exc)},
                        )
                        payload = None

                    if isinstance(payload, dict) and payload.get("success", True):
                        web_context, results_count, provider = self._format_web_context(
                            payload, query=decision.query
                        )
                        if web_context and not enrich_only:
                            self._apply_web_context(
                                plan_id=plan_id,
                                node=node,
                                tree=tree,
                                context=web_context,
                                query=decision.query,
                                provider=provider,
                                results_count=results_count,
                            )
                        _log_job(
                            "info",
                            "Web search completed",
                            {
                                "node_id": current.node_id,
                                "query": decision.query,
                                "provider": provider,
                                "results_count": results_count,
                            },
                        )
                    elif isinstance(payload, dict):
                        _log_job(
                            "error",
                            "Web search returned failure",
                            {
                                "node_id": current.node_id,
                                "query": decision.query,
                                "error": payload.get("error"),
                            },
                        )
                if enrich_only:
                    if web_context and node is not None:
                        enrich_prompt = self._build_node_enrichment_prompt(
                            plan=tree,
                            node=node,
                            outline=outline_cache,
                            parent_web_context=parent_web_context,
                            current_web_context=current_web_context,
                            new_web_context=web_context,
                            search_query=decision.query,
                            provider=provider,
                            results_count=results_count,
                        )
                        try:
                            raw_update = self._llm.enrich_node(enrich_prompt)
                            update_payload = self._parse_node_update(raw_update)
                            updated = self._apply_node_update(
                                plan_id=plan_id,
                                node=node,
                                tree=tree,
                                update=update_payload,
                                web_context=web_context,
                                query=decision.query,
                                provider=provider,
                                results_count=results_count,
                            )
                            if updated:
                                enriched_nodes += 1
                            llm_calls += 1
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.exception(
                                "Node enrichment failed for node %s: %s",
                                current.node_id,
                                exc,
                            )
                            _log_job(
                                "error",
                                "Node enrichment failed",
                                {"node_id": current.node_id, "error": str(exc)},
                            )
                            if web_context:
                                self._apply_web_context(
                                    plan_id=plan_id,
                                    node=node,
                                    tree=tree,
                                    context=web_context,
                                    query=decision.query,
                                    provider=provider,
                                    results_count=results_count,
                                )
                                enriched_nodes += 1
                    processed.append(current.node_id)
                    budget_remaining -= 1
                    if node is not None and current.relative_depth < max_depth:
                        for child_id in tree.children_ids(node.id):
                            if budget_remaining <= 0:
                                break
                            queue.append(
                                QueueItem(
                                    node_id=child_id,
                                    relative_depth=current.relative_depth + 1,
                                )
                            )
                    continue
            elif effective_allow_web_search:
                _log_job(
                    "debug",
                    "Search decision skipped (unsupported LLM)",
                    {"node_id": current.node_id},
                )
            if enrich_only:
                processed.append(current.node_id)
                budget_remaining -= 1
                if node is not None and current.relative_depth < max_depth:
                    for child_id in tree.children_ids(node.id):
                        if budget_remaining <= 0:
                            break
                        queue.append(
                            QueueItem(
                                node_id=child_id,
                                relative_depth=current.relative_depth + 1,
                            )
                        )
                continue
            prompt = self._prompt_builder.build(
                plan=tree,
                node=node,
                outline=outline_cache,
                web_context=web_context,
                mode=mode,
                settings=self._settings,
                depth=current.relative_depth,
                max_depth=max_depth,
            )

            try:
                llm_result = self._llm.generate(prompt)
                llm_calls += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Decomposition failed for node %s: %s", current.node_id, exc)
                _log_job(
                    "error",
                    "LLM decomposition call failed",
                    {"node_id": current.node_id, "error": str(exc)},
                )
                failed.append(current.node_id)
                continue

            processed.append(current.node_id)

            children = self._trim_children(
                llm_result.children, self._settings.max_children
            )
            _log_job(
                "info",
                "LLM returned a decomposition payload",
                {
                    "node_id": current.node_id,
                    "children_count": len(children),
                    "should_stop": llm_result.should_stop,
                },
            )
            if not children:
                if llm_result.should_stop:
                    stopped_reason = llm_result.reason or "llm_requested_stop"
                    _log_job(
                        "info",
                        "LLM requested to stop decomposition",
                        {"node_id": current.node_id, "reason": stopped_reason},
                    )
                    break
                if self._settings.stop_on_empty:
                    stopped_reason = llm_result.reason or "empty_children"
                    _log_job(
                        "info",
                        "No new subtasks; stopping according to settings",
                        {"node_id": current.node_id, "reason": stopped_reason},
                    )
                    break
                continue

            for child in children:
                if budget_remaining <= 0:
                    break
                new_node = self._create_child_node(
                    plan_id, parent_id=current.node_id, child=child
                )
                budget_remaining -= 1
                created_nodes.append(new_node)
                self._update_tree_cache(tree, new_node)
                outline_cache = tree.to_outline(max_depth=5, max_nodes=80)
                _log_job(
                    "info",
                    "Created child task node",
                    {
                        "parent_id": current.node_id,
                        "task_id": new_node.id,
                        "name": new_node.name,
                    },
                )
                if (
                    not child.leaf
                    and current.relative_depth + 1 <= max_depth
                    and budget_remaining > 0
                ):
                    queue.append(
                        QueueItem(
                            node_id=new_node.id,
                            relative_depth=current.relative_depth + 1,
                        )
                    )

            if llm_result.should_stop:
                stopped_reason = llm_result.reason or "llm_requested_stop"
                _log_job(
                    "info",
                    "LLM requested to stop further decomposition",
                    {"node_id": current.node_id, "reason": stopped_reason},
                )
                break

        if budget_remaining <= 0:
            stopped_reason = stopped_reason or "node_budget_exhausted"
            _log_job(
                "info",
                "Decomposition budget exhausted; stopping",
                {"node_budget": node_budget},
            )

        return DecompositionResult(
            plan_id=plan_id,
            mode=mode,
            root_node_id=root_reference,
            processed_nodes=processed,
            created_tasks=created_nodes,
            failed_nodes=failed,
            stopped_reason=stopped_reason,
            stats={
                "node_budget": node_budget,
                "consumed_budget": node_budget - budget_remaining,
                "queue_remaining": len(queue),
                "llm_calls": llm_calls,
                "enriched_nodes": enriched_nodes,
            },
        )

    def _trim_children(
        self, children: Iterable[DecompositionChild], limit: int
    ) -> List[DecompositionChild]:
        return list(children)[: max(limit, 0)]

    def _create_child_node(
        self,
        plan_id: int,
        *,
        parent_id: Optional[int],
        child: DecompositionChild,
    ) -> PlanNode:
        node = self._repo.create_task(
            plan_id,
            name=child.name,
            instruction=child.instruction,
            parent_id=parent_id,
            dependencies=child.dependencies,
        )
        has_context = any(
            [
                child.context_combined,
                child.context_sections,
                child.context_meta,
            ]
        )
        if has_context:
            self._repo.update_task(
                plan_id,
                node.id,
                context_combined=child.context_combined,
                context_sections=child.context_sections,
                context_meta=child.context_meta,
            )
            node = self._repo.get_node(plan_id, node.id)
        return node

    def _update_tree_cache(self, tree: PlanTree, node: PlanNode) -> None:
        tree.nodes[node.id] = node
        tree.adjacency.setdefault(node.parent_id, []).append(node.id)
        tree.rebuild_adjacency()


def run_plan_decomposition(plan_id: int) -> DecompositionResult:
    """Convenience helper mirroring high-level API."""
    decomposer = PlanDecomposer()
    return decomposer.run_plan(plan_id)


def decompose_single_node(plan_id: int, node_id: int) -> DecompositionResult:
    decomposer = PlanDecomposer()
    return decomposer.decompose_node(plan_id, node_id)
