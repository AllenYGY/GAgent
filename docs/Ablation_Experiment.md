# Plan Experiment

## Ablation Matrix

This doc focuses on plan-generation ablations across planner type, tool access, and LLM model.

| Label | Planner | Tool Access | Script | Notes |
| --- | --- | --- | --- | --- |
| llm | LLM direct | none | `scripts/generate_llm_plans.py` | Pure JSON plan generation. |
| agent | Agent (decomposer) | none | `scripts/decomposer_plan_generator.py` | Disable web_search via env. |
| agent_web | Agent (decomposer) | web_search | `scripts/decomposer_plan_generator.py` | Enable web_search via env. |
| agent_web_rag | Agent (chat) | web_search + graph_rag | `scripts/bulk_generate_plans.py` | Extend the web-enriched setting with one extra graph_rag call before create_plan. |

Model axis: run each label with different LLM models (e.g., qwen3-max, deepseek-v3) by setting provider/model env or CLI flags.

## Tooling Notes

- `web_search` is only used by the decomposer when enabled (`DECOMP_ENABLE_WEB_SEARCH=true`).
- `graph_rag` is a chat tool; it is not called by the decomposer automatically.
- We do not run a standalone `graph_rag`-only ablation anymore.
- The combined `web_search + graph_rag` condition is defined as the web-enriched version plus one explicit `graph_rag` call before `plan_operation.create_plan`.
- Use the chat/bulk agent path for the combined condition and instruct tool calls explicitly in the prompt template.

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

### Agent With Web Search + GraphRAG

This condition extends the web-enriched agent setting. The intended comparison is:

- `agent`: no external retrieval
- `agent_web`: `web_search`
- `agent_web_rag`: `web_search` + `graph_rag`

We do not keep a separate `graph_rag`-only line in this ablation.

Use a prompt template that preserves the web-enriched flow and adds one focused
`graph_rag` lookup before plan creation.

```text
# agent_web_graph_rag.txt
Topic: "{title}"
Goal: {goal}

This condition extends the web-enriched baseline.
First call tool_operation.web_search with a focused query.
Then call tool_operation.graph_rag with a focused domain query that complements the web results.
Then call plan_operation.create_plan exactly once and confirm the plan_id.
```

#### Qwen deepseek-v3

```shell
export LLM_PROVIDER=qwen
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/bulk_generate_plans.py \
    --input data/phage_plans.csv \
    --prompt-template prompts/agent_web_graph_rag.txt \
    --dump-dir results/agent_plans_phage_deepseek_web_rag \
    --output results/agent_plans_phage_deepseek_web_rag/summary.csv \
    --concurrency 6
```

#### Qwen qwen3-max

```shell
export LLM_PROVIDER=qwen
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=qwen3-max
python scripts/bulk_generate_plans.py \
    --input data/phage_plans.csv \
    --prompt-template prompts/agent_web_graph_rag.txt \
    --dump-dir results/agent_plans_phage_qwen_web_rag \
    --output results/agent_plans_phage_qwen_web_rag/summary.csv \
    --concurrency 6
```

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

### agent_plans_phage_qwen_web_enriched_refactor_v2

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web_enriched_refactor_v2/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web_enriched_refactor_v2/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3.jsonl
```

### agent_plans_phage_deepseek_web_enriched_refactor_v2

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek_web_enriched_refactor_v2/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek_web_enriched_refactor_v2/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3.jsonl
```

### agent_plans_phage_qwen_web_rag

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web_rag/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_qwen_web_rag/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.jsonl
```

### agent_plans_phage_deepseek_web_rag

```shell
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek_web_rag/plans \
    --provider qwen \
    --model qwen3-max \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.csv \
    --jsonl-output results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.jsonl
```

```shell
export QWEN_API_KEY=YOUR_QWEN_API_KEY
export QWEN_MODEL=deepseek-v3
python scripts/eval_plan_quality.py \
    --plan-tree-dir /Users/allenygy/Research/GAgent/results/agent_plans_phage_deepseek_web_rag/plans \
    --provider qwen \
    --model deepseek-v3 \
    --batch-size 2 \
    --max-retries 3 \
    --output results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.csv \
    --jsonl-output results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.jsonl
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

Use the current web-enriched result folders for plotting:

- `results/agent_plans_phage_qwen_web_enriched_refactor_v2`
- `results/agent_plans_phage_deepseek_web_enriched_refactor_v2`

Note:

- Legacy `llm` / `agent` / `agent_web` runs currently use timestamped files such as `plan_scores_qwen_10pt_20260202_103446.csv`.
- New `agent_web_rag` runs currently use plain filenames such as `plan_scores_qwen.csv`.
- Because the filenames are mixed, prefer explicit `--files` lists over `--run-dirs` for the publication figures below.

### Overall

```shell
# qwen3-max evaluator
python scripts/plot/plot_plan_score_bars.py \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output results/score_bars_qwen.png
```

```shell
# deepseek-v3 evaluator
python scripts/plot/plot_plan_score_bars.py \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output results/score_bars_deepseekv3.png
```

### Violin plots (per metric)

```shell
python scripts/plot/plot_plan_score_boxplots.py \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_boxplots_qwen
```

```shell
python scripts/plot/plot_plan_score_boxplots.py \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_boxplots_deepseekv3
```

### Radar charts (per model)

```shell
python scripts/plot/plot_plan_score_radars.py \
  --files \
    results/llm_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.csv \
  --labels \
    llm_qwen llm_deepseek agent_qwen agent_deepseek \
    agent_qwen_web agent_deepseek_web \
    agent_qwen_web_rag agent_deepseek_web_rag \
  --output-dir results/score_radars_qwen
```

```shell
python scripts/plot/plot_plan_score_radars.py \
  --files \
    results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.csv \
  --labels \
    llm_qwen llm_deepseek agent_qwen agent_deepseek \
    agent_qwen_web agent_deepseek_web \
    agent_qwen_web_rag agent_deepseek_web_rag \
  --output-dir results/score_radars_deepseekv3
```

These explicit `--files` commands are recommended for the current ablation
because legacy and new runs do not share the same score filename pattern.

### By category

```shell
# qwen3-max evaluator
python scripts/plot/plot_plan_score_bars_by_category.py \
  --category-csv data/phage_plans.csv \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_qwen.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_qwen_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_qwen_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_bars_by_category_qwen
```

```shell
# deepseek-v3 evaluator
python scripts/plot/plot_plan_score_bars_by_category.py \
  --category-csv data/phage_plans.csv \
  --files \
    results/agent_plans_phage_qwen_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek_web_enriched_refactor_v2/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_qwen_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_deepseek_web_rag/eval/plan_scores_deepseekv3.csv \
    results/agent_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/agent_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_qwen/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
    results/llm_plans_phage_deepseek/eval/plan_scores_deepseekv3_10pt_20260202_103446.csv \
  --labels agent_qwen_web agent_deepseek_web agent_qwen_web_rag agent_deepseek_web_rag agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
  --output-dir results/score_bars_by_category_deepseekv3
```
