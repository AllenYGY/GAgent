# Plan Quality Evaluation Plan

## Goal
Run an automated experiment where each generated plan is fed to an LLM evaluator that returns 5 Likert-style scores:

- **Contextual Completeness** – Are rationale/context fields present to explain why steps are performed?
- **Accuracy** – Are methods, tools, and assumptions technically correct and feasible?
- **Task Granularity & Atomicity** – Are tasks broken into clear, executable actions?
- **Reproducibility & Parameterization** – Are tools/parameters/standards specified (not just named)?
- **Scientific Rigor** – Are evaluation metrics, controls, and validation steps present?

Scores are integers 1–5 (1 = very poor, 5 = excellent), similar to survey ratings.

> 可选：10 分制版本  
> 如果需要更细粒度的评分（1–10），可以使用 `scripts/eval_plan_quality_10pt.py`。
> 该版本使用更细的打分表（见下方“10 分制打分表”）。

## Experiment Flow

1. Read plan metadata (title, goal, plan tree) from JSON exports (e.g., `direct_plans/plan_<id>.json` or via `PlanRepository`).
2. Build an evaluator prompt containing:
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
       "contextual_completeness": 4,
       "accuracy": 4,
       "task_granularity_atomicity": 5,
       "reproducibility_parameterization": 4,
       "scientific_rigor": 5
     },
     "rationales": {
       "contextual_completeness": "Short rationale (<=40 words).",
       "accuracy": "Short rationale (<=40 words).",
       "task_granularity_atomicity": "Short rationale (<=40 words).",
       "reproducibility_parameterization": "Short rationale (<=40 words).",
       "scientific_rigor": "Short rationale (<=40 words)."
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
  - Include instructions to mention if information is missing/uncertain (impacts Contextual Completeness/Accuracy).
- Output Format:
  - CSV columns: `plan_id,title,contextual_completeness,accuracy,task_granularity_atomicity,reproducibility_parameterization,scientific_rigor,rationale_<dimension>,comments`.

## 10 分制打分表（可选）
> 适用于 `scripts/eval_plan_quality_10pt.py`，评分范围 1–10（整数）。

**统一计分方法（每个维度都用）**

| 满足标准数 | 分数区间 |
|---|---|
| 0 项 | 1 分 |
| 1 项 | 2–3 分 |
| 2 项 | 4–5 分 |
| 3 项 | 6–7 分 |
| 4 项 | 8–9 分 |
| ≥5 项 | 10 分 |

> 只有明确证据（引用节点 ID/步骤）时才给区间上限。

**维度标准（互斥）**

| 维度 | 只看 | 标准（满足项越多分越高） |
|---|---|---|
| contextual_completeness | “为什么/动机” | C1 多数关键步骤有明确理由<br>C2 理由对齐计划目标<br>C3 说明关键假设/约束<br>C4 解释步骤顺序/流程合理性<br>C5 提到替代方案或权衡 |
| accuracy | 方法/工具/假设正确性与可行性 | A1 方法/工具匹配任务<br>A2 假设技术上可行<br>A3 步骤无明显矛盾<br>A4 工具能力与用途一致<br>A5 符合领域常规/最佳实践 |
| task_granularity_atomicity | 拆分粒度/可执行性 | G1 多数步骤原子化（单一动作）<br>G2 步骤可直接执行<br>G3 少/无口号式目标步骤<br>G4 依赖关系清晰且最小化<br>G5 步骤间无明显重复 |
| reproducibility_parameterization | 工具/参数/IO/数据来源 | R1 明确工具/方法名称<br>R2 指定输入/输出格式<br>R3 给出关键参数或决策规则<br>R4 标注数据来源/版本<br>R5 计划层面可复现 |
| scientific_rigor | QC/验证/指标/对照/基线 | S1 有 QC/验证步骤<br>S2 定义评估指标<br>S3 有基线或对照方案<br>S4 误差分析/稳健性检查<br>S5 有验收阈值/通过标准 |

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
