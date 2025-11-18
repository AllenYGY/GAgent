#!/usr/bin/env python3
"""Utility to run multiple simulation clones in parallel without touching the main DB."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass
class SimulationTask:
    index: int
    plan_id: int
    db_root: Path
    session_id: str
    log_path: Path


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _clone_plan_records(
    template_db_root: Path,
    source_plan_id: int,
    clone_count: int,
) -> List[Dict[str, int]]:
    main_db_path = template_db_root / "main" / "plan_registry.db"
    plans_dir = template_db_root / "plans"
    if not main_db_path.exists():
        raise FileNotFoundError(f"Main DB not found at {main_db_path}")
    if not plans_dir.exists():
        raise FileNotFoundError(f"Plan storage dir not found at {plans_dir}")

    conn = sqlite3.connect(main_db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM plans WHERE id=?", (source_plan_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Plan #{source_plan_id} not found in template DB")
        source_plan_file = plans_dir / (row["plan_db_path"] or "")
        if not source_plan_file.exists():
            raise FileNotFoundError(f"Source plan file missing: {source_plan_file}")

        clones: List[Dict[str, int]] = []
        for idx in range(1, clone_count + 1):
            new_title = f"{row['title']} clone_{idx}"
            cursor = conn.execute(
                """
                INSERT INTO plans (title, owner, description, metadata, plan_db_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    new_title,
                    row["owner"],
                    row["description"],
                    row["metadata"],
                ),
            )
            new_plan_id = int(cursor.lastrowid)
            new_rel_path = f"plan_{new_plan_id}.sqlite"
            conn.execute(
                "UPDATE plans SET plan_db_path=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_rel_path, new_plan_id),
            )
            target_file = plans_dir / new_rel_path
            if target_file.exists():
                target_file.unlink()
            shutil.copy2(source_plan_file, target_file)
            clones.append({"index": idx, "plan_id": new_plan_id})
        conn.commit()
        return clones
    finally:
        conn.close()


def _prune_plan_files(plans_dir: Path, keep_plan_id: int) -> None:
    keep_name = f"plan_{keep_plan_id}.sqlite"
    for path in plans_dir.glob("plan_*.sqlite"):
        if path.name == keep_name:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _prune_plan_registry(main_db_path: Path, keep_plan_id: int) -> None:
    if not main_db_path.exists():
        return
    conn = sqlite3.connect(main_db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM plans WHERE id != ?", (keep_plan_id,))
        conn.commit()
    finally:
        conn.close()


def _prepare_runs(
    template_db_root: Path,
    clones: Sequence[Dict[str, int]],
    output_root: Path,
) -> List[SimulationTask]:
    tasks: List[SimulationTask] = []
    for clone in clones:
        idx = clone["index"]
        plan_id = clone["plan_id"]
        db_run_dir = output_root / f"db_run_{idx:02d}"
        _copy_tree(template_db_root, db_run_dir)
        plan_dir = db_run_dir / "plans"
        if plan_dir.exists():
            _prune_plan_files(plan_dir, plan_id)
        main_db_path = db_run_dir / "main" / "plan_registry.db"
        _prune_plan_registry(main_db_path, plan_id)
        session_id = f"sim{plan_id}_clone_{idx:02d}"
        log_path = output_root / "process_logs" / f"run_{idx:02d}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        tasks.append(
            SimulationTask(
                index=idx,
                plan_id=plan_id,
                db_root=db_run_dir,
                session_id=session_id,
                log_path=log_path,
            )
        )
    return tasks


def _run_single_simulation(
    task: SimulationTask,
    *,
    max_turns: int,
    goal: str | None,
    show_raw: bool,
    run_logs_dir: Path,
    session_logs_dir: Path,
    max_actions_per_turn: int,
    enable_execute: bool,
) -> tuple[int, int]:
    env = os.environ.copy()
    env["DB_ROOT"] = str(task.db_root)
    env["SIMULATION_RUN_OUTPUT_DIR"] = str(run_logs_dir)
    env["SIMULATION_SESSION_OUTPUT_DIR"] = str(session_logs_dir)

    cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "run_simulation.py"),
        "--plan-id",
        str(task.plan_id),
        "--session-id",
        task.session_id,
        "--max-turns",
        str(max_turns),
        "--db-root",
        str(task.db_root),
        "--max-actions-per-turn",
        str(max_actions_per_turn),
    ]
    if goal:
        cmd.extend(["--goal", goal])
    if show_raw:
        cmd.append("--show-raw")
    if enable_execute:
        cmd.append("--enable-execute")

    task.log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(task.log_path, "w", encoding="utf-8") as log_file:
        log_file.write(
            f"[INFO] Starting simulation #{task.index} (plan_id={task.plan_id})\n"
        )
        log_file.flush()
        process = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        returncode = process.wait()
        log_file.write(
            f"\n[INFO] Simulation #{task.index} finished with code {returncode}\n"
        )
    return task.index, returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multiple simulations in parallel."
    )
    parser.add_argument(
        "--plan-id", type=int, required=True, help="Source plan id to clone."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of clones/simulations to run (default 10).",
    )
    parser.add_argument(
        "--parallelism", type=int, default=5, help="Maximum concurrent simulations."
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Maximum turns per simulation (capped at 20 by run_simulation).",
    )
    parser.add_argument(
        "--max-actions-per-turn",
        type=int,
        choices=[1, 2],
        default=2,
        help="Limit ACTION count per turn passed to each simulation (1 or 2).",
    )
    parser.add_argument(
        "--enable-execute",
        action="store_true",
        help="Allow execute_plan actions during simulations (disabled by default).",
    )
    parser.add_argument(
        "--goal", help="Optional override goal passed to each simulation run."
    )
    parser.add_argument(
        "--db-root", help="Source DB_ROOT to copy (defaults to app config / env)."
    )
    parser.add_argument(
        "--output-root",
        default="experiments",
        help="Directory to store experiment artifacts (default experiments).",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Forward --show-raw to each simulation run.",
    )
    args = parser.parse_args()

    source_db_root = Path(args.db_root or os.getenv("DB_ROOT", "data/databases"))
    if not source_db_root.exists():
        parser.error(f"Source DB_ROOT not found: {source_db_root}")

    output_root = (ROOT_DIR / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    db_template_dir = output_root / "db_template"
    _copy_tree(source_db_root, db_template_dir)
    plans_dir = db_template_dir / "plans"
    if plans_dir.exists():
        _prune_plan_files(plans_dir, args.plan_id)
    template_main_db = db_template_dir / "main" / "plan_registry.db"
    _prune_plan_registry(template_main_db, args.plan_id)

    clones = _clone_plan_records(db_template_dir, args.plan_id, args.runs)
    if len(clones) < args.runs:
        parser.error("Failed to produce enough plan clones for simulations")

    run_logs_dir = output_root / "run_logs"
    session_logs_dir = output_root / "session_logs"
    run_logs_dir.mkdir(parents=True, exist_ok=True)
    session_logs_dir.mkdir(parents=True, exist_ok=True)

    tasks = _prepare_runs(db_template_dir, clones, output_root)

    manifest_path = output_root / "experiment_manifest.json"
    manifest_payload = {
        "source_plan_id": args.plan_id,
        "runs": args.runs,
        "parallelism": args.parallelism,
        "max_turns": args.max_turns,
        "goal": args.goal,
        "max_actions_per_turn": args.max_actions_per_turn,
        "enable_execute": args.enable_execute,
        "output_root": str(output_root),
        "tasks": [
            {
                "index": task.index,
                "plan_id": task.plan_id,
                "db_root": str(task.db_root),
                "session_id": task.session_id,
                "log_path": str(task.log_path),
                "max_actions_per_turn": args.max_actions_per_turn,
                "enable_execute": args.enable_execute,
            }
            for task in tasks
        ],
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest_payload, handle, indent=2, ensure_ascii=False)

    print(f"[INFO] Prepared {len(tasks)} simulation clones under {output_root}")

    parallelism = max(1, min(args.parallelism, len(tasks)))
    max_turns = max(args.max_turns, 20)

    results: Dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = {
            executor.submit(
                _run_single_simulation,
                task,
                max_turns=max_turns,
                goal=args.goal,
                show_raw=args.show_raw,
                run_logs_dir=run_logs_dir,
                session_logs_dir=session_logs_dir,
                max_actions_per_turn=args.max_actions_per_turn,
                enable_execute=args.enable_execute,
            ): task
            for task in tasks
        }
        for future in as_completed(futures):
            idx, code = future.result()
            results[idx] = code
            status = "OK" if code == 0 else f"ERR({code})"
            print(f"[INFO] Simulation #{idx:02d} completed -> {status}")

    failed = [idx for idx, code in sorted(results.items()) if code != 0]
    if failed:
        print(f"[WARN] {len(failed)} simulations failed: {failed}")
        sys.exit(1)
    print("[INFO] All simulations completed successfully.")


if __name__ == "__main__":
    main()
