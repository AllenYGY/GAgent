#!/usr/bin/env python3
"""
Resume decomposition for existing plans without creating new plan IDs.

Use cases:
- API key exhaustion caused partial plans (root-only). This script resumes
  decomposition for plans with small node counts.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Ensure repository root is on sys.path so we can import app.*
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import find_dotenv, load_dotenv  # type: ignore

from app.config.decomposer_config import get_decomposer_settings
from app.database import init_db
from app.repository.plan_repository import PlanRepository
from app.services.plans.plan_decomposer import PlanDecomposer


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume decomposition for existing plans.")
    parser.add_argument("--input", required=True, type=Path, help="Topic list (.txt/.csv/.json/.jsonl).")
    parser.add_argument("--passes", type=int, default=1, help="Recursive decomposition passes (default: 1).")
    parser.add_argument("--expand-depth", type=int, default=1, help="expand_depth for PlanDecomposer (default: 1).")
    parser.add_argument("--node-budget", type=int, default=20, help="node_budget per decomposition call (default: 20).")
    parser.add_argument("--min-nodes", type=int, default=2, help="Resume if plan has fewer than this many nodes.")
    parser.add_argument("--dump-dir", type=Path, help="Optional directory to store plan trees (JSON).")
    parser.add_argument("--concurrency", type=int, default=1, help="Parallel workers (default: 1 = sequential).")
    return parser.parse_args(argv)


def _load_topics(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        lines = path.read_text(encoding="utf-8").splitlines()
        titles = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = __import__("json").loads(raw)
            except Exception:
                obj = raw
            if isinstance(obj, str):
                titles.append(obj)
            elif isinstance(obj, dict):
                titles.append(str(obj.get("title") or obj.get("goal") or "").strip())
        return [t for t in titles if t]
    if suffix == ".json":
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("topics") or data.get("items") or []
        titles = []
        for item in data:
            if isinstance(item, str):
                titles.append(item)
            elif isinstance(item, dict):
                titles.append(str(item.get("title") or item.get("goal") or "").strip())
        return [t for t in titles if t]
    if suffix == ".csv":
        import csv

        titles = []
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                title = (row.get("title") or row.get("goal") or "").strip()
                if title:
                    titles.append(title)
        return titles
    # txt
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_env() -> None:
    if os.getenv("SKIP_DOTENV", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("[INFO] SKIP_DOTENV set; skipping .env loading.")
        return
    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path)
            print(f"[INFO] Loaded environment variables from {env_path}")
        except Exception as exc:
            print(f"[WARN] Failed to parse {env_path}: {exc}. Check for invalid lines.")
    else:
        print("[INFO] No .env file found; using default environment.")


def _configure_decomposer(repo: PlanRepository) -> PlanDecomposer:
    settings = get_decomposer_settings()
    provider = os.getenv("DECOMP_PROVIDER") or settings.provider
    model = os.getenv("DECOMP_MODEL") or settings.model
    api_url = os.getenv("DECOMP_API_URL") or settings.api_url
    api_key = os.getenv("DECOMP_API_KEY") or settings.api_key
    enable_web = os.getenv("DECOMP_ENABLE_WEB_SEARCH")
    if enable_web is not None:
        enable_web_search = str(enable_web).strip().lower() in {"1", "true", "yes", "on"}
    else:
        enable_web_search = settings.enable_web_search
    settings = replace(
        settings,
        provider=provider,
        model=model,
        api_url=api_url,
        api_key=api_key,
        enable_web_search=enable_web_search,
    )
    decomposer = PlanDecomposer(repo=repo, settings=settings)
    ds = decomposer.settings
    print(
        "[INFO] LLM/decomposer config: "
        f"model={ds.model or 'default'} provider={ds.provider or 'default'} "
        f"api_url={ds.api_url or 'default'} max_depth={ds.max_depth} "
        f"min_children={ds.min_children} max_children={ds.max_children}",
        flush=True,
    )
    return decomposer


def _resume_plan(
    repo: PlanRepository,
    decomposer: PlanDecomposer,
    plan_id: int,
    *,
    passes: int,
    expand_depth: int,
    node_budget: int,
    dump_dir: Optional[Path],
) -> bool:
    tree = repo.get_plan_tree(plan_id)
    node_count = len(tree.nodes)
    if node_count >= 2:
        return False
    roots = tree.adjacency.get(None, [])
    if not roots:
        roots = [node.id for node in tree.nodes.values() if node.parent_id is None]
    if not roots:
        print(f"[WARN] Plan #{plan_id}: no root task found.", flush=True)
        return False

    queue = list(roots)
    for depth in range(passes):
        if not queue:
            break
        print(
            f"[INFO] Plan #{plan_id} pass {depth + 1}/{passes} – seeds: {len(queue)} "
            f"(expand_depth={expand_depth}, node_budget={node_budget})",
            flush=True,
        )
        next_seeds: List[int] = []
        for task_id in queue:
            result = decomposer.decompose_node(
                plan_id,
                task_id,
                expand_depth=expand_depth,
                node_budget=node_budget,
                allow_existing_children=True,
            )
            new_ids = [node.id for node in result.created_tasks]
            print(
                f"[INFO]   decomposed task {task_id} → +{len(new_ids)} nodes "
                f"(llm_calls={result.stats.get('llm_calls', 0)}, stopped={result.stopped_reason or 'no'})",
                flush=True,
            )
            if depth < passes - 1:
                next_seeds.extend(new_ids)
        queue = next_seeds

    if dump_dir:
        dump_dir.mkdir(parents=True, exist_ok=True)
        updated = repo.get_plan_tree(plan_id)
        path = dump_dir / f"plan_{plan_id}.json"
        path.write_text(updated.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[INFO] Dumped plan #{plan_id} to {path}", flush=True)
    return True


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    topics = _load_topics(args.input)
    if not topics:
        print("[ERR] No topics parsed from input.", file=sys.stderr)
        sys.exit(1)

    _load_env()
    print("[INFO] Initialising database ...")
    init_db()
    print("[INFO] Database ready. Starting resume...")

    repo = PlanRepository()
    decomposer = _configure_decomposer(repo)

    plan_ids = list(range(1, len(topics) + 1))
    min_nodes = max(1, args.min_nodes)

    def worker(plan_id: int) -> tuple[int, bool, Optional[str]]:
        try:
            tree = repo.get_plan_tree(plan_id)
        except Exception as exc:
            return plan_id, False, f"plan not found: {exc}"
        if len(tree.nodes) >= min_nodes:
            return plan_id, False, None
        try:
            resumed = _resume_plan(
                repo,
                decomposer,
                plan_id,
                passes=max(1, args.passes),
                expand_depth=max(1, args.expand_depth),
                node_budget=max(1, args.node_budget),
                dump_dir=args.dump_dir,
            )
            return plan_id, resumed, None
        except Exception as exc:
            return plan_id, False, str(exc)

    concurrency = max(1, args.concurrency)
    if concurrency == 1:
        results = [worker(pid) for pid in plan_ids]
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_map = {executor.submit(worker, pid): pid for pid in plan_ids}
            for future in as_completed(future_map):
                results.append(future.result())

    resumed = sum(1 for _, did, err in results if did and not err)
    skipped = sum(1 for _, did, err in results if not did and not err)
    failed = sum(1 for _, did, err in results if err)
    print(f"\nResume summary → resumed={resumed} skipped={skipped} failed={failed}")
    for pid, _, err in results:
        if err:
            print(f" - Plan #{pid}: {err}")


if __name__ == "__main__":
    main()
