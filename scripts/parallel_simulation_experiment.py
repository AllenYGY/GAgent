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
from typing import Any, Dict, List, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.llm import LLMClient
from app.services.agents.simulation.models import JudgeVerdict
from app.services.llm.llm_service import LLMService


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
            new_id = cursor.lastrowid
            if new_id is None:
                raise RuntimeError("Failed to create cloned plan record")
            new_plan_id = int(new_id)
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
    disable_web_search: bool,
    disable_rerun_task: bool,
    disable_graph_rag: bool,
    no_stop_on_misalignment: bool,
) -> tuple[int, int]:
    env = os.environ.copy()
    env["DB_ROOT"] = str(task.db_root)
    env["SIMULATION_RUN_OUTPUT_DIR"] = str(run_logs_dir)
    env["SIMULATION_SESSION_OUTPUT_DIR"] = str(session_logs_dir)
    env["SIM_USER_PROMPT_OUTPUT_DIR"] = str(run_logs_dir / "sim_user_prompts")
    env["CHAT_AGENT_PROMPT_OUTPUT_DIR"] = str(run_logs_dir / "chat_agent_prompts")
    env["JUDGE_PROMPT_OUTPUT_DIR"] = str(run_logs_dir / "judge_prompts")

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
    if disable_web_search:
        cmd.append("--disable-web-search")
    if disable_rerun_task:
        cmd.append("--disable-rerun-task")
    if disable_graph_rag:
        cmd.append("--disable-graph-rag")
    if no_stop_on_misalignment:
        cmd.append("--no-stop-on-misalignment")
    # show_tasks stays disabled by default; no enable flag exposed

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


def _extract_misaligned_turns(log_path: Path) -> List[int]:
    """Parse the per-run log to find misaligned turn indices from the summary."""
    turns: List[int] = []
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return turns

    for idx, line in enumerate(text):
        if line.strip().startswith("Misaligned turns:"):
            # Following lines like "  - Turn 2 (pending): ..."
            for follow in text[idx + 1 :]:
                stripped = follow.strip()
                if not stripped.startswith("- Turn"):
                    break
                try:
                    # "- Turn 2 (pending): ..." -> 2
                    after_turn = stripped.split("Turn", 1)[1].strip()
                    turn_num = int(after_turn.split()[0])
                    turns.append(turn_num)
                except Exception:
                    continue
            break
    return turns


# ---------------- full_plan utilities ---------------- #
DEFAULT_FULL_PLAN_JUDGE_PROMPT = """You are a strict evaluator. Given a user goal and two full plans (baseline and agent), decide if the agent plan aligns with the goal and the baseline intent.
- Respond ONLY in JSON with fields: alignment (aligned|misaligned), reason (string).
- Do not include code fences or extra text.

User goal:
{goal}

Simulated user baseline plan:
{baseline_plan}

Chat agent plan:
{agent_plan}
"""

DEFAULT_FULL_PLAN_CHAT_PROMPT = """You are a planning assistant. Given a current plan, recent agent plans (if any), and the goal, produce an improved full plan as strict JSON only.
- Do NOT include code fences or extra text.
- Include tasks with fields: id (int), name, instruction, parent_id (null for roots), dependencies (id list), status ("pending"), position (int order).
- Keep dependencies consistent; parent_id must reference defined tasks or null for roots.
- Aim to make the plan clearer, more complete, and executable. Depth ≤3, total tasks ≤30.

Goal:
{goal}

Current plan JSON:
{baseline_plan}

Recent agent plans (last 10, may be empty):
{history}
"""

DEFAULT_FULL_PLAN_SIM_USER_PROMPT = """You are a simulated user refining a plan. Given the last agent plan (baseline) and recent agent plans, produce an updated full plan as strict JSON only.
- Do NOT include code fences or extra text.
- Include tasks with fields: id (int), name, instruction, parent_id (null for roots), dependencies (id list), status ("pending"), position (int order).
- Keep dependencies consistent; parent_id must reference defined tasks or null for roots.
- Keep depth ≤3 and total tasks ≤30. Focus on clarity and usability rather than aggressive restructuring.
- Do NOT repeat prior changes; each turn must introduce a new, incremental improvement.

Goal:
{goal}

Baseline plan JSON:
{baseline_plan}

Recent agent plans (last 10, may be empty):
{history}
"""


def _load_plan_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _judge_full_plan_pair(
    baseline_plan_path: Path,
    agent_plan_path: Path,
    goal: str,
    llm: LLMService,
    prompt_template: str,
    temperature: Optional[float] = None,
) -> JudgeVerdict:
    try:
        prompt = prompt_template.format(
            goal=goal,
            baseline_plan=_load_plan_text(baseline_plan_path),
            agent_plan=_load_plan_text(agent_plan_path),
        )
        chat_kwargs = {}
        if temperature is not None:
            chat_kwargs["temperature"] = temperature
        resp = llm.chat(prompt, **chat_kwargs)
        try:
            payload = json.loads(_strip_code_fences(resp))
        except Exception:
            return JudgeVerdict(
                alignment="misaligned",
                explanation="Invalid JSON from judge",
                raw_response={"raw": resp},
            )

        alignment = str(payload.get("alignment") or "").strip().lower()
        explanation = (
            str(payload.get("reason") or payload.get("explanation") or "").strip()
            or "No explanation provided."
        )
        if alignment not in {"aligned", "misaligned"}:
            explanation = f"Coerced to misaligned (judge returned {alignment or 'invalid'}): {explanation}"
            alignment = "misaligned"
        return JudgeVerdict(
            alignment=alignment,  # type: ignore[arg-type]
            explanation=explanation,
            raw_response=payload,
        )
    except Exception as exc:
        return JudgeVerdict(
            alignment="misaligned",
            explanation=f"Judge error: {exc}",
            raw_response={"error": str(exc)},
        )


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rstrip("`")
    return cleaned.strip()


def _parse_plan_text(raw: str) -> Dict[str, Any]:
    cleaned = _strip_code_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = cleaned[start : end + 1]
            return json.loads(snippet)
        raise


def _generate_agent_plan(
    baseline_plan_path: Path,
    run_idx: int,
    turn_idx: int,
    goal: str,
    llm: LLMService,
    prompt_template: str,
    raw_dir: Path,
    parsed_dir: Path,
    history_text: str,
    temperature: Optional[float] = None,
) -> Path:
    prompt = prompt_template.format(
        goal=goal,
        baseline_plan=_load_plan_text(baseline_plan_path),
        history=history_text or "None",
    )
    chat_kwargs = {}
    if temperature is not None:
        chat_kwargs["temperature"] = temperature
    raw_resp = llm.chat(prompt, **chat_kwargs)
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"run{run_idx:03d}_turn{turn_idx:03d}.txt"
    raw_path.write_text(raw_resp, encoding="utf-8")
    payload = _parse_plan_text(raw_resp)
    parsed_path = parsed_dir / f"run{run_idx:03d}_turn{turn_idx:03d}.json"
    parsed_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return parsed_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multiple simulations in parallel."
    )
    parser.add_argument(
        "--mode",
        choices=["action", "full_plan"],
        default="action",
        help="Simulation mode: action (default, tool actions) or full_plan (direct plan JSON scoring).",
    )
    parser.add_argument(
        "--plan-id",
        type=int,
        help="Source plan id to clone (required for action mode).",
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
        "--provider",
        type=str,
        help="Override LLM provider (e.g., qwen, deepseek, glm, doubao, moonshot, gemini...).",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Override LLM model name for the chosen provider.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Override API key for ad-hoc provider tests.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="Override base URL for the provider (e.g., gateway endpoint).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Sampling temperature passed to LLM calls (full_plan mode).",
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
        "--goal",
        default="Improve the current plan to make it clearer, more complete, and executable.",
        help="User goal/intent for both action and full_plan modes (default: improve the current plan).",
    )
    parser.add_argument(
        "--db-root", help="Source DB_ROOT to copy (defaults to app config / env)."
    )
    parser.add_argument(
        "--output-root",
        default="experiments",
        help="Directory to store experiment artifacts (default: experiments/...).",
    )
    parser.add_argument(
        "--input-plan-json",
        type=str,
        help="In full_plan mode: file or directory of plan_*.json (PlanTree) to judge directly (skip action simulation).",
    )
    parser.add_argument(
        "--full-plan-judge-prompt",
        type=Path,
        help="Optional prompt template for full_plan judge (default internal).",
    )
    parser.add_argument(
        "--full-plan-chat-prompt",
        type=Path,
        help="Optional prompt template for chat agent full plan generation (default internal).",
    )
    parser.add_argument(
        "--full-plan-sim-user-prompt",
        type=Path,
        help="Optional prompt template for simulated user full plan generation (default internal).",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Forward --show-raw to each simulation run.",
    )
    parser.add_argument(
        "--disable-web-search",
        action="store_true",
        help="Disable web_search action for all simulations.",
    )
    parser.add_argument(
        "--disable-rerun-task",
        action="store_true",
        help="Disable rerun_task action for all simulations.",
    )
    parser.add_argument(
        "--disable-graph-rag",
        action="store_true",
        help="Disable graph_rag action for all simulations.",
    )
    parser.add_argument(
        "--no-stop-on-misalignment",
        action="store_true",
        help="Do not stop early when misaligned; run all turns to max_turns.",
    )
    args = parser.parse_args()

    if args.mode == "action" and args.plan_id is None:
        parser.error("--plan-id is required in action mode")
    if args.mode == "full_plan" and not args.input_plan_json:
        parser.error("--input-plan-json is required in full_plan mode")

    source_db_root = Path(args.db_root or os.getenv("DB_ROOT", "data/databases"))
    if args.mode == "action" and not source_db_root.exists():
        parser.error(f"Source DB_ROOT not found: {source_db_root}")

    output_root = (ROOT_DIR / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    # ---------------- full_plan mode: judge alignment on plan JSON (no actions) ---------------- #
    if args.mode == "full_plan":
        ip = Path(args.input_plan_json)
        if ip.is_dir():
            plan_inputs = sorted(ip.glob("plan_*.json"))
        else:
            plan_inputs = [ip]
        if not plan_inputs:
            parser.error(f"No plan_*.json found under {ip}")

        manifest_path = output_root / "experiment_manifest.json"
        manifest_payload = {
            "mode": "full_plan",
            "input_plan_json": str(ip),
            "runs": args.runs,
            "max_turns": args.max_turns,
            "parallelism": args.parallelism,
            "output_root": str(output_root),
            "plans": [str(p) for p in plan_inputs],
        }
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest_payload, handle, indent=2, ensure_ascii=False)

        judge_prompt = (
            args.full_plan_judge_prompt.read_text(encoding="utf-8")
            if args.full_plan_judge_prompt
            else DEFAULT_FULL_PLAN_JUDGE_PROMPT
        )
        sim_user_prompt = (
            args.full_plan_sim_user_prompt.read_text(encoding="utf-8")
            if args.full_plan_sim_user_prompt
            else DEFAULT_FULL_PLAN_SIM_USER_PROMPT
        )
        llm_client: Optional[LLMClient] = None
        if any([args.provider, args.model, args.api_key, args.api_url]):
            llm_client = LLMClient(
                provider=args.provider,
                api_key=args.api_key,
                url=args.api_url,
                model=args.model,
            )
        llm = LLMService(client=llm_client)
        chat_prompt = (
            args.full_plan_chat_prompt.read_text(encoding="utf-8")
            if args.full_plan_chat_prompt
            else DEFAULT_FULL_PLAN_CHAT_PROMPT
        )
        eval_dir = output_root / "eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        results_path = eval_dir / "results.csv"
        import csv

        parallelism = max(1, min(args.parallelism, args.runs)) if args.runs else 1
        plan_results: List[Dict[str, Any]] = []
        raw_dir = output_root / "run_logs" / "raw"
        parsed_dir = output_root / "run_logs" / "parsed"
        sim_user_dir = output_root / "run_logs" / "sim_user"
        judge_dir = output_root / "run_logs" / "judge"
        sim_user_raw_dir = sim_user_dir / "raw"
        sim_user_parsed_dir = sim_user_dir / "parsed"
        sim_user_raw_dir.mkdir(parents=True, exist_ok=True)
        sim_user_parsed_dir.mkdir(parents=True, exist_ok=True)
        judge_dir.mkdir(parents=True, exist_ok=True)

        def _record_failure(
            run_idx: int,
            turn_idx: int,
            base_path: Path,
            reason: str,
            rows: List[Dict[str, str]],
        ) -> None:
            entry = {
                "run": run_idx,
                "turn": turn_idx,
                "base_plan_path": str(base_path),
                "agent_plan_path": None,
                "alignment": "misaligned",
                "reason": reason,
            }
            rows.append(entry)
            try:
                judge_out_path = judge_dir / f"run{run_idx:03d}_turn{turn_idx:03d}.json"
                judge_out_path.write_text(
                    json.dumps(
                        {
                            "run": run_idx,
                            "turn": turn_idx,
                            "base_plan_path": str(base_path),
                            "agent_plan_path": None,
                            "alignment": "misaligned",
                            "reason": reason,
                            "raw_response": {"error": reason},
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:  # pragma: no cover - best effort
                print(
                    f"[WARN] Failed to save judge failure run={run_idx} turn={turn_idx}: {exc}"
                )

        def _run_full_plan(run_idx: int, base_plan: Path) -> List[Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            baseline_path = base_plan
            history_texts: List[str] = []
            for turn_idx in range(1, args.max_turns + 1):
                history_block = (
                    "\n\n".join(history_texts[-10:]) if history_texts else "None"
                )
                print(
                    f"[INFO] Run {run_idx} Turn {turn_idx} generating simulated user plan from {baseline_path.name}"
                )
                def _gen_with_retry(base_path: Path, prompt: str, raw_dir: Path, parsed_dir: Path):
                    # retry once on generation/parsing errors
                    last_exc: Optional[Exception] = None
                    for attempt in (1, 2):
                        try:
                            return _generate_agent_plan(
                                base_path,
                                run_idx,
                                turn_idx,
                                args.goal or "",
                                llm,
                                prompt,
                                raw_dir,
                                parsed_dir,
                                history_block,
                                args.temperature,
                            )
                        except Exception as exc:
                            last_exc = exc
                            if attempt == 1:
                                print(
                                    f"[WARN] Retry sim/agent generation run={run_idx} turn={turn_idx} attempt={attempt} failed: {exc}"
                                )
                                continue
                    if last_exc is None:
                        raise RuntimeError("Plan generation failed")
                    raise last_exc

                try:
                    sim_user_path = _gen_with_retry(
                        baseline_path,
                        sim_user_prompt,
                        sim_user_raw_dir,
                        sim_user_parsed_dir,
                    )
                except Exception as exc:
                    print(
                        f"[ERR] Failed to generate simulated user plan run={run_idx} turn={turn_idx}: {exc}"
                    )
                    _record_failure(
                        run_idx,
                        turn_idx,
                        baseline_path,
                        f"Sim user generation failed: {exc}",
                        rows,
                    )
                    continue
                print(
                    f"[INFO] Generated simulated user plan run={run_idx} turn={turn_idx} base={baseline_path.name} -> {sim_user_path.name}"
                )
                print(
                    f"[INFO] Run {run_idx} Turn {turn_idx} generating agent plan from simulated user plan"
                )
                try:
                    agent_path = _gen_with_retry(
                        sim_user_path,
                        chat_prompt,
                        raw_dir,
                        parsed_dir,
                    )
                except Exception as exc:
                    print(
                        f"[ERR] Failed to generate agent plan run={run_idx} turn={turn_idx}: {exc}"
                    )
                    _record_failure(
                        run_idx,
                        turn_idx,
                        sim_user_path,
                        f"Agent generation failed: {exc}",
                        rows,
                    )
                    continue
                print(
                    f"[INFO] Generated agent plan run={run_idx} turn={turn_idx} base={sim_user_path.name} -> {agent_path.name}"
                )
                try:
                    verdict = _judge_full_plan_pair(
                        sim_user_path,
                        agent_path,
                        args.goal or "",
                        llm,
                        judge_prompt,
                        args.temperature,
                    )
                except Exception as exc:
                    print(f"[ERR] Judge failed run={run_idx} turn={turn_idx}: {exc}")
                    _record_failure(
                        run_idx,
                        turn_idx,
                        sim_user_path,
                        f"Judge failed: {exc}",
                        rows,
                    )
                    continue
                print(
                    f"[INFO] Judged run={run_idx} turn={turn_idx} base={sim_user_path.name} agent={agent_path.name} -> {verdict.alignment}"
                )
                rows.append({
                    "run": run_idx,
                    "turn": turn_idx,
                    "base_plan_path": str(sim_user_path),
                    "agent_plan_path": str(agent_path),
                    "alignment": verdict.alignment,
                    "reason": verdict.explanation,
                })
                # Persist judge verdict
                try:
                    judge_out_path = (
                        judge_dir / f"run{run_idx:03d}_turn{turn_idx:03d}.json"
                    )
                    judge_out_path.write_text(
                        json.dumps(
                            {
                                "run": run_idx,
                                "turn": turn_idx,
                                "base_plan_path": str(baseline_path),
                                "agent_plan_path": str(agent_path),
                                "alignment": verdict.alignment,
                                "reason": verdict.explanation,
                                "raw_response": verdict.raw_response,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    print(
                        f"[WARN] Failed to save judge verdict run={run_idx} turn={turn_idx}: {exc}"
                    )
                # Continue even if misaligned; use latest agent plan as next baseline
                baseline_path = agent_path
                try:
                    history_texts.append(_load_plan_text(agent_path))
                except Exception:
                    history_texts.append("")
            return rows

        # Each run uses a base plan (cycle if fewer plans than runs)
        run_targets = [
            (run_idx, plan_inputs[(run_idx - 1) % len(plan_inputs)])
            for run_idx in range(1, args.runs + 1)
        ]

        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            future_map = {
                executor.submit(_run_full_plan, run_idx, base_plan): run_idx
                for run_idx, base_plan in run_targets
            }
            for future in as_completed(future_map):
                run_idx = future_map[future]
                try:
                    rows = future.result()
                    plan_results.extend(rows)
                except Exception as exc:
                    print(f"[ERR] Run {run_idx} failed: {exc}")

        with results_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "run",
                "turn",
                "base_plan_path",
                "agent_plan_path",
                "alignment",
                "reason",
            ])
            for row in plan_results:
                writer.writerow([
                    row["run"],
                    row["turn"],
                    row["base_plan_path"],
                    row["agent_plan_path"],
                    row["alignment"],
                    row["reason"],
                ])
        print(f"[INFO] Full-plan judging completed. Results: {results_path}")
        return

    # ---------------- action mode: existing simulation flow ---------------- #
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
        "mode": "action",
        "source_plan_id": args.plan_id,
        "runs": args.runs,
        "parallelism": args.parallelism,
        "max_turns": args.max_turns,
        "goal": args.goal,
        "max_actions_per_turn": args.max_actions_per_turn,
        "enable_execute": args.enable_execute,
        "disable_web_search": args.disable_web_search,
        "disable_rerun_task": args.disable_rerun_task,
        "disable_graph_rag": args.disable_graph_rag,
        "stop_on_misalignment": not args.no_stop_on_misalignment,
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
                "disable_web_search": args.disable_web_search,
                "disable_rerun_task": args.disable_rerun_task,
                "disable_graph_rag": args.disable_graph_rag,
                "stop_on_misalignment": not args.no_stop_on_misalignment,
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
                disable_web_search=args.disable_web_search,
                disable_rerun_task=args.disable_rerun_task,
                disable_graph_rag=args.disable_graph_rag,
                no_stop_on_misalignment=args.no_stop_on_misalignment,
            ): task
            for task in tasks
        }
        for future in as_completed(futures):
            idx, code = future.result()
            task = futures[future]
            misaligned_turns = _extract_misaligned_turns(task.log_path)
            results[idx] = code
            status = "OK" if code == 0 else f"ERR({code})"
            if misaligned_turns:
                first = misaligned_turns[0]
                more = (
                    f" +{len(misaligned_turns) - 1} more"
                    if len(misaligned_turns) > 1
                    else ""
                )
                status = f"{status} (misaligned turn {first}{more})"
            print(f"[INFO] Simulation #{idx:02d} completed -> {status}")

    failed = [idx for idx, code in sorted(results.items()) if code != 0]
    if failed:
        print(f"[WARN] {len(failed)} simulations failed: {failed}")
        sys.exit(1)
    print("[INFO] All simulations completed successfully.")


if __name__ == "__main__":
    main()
