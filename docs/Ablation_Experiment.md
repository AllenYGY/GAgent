# Plan Experiment

## LLM Plan

### Qwen deepseek-v3

```shell
export LLM_PROVIDER=qwen
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3

  python scripts/generate_llm_plans.py \
    --input data/phage_plans.csv \
    --provider qwen \
    --model deepseek-v3 \
    --out-dir results/llm_plans_phage_deepseek \
    --concurrency 4 \
    --max-retries 2
```

### Qwen qwen3-max

```shell
python scripts/generate_llm_plans.py \
    --input data/phage_plans.csv \
    --out-dir results/llm_plans_phage_qwen \
    --concurrency 4 \
    --max-retries 2
```

## Agent Plan

### Qwen deepseek-v3

```shell
export LLM_PROVIDER=qwen
export QWEN_MODEL=deepseek-v3
python scripts/direct_plan_generator.py \                         
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_deepseek \
    --concurrency 10
```

### Qwen qwen3-max

```shell
python scripts/direct_plan_generator.py \
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_qwen \
    --concurrency 5
```

## Evaluation

### llm_plans_phage_qwen

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/llm_plans_phage_qwen/parsed \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
    --jsonl-output results/llm_plans_phage_qwen/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/llm_plans_phage_qwen/parsed \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.jsonl
```

### llm_plans_phage_deepseek

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/llm_plans_phage_deepseek/parsed \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --jsonl-output results/llm_plans_phage_deepseek/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/llm_plans_phage_deepseek/parsed \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.jsonl
```

### agent_plans_phage_qwen

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_qwen/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.jsonl
```

### agent_plans_phage_deepseek

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_deepseek/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.jsonl
```

## Plotting

### Overall

```shell
 # qwen-max 评测（plan_scores_qwen.csv）
python scripts/plot_plan_score_bars.py \
    --files \
      results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --labels agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output results/score_bars_qwen.png
```

```shell
 # deepseek-v3 评测（plan_scores_deepseekv3.csv）
python scripts/plot_plan_score_bars.py \
    --files \
      results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --labels agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output results/score_bars_deepseekv3.png
```

### By category

```shell
  # qwen-max 评测按类别
  python scripts/plot_plan_score_bars_by_category.py \
    --category-csv data/phage_plans.csv \
    --files \
      results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --labels agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output-dir results/score_bars_by_category_qwen
```

```shell
  # deepseek-v3 评测按类别
  python scripts/plot_plan_score_bars_by_category.py \
    --category-csv data/phage_plans.csv \
    --files \
      results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --labels agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output-dir results/score_bars_by_category_deepseekv3
```
