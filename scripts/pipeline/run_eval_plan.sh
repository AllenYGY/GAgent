#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export OPENROUTER_API_KEY="..."
#   bash scripts/pipeline/run_eval_plan.sh

ROOT="/Users/allenygy/Research/GAgent"

RUNS=(
  "results/agent_plans_phage_gemini"
  "results/agent_plans_phage_grok"
  "results/agent_plans_phage_gpt52chat"
  "results/agent_plans_phage_deepseek"
  "results/agent_plans_phage_qwen"
  "results/agent_plans_phage_deepseek_web_enriched_refactor_v2"
  "results/agent_plans_phage_qwen_web_enriched_refactor_v2"
  "results/llm_plans_phage_gemini"
  "results/llm_plans_phage_grok"
  "results/llm_plans_phage_gpt52chat"
  "results/llm_plans_phage_deepseek"
  "results/llm_plans_phage_qwen"
)

MODELS=(
  "google/gemini-3-pro-preview"
  "openai/gpt-5.2-chat"
)

RUN_TS="$(date +%Y%m%d_%H%M%S)"
SCORE_BASE="10pt"
SCORE_SUFFIX="_${SCORE_BASE}_${RUN_TS}"
EVAL_TAG_GEMINI="gemini_${SCORE_BASE}"
EVAL_TAG_GPT52="gpt52chat_${SCORE_BASE}"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "[ERR] OPENROUTER_API_KEY is required." >&2
  exit 1
fi

if (( ${#RUNS[@]} == 0 )); then
  echo "[ERR] RUNS is empty." >&2
  exit 1
fi

start_ts=$(date +%s)

# Resolve plan tree dir per run: prefer plans/, fallback to parsed/
PLAN_DIRS=()
for run in "${RUNS[@]}"; do
  if [[ -d "$ROOT/$run/plans" ]]; then
    PLAN_DIRS+=("$ROOT/$run/plans")
  elif [[ -d "$ROOT/$run/parsed" ]]; then
    PLAN_DIRS+=("$ROOT/$run/parsed")
  else
    echo "[ERR] Missing plans/ or parsed/ directory under: $ROOT/$run" >&2
    exit 1
  fi
done

echo "[INFO] Runs (${#RUNS[@]}):"
for i in "${!RUNS[@]}"; do
  echo "  - ${RUNS[$i]} (plan_dir=${PLAN_DIRS[$i]})"
done
echo "[INFO] Models (${#MODELS[@]}): ${MODELS[*]}"
EVAL_CONCURRENCY="${EVAL_CONCURRENCY:-2}"
echo "[INFO] Using provider: openrouter (single key)"
echo "[INFO] Eval concurrency: $EVAL_CONCURRENCY"

export OPENROUTER_API_KEY="$OPENROUTER_API_KEY"

job_dir=$(mktemp -d -t run_eval_plan)
trap 'rm -rf "$job_dir"' EXIT
jobs_file="$job_dir/jobs.tsv"
: > "$jobs_file"

for i in "${!RUNS[@]}"; do
  run="${RUNS[$i]}"
  plan_dir="${PLAN_DIRS[$i]}"
  for model in "${MODELS[@]}"; do
    printf "%s\t%s\t%s\n" "$run" "$model" "$plan_dir" >> "$jobs_file"
  done
done

parallel --colsep '\t' --jobs "$EVAL_CONCURRENCY" --lb \
  'run={1}; model={2}; plan_dir={3}; \
   if [[ "$model" == *"gemini"* ]]; then tag="gemini"; else tag="gpt52chat"; fi; \
    mkdir -p "'$ROOT'/$run/eval"; \
    log_file="'$ROOT'/$run/eval/eval_${tag}'"$SCORE_SUFFIX"'.log"; \
    python -u "'$ROOT'/scripts/eval/eval_plan_quality.py" \
      --plan-tree-dir "$plan_dir" \
      --provider openrouter \
      --model "$model" \
      --stream-output \
      --batch-size 2 \
      --max-retries 3 \
      --output "'$ROOT'/$run/eval/plan_scores_${tag}'"$SCORE_SUFFIX"'.csv" \
      --jsonl-output "'$ROOT'/$run/eval/plan_scores_${tag}'"$SCORE_SUFFIX"'.jsonl" \
      2>&1 | tee -a "$log_file";' :::: "$jobs_file"

end_ts=$(date +%s)
elapsed=$(( end_ts - start_ts ))
echo "[INFO] Eval finished in ${elapsed}s. Output files:"
for run in "${RUNS[@]}"; do
  echo "  - $ROOT/$run/eval/plan_scores_gemini${SCORE_SUFFIX}.csv"
  echo "  - $ROOT/$run/eval/plan_scores_gemini${SCORE_SUFFIX}.jsonl"
  echo "  - $ROOT/$run/eval/plan_scores_gpt52chat${SCORE_SUFFIX}.csv"
  echo "  - $ROOT/$run/eval/plan_scores_gpt52chat${SCORE_SUFFIX}.jsonl"
done

echo "[INFO] Generating plots..."
python -u "$ROOT/scripts/plot/run_plot_eval_all.sh"
