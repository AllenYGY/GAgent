#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export QWEN_API_KEYS="key1,key2,..."  # or QWEN_API_KEY
#   bash scripts/pipeline/run_eval_plan.sh
#
# Concurrency is min(number of api keys, number of runs * number of models).
# Provide keys via environment, e.g.:
#   export QWEN_API_KEYS="key1,key2,..."  # or QWEN_API_KEY
: "${QWEN_API_KEYS:=sk-673316f7b0b24c71b1cdc2b718dccb94,sk-389de519c141411f827d305a0d3986e9,sk-8c72557962224342bc6713bcd552dc7c,sk-9417e4ec0397402d8fb2732f7d295692,sk-17c45c123dd1403d80cc78aa77d46c10}"
export QWEN_API_KEYS

ROOT="/Users/allenygy/Research/GAgent"

RUNS=(
  "results/agent_plans_phage_deepseek_web_enriched_v2"
  "results/agent_plans_phage_qwen_web_enriched_v2"
  "results/agent_plans_phage_deepseek"
  "results/agent_plans_phage_qwen"
  "results/llm_plans_phage_deepseek"
  "results/llm_plans_phage_qwen"
)

MODELS=(
  "qwen3-max"
  "deepseek-v3"
)

RUN_TS="$(date +%Y%m%d_%H%M%S)"
SCORE_BASE="10pt"
SCORE_SUFFIX="_${SCORE_BASE}_${RUN_TS}"
EVAL_TAG_QWEN="qwen_${SCORE_BASE}"
EVAL_TAG_DEEP="deepseekv3_${SCORE_BASE}"
KEY_SLOTS_PER_KEY="${KEY_SLOTS_PER_KEY:-2}"

if ! command -v parallel >/dev/null 2>&1; then
  echo "[ERR] GNU parallel is required. Install it or set USE_XARGS=1 to use xargs -P." >&2
  exit 1
fi

# Load API keys (comma-separated)
if [[ -n "${QWEN_API_KEYS:-}" ]]; then
  IFS=',' read -r -a KEYS <<<"$QWEN_API_KEYS"
elif [[ -n "${QWEN_API_KEY:-}" ]]; then
  KEYS=("$QWEN_API_KEY")
else
  echo "[ERR] Set QWEN_API_KEYS or QWEN_API_KEY." >&2
  exit 1
fi

# Trim whitespace and drop empty keys
_clean_keys=()
for k in "${KEYS[@]}"; do
  k="${k//[[:space:]]/}"
  if [[ -n "$k" ]]; then
    _clean_keys+=("$k")
  fi
done
KEYS=("${_clean_keys[@]}")
if (( ${#KEYS[@]} == 0 )); then
  echo "[ERR] No valid keys found in QWEN_API_KEYS/QWEN_API_KEY." >&2
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
echo "[INFO] API keys loaded: ${#KEYS[@]} key(s)"

# Concurrency = min(num_keys, num_runs * num_models)
total_jobs=$(( ${#RUNS[@]} * ${#MODELS[@]} ))
total_slots=$(( ${#KEYS[@]} * KEY_SLOTS_PER_KEY ))
concurrency=$total_jobs
if (( total_slots < concurrency )); then
  concurrency=$total_slots
fi
if (( concurrency < 1 )); then
  concurrency=1
fi
echo "[INFO] Total jobs: $total_jobs"
echo "[INFO] Key slots per key: $KEY_SLOTS_PER_KEY"
echo "[INFO] Concurrency: $concurrency"

# Build per-key job lists: run \t model \t plan_dir
job_dir=$(mktemp -d -t run_eval_plan)
trap 'rm -rf "$job_dir"' EXIT
echo "[INFO] Job dir: $job_dir"

slot_count=$(( ${#KEYS[@]} * KEY_SLOTS_PER_KEY ))
job_files=()
for i in $(seq 0 $((slot_count - 1))); do
  job_files[i]="$job_dir/jobs_$i.tsv"
  : > "${job_files[$i]}"
done

idx=0
for i in "${!RUNS[@]}"; do
  run="${RUNS[$i]}"
  plan_dir="${PLAN_DIRS[$i]}"
  for model in "${MODELS[@]}"; do
    slot_idx=$(( idx % slot_count ))
    printf "%s\t%s\t%s\n" "$run" "$model" "$plan_dir" >> "${job_files[$slot_idx]}"
    idx=$((idx + 1))
  done
done

# Pair each key with its job file (only if it has work)
pairs_file="$job_dir/pairs.tsv"
: > "$pairs_file"
for i in $(seq 0 $((slot_count - 1))); do
  if [[ -s "${job_files[$i]}" ]]; then
    key_idx=$(( i % ${#KEYS[@]} ))
    printf "%s\t%s\n" "${KEYS[$key_idx]}" "${job_files[$i]}" >> "$pairs_file"
  fi
done
pair_count=$(wc -l < "$pairs_file" | tr -d ' ')
echo "[INFO] Parallel workers to launch: $pair_count"
if (( pair_count == 0 )); then
  echo "[ERR] No jobs scheduled. Check RUNS/MODELS." >&2
  exit 1
fi
echo "[INFO] Job distribution per key:"
for i in "${!KEYS[@]}"; do
  total_for_key=0
  for s in $(seq 0 $((slot_count - 1))); do
    if (( s % ${#KEYS[@]} == i )); then
      if [[ -s "${job_files[$s]}" ]]; then
        count=$(wc -l < "${job_files[$s]}")
        total_for_key=$(( total_for_key + count ))
      fi
    fi
  done
  echo "  - key #$((i+1)): ${total_for_key} job(s)"
done

parallel --colsep '\t' --jobs "$concurrency" --lb \
  'export QWEN_API_KEY={1}; export LLM_PROVIDER=qwen; \
  while IFS=$'\''\t'\'' read -r run model plan_dir; do \
    [ -n "$run" ] && [ -n "$model" ] && [ -n "$plan_dir" ] || continue; \
    export QWEN_MODEL="$model"; \
    if [ "$model" = "qwen3-max" ]; then tag="qwen"; else tag="deepseekv3"; fi; \
    mkdir -p "'$ROOT'/$run/eval"; \
    python -u "'$ROOT'/scripts/eval/eval_plan_quality_10pt.py" \
      --plan-tree-dir "$plan_dir" \
      --provider qwen \
      --model "$model" \
      --batch-size 2 \
      --max-retries 3 \
      --output "'$ROOT'/$run/eval/plan_scores_${tag}'"$SCORE_SUFFIX"'.csv" \
      --jsonl-output "'$ROOT'/$run/eval/plan_scores_${tag}'"$SCORE_SUFFIX"'.jsonl"; \
  done < {2}' :::: "$pairs_file"

end_ts=$(date +%s)
elapsed=$(( end_ts - start_ts ))
echo "[INFO] Eval finished in ${elapsed}s. Output files:"
for run in "${RUNS[@]}"; do
  echo "  - $ROOT/$run/eval/plan_scores_qwen${SCORE_SUFFIX}.csv"
  echo "  - $ROOT/$run/eval/plan_scores_qwen${SCORE_SUFFIX}.jsonl"
  echo "  - $ROOT/$run/eval/plan_scores_deepseekv3${SCORE_SUFFIX}.csv"
  echo "  - $ROOT/$run/eval/plan_scores_deepseekv3${SCORE_SUFFIX}.jsonl"
done

echo "[INFO] Generating plots..."

# Build labels from run directory names
labels=()
for run in "${RUNS[@]}"; do
  labels+=("${run##*/}")
done

plots_root="$ROOT/results/plots_web_v2"
mkdir -p "$plots_root"

# Boxplots (qwen3-max)
files_qwen=()
for run in "${RUNS[@]}"; do
  files_qwen+=("$ROOT/$run/eval/plan_scores_qwen${SCORE_SUFFIX}.csv")
done
missing=0
for f in "${files_qwen[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "[WARN] Missing score file: $f"
    missing=1
  fi
done
if (( missing == 0 )); then
  python -u "$ROOT/scripts/plot/plot_plan_score_boxplots.py" \
    --files "${files_qwen[@]}" \
    --labels "${labels[@]}" \
    --output-dir "$plots_root/score_boxplots_qwen"
else
  echo "[WARN] Skipping qwen boxplots due to missing files."
fi

# Boxplots (deepseek-v3)
files_deep=()
for run in "${RUNS[@]}"; do
  files_deep+=("$ROOT/$run/eval/plan_scores_deepseekv3${SCORE_SUFFIX}.csv")
done
missing=0
for f in "${files_deep[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "[WARN] Missing score file: $f"
    missing=1
  fi
done
if (( missing == 0 )); then
  python -u "$ROOT/scripts/plot/plot_plan_score_boxplots.py" \
    --files "${files_deep[@]}" \
    --labels "${labels[@]}" \
    --output-dir "$plots_root/score_boxplots_deepseekv3"
else
  echo "[WARN] Skipping deepseek boxplots due to missing files."
fi

# Radar charts (per model)
run_dirs=()
for run in "${RUNS[@]}"; do
  run_dirs+=("$ROOT/$run")
done

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "$EVAL_TAG_QWEN" \
  --output-dir "$plots_root/score_radars_qwen" || echo "[WARN] Radar (qwen) failed."

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "$EVAL_TAG_DEEP" \
  --output-dir "$plots_root/score_radars_deepseekv3" || echo "[WARN] Radar (deepseekv3) failed."

echo "[INFO] Plots output root: $plots_root"
