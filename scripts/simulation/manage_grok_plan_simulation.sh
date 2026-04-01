#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/allenygy/Research/GAgent"
RUN_SCRIPT="$ROOT/scripts/simulation/run_grok_plan_simulation.sh"

ACTION="${1:-status}"
EXPERIMENT_DIR="${2:-}"

find_latest_experiment() {
  ls -1dt "$ROOT"/experiments/sim_plan_grok_* 2>/dev/null | head -n1 || true
}

resolve_experiment() {
  if [[ -n "$EXPERIMENT_DIR" ]]; then
    echo "$EXPERIMENT_DIR"
    return
  fi
  find_latest_experiment
}

print_progress() {
  local exp_dir="$1"
  if [[ -z "$exp_dir" || ! -d "$exp_dir" ]]; then
    echo "[ERR] Experiment directory not found: $exp_dir" >&2
    exit 1
  fi

  python3 - "$exp_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

exp = Path(sys.argv[1])
manifest_path = exp / "experiment_manifest.json"
judge_dir = exp / "run_logs" / "judge"

if not judge_dir.exists():
    print(f"[ERR] Judge directory not found: {judge_dir}")
    raise SystemExit(1)

total_runs = 100
max_turns = 50
if manifest_path.exists():
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        total_runs = int(manifest.get("runs", total_runs))
        max_turns = int(manifest.get("max_turns", max_turns))
    except Exception:
        pass

turns = {}
for f in judge_dir.glob("run*_turn*.json"):
    m = re.match(r"run(\d+)_turn(\d+)\.json", f.name)
    if not m:
        continue
    run_idx = int(m.group(1))
    turn_idx = int(m.group(2))
    turns.setdefault(run_idx, set()).add(turn_idx)

if not turns:
    print(f"[INFO] No progress files in {judge_dir}")
    raise SystemExit(0)

full_runs = []
next_run = 1
for run_idx in range(1, total_runs + 1):
    count = len(turns.get(run_idx, set()))
    if count >= max_turns:
        full_runs.append(run_idx)
        next_run = run_idx + 1
    else:
        next_run = run_idx
        break
else:
    next_run = total_runs + 1

max_seen_run = max(turns)
max_seen_turn = max(turns[max_seen_run]) if turns[max_seen_run] else 0
done_turns = sum(len(v) for v in turns.values())
expected_turns = total_runs * max_turns

print(f"[INFO] Experiment: {exp}")
print(f"[INFO] Full runs: {len(full_runs)} (last full run: {full_runs[-1] if full_runs else 0})")
print(f"[INFO] Latest activity: run {max_seen_run}, max turn {max_seen_turn}")
print(f"[INFO] Total turns: {done_turns}/{expected_turns} ({(done_turns / expected_turns * 100):.1f}%)")
print(f"[INFO] Next resume point: run {next_run}")
PY
}

stop_grok_only() {
  pkill -f "scripts/simulation/run_grok_plan_simulation.sh" || true
  pkill -f "parallel_simulation_experiment.py --mode plan.*sim_plan_grok" || true
  echo "[OK] Stopped grok plan simulation processes."
}

resume_grok() {
  local exp_dir="$1"
  if [[ -z "$exp_dir" || ! -d "$exp_dir" ]]; then
    echo "[ERR] Experiment directory not found: $exp_dir" >&2
    exit 1
  fi
  if [[ ! -f "$RUN_SCRIPT" ]]; then
    echo "[ERR] Run script not found: $RUN_SCRIPT" >&2
    exit 1
  fi

  local resume_info
  resume_info="$(python3 - "$exp_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

exp = Path(sys.argv[1])
manifest = json.loads((exp / "experiment_manifest.json").read_text(encoding="utf-8"))
total_runs = int(manifest.get("runs", 100))
max_turns = int(manifest.get("max_turns", 50))
judge_dir = exp / "run_logs" / "judge"

turns = {}
for f in judge_dir.glob("run*_turn*.json"):
    m = re.match(r"run(\d+)_turn(\d+)\.json", f.name)
    if not m:
        continue
    run_idx = int(m.group(1))
    turn_idx = int(m.group(2))
    turns.setdefault(run_idx, set()).add(turn_idx)

start = 1
for run_idx in range(1, total_runs + 1):
    if len(turns.get(run_idx, set())) < max_turns:
        start = run_idx
        break
else:
    start = total_runs + 1

remaining = max(0, total_runs - start + 1)
print(f"{start} {remaining} {max_turns}")
PY
)"

  local run_start runs_left max_turns
  run_start="$(echo "$resume_info" | awk '{print $1}')"
  runs_left="$(echo "$resume_info" | awk '{print $2}')"
  max_turns="$(echo "$resume_info" | awk '{print $3}')"

  if [[ "$runs_left" -le 0 ]]; then
    echo "[INFO] Nothing to resume. All runs are complete."
    return
  fi

  echo "[INFO] Resuming from run $run_start, remaining runs: $runs_left (max_turns=$max_turns)"
  OUT_DIR="$exp_dir" \
  RUN_START="$run_start" \
  RUNS="$runs_left" \
  MAX_TURNS="$max_turns" \
  "$RUN_SCRIPT"
}

case "$ACTION" in
  status)
    print_progress "$(resolve_experiment)"
    ;;
  stop)
    stop_grok_only
    ;;
  resume)
    resume_grok "$(resolve_experiment)"
    ;;
  stop-status)
    stop_grok_only
    print_progress "$(resolve_experiment)"
    ;;
  *)
    echo "Usage: $0 [status|stop|resume|stop-status] [EXPERIMENT_DIR]" >&2
    exit 1
    ;;
esac

