#!/usr/bin/env python3
"""
LLM-based plan quality evaluation script (10-point rubric).

Evaluates plan trees using a per-criterion 0/1/2 checklist. The LLM returns
criterion scores + reasons; this script computes 1–10 dimension scores by
summing the five criteria per dimension (minimum score of 1).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import find_dotenv, load_dotenv

# Ensure repository root is importable when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from app.database import init_db
from app.llm import PROVIDER_CONFIGS, LLMClient
from app.repository.plan_repository import PlanRepository
from app.services.llm.llm_service import LLMService
from app.services.plans.plan_models import PlanTree

# --- Constants ----------------------------------------------------------------

DIMENSIONS: List[Dict[str, str]] = [
    {
        "key": "contextual_completeness",
        "label": "Contextual Completeness",
        "desc": (
            "The availability of rationale or context fields that explain why "
            "a step is being performed. Missing context reduces interpretability "
            "and should lower the score."
        ),
    },
    {
        "key": "accuracy",
        "label": "Accuracy",
        "desc": (
            "Methods, tools, and assumptions are technically correct, current, "
            "and feasible for the stated constraints. No contradictions or "
            "hallucinated facts."
        ),
    },
    {
        "key": "task_granularity_atomicity",
        "label": "Task Granularity & Atomicity",
        "desc": (
            "Measures whether tasks are broken down into single, unambiguous "
            "executable actions rather than broad goals. Higher granularity "
            "reduces ambiguity for execution."
        ),
    },
    {
        "key": "reproducibility_parameterization",
        "label": "Reproducibility & Parameterization",
        "desc": (
            "The extent to which the plan specifies how to run tools (parameters, "
            "standards, formats), not just which tools to use."
        ),
    },
    {
        "key": "scientific_rigor",
        "label": "Scientific Rigor",
        "desc": (
            "Includes evaluation metrics, controls/baselines, data-quality checks, "
            "and reproducibility steps (e.g., documentation, validation, error analysis)."
        ),
    },
]

CRITERIA: Dict[str, List[Tuple[str, str]]] = {
    "contextual_completeness": [
        (
            "C1",
            "At least ~60% of major steps include an explicit 'why' (rationale).",
        ),
        ("C2", "Rationale explicitly links steps to the plan goal."),
        ("C3", "Key assumptions/constraints are explicitly stated."),
        ("C4", "Ordering/sequence is explicitly justified."),
        ("C5", "Alternatives or tradeoffs are explicitly mentioned."),
    ],
    "accuracy": [
        ("A1", "Methods/tools fit the task and are explicitly justified."),
        ("A2", "Assumptions are explicitly stated and technically plausible."),
        ("A3", "No clear contradictions between steps."),
        ("A4", "Tool capabilities match stated usage (no impossible steps)."),
        ("A5", "Explicitly cites a standard/best practice."),
    ],
    "task_granularity_atomicity": [
        (
            "G1",
            "Most steps specify one clear output artifact (file/table/model/report). A step may include 1–2 tightly coupled actions only if they lead to the same output.",
        ),
        (
            "G2",
            "Steps are minimal executable units; they do not combine distinct phases or multiple outputs/tools in a single step.",
        ),
        ("G3", "Almost no high-level goal-only steps remain."),
        ("G4", "Dependencies are explicit and minimal."),
        ("G5", "No clear redundancy or overlap across steps."),
    ],
    "reproducibility_parameterization": [
        ("R1", "Tool name plus version/implementation is given."),
        ("R2", "Inputs & outputs specify files/formats explicitly."),
        ("R3", "Key parameters/thresholds/decision rules are explicit."),
        ("R4", "Data sources or versions are explicitly identified."),
        ("R5", "Plan-level reproducibility (could implement the workflow)."),
    ],
    "scientific_rigor": [
        ("S1", "Explicit QC/validation steps included."),
        ("S2", "Explicit evaluation metrics defined (e.g., F1, N50)."),
        ("S3", "Explicit baselines or controls specified."),
        ("S4", "Explicit error/robustness analysis included."),
        ("S5", "Explicit acceptance thresholds/go-no-go criteria defined."),
    ],
}

SCALE_GUIDE = "Each criterion is scored 0/1/2 only."

DEFAULT_PROVIDER_SEQUENCE = [
    provider
    for provider in (
        "glm",
        "qwen",
        "doubao",
        "moonshot",
        "deepseek",
        "grok",
        "gemini",
        "perplexity",  # kept for completeness; filtered later
    )
    if provider in PROVIDER_CONFIGS
]


# --- Data structures ----------------------------------------------------------


@dataclass
class PlanPayload:
    plan_id: int
    title: str
    goal: str
    tree: PlanTree
    source: str


@dataclass
class EvaluationRecord:
    plan_id: int
    title: str
    scores: Dict[str, int]
    criteria: Dict[str, Dict[str, Dict[str, Any]]]
    comments: str
    raw: Dict[str, Any]


# --- CLI parsing --------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate plan quality with an LLM.")
    parser.add_argument(
        "--plan-tree-dir",
        type=Path,
        help="Directory containing plan_<id>.json exports produced by direct_plan_generator.",
    )
    parser.add_argument(
        "--plans",
        type=Path,
        help="File listing plan IDs (txt/csv/json) to fetch from the plan repository.",
    )
    parser.add_argument(
        "--plan-limit",
        type=int,
        help="Optional cap on the number of plans to evaluate.",
    )
    parser.add_argument(
        "--outline-max-nodes",
        type=int,
        help="Limit the number of nodes rendered in the outline (default: full plan).",
    )
    parser.add_argument(
        "--model", type=str, help="LLM model override (passed through to the client)."
    )
    parser.add_argument(
        "--provider",
        type=str,
        help="Override the LLM provider (glm, qwen, perplexity, doubao, moonshot, deepseek, grok, gemini, ...).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Optional API key override for ad-hoc provider tests.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="Optional base URL override (useful when pointing at gateways).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM sampling temperature (default: 0.0 for deterministic scoring).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Max number of concurrent LLM evaluations (default: 1 = sequential).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="LLM retries per plan before giving up (default: 3).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/plan_scores.csv"),
        help="CSV path for aggregated scores (default: results/plan_scores.csv).",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=Path("results/plan_scores.jsonl"),
        help="JSONL path for raw evaluator payloads (default: results/plan_scores.jsonl).",
    )
    parser.add_argument(
        "--provider-workers",
        type=int,
        help="Max concurrent providers to evaluate (default: min(provider count, 4)).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls and print outline previews instead (useful for debugging).",
    )
    return parser.parse_args(argv)


# --- Environment helpers ------------------------------------------------------


def load_environment() -> None:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        try:
            load_dotenv(env_path, override=True)
            print(
                f"[INFO] Loaded environment variables from {env_path} (override enabled)"
            )
        except Exception as exc:  # pragma: no cover - best effort notice
            print(
                f"[WARN] Failed to parse {env_path}: {exc}. Check for invalid characters such as ';'."
            )
    else:
        print("[INFO] No .env file found; using process environment only.")


# --- Plan loading -------------------------------------------------------------


def load_plan_ids(path: Path) -> List[int]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("plan_ids") or data.get("ids") or data.get("items") or []
        if not isinstance(data, list):
            raise ValueError(f"Unsupported JSON shape in {path}")
        return [int(item) for item in data]
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            field = None
            for candidate in ("plan_id", "id", "planId"):
                if reader.fieldnames and candidate in reader.fieldnames:
                    field = candidate
                    break
            if not field:
                raise ValueError(f"CSV {path} must contain a plan_id/id column.")
            return [int(row[field]) for row in reader if row.get(field)]
    # Treat as plain text with one ID per line (allowing trailing commas/comments).
    ids: List[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        token = line.split(",", 1)[0]
        ids.append(int(token))
    return ids


def infer_goal(tree: PlanTree) -> str:
    metadata_goal = (
        tree.metadata.get("goal") if isinstance(tree.metadata, dict) else None
    )
    if isinstance(metadata_goal, str) and metadata_goal.strip():
        return metadata_goal.strip()
    if tree.description:
        return tree.description.strip()
    for root_id in tree.root_node_ids():
        node = tree.nodes.get(root_id)
        if not node:
            continue
        instruction = (node.instruction or "").strip()
        if instruction:
            if "Details:" in instruction:
                return instruction.split("Details:", 1)[0].strip()
            return instruction
    return tree.title


def _normalize_plan_tree_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON (string) keys to the shapes expected by PlanTree."""

    nodes = raw.get("nodes") or {}
    normalized_nodes: Dict[int, Any] = {}
    for key, value in nodes.items():
        try:
            node_id = int(key)
        except (TypeError, ValueError):
            continue
        normalized_nodes[node_id] = value
    raw["nodes"] = normalized_nodes

    adjacency = raw.get("adjacency") or {}
    normalized_adj: Dict[Optional[int], List[int]] = {}
    for key, child_list in adjacency.items():
        if key in (None, "None", "null", ""):
            parent_id = None
        else:
            try:
                parent_id = int(key)
            except (TypeError, ValueError):
                continue
        normalized_adj[parent_id] = [int(child) for child in child_list]
    raw["adjacency"] = normalized_adj
    return raw


def load_plans_from_dir(path: Path) -> List[PlanPayload]:
    if not path or not path.exists():
        return []
    payloads: List[PlanPayload] = []
    for file_path in sorted(path.glob("plan_*.json")):
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            tree = PlanTree.model_validate(_normalize_plan_tree_payload(raw))
            tree.rebuild_adjacency()
        except Exception as exc:
            print(f"[WARN] Skipping {file_path}: {exc}")
            continue
        payloads.append(
            PlanPayload(
                plan_id=tree.id,
                title=tree.title,
                goal=infer_goal(tree),
                tree=tree,
                source=str(file_path),
            )
        )
    return payloads


def load_plans_from_repo(plan_ids: Iterable[int]) -> List[PlanPayload]:
    repo = PlanRepository()
    payloads: List[PlanPayload] = []
    for plan_id in plan_ids:
        try:
            tree = repo.get_plan_tree(plan_id)
        except Exception as exc:
            print(f"[WARN] Failed to load plan #{plan_id} from repository: {exc}")
            continue
        payloads.append(
            PlanPayload(
                plan_id=tree.id,
                title=tree.title,
                goal=infer_goal(tree),
                tree=tree,
                source="database",
            )
        )
    return payloads


def gather_plan_payloads(args: argparse.Namespace) -> List[PlanPayload]:
    payloads: List[PlanPayload] = []
    seen: set[int] = set()
    if args.plan_tree_dir:
        for payload in load_plans_from_dir(args.plan_tree_dir):
            if payload.plan_id in seen:
                continue
            payloads.append(payload)
            seen.add(payload.plan_id)
    if args.plans:
        plan_ids = load_plan_ids(args.plans)
        for payload in load_plans_from_repo(plan_ids):
            if payload.plan_id in seen:
                continue
            payloads.append(payload)
            seen.add(payload.plan_id)
    if args.plan_limit is not None:
        payloads = payloads[: args.plan_limit]
    return payloads


def provider_suffix_path(path: Path, provider: str) -> Path:
    """Insert `_provider` before the filename suffix."""
    provider = provider.lower().replace("/", "_")
    stem = path.stem
    suffix = path.suffix
    new_name = f"{stem}_{provider}{suffix}"
    return path.with_name(new_name)


def resolve_target_providers(args: argparse.Namespace) -> List[str]:
    if args.provider:
        return [args.provider.lower()]
    providers: List[str] = []
    for name in DEFAULT_PROVIDER_SEQUENCE:
        if name == "perplexity":
            continue
        if name not in providers:
            providers.append(name)
    return providers


# --- Prompt construction ------------------------------------------------------


def build_prompt(plan: PlanPayload, *, max_nodes: Optional[int]) -> str:
    outline = plan.tree.to_outline(max_nodes=max_nodes)
    dims = DIMENSIONS
    dim_lines = [
        f"- {dim['label']} (`{dim['key']}`): {dim['desc']}" for dim in dims
    ]
    schema_example = {
        "plan_id": plan.plan_id,
        "title": plan.title,
        "criteria": {
            dim["key"]: {
                crit_id: {"value": 0, "reason": "Short reason (<=30 words)."}
                for crit_id, _ in CRITERIA[dim["key"]]
            }
            for dim in DIMENSIONS
        },
        "comments": 'Optional short overall note ("" if none).',
    }
    instructions = (
        "You are an expert reviewer. Evaluate plan quality only (not execution). "
        "For each criterion, output a 0/1/2 value with a short reason and evidence. "
        "Do not infer missing details; if not stated, score 0. "
        "If evidence is weak/implicit, score 1 (not 2)."
    )
    scoring_method = [
        "SCORING METHOD (applied by the evaluator script):",
        "- Each criterion value is 0/1/2.",
        "  0 = not stated / missing",
        "  1 = partially implied or vague",
        "  2 = explicitly stated with concrete evidence",
        "- Dimension score = sum of its five criteria (0–10).",
        "- If the sum is 0, the script reports it as 1 to keep scores in 1–10.",
    ]
    scorecard = [
        "DIMENSION RUBRICS (mutually exclusive by design; only score what the dimension covers):",
        "",
        "contextual_completeness (ONLY rationale/why; ignore tools/parameters/QC):",
        *[f"- {cid}: {desc}" for cid, desc in CRITERIA["contextual_completeness"]],
        "",
        "accuracy (ONLY correctness/feasibility of methods/tools/assumptions; ignore missing parameters/QC):",
        *[f"- {cid}: {desc}" for cid, desc in CRITERIA["accuracy"]],
        "",
        "task_granularity_atomicity (ONLY decomposition quality; ignore rationale/parameters/QC):",
        *[f"- {cid}: {desc}" for cid, desc in CRITERIA["task_granularity_atomicity"]],
        "- IMPORTANT: Do NOT give 2 just because a step starts with a verb.",
        "- A step may include up to 2 tightly coupled micro-actions ONLY if it produces one explicit output and uses a single method/tool context.",
        "- If a step combines distinct phases (e.g., preprocess + train + evaluate), multiple outputs, or multiple tool contexts, it is NOT atomic.",
        "- Abstract outcomes like “insights/analysis/understanding” do NOT count as concrete outputs.",
        "- For G1/G2=2, the reason must cite a concrete step showing a single explicit output artifact.",
        "",
        "reproducibility_parameterization (ONLY tools/parameters/IO/data sources; ignore validation rigor):",
        *[f"- {cid}: {desc}" for cid, desc in CRITERIA["reproducibility_parameterization"]],
        "",
        "scientific_rigor (ONLY QC/validation/metrics/baselines/controls):",
        *[f"- {cid}: {desc}" for cid, desc in CRITERIA["scientific_rigor"]],
        "",
        "EVIDENCE REQUIREMENTS:",
        "- For each criterion, provide a short reason (<=30 words).",
        "- Cite 1–2 concrete pieces of evidence (node IDs or steps).",
        "- If information is missing, explicitly name what is missing.",
    ]
    prompt = (
        f"{instructions}\n\n"
        f"Plan metadata:\n"
        f"- Plan ID: {plan.plan_id}\n"
        f"- Title: {plan.title}\n"
        f"- Goal: {plan.goal}\n\n"
        f"Plan outline:\n{outline}\n\n"
        f"Scoring dimensions:\n" + "\n".join(dim_lines) + "\n\n"
        f"{SCALE_GUIDE}\n\n"
        + "\n".join(scoring_method)
        + "\n\n"
        + "\n".join(scorecard)
        + "\n\n"
        "Return valid JSON ONLY using this schema:\n"
        f"{json.dumps(schema_example, indent=2)}\n\n"
        "Rules:\n"
        "- Utilize the most rigorous standard audit program.\n"
        "- Do not include markdown fences or commentary outside the JSON.\n"
        "- Every criterion must include {value, reason}.\n"
        "- value must be 0, 1, or 2.\n"
        "- reason must be a short string (<=30 words).\n"
        "- Keep comments under 80 words; use an empty string if there is nothing to add.\n"
    )
    return prompt


def validate_response(
    data: Dict[str, Any], plan: PlanPayload
) -> Optional[EvaluationRecord]:
    if not isinstance(data, dict):
        return None
    raw_criteria = data.get("criteria")
    if not isinstance(raw_criteria, dict):
        return None
    parsed_criteria: Dict[str, Dict[str, Dict[str, Any]]] = {}
    parsed_scores: Dict[str, int] = {}
    for dim in DIMENSIONS:
        dim_key = dim["key"]
        dim_criteria = raw_criteria.get(dim_key)
        if not isinstance(dim_criteria, dict):
            return None
        parsed_criteria[dim_key] = {}
        total = 0
        for crit_id, _ in CRITERIA[dim_key]:
            crit_payload = dim_criteria.get(crit_id)
            if not isinstance(crit_payload, dict):
                return None
            value = crit_payload.get("value")
            reason = crit_payload.get("reason")
            try:
                value = int(value)
            except Exception:
                return None
            if value not in (0, 1, 2):
                return None
            if reason is None:
                return None
            if not isinstance(reason, str):
                reason = str(reason)
            reason = reason.strip()
            if not reason:
                return None
            parsed_criteria[dim_key][crit_id] = {
                "value": value,
                "reason": reason,
            }
            total += value
        if total <= 0:
            total = 1
        if total > 10:
            total = 10
        parsed_scores[dim_key] = total
    title = str(data.get("title") or plan.title)
    comments = data.get("comments")
    if comments is None:
        comments = ""
    elif not isinstance(comments, str):
        comments = str(comments)
    else:
        comments = comments.strip()
    try:
        raw_pid = data.get("plan_id", plan.plan_id)
        plan_id = int(raw_pid) if raw_pid is not None else plan.plan_id
    except Exception:
        plan_id = plan.plan_id
    if plan_id != plan.plan_id:
        plan_id = plan.plan_id
    return EvaluationRecord(
        plan_id=plan_id,
        title=title,
        scores=parsed_scores,
        criteria=parsed_criteria,
        comments=comments,
        raw={
            "plan_id": plan_id,
            "title": title,
            "scores": parsed_scores,
            "criteria": parsed_criteria,
            "comments": comments,
        },
    )


# --- Evaluation loop ---------------------------------------------------------


async def score_plan(
    plan: PlanPayload,
    service: LLMService,
    *,
    args: argparse.Namespace,
    prompt_dir: Optional[Path] = None,
) -> EvaluationRecord:
    prompt = build_prompt(plan, max_nodes=args.outline_max_nodes)
    if prompt_dir:
        try:
            prompt_dir.mkdir(parents=True, exist_ok=True)
            out_path = prompt_dir / f"plan_{plan.plan_id}.txt"
            out_path.write_text(prompt, encoding="utf-8")
        except Exception:
            pass
    last_error: Optional[str] = None
    attempts = max(1, args.max_retries)
    for attempt in range(1, attempts + 1):
        try:
            response = await service.chat_async(
                prompt,
                model=args.model,
                temperature=args.temperature,
            )
        except Exception as exc:
            last_error = f"LLM request failed: {exc}"
            continue
        data = service.parse_json_response(response)
        if not data:
            last_error = "LLM response was not valid JSON."
            continue
        record = validate_response(data, plan)
        if record:
            print(f"[OK] Plan #{plan.plan_id} scored on attempt {attempt}.")
            return record
        last_error = "LLM response failed schema validation."
    raise RuntimeError(last_error or "Unknown evaluation failure.")


async def evaluate_plans_async(
    plans: List[PlanPayload],
    args: argparse.Namespace,
    service: LLMService,
    provider_label: Optional[str] = None,
    model_label: Optional[str] = None,
    prompt_dir: Optional[Path] = None,
) -> List[EvaluationRecord]:
    semaphore = asyncio.Semaphore(max(1, args.batch_size))
    records: List[Optional[EvaluationRecord]] = [None] * len(plans)
    failures: List[str] = []

    async def runner(index: int, plan: PlanPayload) -> None:
        async with semaphore:
            label = provider_label or "default"
            model = model_label or "auto"
            print(
                f"[INFO] [{label}/{model}] Evaluating plan #{plan.plan_id}: {plan.title}"
            )
            try:
                records[index] = await score_plan(
                    plan,
                    service,
                    args=args,
                    prompt_dir=prompt_dir,
                )
            except Exception as exc:
                failures.append(f"Plan #{plan.plan_id}: {exc}")

    await asyncio.gather(*(runner(idx, plan) for idx, plan in enumerate(plans)))

    if failures:
        print("[WARN] Some plans failed to score:")
        for msg in failures:
            print(f" - {msg}")
    return [record for record in records if record is not None]


# --- Output helpers -----------------------------------------------------------


def write_outputs(
    records: List[EvaluationRecord], output_path: Path, jsonl_path: Path
) -> None:
    if not records:
        print("[WARN] No evaluation records to write.")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    score_fields = [dim["key"] for dim in DIMENSIONS]
    criteria_fields: List[str] = []
    for dim in DIMENSIONS:
        dim_key = dim["key"]
        for crit_id, _ in CRITERIA[dim_key]:
            criteria_fields.append(f"{dim_key}_{crit_id}_value")
            criteria_fields.append(f"{dim_key}_{crit_id}_reason")
    fieldnames = ["plan_id", "title"] + score_fields + criteria_fields + ["comments"]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "plan_id": record.plan_id,
                "title": record.title,
                "comments": record.comments,
            }
            for key, value in record.scores.items():
                row[key] = value
            for dim_key, crits in record.criteria.items():
                for crit_id, crit_payload in crits.items():
                    row[f"{dim_key}_{crit_id}_value"] = crit_payload.get("value")
                    row[f"{dim_key}_{crit_id}_reason"] = crit_payload.get("reason")
            writer.writerow(row)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.raw, ensure_ascii=False) + "\n")
    print(f"[INFO] Wrote {len(records)} evaluations to {output_path} and {jsonl_path}")


def print_averages(records: List[EvaluationRecord]) -> None:
    if not records:
        print("[WARN] No records to summarize averages.")
        return
    metrics = [dim["key"] for dim in DIMENSIONS]
    totals = {m: 0 for m in metrics}
    n = len(records)
    for rec in records:
        for m in metrics:
            totals[m] += rec.scores.get(m, 0)
    avgs = {m: round(totals[m] / n, 3) for m in metrics}
    line = " / ".join(f"{m}={avgs[m]}" for m in metrics)
    print(f"[INFO] Average scores over {n} plans: {line}")




# --- Entrypoint ---------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    if not args.plan_tree_dir and not args.plans:
        raise SystemExit("Provide --plan-tree-dir, --plans, or both.")
    load_environment()
    init_db()
    plans = gather_plan_payloads(args)
    if not plans:
        raise SystemExit("No plans were loaded for evaluation.")
    print(f"[INFO] Loaded {len(plans)} plan(s) for evaluation.")
    if args.dry_run:
        for plan in plans:
            outline = plan.tree.to_outline(max_nodes=args.outline_max_nodes)
            print(
                f"\nPlan #{plan.plan_id} — {plan.title}\n"
                f"Goal: {plan.goal}\nSource: {plan.source}\nOutline preview:\n{outline}\n"
            )
        return
    if args.api_key and not args.provider:
        print(
            "[WARN] --api-key is ignored unless --provider is specified. "
            "Set provider-specific keys in the environment instead."
        )
    if args.api_url and not args.provider:
        print(
            "[WARN] --api-url is ignored unless --provider is specified. "
            "Set provider-specific URLs in the environment instead."
        )

    target_providers = resolve_target_providers(args)
    if not target_providers:
        raise SystemExit("No target providers resolved for evaluation.")

    use_suffix = args.provider is None

    def run_for_provider(provider_name: str) -> Tuple[str, bool, Optional[str]]:
        print(f"[INFO] Starting evaluation with provider '{provider_name}'.")
        api_key_override = args.api_key if args.provider else None
        api_url_override = args.api_url if args.provider else None
        try:
            llm_client = LLMClient(
                provider=provider_name,
                api_key=api_key_override,
                url=api_url_override,
                model=args.model,
            )
        except Exception as exc:
            return provider_name, False, f"Client init failed: {exc}"
        print(
            f"[INFO] Provider '{provider_name}' configured with model '{llm_client.model}'."
        )

        service = LLMService(llm_client)
        # Place prompts alongside outputs, under the output directory
        prompt_dir = (
            (args.output.parent / "Prompts") if args.output else Path("results/Prompts")
        )
        try:
            records = asyncio.run(
                evaluate_plans_async(
                    plans,
                    args,
                    service,
                    provider_label=provider_name,
                    model_label=llm_client.model,
                    prompt_dir=prompt_dir,
                )
            )
        except Exception as exc:
            return provider_name, False, f"Evaluation failed: {exc}"

        output_path = (
            provider_suffix_path(args.output, provider_name)
            if use_suffix
            else args.output
        )
        jsonl_path = (
            provider_suffix_path(args.jsonl_output, provider_name)
            if use_suffix
            else args.jsonl_output
        )
        write_outputs(records, output_path, jsonl_path)
        print_averages(records)
        return provider_name, True, None

    max_workers = args.provider_workers or min(len(target_providers), 4)
    successful_runs = 0
    failures: List[str] = []

    with ThreadPoolExecutor(max_workers=max_workers or 1) as executor:
        future_map = {
            executor.submit(run_for_provider, provider): provider
            for provider in target_providers
        }
        for future in as_completed(future_map):
            provider_name = future_map[future]
            try:
                _, success, error = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                success = False
                error = str(exc)
            if success:
                successful_runs += 1
            else:
                failures.append(f"{provider_name}: {error}")

    if failures:
        print("[WARN] Some providers failed:")
        for msg in failures:
            print(f" - {msg}")

    if successful_runs == 0:
        raise SystemExit("All provider evaluations failed; no results written.")


if __name__ == "__main__":
    main()
