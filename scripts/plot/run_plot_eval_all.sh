#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/allenygy/Research/GAgent"
plots_root="$ROOT/results/plots_eval_all_models"

run_dirs=(
  "$ROOT/results/agent_plans_phage_gemini"
  "$ROOT/results/agent_plans_phage_grok"
  "$ROOT/results/agent_plans_phage_gpt52chat"
  "$ROOT/results/agent_plans_phage_deepseek"
  "$ROOT/results/agent_plans_phage_qwen"
  "$ROOT/results/agent_plans_phage_deepseek_web_enriched_refactor_v2"
  "$ROOT/results/agent_plans_phage_qwen_web_enriched_refactor_v2"
  "$ROOT/results/llm_plans_phage_gemini"
  "$ROOT/results/llm_plans_phage_grok"
  "$ROOT/results/llm_plans_phage_gpt52chat"
  "$ROOT/results/llm_plans_phage_deepseek"
  "$ROOT/results/llm_plans_phage_qwen"
)

mkdir -p "$plots_root"

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "qwen_10pt" \
  --output-dir "$plots_root/score_radars_qwen"

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "deepseekv3_10pt" \
  --output-dir "$plots_root/score_radars_deepseekv3"

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "gemini_10pt" \
  --output-dir "$plots_root/score_radars_gemini"

python -u "$ROOT/scripts/plot/plot_plan_score_radars.py" \
  --run-dirs "${run_dirs[@]}" \
  --eval-tag "gpt52chat_10pt" \
  --output-dir "$plots_root/score_radars_gpt52chat"

shopt -s nullglob

plot_boxplots_all() {
  local tag="$1"
  declare -A groups
  local any=0
  for d in "${run_dirs[@]}"; do
    for f in "$d"/eval/plan_scores_${tag}_10pt_*.csv; do
      [[ -e "$f" ]] || continue
      any=1
      local base ts key
      base=$(basename "$f")
      ts=$(echo "$base" | sed -E 's/.*_([0-9]{8}_[0-9]{6})\.csv/\1/')
      key="${tag}|${ts}"
      groups["$key"]+="$f|$(basename "$d")"$'\n'
    done
  done
  if (( any == 0 )); then
    echo "[WARN] No files found for tag ${tag}; skipping boxplots."
    return
  fi
  for key in "${!groups[@]}"; do
    local files=()
    local labels=()
    local ts="${key#*|}"
    while IFS='|' read -r f l; do
      [[ -n "$f" ]] || continue
      files+=("$f")
      labels+=("$l")
    done <<< "${groups[$key]}"
    python -u "$ROOT/scripts/plot/plot_plan_score_boxplots.py" \
      --files "${files[@]}" \
      --labels "${labels[@]}" \
      --output-dir "$plots_root/score_boxplots_${tag}/eval_${tag}_10pt_${ts}"
  done
}

plot_boxplots_all "qwen"
plot_boxplots_all "deepseekv3"
plot_boxplots_all "gemini"
plot_boxplots_all "gpt52chat"

echo "[INFO] Plots output root: $plots_root"
