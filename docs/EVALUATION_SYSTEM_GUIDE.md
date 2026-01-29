# 计划质量评估系统指南

## 概述

本指南描述当前的**计划质量评估流程**，与 `scripts/eval_plan_quality.py` 的实现保持一致。评估输入为计划树（PlanTree），先渲染为大纲（outline），再由 LLM 返回 1–5 的评分结果与简短说明。

## 5 分制

> 评分范围均为 1–5，整数打分。

- **Contextual Completeness (`contextual_completeness`)**  
  是否提供必要的“为什么要做该步骤”的上下文/理由，影响可解释性与调试效率。

- **Accuracy (`accuracy`)**  
  方法与结论是否科学准确，是否使用合理的工具与流程。

- **Task Granularity & Atomicity (`task_granularity_atomicity`)**  
  任务是否拆分为清晰、可执行的原子动作，而不是宽泛目标。

- **Reproducibility & Parameterization (`reproducibility_parameterization`)**  
  是否明确“如何运行工具”（参数、标准、格式），而不是只说明“用什么工具”。

- **Scientific Rigor (`scientific_rigor`)**  
  是否有严格的方法学与验证流程（基准、对照、误差分析等）。

## 10 分制（可选）

如果需要更细粒度的评分，可使用 `scripts/eval_plan_quality_10pt.py`。
该版本采用 1–10 的整数分，并使用**多标准计分**（维度互斥、避免重复扣分）。

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

## 评估输入：大纲渲染规则

评估器会把计划树渲染成大纲文本后送入 LLM。每个节点包含：

- **[id] name**（任务 ID 与名称）
- **instruction**（去除多余空白后的完整指令内容）
- **deps**（依赖任务 ID）
- **context**（`context_combined` 或 `context_sections`）
- **exec**（执行结果摘要，如有）

当前大纲**不会显示** `status`，也**不会输出** `metadata` 的键名。

## 提示词与返回格式

LLM 必须返回**纯 JSON**，结构如下：

```json
{
  "plan_id": 123,
  "title": "Plan Title",
  "scores": {
    "contextual_completeness": 3,
    "accuracy": 4,
    "task_granularity_atomicity": 3,
    "reproducibility_parameterization": 2,
    "scientific_rigor": 4
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

约束规则：

- 仅接受整数分（1–5）。
- `rationales` 必须包含每个维度的简短理由（<=40 词）。
- `comments` 不超过 80 词；无补充时可为空字符串。
- **不要**输出 Markdown 或代码块。

## 输出文件与提示词存储

- **CSV**：计划分数汇总（默认 `results/plan_scores.csv`），包含 `rationale_<dimension>` 列。
- **JSONL**：原始评估输出（默认 `results/plan_scores.jsonl`）。
- **Prompts**：每个计划的最终提示词会保存到**输出目录**的 `Prompts/` 目录中：
  - 例如输出路径为 `results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv`  
    则提示词保存在 `results/agent_plans_phage_qwen/eval/Prompts/`.

## 常用命令

### 使用导出计划（plan_*.json）

```bash
python scripts/eval_plan_quality.py \
  --plan-tree-dir /path/to/plans \
  --provider qwen \
  --model qwen3-max \
  --batch-size 2 \
  --max-retries 3 \
  --output /path/to/eval/plan_scores_qwen.csv \
  --jsonl-output /path/to/eval/plan_scores_qwen.jsonl
```

### 使用数据库计划 ID

```bash
python scripts/eval_plan_quality.py \
  --plans /path/to/plan_ids.txt \
  --provider qwen \
  --model qwen3-max \
  --output results/plan_scores_qwen.csv \
  --jsonl-output results/plan_scores_qwen.jsonl
```

### 多提供方批量评估（不指定 `--provider`）

脚本会按内置 provider 列表依次运行，并在输出文件名中追加 `_provider` 后缀。

## 常见参数说明

- `--outline-max-nodes`：限制大纲节点数（默认不截断）。
- `--batch-size`：并发评估计划数量。
- `--max-retries`：每个计划的 LLM 重试次数。
- `--temperature`：评分时采样温度（默认 0.0）。
- `--provider` / `--model`：评估使用的 LLM 供应商与模型。

## 注意事项

- `.env` 会在脚本启动时自动加载并覆盖环境变量。
- 如果 JSON 解析失败，脚本会重试，超过 `--max-retries` 后该计划记为失败。
- 计划规模较大时建议设置 `--outline-max-nodes` 控制上下文长度。
