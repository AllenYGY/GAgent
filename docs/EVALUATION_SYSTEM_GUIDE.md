# 计划质量评估系统指南

## 概述

本指南描述当前的**计划质量评估流程**，与 `scripts/eval_plan_quality.py` 的实现保持一致。评估输入为计划树（PlanTree），先渲染为大纲（outline），再由 LLM 返回 1–5 的评分结果与简短说明。

## 评分维度（当前版本）

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
  "comments": "Optional short justification."
}
```

约束规则：

- 仅接受整数分（1–5）。
- `comments` 不超过 80 词；无补充时可为空字符串。
- **不要**输出 Markdown 或代码块。

## 输出文件与提示词存储

- **CSV**：计划分数汇总（默认 `results/plan_scores.csv`）。
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
