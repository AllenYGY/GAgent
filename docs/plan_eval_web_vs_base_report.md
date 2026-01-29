# Web vs Base Plan Quality Report (Qwen Judge, 10‑pt)

**Date:** 2026‑01‑27  
**Author:** Codex  
**Scope:** Agent plans with/without web search for Phage tasks, evaluated by Qwen judge using `scripts/eval_plan_quality_10pt.py`.

> **Important caveat:** These numbers are based on the **previous evaluation prompt** (before the latest rubric refinement).  
> For formal comparison, rerun evaluation using the updated prompt.

---

## 1) Data Sources

**Runs analyzed**

- `results/agent_plans_phage_deepseek_web_v3`  
- `results/agent_plans_phage_qwen_web_v2`  
- `results/agent_plans_phage_deepseek`  
- `results/agent_plans_phage_qwen`  
- `results/llm_plans_phage_deepseek`  
- `results/llm_plans_phage_qwen`

**Judge output used**

- `plan_scores_qwen_10pt.csv`  
- `plan_scores_qwen_10pt.jsonl`

---

## 2) Summary Table (Mean Scores)

All values are means over 200 plans (10‑pt scale).

| Run | n | overall | contextual | accuracy | granularity | reproducibility | rigor |
|---|---:|---:|---:|---:|---:|---:|---:|
| agent_deepseek_web_v3 | 200 | 8.951 | 8.815 | 9.200 | 8.575 | 9.200 | 8.965 |
| agent_deepseek_base | 200 | 9.485 | 9.785 | 9.945 | 8.540 | 9.460 | 9.695 |
| agent_qwen_web_v2 | 200 | 9.140 | 9.430 | 9.635 | 8.765 | 8.955 | 8.915 |
| agent_qwen_base | 200 | 9.499 | 9.810 | 9.945 | 8.585 | 9.455 | 9.700 |
| llm_deepseek | 200 | 6.123 | 3.200 | 8.315 | 8.110 | 4.905 | 6.085 |
| llm_qwen | 200 | 6.668 | 3.885 | 8.850 | 8.380 | 6.005 | 6.220 |

---

## 3) Web vs Base Deltas (Agent)

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

**Interpretation**

- Web improves **granularity** slightly (more steps), but lowers **contextual completeness**, **accuracy**, **reproducibility**, and **scientific rigor**.

---

## 4) Structural Differences (Plan Size)

Average node counts (plan trees):

| Run | avg nodes | min | max |
|---|---:|---:|---:|
| agent_deepseek_web_v3 | 105.0 | 6 | 111 |
| agent_qwen_web_v2 | 35.7 | 13 | 65 |
| agent_deepseek_base | 45.4 | 13 | 73 |
| agent_qwen_base | 45.1 | 13 | 73 |

**Key effect**

- `deepseek_web_v3` plans are much longer, but rationale/QC/parameter coverage does not scale with length → **context + rigor drop**.  
- `qwen_web_v2` plans are shorter than base, suggesting **token pressure** or **shallow decomposition** when web context is injected → **reproducibility + rigor drop**.

---

## 5) Reason‑Signal Analysis (from Rationales)

We scanned `rationales` text for issue signals (missing rationale, missing params/IO, missing QC/metrics, infeasible tools, high‑level/vague steps).
This is a lightweight proxy, but it highlights where the judge is consistently complaining.

### deepseek_web_v3 vs deepseek_base (issue‑rate deltas)

- **Contextual completeness issue signals:** **+27.5%**
  - More mentions of missing rationale, missing constraints, weak justification.
- **Scientific rigor issue signals:** **+25.0%**
  - More mentions of missing validation/metrics/baselines.
- **Accuracy issue signals:** slightly worse (tool infeasibility mentions more frequent).

### qwen_web_v2 vs qwen_base (issue‑rate deltas)

- **Scientific rigor issue signals:** **+27.5%**
  - Judge frequently notes missing metrics/baselines/validation.
- **Reproducibility issue signals:** **+13.5%**
  - Missing parameters/IO/versions more common.
- Contextual/accuracy differences are smaller but still negative.

---

## 6) Root‑Cause Hypotheses

1) **Web context is injected but not “translated into plans.”**  
   Web summaries are present in `context_sections`, but task instructions often remain general (no parameter ranges, no IO formats, no QC thresholds).

2) **Hallucinated or unverifiable tools appear more often.**  
   Web search encourages novel tool names, but feasibility checks are weak → accuracy penalties.

3) **Plan length mismatch.**  
   - deepseek_web_v3: plans explode in size → rationale/QC coverage doesn’t scale.  
   - qwen_web_v2: plans shrink → fewer steps covering validation and reproducibility.

---

## 7) Recommendations to Improve Web Plans

**A. Enforce “web‑to‑plan translation”**

- For each web context, require the plan to extract:
  - **tool + version**
  - **parameter range / decision rule**
  - **input/output format**
  - **QC metric or threshold**

**B. Add a “tool validity check” step**

- If a web source suggests a tool, require a quick validation step:
  - Is the tool real? published? actively maintained?
  - If unknown → downgrade or add fallback tool.

**C. Limit web context size**

- Truncate web context to 4–6 bullets, focus on **parameters + thresholds + versions**.

**D. Add a “QC baseline” template**

- For every plan, enforce at least one baseline/metric for validation.

---

## 8) Next Steps (Recommended)

1) **Re‑run evaluation using the updated rubric** (mutually exclusive, multi‑criteria).  
2) Re‑plot results and regenerate this report.  
3) Check top‑20 worst web plans for recurring missing items.  
4) Iterate decomposer prompt to force web details into instructions.

---

## Appendix: Files Used

- `results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.jsonl`
- `results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.csv`  
  `results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.jsonl`

