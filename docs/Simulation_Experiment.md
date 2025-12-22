# Simulation Experiment Documentation

本说明覆盖 `parallel_simulation_experiment.py` 的两种模式：

- **full_plan**：对完整计划 JSON 做“模拟用户↔代理”循环评估
- **action**：对数据库中的 plan_id 走 Action 模式回合评估

## full_plan 模式

### qwen / qwen3-max

```shell
cd /Users/allenygy/Research/GAgent
export LLM_PROVIDER=qwen
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=qwen3-max

python scripts/parallel_simulation_experiment.py \
  --mode full_plan \
  --input-plan-json /Users/allenygy/Research/GAgent/direct_plans/plan_41.json \
  --runs 100 \
  --parallelism 10 \
  --max-turns 50 \
  --provider qwen \
  --model qwen3-max \
  --output-root /Users/allenygy/Research/GAgent/experiments/experiments-plan41-qwen
```

### qwen / deepseek-v3

```shell
cd /Users/allenygy/Research/GAgent
export LLM_PROVIDER=qwen
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3

python scripts/parallel_simulation_experiment.py \
  --mode full_plan \
  --input-plan-json /Users/allenygy/Research/GAgent/direct_plans/plan_41.json \
  --runs 100 \
  --parallelism 10 \
  --max-turns 50 \
  --provider qwen \
  --model deepseek-v3 \
  --output-root /Users/allenygy/Research/GAgent/experiments/experiments-plan41-deepseekv3
```

### full_plan 结果可视化

full_plan 模式的评估结果在 `eval/results.csv`，绘图应指向 **eval 目录**：

```shell
cd /Users/allenygy/Research/GAgent
python scripts/plot_misalignment_distribution.py \
  --run-dir experiments/experiments-plan41-qwen/eval \
  --output experiments/experiments-plan41-qwen/misalignment_distribution.png \
  --matrix-output experiments/experiments-plan41-qwen/misalignment_matrix.csv
```

## action 模式

```shell
cd /Users/allenygy/Research/GAgent
python scripts/parallel_simulation_experiment.py \
  --mode action \
  --plan-id 41 \
  --runs 100 \
  --parallelism 10 \
  --max-turns 50 \
  --max-actions-per-turn 2 \
  --disable-rerun-task \
  --no-stop-on-misalignment \
  --output-root /Users/allenygy/Research/GAgent/experiments/experiments-21
```

### action 结果可视化

action 模式使用 `run_logs/`：

```shell
cd /Users/allenygy/Research/GAgent
python scripts/plot_misalignment_distribution.py \
  --run-dir experiments/experiments-21/run_logs \
  --output experiments/experiments-21/misalignment_distribution.png \
  --matrix-output experiments/experiments-21/misalignment_matrix.csv
```
