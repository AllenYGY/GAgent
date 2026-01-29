# Web vs Base 计划质量分析报告（Qwen Judge，10 分制）

## 1) 数据来源

**分析的 runs**

- `results/agent_plans_phage_deepseek_web_v3`  
- `results/agent_plans_phage_qwen_web_v2`  
- `results/agent_plans_phage_deepseek`  
- `results/agent_plans_phage_qwen`  
- `results/llm_plans_phage_deepseek`  
- `results/llm_plans_phage_qwen`

**使用的评估输出**

- `plan_scores_qwen_10pt.csv`  
- `plan_scores_qwen_10pt.jsonl`

---

## 2) 总体均值表（Mean Scores）

以下为 10 分制均值（每项 n=200）。

| Run | n | overall | contextual | accuracy | granularity | reproducibility | rigor |
|---|---:|---:|---:|---:|---:|---:|---:|
| agent_deepseek_web_v3 | 200 | 8.951 | 8.815 | 9.200 | 8.575 | 9.200 | 8.965 |
| agent_deepseek_base | 200 | 9.485 | 9.785 | 9.945 | 8.540 | 9.460 | 9.695 |
| agent_qwen_web_v2 | 200 | 9.140 | 9.430 | 9.635 | 8.765 | 8.955 | 8.915 |
| agent_qwen_base | 200 | 9.499 | 9.810 | 9.945 | 8.585 | 9.455 | 9.700 |
| llm_deepseek | 200 | 6.123 | 3.200 | 8.315 | 8.110 | 4.905 | 6.085 |
| llm_qwen | 200 | 6.668 | 3.885 | 8.850 | 8.380 | 6.005 | 6.220 |

---

## 3) Web vs Base 差值（Agent）

**deepseek_web_v3 – deepseek_base**

- overall: **‑0.534**
- contextual_completeness: **‑0.970**
- accuracy: **‑0.745**
- task_granularity_atomicity: **+0.035**
- reproducibility_parameterization: **‑0.260**
- scientific_rigor: **‑0.730**

**qwen_web_v2 – qwen_base**

- overall: **‑0.359**
- contextual_completeness: **‑0.380**
- accuracy: **‑0.310**
- task_granularity_atomicity: **+0.180**
- reproducibility_parameterization: **‑0.500**
- scientific_rigor: **‑0.785**

**解释**

- Web 版本在**粒度**维度略有提升，但在**上下文、准确性、可复现性、科学严谨性**上普遍下降。

---

## 4) 结构差异（计划规模）

平均节点数：

| Run | 平均节点数 | 最小 | 最大 |
|---|---:|---:|---:|
| agent_deepseek_web_v3 | 105.0 | 6 | 111 |
| agent_qwen_web_v2 | 35.7 | 13 | 65 |
| agent_deepseek_base | 45.4 | 13 | 73 |
| agent_qwen_base | 45.1 | 13 | 73 |

**关键影响**

- `deepseek_web_v3` 计划显著变长，但理由/QC/参数覆盖没有同步增长 → **context 与 rigor 下降**。  
- `qwen_web_v2` 计划反而更短，说明 web context 占用 token 导致分解变浅 → **reproducibility 与 rigor 下降**。

---

## 5) 基于 Rationales 的“原因信号”统计

我们对 `rationales` 进行了关键词统计（缺失理由、缺参数、缺验证、不可行工具等）。
这是一种“问题信号”代理，但能反映评审主要抱怨点。

### deepseek_web_v3 vs deepseek_base

- **Contextual Completeness 问题信号 +27.5%**  
  → 更多“缺乏动机/约束/理由”的描述  
- **Scientific Rigor 问题信号 +25.0%**  
  → 更多“缺指标/缺基线/缺验证”的描述  
- Accuracy/可复现性问题信号上升不明显

### qwen_web_v2 vs qwen_base

- **Scientific Rigor 问题信号 +27.5%**  
  → 缺指标/缺验证最明显  
- **Reproducibility 问题信号 +13.5%**  
  → 参数/IO/版本缺失更常见  
- Contextual/Accuracy 下降较小，但仍负向

---

## 6) 根因假设

1) **Web 信息没有被转写成“可执行计划细节”**  
   Web context 存在，但 instruction 没有落地到参数/IO/QC。

2) **引入了更多“不可验证/可疑工具”**  
   Web 提到的新工具未核查，导致准确性扣分。

3) **计划长度与质量覆盖不匹配**  
   - deepseek_web_v3：计划过长但动机与验证没跟上  
   - qwen_web_v2：计划变短，验证/参数环节被挤掉

---

## 7) 改进建议

**A. 强制“Web → Plan 落地”**

- 从 web context 抽取：
  - 工具 + 版本
  - 参数范围/决策规则
  - 输入输出格式
  - QC 指标/阈值

**B. 增加“工具可用性验证步骤”**

- 如工具无公开来源 → 必须给出替代方案

**C. 控制 web context 长度**

- 4–6 条要点即可，聚焦参数/版本/阈值

**D. 加统一 QC 基线模板**

- 每个计划至少一个 baseline/metric

---

## 8) 下一步建议

1) **使用新版评分 prompt 重新跑评估**  
2) 重新出图并更新本报告  
3) 抽取 Web 版本最低分的 Top‑20 计划做人工复核  
4) 修改 decomposer prompt，强制 web 信息落地为参数/QC

---

## 附录：使用的文件

- `results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.jsonl`
