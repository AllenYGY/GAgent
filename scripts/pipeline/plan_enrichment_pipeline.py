#!/usr/bin/env python3
"""
Import plan JSON files into a new database, run enrichment, and dump enriched JSON.

This script is configured in-code (no CLI args) so it can be reused later
for other tool-based enrich workflows.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import find_dotenv, load_dotenv  # noqa: E402

from app.config import get_graph_rag_settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.repository.plan_repository import PlanRepository  # noqa: E402
from app.services.plans.action_executor import ActionExecutor  # noqa: E402
from app.services.plans.plan_decomposer import PlanDecomposer  # noqa: E402
from app.services.plans.plan_refactor import (
    PlanRefactor,  # noqa: E402
    RefactorLLMConfig)
from app.utils import run_async  # noqa: E402
from tool_box.tools_impl.graph_rag.service import (  # noqa: E402
    check_graph_rag_health,
)

# --- In-script defaults (override via env) -----------------------------------
DEFAULT_DB_ROOT = "data/databases_deepseek_web_enrich_from_deepseek_v2"
DEFAULT_INPUT_PATH = "results/agent_plans_phage_deepseek/plans"
DEFAULT_OUTPUT_DIR = "results/agent_plans_phage_deepseek_web_enriched_v2/plans"
DEFAULT_TITLE_PREFIX = "Imported"
DEFAULT_ENRICH_MODE = "web_enrich"
DEFAULT_ALLOW_WEB_SEARCH = True
DEFAULT_ALLOW_GRAPH_RAG = True
DEFAULT_GRAPH_RAG_MODE = "mix"
DEFAULT_MAX_DEPTH = None
DEFAULT_NODE_BUDGET = None
DEFAULT_GRAPH_RAG_BACKEND = "lightrag_8_shard"
DEFAULT_REFACTOR_ALLOWLIST = [
    "create_task",
    "update_task",
    "move_task",
    "delete_task",
    "decompose_task",
]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_optional_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_optional_float(name: str,
                        default: Optional[float]) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_plan_tree(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


class GraphRAGUnavailableError(RuntimeError):
    """Raised when continuing would produce an invalid RAG experiment."""


def _iter_plan_nodes(data: Dict):
    nodes = data.get("nodes") or {}
    if isinstance(nodes, dict):
        return nodes.values()
    if isinstance(nodes, list):
        return nodes
    return []


def _is_completed_graph_rag_checkpoint(path: Path,
                                       expected_backend: str) -> bool:
    if not path.is_file():
        return False
    try:
        data = load_plan_tree(path)
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    for node in _iter_plan_nodes(data):
        if not isinstance(node, dict):
            continue
        meta = node.get("context_meta")
        if not isinstance(meta, dict):
            context = node.get("context")
            meta = context.get("meta") if isinstance(context, dict) else None
        graph_meta = meta.get("graph_rag") if isinstance(meta, dict) else None
        backend = graph_meta.get("backend") if isinstance(graph_meta, dict) else None
        if str(backend or "").strip() == expected_backend:
            return True
    return False


def _pending_plan_files(
    files: List[Path],
    *,
    output_dir: Path,
    resume: bool,
    expected_backend: str,
) -> List[Path]:
    if not resume:
        return list(files)
    return [
        path for path in files
        if not _is_completed_graph_rag_checkpoint(output_dir / path.name,
                                                  expected_backend)
    ]


def _validate_graph_rag_health(payload: Dict) -> None:
    total = payload.get("shards_total")
    healthy = payload.get("shards_ok")
    if (payload.get("success") is True and payload.get("status") == "healthy"
            and total == 8 and healthy == 8):
        return
    error = payload.get("error") or "gateway is not fully healthy"
    raise GraphRAGUnavailableError(
        f"LightRAG unavailable ({healthy}/{total} shards healthy): {error}")


def _require_graph_rag_health() -> Dict:
    health = run_async(
        check_graph_rag_health(get_graph_rag_settings(), force=True))
    if not isinstance(health, dict):
        raise GraphRAGUnavailableError(
            "LightRAG health check returned an invalid payload")
    _validate_graph_rag_health(health)
    return health


def _extract_context(node: Dict) -> Dict[str, Optional[object]]:
    if not isinstance(node, dict):
        return {"combined": None, "sections": None, "meta": None}
    if "context" in node and isinstance(node.get("context"), dict):
        ctx = node.get("context") or {}
        return {
            "combined": ctx.get("combined"),
            "sections": ctx.get("sections"),
            "meta": ctx.get("meta"),
        }
    return {
        "combined": node.get("context_combined"),
        "sections": node.get("context_sections"),
        "meta": node.get("context_meta"),
    }


def insert_plan(repo: PlanRepository, data: Dict, prefix: str) -> int:
    title = data.get("title") or f"Plan from {data.get('id', 'unknown')}"
    full_title = f"{prefix} {title}".strip()
    description = data.get("description") or ""
    metadata = data.get("metadata") if isinstance(data.get("metadata"),
                                                  dict) else {}
    nodes = data.get("nodes") or {}
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError("No nodes found in plan JSON.")

    plan = repo.create_plan(title=full_title,
                            description=description,
                            metadata=metadata)
    ext_to_db: Dict[int, int] = {}
    pending: List[Dict] = []
    for key, node in nodes.items():
        try:
            ext_id = int(node.get("id") or key)
        except Exception:
            continue
        pending.append({
            "ext_id":
            ext_id,
            "name":
            node.get("name") or f"Task {ext_id}",
            "instruction":
            node.get("instruction") or node.get("description")
            or node.get("name") or "",
            "parent_id":
            node.get("parent_id"),
            "dependencies":
            node.get("dependencies") or [],
            "status":
            node.get("status") or "pending",
            "position":
            node.get("position"),
            "metadata":
            node.get("metadata")
            if isinstance(node.get("metadata"), dict) else {},
            "context":
            _extract_context(node),
            "execution_result":
            node.get("execution_result"),
        })

    # Insert respecting parent/dependency availability
    progress = True
    while pending and progress:
        progress = False
        remaining: List[Dict] = []
        for task in pending:
            parent_ext = task["parent_id"]
            deps_ext = task["dependencies"]
            if parent_ext is not None and parent_ext not in ext_to_db:
                remaining.append(task)
                continue
            if any(d not in ext_to_db for d in deps_ext):
                remaining.append(task)
                continue
            db_parent = ext_to_db.get(
                parent_ext) if parent_ext is not None else None
            db_deps = [ext_to_db[d] for d in deps_ext if d in ext_to_db]
            node = repo.create_task(
                plan_id=plan.id,
                name=task["name"],
                instruction=task["instruction"],
                parent_id=db_parent,
                status=task["status"],
                dependencies=db_deps,
                metadata=task["metadata"],
                position=int(task["position"])
                if task["position"] is not None else None,
            )
            context = task.get("context") or {}
            exec_result = task.get("execution_result")
            if any([
                    context.get("combined") is not None,
                    context.get("sections") is not None,
                    context.get("meta") is not None,
                    exec_result is not None,
            ]):
                repo.update_task(
                    plan.id,
                    node.id,
                    context_combined=context.get("combined"),
                    context_sections=context.get("sections"),
                    context_meta=context.get("meta"),
                    execution_result=exec_result,
                )
            ext_to_db[task["ext_id"]] = node.id
            progress = True
        pending = remaining

    if pending:
        unresolved = [t["ext_id"] for t in pending]
        raise ValueError(
            f"Unresolved parent/dependencies for tasks: {unresolved}")

    return plan.id


def dump_plan_json(repo: PlanRepository,
                   plan_id: int,
                   output_dir: Path,
                   *,
                   filename: Optional[str] = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    tree = repo.get_plan_tree(plan_id)
    output_path = output_dir / (filename or f"plan_{plan_id}.json")
    checkpoint_plan_id = _checkpoint_plan_id(filename)
    if checkpoint_plan_id is not None:
        _reassign_plan_id(tree, checkpoint_plan_id)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        tree.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary_path, output_path)
    return output_path


def _plan_file_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"plan_(\d+)\.json$", path.name)
    if match:
        return int(match.group(1)), path.name
    return sys.maxsize, path.name


def _checkpoint_plan_id(filename: Optional[str]) -> Optional[int]:
    if not filename:
        return None
    match = re.fullmatch(r"plan_(\d+)\.json", Path(filename).name)
    return int(match.group(1)) if match else None


def _reassign_plan_id(tree, canonical_plan_id: int) -> None:
    tree.id = canonical_plan_id
    for node in tree.nodes.values():
        node.plan_id = canonical_plan_id


def _has_web_enriched_context(tree) -> bool:
    for node in tree.iter_nodes():
        if isinstance(node.context_meta,
                      dict) and node.context_meta.get("web_search"):
            return True
        for section in node.context_sections or []:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or "").strip().lower()
            if title.startswith("web"):
                return True
    return False


def _run_enrichment(
    *,
    decomposer: PlanDecomposer,
    repo: PlanRepository,
    plan_id: int,
    mode: str,
    max_depth: Optional[int],
    node_budget: Optional[int],
    allow_web_search: bool,
    allow_graph_rag: bool,
    graph_rag_mode: str,
):
    if mode == "graph_rag_enrich":
        if not allow_graph_rag:
            raise ValueError(
                "graph_rag_enrich requires ENRICH_ALLOW_GRAPH_RAG=true")
        tree = repo.get_plan_tree(plan_id)
        if not _has_web_enriched_context(tree):
            print(
                f"[WARN] Plan #{plan_id} does not appear to include prior web enrichment context.",
                file=sys.stderr,
            )
        result = decomposer.enrich_plan_with_shared_graph_rag(
            plan_id,
            max_depth=max_depth,
            node_budget=node_budget,
            graph_rag_mode=graph_rag_mode,
        )
        if result.stopped_reason in {"graph_rag_failed", "graph_rag_empty"}:
            error = result.stats.get("graph_rag_error") or result.stopped_reason
            raise GraphRAGUnavailableError(
                f"{result.stopped_reason}: {error}")
        return result

    return decomposer.run_plan(
        plan_id,
        max_depth=max_depth,
        node_budget=node_budget,
        allow_web_search=allow_web_search,
        web_enrich_only=True,
    )


def main() -> None:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path)
            print(f"[INFO] Loaded environment variables from {env_path}")
        except Exception as exc:
            print(f"[WARN] Failed to parse {env_path}: {exc}")
    else:
        print("[INFO] No .env file found; using default environment.")

    db_root = os.getenv("DB_ROOT", DEFAULT_DB_ROOT)
    input_path = Path(os.getenv("ENRICH_INPUT_PATH", DEFAULT_INPUT_PATH))
    output_dir = Path(os.getenv("ENRICH_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    title_prefix = os.getenv("ENRICH_TITLE_PREFIX", DEFAULT_TITLE_PREFIX)
    enrich_mode = (os.getenv("ENRICH_MODE",
                             DEFAULT_ENRICH_MODE).strip().lower()
                   or DEFAULT_ENRICH_MODE)
    allow_web_search = _env_bool("ENRICH_ALLOW_WEB_SEARCH",
                                 DEFAULT_ALLOW_WEB_SEARCH)
    allow_graph_rag = _env_bool("ENRICH_ALLOW_GRAPH_RAG",
                                DEFAULT_ALLOW_GRAPH_RAG)
    graph_rag_mode = (os.getenv("ENRICH_GRAPH_RAG_MODE",
                                DEFAULT_GRAPH_RAG_MODE).strip().lower()
                      or DEFAULT_GRAPH_RAG_MODE)
    graph_rag_backend = (os.getenv("ENRICH_GRAPH_RAG_BACKEND",
                                  DEFAULT_GRAPH_RAG_BACKEND).strip()
                         or DEFAULT_GRAPH_RAG_BACKEND)
    resume = _env_bool("ENRICH_RESUME", False)
    max_depth = _env_optional_int("ENRICH_MAX_DEPTH", DEFAULT_MAX_DEPTH)
    node_budget = _env_optional_int("ENRICH_NODE_BUDGET", DEFAULT_NODE_BUDGET)
    enable_refactor = _env_bool("ENRICH_ENABLE_REFACTOR", False)
    refactor_max_actions = _env_optional_int("REFACTOR_MAX_ACTIONS", 25) or 25
    refactor_allowlist = _env_list("REFACTOR_ACTION_ALLOWLIST",
                                   DEFAULT_REFACTOR_ALLOWLIST)
    refactor_allow_delete_subtree = _env_bool("REFACTOR_ALLOW_DELETE_SUBTREE",
                                              False)
    refactor_decompose_allow_web_search = _env_bool(
        "REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH", False)
    refactor_provider = os.getenv("REFACTOR_PROVIDER")
    refactor_model = os.getenv("REFACTOR_MODEL")
    refactor_api_url = os.getenv("REFACTOR_API_URL")
    refactor_api_key = os.getenv("REFACTOR_API_KEY")
    refactor_temperature = _env_optional_float("REFACTOR_TEMPERATURE", None)
    refactor_log_dir = os.getenv("REFACTOR_LOG_DIR")

    if enrich_mode not in {"web_enrich", "graph_rag_enrich"}:
        print(
            f"[ERR] Unsupported ENRICH_MODE={enrich_mode!r}. "
            "Expected one of: web_enrich, graph_rag_enrich.",
            file=sys.stderr,
        )
        sys.exit(1)

    os.environ["DB_ROOT"] = db_root

    init_db()
    repo = PlanRepository()
    decomposer = PlanDecomposer(repo=repo)
    action_executor = ActionExecutor(repo=repo, plan_decomposer=decomposer)
    refactor = None
    if enable_refactor:
        llm_config = RefactorLLMConfig(
            provider=refactor_provider,
            model=refactor_model,
            api_url=refactor_api_url,
            api_key=refactor_api_key,
            temperature=refactor_temperature,
        )
        refactor = PlanRefactor(
            repo=repo,
            action_executor=action_executor,
            llm_config=llm_config,
        )

    if input_path.is_dir():
        files = sorted(input_path.glob("plan_*.json"), key=_plan_file_sort_key)
    else:
        files = [input_path]

    if not files:
        print(f"[ERR] No plan_*.json files found under {input_path}",
              file=sys.stderr)
        sys.exit(1)

    all_files = files
    files = _pending_plan_files(
        all_files,
        output_dir=output_dir,
        resume=resume and enrich_mode == "graph_rag_enrich",
        expected_backend=graph_rag_backend,
    )
    completed_count = len(all_files) - len(files)
    print(
        f"[INFO] Checkpoints: completed={completed_count} "
        f"pending={len(files)} total={len(all_files)} resume={resume}",
        flush=True,
    )
    if not files:
        print("[INFO] All input plans already have valid checkpoints. Exiting.")
        return

    created: List[tuple[Path, int]] = []
    for path in files:
        try:
            data = load_plan_tree(path)
            plan_id = insert_plan(repo, data, title_prefix)
            created.append((path, plan_id))
            print(f"[OK] Imported {path.name} -> plan #{plan_id}")
        except Exception as exc:
            print(f"[ERR] Failed to import {path}: {exc}", file=sys.stderr)

    if not created:
        print("[WARN] No plans imported. Exiting.")
        return

    mode_label = ("web enrich-only" if enrich_mode == "web_enrich" else
                  f"graph_rag enrich-only (mode={graph_rag_mode})")
    print(f"\n[INFO] Running {mode_label} on imported plans...")
    total = len(created)
    for idx, (path, plan_id) in enumerate(created, start=1):
        print(
            f"[INFO] Enriching plan {idx}/{total}: {path.name} -> plan #{plan_id}"
        )
        try:
            if enrich_mode == "graph_rag_enrich":
                health = _require_graph_rag_health()
                print(
                    f"[INFO] LightRAG health: "
                    f"{health.get('shards_ok')}/{health.get('shards_total')} shards",
                    flush=True,
                )
            started = time.perf_counter()
            result = _run_enrichment(
                decomposer=decomposer,
                repo=repo,
                plan_id=plan_id,
                mode=enrich_mode,
                max_depth=max_depth,
                node_budget=node_budget,
                allow_web_search=allow_web_search,
                allow_graph_rag=allow_graph_rag,
                graph_rag_mode=graph_rag_mode,
            )
            elapsed = time.perf_counter() - started
            print(f"[OK] Enriched plan #{plan_id} "
                  f"(processed={len(result.processed_nodes)}, "
                  f"enriched={result.stats.get('enriched_nodes', 0)}, "
                  f"llm_calls={result.stats.get('llm_calls', 0)}, "
                  f"graph_rag_calls={result.stats.get('graph_rag_calls', 0)}, "
                  f"elapsed={elapsed:.1f}s)")
        except GraphRAGUnavailableError as exc:
            print(f"[FATAL] {exc}", file=sys.stderr, flush=True)
            raise
        except Exception as exc:
            print(f"[ERR] Enrich failed for plan #{plan_id}: {exc}",
                  file=sys.stderr)
            continue

        if enable_refactor and refactor is not None:
            print(f"[INFO] Refactoring plan #{plan_id} with ACTIONs...")
            try:
                started = time.perf_counter()
                log_dir = (Path(refactor_log_dir) if refactor_log_dir else
                           output_dir / "refactor_logs")
                result = refactor.run(
                    plan_id,
                    allowlist=refactor_allowlist,
                    max_actions=refactor_max_actions,
                    allow_delete_subtree=refactor_allow_delete_subtree,
                    allow_decompose_web_search=
                    refactor_decompose_allow_web_search,
                    model=refactor_model,
                    temperature=refactor_temperature,
                    log_dir=log_dir,
                )
                elapsed = time.perf_counter() - started
                success_count = sum(1 for r in result.results if r.success)
                failed_count = sum(1 for r in result.results if not r.success)
                print(f"[OK] Refactor plan #{plan_id} "
                      f"(actions={len(result.actions)}, "
                      f"dropped={result.dropped_count}, "
                      f"success={success_count}, failed={failed_count}, "
                      f"elapsed={elapsed:.1f}s)")
            except Exception as exc:
                print(
                    f"[ERR] Refactor failed for plan #{plan_id}: {exc}",
                    file=sys.stderr,
                )
        try:
            output_path = dump_plan_json(repo,
                                         plan_id,
                                         output_dir,
                                         filename=path.name)
            print(f"[CHECKPOINT] {output_path}", flush=True)
        except Exception as exc:
            print(f"[ERR] Checkpoint failed for plan #{plan_id}: {exc}",
                  file=sys.stderr,
                  flush=True)
            raise


if __name__ == "__main__":
    main()
