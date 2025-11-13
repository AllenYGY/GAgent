#!/usr/bin/env python3
"""
Direct plan generator.

Creates plans and performs synchronous decomposition by calling the repository
and decomposer classes directly (no /chat/message round-trip).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Ensure repository root is on sys.path so we can import app.*
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv, find_dotenv

from app.config.decomposer_config import get_decomposer_settings
from app.database import init_db
from app.repository.plan_repository import PlanRepository
from app.services.plans.plan_decomposer import PlanDecomposer


@dataclass
class PlanTopic:
    title: str
    goal: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class GenerationResult:
    topic: PlanTopic
    plan_id: Optional[int]
    root_task_id: Optional[int]
    created_tasks: List[int]
    passes_run: int
    stopped_reasons: List[str]
    error: Optional[str] = None
    tree_path: Optional[Path] = None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct plan generator (repository + decomposer).")
    parser.add_argument("--input", required=True, type=Path, help="Topic list (.txt/.csv/.json/.jsonl).")
    parser.add_argument("--passes", type=int, default=1, help="Recursive decomposition passes (default: 1).")
    parser.add_argument("--expand-depth", type=int, default=1, help="expand_depth for PlanDecomposer (default: 1).")
    parser.add_argument("--node-budget", type=int, default=20, help="node_budget per decomposition call (default: 20).")
    parser.add_argument("--dump-dir", type=Path, help="Optional directory to store plan trees (JSON).")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed topics without touching DB.")
    parser.add_argument("--concurrency", type=int, default=1, help="Parallel workers (default: 1 = sequential).")
    return parser.parse_args(argv)


def _load_text(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            title = line.strip()
            if title:
                yield PlanTopic(title=title, goal=title)


def _load_csv(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "title" not in reader.fieldnames and "goal" not in reader.fieldnames:
            raise ValueError("CSV must include a 'title' or 'goal' column.")
        for row in reader:
            title = (row.get("title") or row.get("goal") or "").strip()
            if not title:
                continue
            goal = (row.get("goal") or title).strip()
            metadata = None
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    metadata = None
            yield PlanTopic(
                title=title,
                goal=goal,
                description=row.get("description") or None,
                metadata=metadata,
            )


def _load_json_lines(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            payload = raw.strip()
            if not payload:
                continue
            record = json.loads(payload)
            if isinstance(record, str):
                yield PlanTopic(title=record, goal=record)
                continue
            title = str(record.get("title") or record.get("goal") or "").strip()
            if not title:
                continue
            goal = str(record.get("goal") or title).strip()
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else None
            yield PlanTopic(title=title, goal=goal, description=record.get("description"), metadata=metadata)


def _load_json_array(path: Path) -> Iterable[PlanTopic]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("topics") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError(f"Unsupported JSON shape in {path}")
    for entry in data:
        if isinstance(entry, str):
            yield PlanTopic(title=entry, goal=entry)
            continue
        title = str(entry.get("title") or entry.get("goal") or "").strip()
        if not title:
            continue
        goal = str(entry.get("goal") or title).strip()
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None
        yield PlanTopic(title=title, goal=goal, description=entry.get("description"), metadata=metadata)


def load_topics(path: Path) -> List[PlanTopic]:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        items = list(_load_json_lines(path))
    elif suffix == ".json":
        items = list(_load_json_array(path))
    elif suffix == ".csv":
        items = list(_load_csv(path))
    else:
        items = list(_load_text(path))
    if not items:
        raise ValueError(f"No topics parsed from {path}")
    return items


def build_instruction(topic: PlanTopic) -> str:
    parts = [topic.goal or topic.title]
    if topic.description:
        parts.append(f"Details: {topic.description}")
    return "\n\n".join(parts)


def create_plan_with_root(repo: PlanRepository, topic: PlanTopic) -> tuple[int, int]:
    plan = repo.create_plan(
        title=topic.title,
        description=topic.description or topic.goal,
        metadata=topic.metadata or {},
    )
    root = repo.create_task(
        plan.id,
        name=topic.title,
        instruction=build_instruction(topic),
    )
    return plan.id, root.id


def run_decomposition(
    repo: PlanRepository,
    decomposer: PlanDecomposer,
    plan_id: int,
    seed_tasks: List[int],
    *,
    passes: int,
    expand_depth: int,
    node_budget: int,
) -> tuple[List[int], List[str]]:
    created_ids: List[int] = []
    stopped: List[str] = []
    queue = list(seed_tasks)
    for depth in range(passes):
        if not queue:
            break
        next_seeds: List[int] = []
        for task_id in queue:
            try:
                result = decomposer.decompose_node(
                    plan_id,
                    task_id,
                    expand_depth=expand_depth,
                    node_budget=node_budget,
                    allow_existing_children=True,
                )
                new_ids = [node.id for node in result.created_tasks]
                created_ids.extend(new_ids)
                if result.stopped_reason:
                    stopped.append(result.stopped_reason)
                if depth < passes - 1:
                    next_seeds.extend(new_ids)
            except Exception as exc:  # pragma: no cover - defensive logging
                stopped.append(f"task {task_id} failed: {exc}")
        queue = next_seeds
    return created_ids, stopped


def dump_plan_tree(repo: PlanRepository, plan_id: int, target_dir: Path) -> Path:
    tree = repo.get_plan_tree(plan_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"plan_{plan_id}.json"
    path.write_text(tree.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def generate_plans(args: argparse.Namespace, topics: List[PlanTopic]) -> List[GenerationResult]:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path)
        except Exception as exc:  # pragma: no cover - best effort messaging
            print(f"[WARN] Failed to parse {env_path}: {exc}. Check for invalid lines (e.g., ';' comments).")
        else:
            print(f"[INFO] Loaded environment variables from {env_path}")
    else:
        print("[INFO] No .env file found; using default environment.")
    print("[INFO] Initialising database ...")
    init_db()
    print("[INFO] Database ready. Starting plan generation...")
    def worker(topic: PlanTopic) -> GenerationResult:
        repo = PlanRepository()
        decomposer = PlanDecomposer(repo=repo, settings=get_decomposer_settings())
        try:
            print(f"[INFO] Creating plan for topic: {topic.title}")
            plan_id, root_task_id = create_plan_with_root(repo, topic)
            created_ids, stopped = run_decomposition(
                repo,
                decomposer,
                plan_id,
                [root_task_id],
                passes=max(1, args.passes),
                expand_depth=max(1, args.expand_depth),
                node_budget=max(1, args.node_budget),
            )
            tree_path = None
            if args.dump_dir:
                tree_path = dump_plan_tree(repo, plan_id, args.dump_dir)
            print(f"[OK] Plan #{plan_id} ({topic.title}) root={root_task_id} created_nodes={len(created_ids)}")
            return GenerationResult(
                topic=topic,
                plan_id=plan_id,
                root_task_id=root_task_id,
                created_tasks=created_ids,
                passes_run=args.passes,
                stopped_reasons=stopped,
                tree_path=tree_path,
            )
        except Exception as exc:
            print(f"[ERR] {topic.title}: {exc}", file=sys.stderr)
            return GenerationResult(
                topic=topic,
                plan_id=None,
                root_task_id=None,
                created_tasks=[],
                passes_run=args.passes,
                stopped_reasons=[],
                error=str(exc),
            )

    concurrency = max(1, args.concurrency)
    if concurrency == 1:
        return [worker(topic) for topic in topics]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: List[GenerationResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {executor.submit(worker, topic): topic for topic in topics}
        for future in as_completed(future_map):
            results.append(future.result())
    return results


def print_summary(results: List[GenerationResult]) -> None:
    total = len(results)
    successes = sum(1 for r in results if r.plan_id is not None)
    print(f"\nGenerated {total} plans – {successes} succeeded, {total - successes} failed.")
    for result in results:
        if result.error:
            print(f" - {result.topic.title}: {result.error}")
        elif result.stopped_reasons:
            reasons = "; ".join(result.stopped_reasons)
            print(f" - {result.topic.title}: stopped={reasons}")


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    topics = load_topics(args.input)

    if args.dry_run:
        for idx, topic in enumerate(topics, 1):
            print(f"{idx:02d}. {topic.title} – goal: {topic.goal}")
        return

    results = generate_plans(args, topics)
    print_summary(results)


if __name__ == "__main__":
    main()
