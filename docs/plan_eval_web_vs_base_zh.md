# Web vs 非 Web 计划评估对比（Qwen，10 分制）

数据来源：

- Web（DeepSeek agent）：`results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.jsonl`
- 非 Web（DeepSeek agent）：`results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.jsonl`
- Web（Qwen agent）：`results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.jsonl`
- 非 Web（Qwen agent）：`results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.jsonl`

## 概览

- 评估计划数：每个 run **200**
- 使用 Qwen 评审，10 分制

| Run | 总分均值 | 总分中位数 |
|---|---:|---:|
| agent_deepseek_web_v3 | 8.951 | 9.200 |
| agent_deepseek_base | 9.485 | 9.600 |
| agent_qwen_web_v2 | 9.140 | 9.200 |
| agent_qwen_base | 9.499 | 9.600 |

## 各维度均值

**DeepSeek agent（web vs base）**

| 维度 | Web均值 | 非Web均值 | 差值（web‑非web） |
|---|---:|---:|---:|
| contextual_completeness | 8.815 | 9.785 | -0.970 |
| accuracy | 9.200 | 9.945 | -0.745 |
| task_granularity_atomicity | 8.575 | 8.540 | +0.035 |
| reproducibility_parameterization | 9.200 | 9.460 | -0.260 |
| scientific_rigor | 8.965 | 9.695 | -0.730 |

**Qwen agent（web vs base）**

| 维度 | Web均值 | 非Web均值 | 差值（web‑非web） |
|---|---:|---:|---:|
| contextual_completeness | 9.430 | 9.810 | -0.380 |
| accuracy | 9.635 | 9.945 | -0.310 |
| task_granularity_atomicity | 8.765 | 8.585 | +0.180 |
| reproducibility_parameterization | 8.955 | 9.455 | -0.500 |
| scientific_rigor | 8.915 | 9.700 | -0.785 |

## 按维度分析（含案例）

> 配对方式：按**标题**匹配（重复标题按 plan_id 顺序配对）。

### contextual_completeness

**DeepSeek web vs base：** 均值 8.815 vs 9.785（Δ ‑0.970），web<base 共 161/200。  
**Qwen web vs base：** 均值 9.430 vs 9.810（Δ ‑0.380），web<base 共 92/200。

**典型原因：** web 计划更常**缺少权衡/替代方案**或顺序理由不足。

**案例**
- Plan 85 *Prophage Integration Site Homology Mapping*  
  web：理由中指出权衡/顺序解释不足；base 对假设与顺序更充分。
- Plan 193 *Antibiotic‑Phage Synergy Prediction…*  
  web：替代方案讨论不足；base 对范围/顺序/假设更清晰。
- Plan 42 *CRISPR Spacer Matching in Phage Genomes*  
  web：权衡讨论不足；base 上下文覆盖更完整。

### accuracy

**DeepSeek web vs base：** 均值 9.200 vs 9.945（Δ ‑0.745），web<base 共 60/200。  
**Qwen web vs base：** 均值 9.635 vs 9.945（Δ ‑0.310），web<base 共 35/200。

**典型原因：** web 计划更容易引入**不可验证/误用工具**。

**案例**
- Plan 111 *Host Range Inference from Abortive Infection Gene Presence*  
  web：PHISTO 可用性存疑；base 方法与假设一致。
- Plan 36 *Phage‑Borne AMG Cataloging*  
  web：EnVhogDB / GECKO 3.0 可验证性不足；base 工具链合理可行。
- Plan 113 *Host Prediction via Nucleoid‑Associated Protein Binding Sites*  
  web：前提依据不足；base 将方法作为可行假设处理。

### task_granularity_atomicity

**DeepSeek web vs base：** 均值 8.575 vs 8.540（Δ +0.035），web>base 59 / web<base 67。  
**Qwen web vs base：** 均值 8.765 vs 8.585（Δ +0.180），web>base 70 / web<base 56。

**典型原因：** web 计划细节更多，但仍存在**重复**或**高层步骤残留**。

**案例**
- Plan 74 *Phage DNA Modification System Cataloging*  
  web：重复步骤 + 高层目标残留；base 更原子化。
- Plan 181 *Evolutionary Trajectory Simulation…*  
  web：步骤重叠 + 高层目标残留。
- Plan 132 *Time‑Series Phage Community Dynamics Modeling*  
  web：存在高层步骤、可执行细节不足；base 更细。

### reproducibility_parameterization

**DeepSeek web vs base：** 均值 9.200 vs 9.460（Δ ‑0.260），web<base 共 71/200。  
**Qwen web vs base：** 均值 8.955 vs 9.455（Δ ‑0.500），web<base 共 102/200。

**典型原因：** web 计划**工具有但参数/IO/版本不足**。

**案例**
- Plan 133 *Phage Tail Fiber Gene Clustering…*  
  web：缺关键阈值/格式；base 参数与格式明确。
- Plan 117 *Host Prediction Using Bacterial Surface Glycan Profiles*  
  web：缺 docking/ML 参数；base 版本/格式/参数完整。
- Plan 165 *ML‑Based Phage Efficacy Ranking*  
  web：缺超参数（如 k‑mer size）；base 有明确设置。

### scientific_rigor

**DeepSeek web vs base：** 均值 8.965 vs 9.695（Δ ‑0.730），web<base 共 97/200。  
**Qwen web vs base：** 均值 8.915 vs 9.700（Δ ‑0.785），web<base 共 102/200。

**典型原因：** web 计划常缺**指标、基线、QC 阈值、误差分析**。

**案例**
- Plan 31 *Phage Defense System Evasion Mechanism Prediction*  
  web：缺指标/基线/阈值；base 有 QC + 基线 + 验收标准。
- Plan 117 *Host Prediction Using Bacterial Surface Glycan Profiles*  
  web：验证流程缺失；base 指标/基线明确。
- Plan 165 *ML‑Based Phage Efficacy Ranking*  
  web：缺明确 QC/指标；base 有 AUC/PR 与基线。

## 结构差异（计划规模）

平均节点数：

| Run | 平均节点数 |
|---|---:|
| agent_deepseek_web_v3 | 105.0 |
| agent_deepseek_base | 45.4 |
| agent_qwen_web_v2 | 35.7 |
| agent_qwen_base | 45.1 |

## 理由信号统计（启发式）

对 rationales 做关键词统计（缺失/不清晰/未给出等），作为评审主要抱怨点的代理信号。

| 维度 | DeepSeek web‑base 差值 | Qwen web‑base 差值 |
|---|---:|---:|
| contextual_completeness | **+27.5%** | +2.0% |
| reproducibility_parameterization | -5.5% | **+13.5%** |
| scientific_rigor | **+25.0%** | **+27.5%** |

## 具体理由与案例（Web 端）

以下案例来自 web 端 JSONL 的评审理由，用于说明“为什么会降分”。  
是代表性模式，不是穷尽清单。

**contextual_completeness（缺少权衡/动机不足）**
- Plan 193 “Antibiotic‑Phage Synergy Prediction…”：理由明确，但**替代方案/权衡讨论较少**。
- Plan 10 “Comparative Genomics of Marine Phage Clusters”：整体有动机，但**替代方案讨论不足**。

**accuracy（工具不可验证/可能幻觉）**
- Plan 111 “Host Range Inference from Abortive Infection Gene Presence”：**PHISTO 工具疑似不可用/不支持**。
- Plan 131 “Machine Learning‑Based Phage Lysis Gene Prediction”：**“DeepMineLys” 工具疑似幻觉/不可验证**。
- Plan 166 “Resistance Evolution Forecasting in Phage Therapy”：**MSDeepAMR / GeneBac 可验证性不足**。

**task_granularity_atomicity（冗余或仍有高层步骤）**
- Plan 109 “Host Prediction via Secretion System Compatibility”：**数据获取步骤重复**。
- Plan 181 “Evolutionary Trajectory Simulation for Cocktail Durability”：**步骤重叠 + 存在高层目标残留**。

**reproducibility_parameterization（参数/版本缺失）**
- Plan 112 “tRNA Mimicry‑Based Host Targeting Prediction”：**工具有名但参数细节不足**。
- Plan 116 “Phage Lifestyle‑Informed Host Range Modeling”：**运行参数未完全给出**。
- Plan 117 “Host Prediction Using Bacterial Surface Glycan Profiles”：**关键参数缺失（如对接/模型设置）**。

**scientific_rigor（QC/指标/基线不足）**
- Plan 99 “Host Range Inference from Defense System Evasion”：**无明确 QC 指标或基线**。
- Plan 104 “Operon Structure Compatibility Scoring”：**验证指标/阈值未定义**。
- Plan 117 “Host Prediction Using Bacterial Surface Glycan Profiles”：**缺少明确验证流程**。

## 结论

- Web 计划整体评分更低，主要体现在 **contextual completeness** 与 **scientific rigor** 的下降。
- DeepSeek‑web 计划更长（节点数高），但动机/验证覆盖不足 → **context + rigor 下滑**。
- Qwen‑web 计划更短（可能被 web context 占用 token），导致 **参数化与验证步骤减少**。

更详细的报告见：`docs/plan_eval_web_vs_base_report_zh.md`。
