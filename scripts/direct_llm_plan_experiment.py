#!/usr/bin/env python3
"""
Generate plans directly from an LLM (single-shot JSON) and optionally run parallel simulations.

Steps:
1) Read topics (txt/csv/json/jsonl).
2) For each topic, ask LLM to output a complete plan JSON (tasks with parent/dependencies).
3) Validate and insert into the plan repository (creates plan + tasks).
4) Optionally dump raw/parsed plans and run parallel simulations for each plan.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# Ensure repository root is on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv, find_dotenv

from app.database import init_db
from app.repository.plan_repository import PlanRepository
from app.services.llm.llm_service import LLMService


DEFAULT_PROMPT = """You are an expert planner. Generate a complete execution plan as strict JSON with these rules:
- Do NOT include any text outside JSON. No code fences.
- Depth limit: at most 3 levels (root + 2).
- Total tasks: at most 30.
- Each task must include: id (int), name, instruction, parent_id (null for root), dependencies (array of ids), status ("pending").
- Provide reasonable execution order with position (int, per parent).
- Dependencies must reference earlier tasks or siblings already defined.

Return JSON like:
{
  "plan_title": "<title>",
  "description": "<optional description>",
  "tasks": [
    {"id": 1, "name": "...", "instruction": "...", "parent_id": null, "dependencies": [], "status": "pending", "position": 0},
    {"id": 2, "name": "...", "instruction": "...", "parent_id": 1, "dependencies": [1], "status": "pending", "position": 0}
  ]
}

Topic: "{title}"
Goal: {goal}
Details: {description}
"""


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
    error: Optional[str] = None
    raw_path: Optional[Path] = None
    parsed_path: Optional[Path] = None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plans directly from LLM and optionally run simulations.")
    parser.add_argument("--input", required=True, type=Path, help="Topic list (.txt/.csv/.json/.jsonl).")
    parser.add_argument("--prompt-template", type=Path, help="Optional prompt template file.")
    parser.add_argument("--concurrency", type=int, default=2, help="Parallel LLM workers (default: 2).")
    parser.add_argument("--model", type=str, help="Override LLM model name.")
    parser.add_argument("--temperature", type=float, default=0.2, help="LLM sampling temperature (default: 0.2).")
    parser.add_argument("--max-tokens", type=int, help="LLM max tokens.")
    parser.add_argument("--dump-dir", type=Path, default=Path("experiments/llm_direct"), help="Output directory for dumps.")
    parser.add_argument("--skip-sim", action="store_true", help="Only generate plans; skip simulations.")
    parser.add_argument("--runs", type=int, default=0, help="Simulations per plan (default 0 = skip).")
    parser.add_argument("--parallelism", type=int, default=2, help="Max concurrent simulations per plan.")
    parser.add_argument("--max-turns", type=int, default=30, help="Max turns per simulation.")
    parser.add_argument(
        "--max-actions-per-turn",
        type=int,
        choices=[1, 2],
        default=2,
        help="Limit ACTION count per turn for simulations.",
    )
    parser.add_argument("--enable-execute", action="store_true", help="Allow execute_plan during simulations.")
    parser.add_argument("--disable-web-search", action="store_true", help="Disable web_search in simulations.")
    parser.add_argument("--disable-rerun-task", action="store_true", help="Disable rerun_task in simulations.")
    parser.add_argument("--disable-graph-rag", action="store_true", help="Disable graph_rag in simulations.")
    parser.add_argument(
        "--sim-output-root",
        type=Path,
        default=Path("experiments/llm_direct_sim"),
        help="Root directory for simulation outputs (if enabled).",
    )
    return parser.parse_args(argv)


# ---------------- Topic loading ---------------- #


def _load_text(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            title = line.strip()
            if title:
                yield PlanTopic(title=title, goal=title)


def _load_csv(path: Path) -> Iterable[PlanTopic]:
    import csv

    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = {name.lower().strip(): name for name in (reader.fieldnames or [])}
        title_key = fieldnames.get("title")
        goal_key = fieldnames.get("goal")
        desc_key = fieldnames.get("description") or fieldnames.get("detailed description")
        meta_key = fieldnames.get("metadata")
        if not title_key and not goal_key:
            raise ValueError("CSV must include a 'title' or 'goal' column.")
        for row in reader:
            title = (row.get(title_key or "", "") or row.get(goal_key or "", "") or "").strip()
            if not title:
                continue
            goal = (row.get(goal_key or "", "") or title).strip()
            description = (row.get(desc_key or "", "") or None)
            metadata = None
            if meta_key and row.get(meta_key):
                try:
                    metadata = json.loads(row[meta_key])
                except json.JSONDecodeError:
                    metadata = None
            yield PlanTopic(title=title, goal=goal, description=description, metadata=metadata)


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


# ---------------- LLM & parsing ---------------- #


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rstrip("`")
    if cleaned.endswith("```"):
        cleaned = cleaned.rstrip("`")
    return cleaned.strip()


def parse_plan_payload(raw: str) -> Dict[str, Any]:
    text = strip_code_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: attempt to extract first JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            return json.loads(snippet)
        raise


def normalise_tasks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("No tasks provided in payload.")

    norm: List[Dict[str, Any]] = []
    seen_ids: set[int] = set()
    next_id = 1
    for item in tasks:
        if not isinstance(item, dict):
            continue
        ext_id = item.get("id")
        if not isinstance(ext_id, int):
            while next_id in seen_ids:
                next_id += 1
            ext_id = next_id
            next_id += 1
        if ext_id in seen_ids:
            raise ValueError(f"Duplicate task id detected: {ext_id}")
        seen_ids.add(ext_id)
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError(f"Task {ext_id} missing name.")
        instruction = str(item.get("instruction") or name).strip()
        parent_id = item.get("parent_id")
        if not isinstance(parent_id, int):
            parent_id = None
        deps_raw = item.get("dependencies") or []
        deps: List[int] = []
        if isinstance(deps_raw, list):
            for d in deps_raw:
                try:
                    deps.append(int(d))
                except (TypeError, ValueError):
                    continue
        status = str(item.get("status") or "pending").strip() or "pending"
        position = item.get("position")
        try:
            position_int: Optional[int] = int(position) if position is not None else None
        except (TypeError, ValueError):
            position_int = None
        norm.append(
            {
                "ext_id": ext_id,
                "name": name,
                "instruction": instruction,
                "parent_id": parent_id,
                "dependencies": deps,
                "status": status,
                "position": position_int,
            }
        )

    roots = [t for t in norm if t["parent_id"] is None]
    if not roots:
        raise ValueError("No root task (parent_id=null) found.")
    return norm


def insert_plan(repo: PlanRepository, topic: PlanTopic, tasks: List[Dict[str, Any]]) -> int:
    plan = repo.create_plan(
        title=topic.title,
        description=topic.description or topic.goal,
        metadata=topic.metadata or {},
    )
    ext_to_db: Dict[int, int] = {}
    pending = list(tasks)
    progress = True
    while pending and progress:
        progress = False
        remaining: List[Dict[str, Any]] = []
        for task in pending:
            parent_ext = task["parent_id"]
            deps_ext = task["dependencies"]
            if parent_ext is not None and parent_ext not in ext_to_db:
                remaining.append(task)
                continue
            if any(d not in ext_to_db for d in deps_ext):
                remaining.append(task)
                continue
            db_parent = ext_to_db.get(parent_ext) if parent_ext is not None else None
            db_deps = [ext_to_db[d] for d in deps_ext if d in ext_to_db]
            node = repo.create_task(
                plan_id=plan.id,
                name=task["name"],
                instruction=task["instruction"],
                parent_id=db_parent,
                status=task["status"],
                dependencies=db_deps,
                position=task["position"],
            )
            ext_to_db[task["ext_id"]] = node.id
            progress = True
        pending = remaining
    if pending:
        unresolved = [t["ext_id"] for t in pending]
        raise ValueError(f"Unresolved parent/dependencies for tasks: {unresolved}")
    return plan.id


# ---------------- Simulation runner ---------------- #


def run_parallel_simulations(
    plan_id: int,
    args: argparse.Namespace,
    base_output: Path,
) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "parallel_simulation_experiment.py"),
        "--plan-id",
        str(plan_id),
        "--runs",
        str(args.runs),
        "--parallelism",
        str(args.parallelism),
        "--max-turns",
        str(args.max_turns),
        "--max-actions-per-turn",
        str(args.max_actions_per_turn),
        "--output-root",
        str(base_output),
    ]
    if args.enable_execute:
        cmd.append("--enable-execute")
    if args.disable_web_search:
        cmd.append("--disable-web-search")
    if args.disable_rerun_task:
        cmd.append("--disable-rerun-task")
    if args.disable_graph_rag:
        cmd.append("--disable-graph-rag")
    subprocess.run(cmd, check=False)


# ---------------- Main generation logic ---------------- #


def generate_for_topic(
    topic: PlanTopic,
    prompt_template: str,
    args: argparse.Namespace,
    dump_dir: Path,
) -> GenerationResult:
    repo = PlanRepository()
    llm = LLMService()
    prompt = prompt_template.format(
        title=topic.title,
        goal=topic.goal or topic.title,
        description=topic.description or "",
    )
    raw_path = None
    parsed_path = None
    try:
        kwargs: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": args.temperature,
        }
        if args.model:
            kwargs["model"] = args.model
        if args.max_tokens:
            kwargs["max_tokens"] = args.max_tokens
        response = llm.chat(prompt, **kwargs)
        raw_dir = dump_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{topic.title[:50].replace(' ', '_')}_{uuid.uuid4().hex[:6]}.txt"
        raw_path.write_text(response, encoding="utf-8")

        payload = parse_plan_payload(response)
        tasks = normalise_tasks(payload)
        plan_id = insert_plan(repo, topic, tasks)

        if dump_dir:
            parsed_dir = dump_dir / "parsed"
            parsed_dir.mkdir(parents=True, exist_ok=True)
            tree = repo.get_plan_tree(plan_id)
            parsed_path = parsed_dir / f"plan_{plan_id}.json"
            parsed_path.write_text(tree.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] Plan #{plan_id} ({topic.title}) with {len(tasks)} tasks", flush=True)
        return GenerationResult(topic=topic, plan_id=plan_id, raw_path=raw_path, parsed_path=parsed_path)
    except Exception as exc:
        print(f"[ERR] {topic.title}: {exc}", file=sys.stderr, flush=True)
        return GenerationResult(topic=topic, plan_id=None, error=str(exc), raw_path=raw_path, parsed_path=parsed_path)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path)
            print(f"[INFO] Loaded environment variables from {env_path}")
        except Exception as exc:
            print(f"[WARN] Failed to parse {env_path}: {exc}")
    else:
        print("[INFO] No .env file found; using default environment.")

    init_db()
    topics = load_topics(args.input)
    prompt_template = args.prompt_template.read_text(encoding="utf-8") if args.prompt_template else DEFAULT_PROMPT
    dump_dir = args.dump_dir
    dump_dir.mkdir(parents=True, exist_ok=True)

    llm = LLMService()
    print(
        f"[INFO] Starting generation for {len(topics)} topics "
        f"(concurrency={args.concurrency}, model={args.model or 'default'}, temp={args.temperature})"
    )

    results: List[GenerationResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_map = {executor.submit(generate_for_topic, topic, prompt_template, args, dump_dir): topic for topic in topics}
        for future in as_completed(future_map):
            results.append(future.result())

    successes = [r for r in results if r.plan_id is not None]
    failures = [r for r in results if r.plan_id is None]
    print(f"[INFO] Completed generation: {len(successes)} succeeded, {len(failures)} failed.")
    if failures:
        for r in failures:
            print(f" - {r.topic.title}: {r.error}", file=sys.stderr)

    if args.skip_sim or args.runs <= 0 or not successes:
        return

    sim_root = args.sim_output_root
    sim_root.mkdir(parents=True, exist_ok=True)
    for res in successes:
        out_dir = sim_root / f"plan_{res.plan_id}"
        print(f"[INFO] Running simulations for plan #{res.plan_id} into {out_dir}", flush=True)
        run_parallel_simulations(res.plan_id, args, out_dir)


if __name__ == "__main__":
    main()
