#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/allenygy/Research/GAgent"
INPUT="${INPUT:-$ROOT/data/phage_plans.csv}"

LLM_CONCURRENCY="${LLM_CONCURRENCY:-4}"
MAX_RETRIES="${MAX_RETRIES:-2}"

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

echo "[INFO] Input: $INPUT"
echo "[INFO] LLM-only generation"
echo "[INFO] openrouter model=$OPENROUTER_MODEL"

export OPENROUTER_API_KEY="$OPENROUTER_KEY"

cd "$ROOT"

python scripts/generate/generate_llm_plans.py \
  --input "$INPUT" \
  --provider openrouter \
  --model "$OPENROUTER_MODEL" \
  --out-dir "$ROOT/results/llm_plans_phage_gpt52chat" \
  --concurrency "$LLM_CONCURRENCY" \
  --max-retries "$MAX_RETRIES"
