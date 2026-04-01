#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export GROK_API_KEY="..."   # or XAI_API_KEY
#   bash scripts/pipeline/run_eval_plan.sh

ROOT="/Users/allenygy/Research/GAgent"

RUNS=(
  # "results/agent_plans_phage_gemini"
  # "results/agent_plans_phage_grok"
  # "results/agent_plans_phage_gpt52chat"
  # "results/agent_plans_phage_deepseek"
  # "results/agent_plans_phage_qwen"
  # "results/agent_plans_phage_deepseek_web_enriched_refactor_v2"
  # "results/agent_plans_phage_qwen_web_enriched_refactor_v2"
  # Only qwen/deepseek generator runs currently have GraphRAG-enriched plan trees.
  "results/agent_plans_phage_deepseek_web_rag"
  "results/agent_plans_phage_qwen_web_rag"
  # "results/llm_plans_phage_gemini"
  # "results/llm_plans_phage_grok"
  # "results/llm_plans_phage_gpt52chat"
  # "results/llm_plans_phage_deepseek"
  # "results/llm_plans_phage_qwen"
  # Current default scope: only evaluate the two GraphRAG-enriched runs above.
)

EVAL_SPECS=(
  # "openrouter|google/gemini-3-pro-preview|gemini"
  # "openrouter|openai/gpt-5.2-chat|gpt52chat"
  "grok|grok-4|grok"
)

RUN_TS="$(date +%Y%m%d_%H%M%S)"
SCORE_BASE="10pt"
SCORE_SUFFIX="_${SCORE_BASE}_${RUN_TS}"

if [[ -z "${GROK_API_KEY:-${XAI_API_KEY:-}}" ]]; then
  echo "[ERR] GROK_API_KEY or XAI_API_KEY is required for grok evaluation." >&2
  exit 1
fi

if (( ${#RUNS[@]} == 0 )); then
  echo "[ERR] RUNS is empty." >&2
  exit 1
fi

if (( ${#EVAL_SPECS[@]} == 0 )); then
  echo "[ERR] EVAL_SPECS is empty." >&2
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
echo "[INFO] Evaluators (${#EVAL_SPECS[@]}):"
for spec in "${EVAL_SPECS[@]}"; do
  IFS='|' read -r provider model tag <<< "$spec"
  echo "  - provider=${provider} model=${model} tag=${tag}"
done
EVAL_CONCURRENCY="${EVAL_CONCURRENCY:-2}"
echo "[INFO] Eval concurrency: $EVAL_CONCURRENCY"

export GROK_API_KEY="${GROK_API_KEY:-${XAI_API_KEY:-}}"

job_dir=$(mktemp -d -t run_eval_plan)
trap 'rm -rf "$job_dir"' EXIT
jobs_file="$job_dir/jobs.tsv"
: > "$jobs_file"

for i in "${!RUNS[@]}"; do
  run="${RUNS[$i]}"
  plan_dir="${PLAN_DIRS[$i]}"
  for spec in "${EVAL_SPECS[@]}"; do
    IFS='|' read -r provider model tag <<< "$spec"
    printf "%s\t%s\t%s\t%s\t%s\n" "$run" "$provider" "$model" "$tag" "$plan_dir" >> "$jobs_file"
  done
done

parallel --colsep '\t' --jobs "$EVAL_CONCURRENCY" --lb \
  'run={1}; provider={2}; model={3}; tag={4}; plan_dir={5}; \
    mkdir -p "'$ROOT'/$run/eval"; \
    log_file="'$ROOT'/$run/eval/eval_${tag}'"$SCORE_SUFFIX"'.log"; \
    python -u "'$ROOT'/scripts/eval/eval_plan_quality.py" \
      --plan-tree-dir "$plan_dir" \
      --provider "$provider" \
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
  echo "  - $ROOT/$run/eval/plan_scores_grok${SCORE_SUFFIX}.csv"
  echo "  - $ROOT/$run/eval/plan_scores_grok${SCORE_SUFFIX}.jsonl"
done

echo "[INFO] Generating plots..."
bash "$ROOT/scripts/plot/run_plot_eval_all.sh"
