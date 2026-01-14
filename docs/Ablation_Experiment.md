# Plan Experiment

## Ablation Matrix

This doc focuses on plan-generation ablations across planner type, tool access, and LLM model.

| Label | Planner | Tool Access | Script | Notes |
| --- | --- | --- | --- | --- |
| llm | LLM direct | none | `scripts/generate_llm_plans.py` | Pure JSON plan generation. |
| agent | Agent (decomposer) | none | `scripts/decomposer_plan_generator.py` | Disable web_search via env. |
| agent_web | Agent (decomposer) | web_search | `scripts/decomposer_plan_generator.py` | Enable web_search via env. |
| agent_rag | Agent (chat) | graph_rag | `scripts/run_structured_agent.py` | Requires prompt to call graph_rag. |
| agent_web_rag | Agent (chat) | web_search + graph_rag | `scripts/run_structured_agent.py` | Prompt must call tools before create_plan. |

Model axis: run each label with different LLM models (e.g., qwen3-max, deepseek-v3) by setting provider/model env or CLI flags.

## Tooling Notes

- `web_search` is only used by the decomposer when enabled (`DECOMP_ENABLE_WEB_SEARCH=true`).
- `graph_rag` is a chat tool; it is not called by the decomposer automatically.
- For graph_rag ablations, use the chat-based agent and explicitly instruct tool calls in the prompt template.
- You can run the chat agent locally via `scripts/run_structured_agent.py` (no backend).

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

### Decomposer Without any Tools

```shell
# Disable web_search for baseline agent runs
export DECOMP_ENABLE_WEB_SEARCH=false
```

#### Qwen deepseek-v3

```shell
export LLM_PROVIDER=qwen
export QWEN_MODEL=deepseek-v3
python scripts/decomposer_plan_generator.py \                         
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_deepseek/plans \
    --concurrency 10
```

#### Qwen qwen3-max

```shell
export LLM_PROVIDER=qwen
export QWEN_MODEL=qwen3-max
python scripts/decomposer_plan_generator.py \
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_qwen/plans \
    --concurrency 5
```

### Decomposer With Web Search

```shell
# Enable web_search for agent_web runs (default is true)
export DECOMP_ENABLE_WEB_SEARCH=true
```

#### Qwen deepseek-v3

```shell
export LLM_PROVIDER=qwen
export QWEN_MODEL=deepseek-v3
python scripts/decomposer_plan_generator.py \
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_deepseek_web/plans \
    --concurrency 5
```

#### Qwen qwen3-max

```shell
export LLM_PROVIDER=qwen
export QWEN_MODEL=qwen3-max
python scripts/decomposer_plan_generator.py \
    --input data/phage_plans.csv \
    --passes 2 \
    --expand-depth 2 \
    --node-budget 10 \
    --dump-dir results/agent_plans_phage_qwen_web/plans \
    --concurrency 5
```

### Agent With RAG

### Agent With Web Search + RAG

## Evaluation

### Template for new ablations

```shell
python scripts/eval_plan_quality.py \
  --plan-tree-dir results/<run_dir>/plans \
  --provider qwen \
  --model qwen3-max \
  --batch-size 2 \
  --max-retries 3 \
  --output results/<run_dir>/eval/plan_scores_qwen.csv \
  --jsonl-output results/<run_dir>/eval/plan_scores_qwen.jsonl
```

Notes:

- `generate_llm_plans.py` outputs under `<out-dir>/parsed`.
- `decomposer_plan_generator.py` outputs directly under `<dump-dir>`.
- `bulk_generate_plans.py` outputs under `<dump-dir>/plans`.

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

### agent_plans_phage_qwen_web

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_qwen_web/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=sk-9417e4ec0397402d8fb2732f7d295692
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_qwen_web/eval/plan_scores_deepseekv3.jsonl
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
      results/agent_plans_phage_qwen_web/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output results/score_bars_qwen.png
```

```shell
 # deepseek-v3 评测（plan_scores_deepseekv3.csv）
python scripts/plot_plan_score_bars.py \
    --files \
      results/agent_plans_phage_qwen_web/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output results/score_bars_deepseekv3.png
```

### Violin plots (per metric)

```shell
python scripts/plot_plan_score_boxplots.py \
  --files \
    results/agent_plans_phage_qwen_web/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
  --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_boxplots_qwen
```

```shell
python scripts/plot_plan_score_boxplots.py \
  --files \
    results/agent_plans_phage_qwen_web/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
  --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_boxplots_deepseekv3
```

### Demo data + plots (synthetic)

```shell
python scripts/generate_demo_ablation_data.py --with-plots
```

### Radar charts (per model)

```shell
python scripts/plot_plan_score_radars.py \
  --scores-dir results \
  --output-dir results/score_radars
```

Example (restrict to five run folders + choose eval tag):

```shell
python scripts/plot_plan_score_radars.py \
  --run-dirs \
    results/agent_plans_phage_qwen_web \
    results/agent_plans_phage_deepseek \
    results/agent_plans_phage_qwen \
    results/llm_plans_phage_deepseek \
    results/llm_plans_phage_qwen \
  --eval-tag qwen \
  --output-dir results/score_radars
```

If `--eval-tag` is omitted with `--run-dirs`, the script will run all eval tags
shared across the run folders (e.g., `qwen`, `deepseekv3`).

### By category

```shell
  # qwen-max 评测按类别
  python scripts/plot_plan_score_bars_by_category.py \
    --category-csv data/phage_plans.csv \
    --files \
      results/agent_plans_phage_qwen_web/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output-dir results/score_bars_by_category_qwen
```

```shell
  # deepseek-v3 评测按类别
  python scripts/plot_plan_score_bars_by_category.py \
    --category-csv data/phage_plans.csv \
    --files \
      results/agent_plans_phage_qwen_web/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3.csv \
    --labels agent_qwen_web agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output-dir results/score_bars_by_category_deepseekv3
```
