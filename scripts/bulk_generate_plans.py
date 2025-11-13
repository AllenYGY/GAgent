#!/usr/bin/env python3
"""
Bulk plan generation helper.

Given an input list of topics, this script talks to the running backend's
`/chat/message` endpoint so that the structured agent emits
`plan_operation.create_plan` for each topic. Results (plan id, status, logs)
are streamed to stdout and optionally persisted to CSV/JSON dumps.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

DEFAULT_PROMPT = """Topic: "{title}"
Goal: {goal}

Please create a detailed execution plan that can be executed by the planning system.
Requirements:
- Call `plan_operation.create_plan` exactly once for this topic.
- Automatically decompose the root task if possible.
- After the tool call completes, confirm the plan ID in your response.
"""


@dataclass
class PlanTopic:
    title: str
    goal: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PlanRunResult:
    topic: PlanTopic
    session_id: str
    plan_id: Optional[int]
    success: bool
    retries: int
    error: Optional[str] = None
    response_path: Optional[Path] = None
    tree_path: Optional[Path] = None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk plan generation driver.")
    parser.add_argument("--input", required=True, type=Path, help="File containing plan topics.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:9000",
        help="Backend base URL (default: http://localhost:9000)",
    )
    parser.add_argument("--api-key", help="Optional API key for Authorization header.")
    parser.add_argument("--concurrency", type=int, default=6, help="Concurrent workers (default: 6).")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries per topic (default: 3).")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout in seconds (default: 90).")
    parser.add_argument(
        "--prompt-template",
        type=Path,
        help="Optional file containing a custom prompt template.",
    )
    parser.add_argument(
        "--dump-dir",
        type=Path,
        help="If set, responses are written under this directory (responses/, plans/).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bulk_plans.csv"),
        help="CSV summary output (default: bulk_plans.csv).",
    )
    parser.add_argument(
        "--session-prefix",
        default="bulk",
        help="Prefix for generated session ids (default: bulk).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned requests without hitting the backend.",
    )
    return parser.parse_args(argv)


def _load_json_lines(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
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
            yield PlanTopic(
                title=title,
                goal=goal,
                description=record.get("description"),
                metadata=record.get("metadata") if isinstance(record.get("metadata"), dict) else None,
            )


def _load_json(path: Path) -> Iterable[PlanTopic]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("topics") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError(f"Unsupported JSON structure in {path}")
    for entry in data:
        if isinstance(entry, str):
            yield PlanTopic(title=entry, goal=entry)
            continue
        title = str(entry.get("title") or entry.get("goal") or "").strip()
        if not title:
            continue
        goal = str(entry.get("goal") or title).strip()
        yield PlanTopic(
            title=title,
            goal=goal,
            description=entry.get("description"),
            metadata=entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None,
        )


def _load_csv(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "title" not in reader.fieldnames and "goal" not in reader.fieldnames:
            raise ValueError("CSV must contain at least a 'title' or 'goal' column.")
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


def _load_text(path: Path) -> Iterable[PlanTopic]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            title = raw.strip()
            if title:
                yield PlanTopic(title=title, goal=title)


def load_topics(path: Path) -> List[PlanTopic]:
    ext = path.suffix.lower()
    if ext in {".jsonl", ".ndjson"}:
        topics = list(_load_json_lines(path))
    elif ext == ".json":
        topics = list(_load_json(path))
    elif ext == ".csv":
        topics = list(_load_csv(path))
    else:
        topics = list(_load_text(path))
    if not topics:
        raise ValueError(f"No topics found in {path}")
    return topics


def render_prompt(template: str, topic: PlanTopic) -> str:
    template_vars = {
        "title": topic.title,
        "goal": topic.goal or topic.title,
        "description": topic.description or "",
    }
    class SafeDict(dict):
        def __missing__(self, key):  # type: ignore[override]
            return ""

    return template.format_map(SafeDict(template_vars))


def extract_plan_id(payload: Dict[str, Any]) -> Optional[int]:
    metadata = payload.get("metadata") or {}
    plan_id = metadata.get("plan_id")
    if isinstance(plan_id, int):
        return plan_id
    try:
        if isinstance(plan_id, str) and plan_id.strip():
            return int(plan_id.strip())
    except ValueError:
        return None
    return None


async def fetch_plan_tree(client: httpx.AsyncClient, base_url: str, plan_id: int, timeout: float) -> Dict[str, Any]:
    url = f"{base_url}/plans/{plan_id}/tree"
    response = await client.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


async def create_plan_for_topic(
    client: httpx.AsyncClient,
    base_url: str,
    topic: PlanTopic,
    session_id: str,
    prompt: str,
    headers: Dict[str, str],
    *,
    timeout: float,
    max_retries: int,
    dump_dir: Optional[Path],
) -> PlanRunResult:
    payload = {
        "message": prompt,
        "history": [],
        "mode": "assistant",
        "session_id": session_id,
        "context": {
            "plan_title": topic.title,
            "topic_metadata": topic.metadata or {},
        },
    }
    last_error = None
    response_path = None
    tree_path = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(f"{base_url}/chat/message", json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            if dump_dir:
                response_path = dump_dir / "responses" / f"{session_id}.json"
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            plan_id = extract_plan_id(data)
            if plan_id is not None:
                if dump_dir:
                    try:
                        tree = await fetch_plan_tree(client, base_url, plan_id, timeout)
                        tree_path = dump_dir / "plans" / f"plan_{plan_id}.json"
                        tree_path.parent.mkdir(parents=True, exist_ok=True)
                        tree_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception as tree_exc:  # pragma: no cover - best effort logging
                        print(f"[WARN] Failed to fetch plan tree #{plan_id}: {tree_exc}", file=sys.stderr)
                return PlanRunResult(
                    topic=topic,
                    session_id=session_id,
                    plan_id=plan_id,
                    success=True,
                    retries=attempt - 1,
                    response_path=response_path,
                    tree_path=tree_path,
                )

            last_error = "Plan ID missing in response metadata."
        except httpx.HTTPError as exc:
            last_error = f"HTTP error: {exc}"
        except json.JSONDecodeError as exc:
            last_error = f"Invalid JSON response: {exc}"

        if attempt < max_retries:
            await asyncio.sleep(1.5 * attempt)

    return PlanRunResult(
        topic=topic,
        session_id=session_id,
        plan_id=None,
        success=False,
        retries=max_retries,
        error=last_error,
        response_path=response_path,
        tree_path=tree_path,
    )


async def run_bulk(args: argparse.Namespace) -> List[PlanRunResult]:
    topics = load_topics(args.input)
    template = args.prompt_template.read_text(encoding="utf-8") if args.prompt_template else DEFAULT_PROMPT
    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}

    if args.dry_run:
        for idx, topic in enumerate(topics, 1):
            prompt = render_prompt(template, topic)
            print(f"--- Topic {idx} ---")
            print(prompt)
        return []

    dump_dir = args.dump_dir
    if dump_dir:
        dump_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(http2=True) as client:
        semaphore = asyncio.Semaphore(max(1, args.concurrency))
        tasks = []
        for idx, topic in enumerate(topics, 1):
            session_id = f"{args.session_prefix}_{idx:05d}_{uuid.uuid4().hex[:6]}"
            prompt = render_prompt(template, topic)

            async def runner(tp=topic, sid=session_id, pr=prompt):
                async with semaphore:
                    return await create_plan_for_topic(
                        client,
                        base_url,
                        tp,
                        sid,
                        pr,
                        headers,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                        dump_dir=dump_dir,
                    )

            tasks.append(asyncio.create_task(runner()))

        return await asyncio.gather(*tasks)


def write_results(path: Path, results: List[PlanRunResult]) -> None:
    if not results:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "title",
                "goal",
                "plan_id",
                "session_id",
                "success",
                "retries",
                "error",
                "response_path",
                "tree_path",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.topic.title,
                    result.topic.goal,
                    result.plan_id or "",
                    result.session_id,
                    "yes" if result.success else "no",
                    result.retries,
                    result.error or "",
                    str(result.response_path or "") or "",
                    str(result.tree_path or "") or "",
                ]
            )


def print_summary(results: List[PlanRunResult]) -> None:
    total = len(results)
    successes = sum(1 for item in results if item.success)
    failures = total - successes
    print(f"\nCompleted {total} topics → {successes} succeeded, {failures} failed.")
    if failures:
        for item in results:
            if not item.success:
                print(f" - {item.topic.title}: {item.error}")


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    try:
        results = asyncio.run(run_bulk(args))
    except KeyboardInterrupt:  # pragma: no cover - user abort
        print("\n[INFO] Interrupted by user.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        return

    write_results(args.output, results)
    print_summary(results)


if __name__ == "__main__":
    main()
