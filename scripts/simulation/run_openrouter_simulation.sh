#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/allenygy/Research/GAgent"
SCRIPT="$ROOT/scripts/simulation/parallel_simulation_experiment.py"

MODE="${MODE:-both}" # action | plan | both
# MODELS="${MODELS:-google/gemini-3-pro-preview,openai/gpt-5.2-chat}"
# MODELS="${MODELS:-google/gemini-3-flash-preview}"
MODELS="${MODELS:-openai/gpt-5.3-chat}"
RUNS="${RUNS:-100}"
MAX_TURNS="${MAX_TURNS:-50}"
PARALLELISM="${PARALLELISM:-2}"
MAX_ACTIONS_PER_TURN="${MAX_ACTIONS_PER_TURN:-2}"
GOAL="${GOAL:-}"

PLAN_ID="${PLAN_ID:-41}"
PLAN_JSON="${PLAN_JSON:-/Users/allenygy/Research/GAgent/results/agent_plans_10_without_web/plan_41.json}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT/experiments}"
RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"

OPENROUTER_KEY="${OPENROUTER_API_KEY:-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}"

if [[ ! -f "$SCRIPT" ]]; then
  echo "[ERR] Simulation script not found: $SCRIPT" >&2
  exit 1
fi

if [[ -z "$OPENROUTER_KEY" ]]; then
  echo "[ERR] OPENROUTER_API_KEY is required." >&2
  exit 1
fi

if [[ "$MODE" == "action" || "$MODE" == "both" ]]; then
  if [[ -z "$PLAN_ID" ]]; then
    echo "[ERR] PLAN_ID is required for action mode." >&2
    exit 1
  fi
fi

if [[ "$MODE" == "plan" || "$MODE" == "both" ]]; then
  if [[ -z "$PLAN_JSON" ]]; then
    echo "[ERR] PLAN_JSON is required for plan mode." >&2
    exit 1
  fi
fi

IFS=',' read -r -a MODEL_LIST <<< "$MODELS"

export OPENROUTER_API_KEY="$OPENROUTER_KEY"

for model in "${MODEL_LIST[@]}"; do
  model="$(echo "$model" | xargs)"
  if [[ -z "$model" ]]; then
    continue
  fi
  slug="$(echo "$model" | tr '/:' '_' | tr -cd 'a-zA-Z0-9._-')"

  pids=()
  if [[ "$MODE" == "action" || "$MODE" == "both" ]]; then
    out_dir="$OUTPUT_ROOT/sim_action_${slug}_${RUN_TAG}"
    cmd=(
      python "$SCRIPT"
      --mode action
      --plan-id "$PLAN_ID"
      --runs "$RUNS"
      --parallelism "$PARALLELISM"
      --max-turns "$MAX_TURNS"
      --max-actions-per-turn "$MAX_ACTIONS_PER_TURN"
      --provider openrouter
      --model "$model"
      --api-key "$OPENROUTER_KEY"
      --output-root "$out_dir"
    )
    if [[ -n "$GOAL" ]]; then
      cmd+=(--goal "$GOAL")
    fi
    echo "[INFO] action mode model=$model output=$out_dir"
    LLM_PROVIDER="openrouter" OPENROUTER_MODEL="$model" OPENROUTER_API_KEY="$OPENROUTER_KEY" "${cmd[@]}" &
    pids+=($!)
  fi

  if [[ "$MODE" == "plan" || "$MODE" == "both" ]]; then
    out_dir="$OUTPUT_ROOT/sim_plan_${slug}_${RUN_TAG}"
    cmd=(
      python "$SCRIPT"
      --mode plan
      --input-plan-json "$PLAN_JSON"
      --runs "$RUNS"
      --parallelism "$PARALLELISM"
      --max-turns "$MAX_TURNS"
      --provider openrouter
      --model "$model"
      --api-key "$OPENROUTER_KEY"
      --output-root "$out_dir"
    )
    if [[ -n "$GOAL" ]]; then
      cmd+=(--goal "$GOAL")
    fi
    echo "[INFO] plan mode model=$model output=$out_dir"
    "${cmd[@]}" &
    pids+=($!)
  fi

  if (( ${#pids[@]} > 0 )); then
    status=0
    for pid in "${pids[@]}"; do
      if ! wait "$pid"; then
        status=1
      fi
    done
    if [[ "$status" -ne 0 ]]; then
      exit 1
    fi
  fi
done
