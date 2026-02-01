#!/usr/bin/env bash
set -euo pipefail

ROOT="experiments/experiments-21"
RUNS=(90 96 97 98 99 100)

for i in "${RUNS[@]}"; do
    RUN=$(printf "%02d" "$i")
    DB_ROOT="${ROOT}/db_run_${RUN}"
    PLAN_ID=$(sqlite3 "${DB_ROOT}/main/plan_registry.db" 'select id from plans limit 1;')
    echo "Re-running run ${RUN} (plan_id=${PLAN_ID})"

    OUT="${ROOT}/rerun_run_${RUN}"
    mkdir -p "${OUT}/run_logs" "${OUT}/session_logs"

    SIMULATION_RUN_OUTPUT_DIR="${OUT}/run_logs" \
    SIMULATION_SESSION_OUTPUT_DIR="${OUT}/session_logs" \
    SIM_USER_PROMPT_OUTPUT_DIR="${OUT}/run_logs/sim_user_prompts" \
    CHAT_AGENT_PROMPT_OUTPUT_DIR="${OUT}/run_logs/chat_agent_prompts" \
    JUDGE_PROMPT_OUTPUT_DIR="${OUT}/run_logs/judge_prompts" \
    python scripts/simulation/run_simulation.py \
        --plan-id "${PLAN_ID}" \
        --session-id "sim${PLAN_ID}_rerun_${RUN}" \
        --db-root "${DB_ROOT}" \
        --max-turns 50 \
        --max-actions-per-turn 2 \
        --disable-rerun-task \
        --disable-web-search \
        --disable-graph-rag \
        --no-stop-on-misalignment

    echo "Finished run ${RUN}"
done