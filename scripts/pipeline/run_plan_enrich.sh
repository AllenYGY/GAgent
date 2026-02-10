#!/usr/bin/env bash
set -euo pipefail

# Run multiple enrich jobs in parallel.
# Each job sets DB_ROOT + input/output paths for plan_enrichment_pipeline.py.


ROOT="/Users/allenygy/Research/GAgent"

RUNS=(
  "data/databases_deepseek_web_enrich_refactor_v2|results/agent_plans_phage_deepseek/plans|results/agent_plans_phage_deepseek_web_enriched_refactor_v2/plans|deepseek-v3"
  "data/databases_qwen_web_enrich_refactor_v2|results/agent_plans_phage_qwen/plans|results/agent_plans_phage_qwen_web_enriched_refactor_v2/plans|qwen3-max"
)

ENRICH_ALLOW_WEB_SEARCH="${ENRICH_ALLOW_WEB_SEARCH:-true}"
ENRICH_TITLE_PREFIX="${ENRICH_TITLE_PREFIX:-Imported}"
ENRICH_MAX_DEPTH="${ENRICH_MAX_DEPTH:-}"
ENRICH_NODE_BUDGET="${ENRICH_NODE_BUDGET:-}"
ENRICH_ENABLE_REFACTOR="${ENRICH_ENABLE_REFACTOR:-true}"
REFACTOR_MAX_ACTIONS="${REFACTOR_MAX_ACTIONS:-25}"
REFACTOR_ACTION_ALLOWLIST="${REFACTOR_ACTION_ALLOWLIST:-create_task,update_task,move_task,delete_task,decompose_task}"
REFACTOR_ALLOW_DELETE_SUBTREE="${REFACTOR_ALLOW_DELETE_SUBTREE:-false}"
REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH="${REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH:-false}"
REFACTOR_LOG_DIR="${REFACTOR_LOG_DIR:-}"

if ! command -v parallel >/dev/null 2>&1; then
  echo "[ERR] GNU parallel is required. Install it or set USE_XARGS=1 to use xargs -P." >&2
  exit 1
fi

: "${QWEN_API_KEYS:=sk-673316f7b0b24c71b1cdc2b718dccb94,sk-389de519c141411f827d305a0d3986e9,sk-8c72557962224342bc6713bcd552dc7c,sk-9417e4ec0397402d8fb2732f7d295692,sk-17c45c123dd1403d80cc78aa77d46c10}"
export QWEN_API_KEYS

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

total_jobs=${#RUNS[@]}
concurrency=$total_jobs
if (( ${#KEYS[@]} < concurrency )); then
  concurrency=${#KEYS[@]}
fi
if (( concurrency < 1 )); then
  concurrency=1
fi

job_dir=$(mktemp -d -t run_plan_enrich)
trap 'rm -rf "$job_dir"' EXIT

job_files=()
for i in "${!KEYS[@]}"; do
  job_files[i]="$job_dir/jobs_$i.tsv"
  : > "${job_files[$i]}"
done

idx=0
for item in "${RUNS[@]}"; do
  IFS='|' read -r db_root input_path output_dir model <<<"$item"
  key_idx=$(( idx % ${#KEYS[@]} ))
  printf "%s\t%s\t%s\t%s\n" "$db_root" "$input_path" "$output_dir" "$model" >> "${job_files[$key_idx]}"
  idx=$((idx + 1))
done

pairs_file="$job_dir/pairs.tsv"
: > "$pairs_file"
for i in "${!KEYS[@]}"; do
  if [[ -s "${job_files[$i]}" ]]; then
    printf "%s\t%s\n" "${KEYS[$i]}" "${job_files[$i]}" >> "$pairs_file"
  fi
done

pair_count=$(wc -l < "$pairs_file" | tr -d ' ')
echo "[INFO] Total jobs: $total_jobs"
echo "[INFO] Concurrency: $concurrency"
echo "[INFO] Parallel workers to launch: $pair_count"
echo "[INFO] Job distribution per key:"
for i in "${!KEYS[@]}"; do
  if [[ -s "${job_files[$i]}" ]]; then
    count=$(wc -l < "${job_files[$i]}")
    echo "  - key #$((i+1)): ${count} job(s)"
  fi
done

parallel --colsep '\t' --jobs "$concurrency" --lb \
  'export QWEN_API_KEY={1}; export LLM_PROVIDER=qwen; \
   while IFS=$'\''\t'\'' read -r db_root input_path output_dir model; do \
     [ -n "$db_root" ] && [ -n "$input_path" ] && [ -n "$output_dir" ] && [ -n "$model" ] || continue; \
     cd "'$ROOT'" || exit 1; \
     export DB_ROOT="$db_root"; \
     export ENRICH_INPUT_PATH="$input_path"; \
     export ENRICH_OUTPUT_DIR="$output_dir"; \
     export QWEN_MODEL="$model"; \
     export REFACTOR_MODEL="$model"; \
     export REFACTOR_PROVIDER="qwen"; \
     export ENRICH_TITLE_PREFIX="'$ENRICH_TITLE_PREFIX'"; \
     export ENRICH_ALLOW_WEB_SEARCH="'$ENRICH_ALLOW_WEB_SEARCH'"; \
     export ENRICH_MAX_DEPTH="'$ENRICH_MAX_DEPTH'"; \
     export ENRICH_NODE_BUDGET="'$ENRICH_NODE_BUDGET'"; \
     export ENRICH_ENABLE_REFACTOR="'$ENRICH_ENABLE_REFACTOR'"; \
     export REFACTOR_MAX_ACTIONS="'$REFACTOR_MAX_ACTIONS'"; \
     export REFACTOR_ACTION_ALLOWLIST="'$REFACTOR_ACTION_ALLOWLIST'"; \
     export REFACTOR_ALLOW_DELETE_SUBTREE="'$REFACTOR_ALLOW_DELETE_SUBTREE'"; \
     export REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH="'$REFACTOR_DECOMPOSE_ALLOW_WEB_SEARCH'"; \
     export REFACTOR_LOG_DIR="'$REFACTOR_LOG_DIR'"; \
     python scripts/pipeline/plan_enrichment_pipeline.py; \
   done < {2}' \
  :::: "$pairs_file"
