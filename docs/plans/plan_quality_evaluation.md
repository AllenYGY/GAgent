# Plan Quality Evaluation Plan

## Goal
Run an automated experiment where each generated plan is fed to an LLM evaluator that returns 6 Likert-style scores:

- **Relevance** – Does content align with the requested topic/task?
- **Completeness** – Are tasks comprehensive and covering the full scope?
- **Accuracy** – Are statements factually sound and scientifically grounded?
- **Clarity** – Is wording easy to understand?
- **Coherence** – Do sections flow logically without contradictions?
- **Scientific Rigor** – Are methods/data considerations rigorous and evidence-based?

Scores are integers 1–5 (1 = very poor, 5 = excellent), similar to survey ratings.

## Experiment Flow
1. Read plan metadata (title, goal, plan tree) from JSON exports (e.g., `direct_plans/plan_<id>.json` or via `PlanRepository`).
2. Build an evaluator prompt in English containing:
   - Title and goal summary.
   - Plan outline (ordered tree).
   - Scoring instructions with definitions for each dimension.
   - Required JSON response schema.
3. Send prompt to the chosen LLM (temperature 0) so it must return JSON with fields:
   ```json
   {
     "plan_id": 42,
     "title": "Hybrid Assembly Benchmarking",
     "scores": {
       "relevance": 4,
       "completeness": 5,
       "accuracy": 4,
       "clarity": 4,
       "coherence": 4,
       "scientific_rigor": 5
     },
     "comments": "Optional short justification."
   }
   ```
4. Validate the response (integers 1–5). Retry on malformed outputs.
5. Persist results to `results/plan_scores.csv` plus raw JSON for auditing.

## Implementation Notes
- Script `scripts/eval_plan_quality.py`:
  - Args: `--plans plan_ids.csv` or `--plan-tree-dir direct_plans`.
  - Optional `--provider`, `--model`, `--api-key`, `--batch-size`, `--output`.
  - Uses existing `LLMService` or direct HTTP client.
  - Includes schema validation; drop any plan that cannot produce valid JSON after N retries.
  - Providers can be configured via `.env` (see `.env.example`) or overridden per run:
    ```bash
    python scripts/eval_plan_quality.py \
        --provider moonshot \
        --model kimi-k2-turbo-preview \
        --plan-tree-dir direct_plans
    ```
  - 默认情况下（未指定 `--provider`）脚本会依次尝试所有已配置且可用的 LLM（除 Perplexity），并为每个 provider 生成独立的输出文件（例如 `plan_scores_qwen.csv`、`plan_scores_glm.csv`）。若仅需要单一 provider，可显式传入 `--provider`，此时 `--api-key/--api-url` 覆盖才会生效。
- Prompt Template:
  - Emphasize: “Return valid JSON only. Use integers 1–5 for each dimension.”
  - Provide short definitions and scoring anchors (1=very poor, 5=excellent).
  - Include instructions to mention if information is missing/uncertain (impacts Completeness/Accuracy).
- Output Format:
  - CSV columns: `plan_id,title,relevance,completeness,accuracy,clarity,coherence,scientific_rigor,comments`.
  - Optional JSONL for raw results.

## Next Steps
1. Implement script + prompt template.
2. Test on 1–2 plans manually; fix parsing edge cases.
3. Run batch on the latest 10 plans; review distributions.
4. Document usage/results in `docs/experiments/plan_quality.md`.

## Visualising Results
- 使用 `scripts/plot_plan_scores.py` 会自动扫描 `results/plan_scores*.csv`，把不同 provider 的输出读取并生成三类热图：
  1. `dimension_provider_heatmap.png` – 各模型总体平均得分
  2. `plan_dimension_heatmap_<provider>.png` – 单个模型下的 plan × dimension 细节（按得分排序截取前 N 个）
  3. `plan_provider_heatmap.png` – plan × provider 的平均得分对比
- 示例命令：
  ```bash
  pip install matplotlib  # 如果还没装
  python scripts/plot_plan_scores.py \
      --scores-dir results \
      --output-dir results/plots \
      --top-plans 20
  ```
- 支持 `--include-provider qwen glm` 仅可视化指定模型，`--plan-order median` 改用不同排名指标等参数，便于生成可用于科研论文的高分辨率图像。
