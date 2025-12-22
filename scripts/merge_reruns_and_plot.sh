#!/usr/bin/env bash
set -euo pipefail

# This script merges rerun results for specific runs into a fresh run_logs directory
# and plots the misalignment distribution using the merged logs.
#
# Default roots (adjust if needed):
#   BASE_ROOT: original experiment root containing run_logs and rerun_run_## directories
#   TARGET_DIR: merged run_logs directory
#   PLOT_OUTPUT: output path for the plot
#
# Usage:
#   ./scripts/merge_reruns_and_plot.sh
#   # or override defaults:
#   BASE_ROOT=experiments/experiments-21 TARGET_DIR=experiments/experiments-21/run_logs_merged \
#     PLOT_OUTPUT=experiments/experiments-21/misalignment_distribution.png \
#     ./scripts/merge_reruns_and_plot.sh

BASE_ROOT="${BASE_ROOT:-experiments/experiments-21}"
TARGET_DIR="${TARGET_DIR:-${BASE_ROOT}/run_logs_merged}"
PLOT_OUTPUT="${PLOT_OUTPUT:-${BASE_ROOT}/misalignment_distribution.png}"

# Runs to replace with rerun results
RERUN_IDS=(${RERUN_IDS:-90 96 97 98 99 100})

RUN_LOGS="${BASE_ROOT}/run_logs"
RERUN_ROOT_PREFIX="${BASE_ROOT}/rerun_run_"

if [[ ! -d "$RUN_LOGS" ]]; then
  echo "Run logs directory not found: $RUN_LOGS" >&2
  exit 1
fi

echo "[INFO] Merging run logs into: $TARGET_DIR"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

echo "[INFO] Copying original run logs..."
cp ${RUN_LOGS}/*.json "$TARGET_DIR"/

# Map rerun IDs to original run_ids (session clone numbers) to remove
declare -A OLD_FILES
OLD_FILES=(
  [90]="79eae196905a4417b8574fcbf3111b9c"
  [96]="c9b63453890c4b388c3110f7a0b01850"
  [97]="3b87301e98a546d5a3b2279bb7b025e8"
  [98]="3599a04dd9fd464e9e9fd10a378f1a65"
  [99]="195d0efa2ae24e52b59f720fd349cf18"
  [100]="4c5f750fad6f4af7996c26e31d88fc5e"
)

echo "[INFO] Removing originals for rerun IDs: ${RERUN_IDS[*]}"
for id in "${RERUN_IDS[@]}"; do
  old="${OLD_FILES[$id]:-}"
  if [[ -n "$old" ]]; then
    rm -f "$TARGET_DIR/${old}.json"
  fi
done

echo "[INFO] Injecting rerun logs..."
for id in "${RERUN_IDS[@]}"; do
  src_dir="${RERUN_ROOT_PREFIX}${id}/run_logs"
  if ls "${src_dir}"/*.json >/dev/null 2>&1; then
    cp "${src_dir}"/*.json "$TARGET_DIR"/
  else
    echo "[WARN] No rerun json found for ${id} under ${src_dir}"
  fi
done

echo "[INFO] Plotting misalignment distribution to $PLOT_OUTPUT"
python scripts/plot_misalignment_distribution.py \
  --run-dir "$TARGET_DIR" \
  --output "$PLOT_OUTPUT"

echo "[INFO] Done. Merged logs: $TARGET_DIR"
