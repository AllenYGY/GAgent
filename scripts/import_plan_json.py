#!/usr/bin/env python3
"""
Import plan JSON files (PlanTree-style) into the plan repository and print new plan ids.

Useful for running simulations on pre-generated plans (e.g., results/.../parsed/plan_*.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv, find_dotenv

from app.database import init_db
from app.repository.plan_repository import PlanRepository


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import plan_*.json (PlanTree) into the repository.")
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="File or directory containing plan_*.json files (PlanTree format).",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="Imported",
        help="Prefix added to plan title to mark imports (default: Imported).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only; do not insert into DB.",
    )
    return parser.parse_args(argv)


def load_plan_tree(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def insert_plan(repo: PlanRepository, data: Dict, prefix: str, dry_run: bool) -> int:
    title = data.get("title") or f"Plan from {data.get('id', 'unknown')}"
    full_title = f"{prefix} {title}".strip()
    description = data.get("description") or ""
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    nodes = data.get("nodes") or {}
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError("No nodes found in plan JSON.")

    if dry_run:
        return -1

    plan = repo.create_plan(title=full_title, description=description, metadata=metadata)
    ext_to_db: Dict[int, int] = {}
    pending: List[Dict] = []
    for key, node in nodes.items():
        try:
            ext_id = int(node.get("id") or key)
        except Exception:
            continue
        pending.append(
            {
                "ext_id": ext_id,
                "name": node.get("name") or f"Task {ext_id}",
                "instruction": node.get("instruction") or node.get("description") or node.get("name") or "",
                "parent_id": node.get("parent_id"),
                "dependencies": node.get("dependencies") or [],
                "status": node.get("status") or "pending",
                "position": node.get("position"),
                "metadata": node.get("metadata") if isinstance(node.get("metadata"), dict) else {},
            }
        )

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
            db_parent = ext_to_db.get(parent_ext) if parent_ext is not None else None
            db_deps = [ext_to_db[d] for d in deps_ext if d in ext_to_db]
            node = repo.create_task(
                plan_id=plan.id,
                name=task["name"],
                instruction=task["instruction"],
                parent_id=db_parent,
                status=task["status"],
                dependencies=db_deps,
                metadata=task["metadata"],
                position=int(task["position"]) if task["position"] is not None else None,
            )
            ext_to_db[task["ext_id"]] = node.id
            progress = True
        pending = remaining

    if pending:
        unresolved = [t["ext_id"] for t in pending]
        raise ValueError(f"Unresolved parent/dependencies for tasks: {unresolved}")

    return plan.id


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
    repo = PlanRepository()

    if args.input.is_dir():
        files = sorted(args.input.glob("plan_*.json"))
    else:
        files = [args.input]

    if not files:
        print(f"[ERR] No plan_*.json files found under {args.input}", file=sys.stderr)
        sys.exit(1)

    created: List[tuple[Path, int]] = []
    for path in files:
        try:
            data = load_plan_tree(path)
            plan_id = insert_plan(repo, data, args.prefix, args.dry_run)
            created.append((path, plan_id))
            status = "DRY-RUN" if args.dry_run else f"plan #{plan_id}"
            print(f"[OK] Imported {path.name} -> {status}")
        except Exception as exc:
            print(f"[ERR] Failed to import {path}: {exc}", file=sys.stderr)

    if not args.dry_run:
        print("\n[INFO] Import summary:")
        for path, pid in created:
            print(f" - {path}: plan_id={pid}")


if __name__ == "__main__":
    main()
