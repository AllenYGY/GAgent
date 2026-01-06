#!/usr/bin/env python3
"""
Generate plans directly from an LLM and export them as PlanTree JSON files.

This follows docs/plans/llm_direct_plan_eval.md:
- Read topics from txt/csv/json/jsonl.
- Prompt the LLM to return a single JSON plan (schema aligned with PlanTree).
- Validate/normalize the JSON, build PlanTree, and save under out_dir/parsed/.
- Store raw LLM responses under out_dir/raw/.
- Record failures in out_dir/failed.jsonl.

Example:
python scripts/generate_llm_plans.py \
  --input topics.jsonl \
  --model qwen3-max \
  --provider qwen \
  --out-dir experiments/llm_plans \
  --concurrency 4 \
  --max-retries 2
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:  # Optional; skip if not available
    from dotenv import find_dotenv as _find_dotenv  # type: ignore
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    _find_dotenv = None
    _load_dotenv = None


def find_dotenv(*args, **kwargs) -> Optional[str]:
    if _find_dotenv is None:
        return None
    return _find_dotenv(*args, **kwargs)


def load_dotenv(*args, **kwargs) -> bool:
    if _load_dotenv is None:
        return False
    return bool(_load_dotenv(*args, **kwargs))


# Ensure repository root on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.llm import LLMClient  # noqa: E402
from app.services.plans.plan_models import PlanNode, PlanTree  # noqa: E402

DEFAULT_PROMPT = """You are a planning expert. Given a topic and goal, return ONLY one JSON object for a plan.
Schema (all fields required unless noted):
{
  "plan_id": "<leave empty or number>",
  "title": "<short title>",
  "description": "<concise description>",
  "tasks": [
    {
      "id": <integer unique>,
      "name": "<task name>",
      "instruction": "<clear, actionable steps>",
      "status": "pending",
      "parent_id": <integer parent id or null for root>,
      "position": <integer order within siblings>,
      "dependencies": [<integer task ids>],
      "metadata": {}
    }
  ]
}
Constraints:
- Depth <= 3; total tasks <= 20.
- Do NOT include any text outside the JSON. Do NOT wrap in markdown.
- Use explicit parent_id/dependencies; keep numbering consistent.
- Make tasks specific and executable for the given goal/topic.
Topic: "{title}"
Goal: {goal}
If description exists, include it: {description}
Return the JSON now."""


# ------------------------- Data structures -----------------------------------


@dataclass
class PlanTopic:
    title: str
    goal: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PlanResult:
    topic: PlanTopic
    plan_id: Optional[int]
    success: bool
    error: Optional[str]
    raw_path: Optional[Path]
    parsed_path: Optional[Path]


# ------------------------- CLI helpers ---------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plans directly from an LLM.")
    parser.add_argument(
        "--input", required=True, type=Path, help="Topic list (txt/csv/json/jsonl)."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("experiments/llm_plans"),
        help="Output root directory.",
    )
    parser.add_argument(
        "--prompt-template", type=Path, help="Optional prompt template file."
    )
    parser.add_argument("--model", type=str, help="LLM model override.")
    parser.add_argument(
        "--provider", type=str, help="LLM provider override (glm/qwen/...)."
    )
    parser.add_argument("--api-key", type=str, help="Override API key.")
    parser.add_argument("--api-url", type=str, help="Override base URL.")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="Parallel workers (default: 4)."
    )
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Retries per topic (default: 2)."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="LLM request timeout seconds (default: 90).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompts only, no LLM calls."
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on number of topics to process (e.g., first 20).",
    )
    return parser.parse_args(argv)


# ------------------------- Topic loading -------------------------------------


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
        field_map = {name.lower().strip(): name for name in (reader.fieldnames or [])}
        title_key = field_map.get("title")
        goal_key = field_map.get("goal")
        desc_key = field_map.get("description") or field_map.get("detailed description")
        meta_key = field_map.get("metadata")

        if not title_key and not goal_key:
            raise ValueError("CSV must include a 'title' or 'goal' column.")
        for row in reader:
            title = (
                row.get(title_key or "", "") or row.get(goal_key or "", "") or ""
            ).strip()
            if not title:
                continue
            goal = (row.get(goal_key or "", "") or title).strip()
            description = row.get(desc_key or "", "") or None
            metadata = None
            raw_meta = row.get(meta_key or "", "")
            if raw_meta:
                try:
                    metadata = json.loads(raw_meta)
                except json.JSONDecodeError:
                    metadata = None
            yield PlanTopic(
                title=title,
                goal=goal,
                description=description,
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
            metadata = (
                record.get("metadata")
                if isinstance(record.get("metadata"), dict)
                else None
            )
            yield PlanTopic(
                title=title,
                goal=goal,
                description=record.get("description"),
                metadata=metadata,
            )


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
        metadata = (
            entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None
        )
        yield PlanTopic(
            title=title,
            goal=goal,
            description=entry.get("description"),
            metadata=metadata,
        )


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


# ------------------------- Prompt & JSON helpers -----------------------------


def render_prompt(template: str, topic: PlanTopic) -> str:
    def _esc(val: Any) -> str:
        return str(val or "").replace("{", "{{").replace("}", "}}")

    title = _esc(topic.title)
    goal = _esc(topic.goal or topic.title)
    desc = _esc(topic.description or "")
    # Use simple replace to avoid recursion issues with str.format
    return (
        template.replace("{title}", title)
        .replace("{goal}", goal)
        .replace("{description}", desc)
    )


def extract_json_block(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction: try full parse; if fails, locate first '{'...' }'.
    """
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response.")
    snippet = text[start : end + 1]
    return json.loads(snippet)


# ------------------------- Plan normalization --------------------------------


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def normalize_plan(raw_plan: Dict[str, Any], fallback_plan_id: int) -> PlanTree:
    plan_id = _safe_int(raw_plan.get("plan_id")) or fallback_plan_id
    title = str(raw_plan.get("title") or f"Plan {plan_id}").strip()
    description = str(raw_plan.get("description") or title).strip()
    tasks = raw_plan.get("tasks") or []
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("tasks must be a non-empty list")

    # First pass: basic fields
    nodes: Dict[int, Dict[str, Any]] = {}
    for item in tasks:
        if not isinstance(item, dict):
            continue
        task_id = _safe_int(item.get("id"))
        if task_id is None or task_id in nodes:
            continue
        parent_id = _safe_int(item.get("parent_id"))
        deps = item.get("dependencies") or []
        dep_list: List[int] = []
        if isinstance(deps, list):
            for d in deps:
                v = _safe_int(d)
                if v is not None and v != task_id:
                    dep_list.append(v)
        nodes[task_id] = {
            "id": task_id,
            "plan_id": plan_id,
            "name": str(item.get("name") or f"Task {task_id}").strip(),
            "instruction": str(item.get("instruction") or "").strip(),
            "status": str(item.get("status") or "pending"),
            "parent_id": parent_id,
            "position": _safe_int(item.get("position")) or 0,
            "metadata": item.get("metadata")
            if isinstance(item.get("metadata"), dict)
            else {},
            "dependencies": dep_list,
        }

    if not nodes:
        raise ValueError("No valid tasks after normalization")

    # Build adjacency and compute depth/path/position
    adjacency: Dict[Optional[int], List[int]] = {}
    for t_id, data in nodes.items():
        pid = data["parent_id"]
        if pid not in nodes:
            pid = None
            data["parent_id"] = None
        adjacency.setdefault(pid, []).append(t_id)

    for pid in adjacency:
        # sort by explicit position then id for stability
        adjacency[pid].sort(key=lambda x: (nodes[x].get("position", 0), x))
        for idx, child_id in enumerate(adjacency[pid]):
            nodes[child_id]["position"] = idx

    def assign_depth_path(node_id: int, depth: int, prefix: str) -> None:
        node = nodes[node_id]
        node["depth"] = depth
        node["path"] = f"{prefix}/{node_id}".replace("//", "/")
        for child_id in adjacency.get(node_id, []):
            assign_depth_path(child_id, depth + 1, node["path"])

    for root_id in adjacency.get(None, []):
        assign_depth_path(root_id, 0, "")

    # Filter dependencies to existing nodes
    for node in nodes.values():
        deps = []
        for d in node["dependencies"]:
            if d in nodes and d != node["id"]:
                deps.append(d)
        node["dependencies"] = deps

    plan_nodes: Dict[int, PlanNode] = {}
    for node_data in nodes.values():
        plan_nodes[node_data["id"]] = PlanNode(**{
            "id": node_data["id"],
            "plan_id": plan_id,
            "name": node_data["name"],
            "status": node_data.get("status") or "pending",
            "instruction": node_data.get("instruction") or "",
            "parent_id": node_data.get("parent_id"),
            "position": node_data.get("position", 0),
            "depth": node_data.get("depth", 0),
            "path": node_data.get("path", f"/{node_data['id']}"),
            "metadata": node_data.get("metadata") or {},
            "dependencies": node_data.get("dependencies") or [],
            "context_combined": None,
            "context_sections": [],
            "context_meta": {},
            "context_updated_at": None,
            "execution_result": None,
        })

    adjacency_map: Dict[Optional[int], List[int]] = {}
    for pid, children in adjacency.items():
        adjacency_map[pid] = children

    raw_metadata = raw_plan.get("metadata")
    metadata: Dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}

    return PlanTree(
        id=plan_id,
        title=title,
        description=description,
        metadata=metadata,
        nodes=plan_nodes,
        adjacency=adjacency_map,
    )


# ------------------------- LLM generation worker -----------------------------


def call_llm(client: LLMClient, prompt: str, retries: int) -> str:
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 2):
        try:
            return client.chat(prompt)
        except Exception as exc:
            last_err = exc
            if attempt <= retries:
                continue
            raise last_err
    raise RuntimeError("unreachable")


def process_topic(
    topic: PlanTopic,
    prompt_tpl: str,
    client: LLMClient,
    retries: int,
    out_dir: Path,
    idx: int,
) -> PlanResult:
    prompt = render_prompt(prompt_tpl, topic)
    raw_dir = out_dir / "raw"
    parsed_dir = out_dir / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    raw_path = raw_dir / f"topic_{idx:04d}.json"
    parsed_path = parsed_dir / f"plan_{idx:04d}.json"

    try:
        response = call_llm(client, prompt, retries)
        raw_path.write_text(response, encoding="utf-8")
        obj = extract_json_block(response)
        tree = normalize_plan(obj, fallback_plan_id=idx)
        parsed_path.write_text(
            tree.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return PlanResult(
            topic=topic,
            plan_id=tree.id,
            success=True,
            error=None,
            raw_path=raw_path,
            parsed_path=parsed_path,
        )
    except Exception as exc:
        failed_path = out_dir / "failed.jsonl"
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        with failed_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "topic": topic.title,
                        "goal": topic.goal,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return PlanResult(
            topic=topic,
            plan_id=None,
            success=False,
            error=str(exc),
            raw_path=None,
            parsed_path=None,
        )


# ------------------------- Main workflow ------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    topics = load_topics(args.input)
    if args.limit is not None and args.limit > 0:
        topics = topics[: args.limit]

    prompt_template = (
        args.prompt_template.read_text(encoding="utf-8")
        if args.prompt_template
        else DEFAULT_PROMPT
    )

    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path)
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] Failed to load {env_path}: {exc}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for i, topic in enumerate(topics, 1):
            print(f"--- Topic {i} ---")
            print(render_prompt(prompt_template, topic))
        return

    client = LLMClient(
        provider=args.provider,
        api_key=args.api_key,
        url=args.api_url,
        model=args.model,
        timeout=args.timeout,
    )
    print(f"[INFO] Using provider={client.provider}, model={client.model}, url={client.url}")
    print(f"[INFO] Loaded {len(topics)} topics from {args.input}")

    results: List[PlanResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_map = {
            executor.submit(
                process_topic,
                topic,
                prompt_template,
                client,
                args.max_retries,
                args.out_dir,
                idx,
            ): topic
            for idx, topic in enumerate(topics, 1)
        }
        for future in as_completed(future_map):
            res = future.result()
            results.append(res)
            status = "OK" if res.success else f"FAIL ({res.error})"
            print(f"[INFO] Topic {res.topic.title} -> {status}")

    successes = sum(1 for r in results if r.success)
    failures = len(results) - successes
    print(
        f"\nCompleted {len(results)} topics → {successes} succeeded, {failures} failed."
    )
    if failures:
        for r in results:
            if not r.success:
                print(f" - {r.topic.title}: {r.error}")


if __name__ == "__main__":
    main()
