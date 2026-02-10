#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/allenygy/Research/GAgent"
INPUT="${INPUT:-$ROOT/data/phage_plans.csv}"

AGENT_CONCURRENCY="${AGENT_CONCURRENCY:-10}"
DECOMP_PASSES="${DECOMP_PASSES:-2}"
DECOMP_EXPAND_DEPTH="${DECOMP_EXPAND_DEPTH:-2}"
DECOMP_NODE_BUDGET="${DECOMP_NODE_BUDGET:-10}"
RESUME_MIN_NODES="${RESUME_MIN_NODES:-2}"

OPENROUTER_MODEL="${OPENROUTER_MODEL:-openai/gpt-5.2-chat}"

OPENROUTER_KEY="${OPENROUTER_API_KEY:-}"

if [[ ! -f "$INPUT" ]]; then
  echo "[ERR] Input file not found: $INPUT" >&2
  exit 1
fi

if [[ -z "$OPENROUTER_KEY" ]]; then
  echo "[ERR] OPENROUTER_API_KEY is required." >&2
  exit 1
fi

if ! command -v parallel >/dev/null 2>&1; then
  echo "[ERR] GNU parallel is required. Install it or run jobs manually." >&2
  exit 1
fi

job_dir=$(mktemp -d -t run_generate_plans)
trap 'rm -rf "$job_dir"' EXIT
jobs_file="$job_dir/jobs.tsv"
: > "$jobs_file"

printf "agent\topenrouter\t%s\t%s\t%s\t%s\n" \
  "$OPENROUTER_MODEL" \
  "$ROOT/results/agent_plans_phage_gpt52chat" \
  "$ROOT/data/databases_gpt52chat" \
  "$ROOT/results/agent_plans_phage_gpt52chat/plans" >> "$jobs_file"

echo "[INFO] Input: $INPUT"
echo "[INFO] Total jobs: $(wc -l < "$jobs_file" | tr -d ' ')"

export OPENROUTER_API_KEY="$OPENROUTER_KEY"
export SKIP_DOTENV=true

parallel --colsep $'\\t' --jobs 4 --lb \
  'kind={1}; provider={2}; model={3}; out={4}; db_root={5}; dump_dir={6}; \
   echo "[INFO] job kind=$kind provider=$provider model=$model db_root=$db_root dump_dir=$dump_dir"; \
   cd "'$ROOT'" || exit 1; \
   api_key="$OPENROUTER_API_KEY"; \
   export DB_ROOT="$db_root"; \
   export DECOMP_PROVIDER="$provider"; \
   export DECOMP_MODEL="$model"; \
   export DECOMP_API_KEY="$api_key"; \
   export DECOMP_ENABLE_WEB_SEARCH=false; \
   echo "[INFO] env DECOMP_PROVIDER=$DECOMP_PROVIDER DECOMP_MODEL=$DECOMP_MODEL DB_ROOT=$DB_ROOT"; \
   env | grep -E "^DECOMP_" || true; \
   if ls "$db_root"/plans/plan_*.sqlite >/dev/null 2>&1; then \
     python scripts/generate/resume_decomposer_plans.py \
       --input "'$INPUT'" \
       --passes "'$DECOMP_PASSES'" \
       --expand-depth "'$DECOMP_EXPAND_DEPTH'" \
       --node-budget "'$DECOMP_NODE_BUDGET'" \
       --min-nodes "'$RESUME_MIN_NODES'" \
       --concurrency "'$AGENT_CONCURRENCY'" \
       --dump-dir "$dump_dir"; \
   else \
     python scripts/generate/decomposer_plan_generator.py \
       --input "'$INPUT'" \
       --passes "'$DECOMP_PASSES'" \
       --expand-depth "'$DECOMP_EXPAND_DEPTH'" \
       --node-budget "'$DECOMP_NODE_BUDGET'" \
       --concurrency "'$AGENT_CONCURRENCY'" \
       --dump-dir "$dump_dir"; \
   fi;' :::: "$jobs_file"
