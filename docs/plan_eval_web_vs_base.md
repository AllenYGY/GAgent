# Web vs Base Plan Evaluation (Qwen, 10‑pt)

Data sources:

- Web (DeepSeek agent): `results/agent_plans_phage_deepseek_web_v3/eval/plan_scores_qwen_10pt.jsonl`
- Base (DeepSeek agent): `results/agent_plans_phage_deepseek/eval/plan_scores_qwen_10pt.jsonl`
- Web (Qwen agent): `results/agent_plans_phage_qwen_web_v2/eval/plan_scores_qwen_10pt.jsonl`
- Base (Qwen agent): `results/agent_plans_phage_qwen/eval/plan_scores_qwen_10pt.jsonl`

## Summary

- Plans evaluated: **200** in each run
- 10‑point scale, Qwen judge

| Run | overall mean | overall median |
|---|---:|---:|
| agent_deepseek_web_v3 | 8.951 | 9.200 |
| agent_deepseek_base | 9.485 | 9.600 |
| agent_qwen_web_v2 | 9.140 | 9.200 |
| agent_qwen_base | 9.499 | 9.600 |

## Mean Scores by Dimension

**DeepSeek agent (web vs base)**

| Dimension | Web mean | Base mean | Delta (web‑base) |
|---|---:|---:|---:|
| contextual_completeness | 8.815 | 9.785 | -0.970 |
| accuracy | 9.200 | 9.945 | -0.745 |
| task_granularity_atomicity | 8.575 | 8.540 | +0.035 |
| reproducibility_parameterization | 9.200 | 9.460 | -0.260 |
| scientific_rigor | 8.965 | 9.695 | -0.730 |

**Qwen agent (web vs base)**

| Dimension | Web mean | Base mean | Delta (web‑base) |
|---|---:|---:|---:|
| contextual_completeness | 9.430 | 9.810 | -0.380 |
| accuracy | 9.635 | 9.945 | -0.310 |
| task_granularity_atomicity | 8.765 | 8.585 | +0.180 |
| reproducibility_parameterization | 8.955 | 9.455 | -0.500 |
| scientific_rigor | 8.915 | 9.700 | -0.785 |

## Per‑Dimension Analysis (with examples)

> Pairing method: plans are matched by **title** (for duplicate titles, pairs are aligned by plan_id order).

### contextual_completeness

**DeepSeek web vs base:** mean 8.815 vs 9.785 (Δ ‑0.970), web<base in 161/200 pairs.  
**Qwen web vs base:** mean 9.430 vs 9.810 (Δ ‑0.380), web<base in 92/200 pairs.

**Typical reason:** web plans often **omit tradeoffs/alternatives** and provide weaker sequencing justification.

**Examples (plan‑level reasons from web rationales)**
- Plan 85 *Prophage Integration Site Homology Mapping*  
  web: rationale notes missing tradeoffs/sequence justification; base explains assumptions and ordering.
- Plan 193 *Antibiotic‑Phage Synergy Prediction…*  
  web: rationale says alternatives are rarely discussed; base justifies scope and sequencing.
- Plan 42 *CRISPR Spacer Matching in Phage Genomes*  
  web: rationale flags limited tradeoff discussion; base has fuller context coverage.

### accuracy

**DeepSeek web vs base:** mean 9.200 vs 9.945 (Δ ‑0.745), web<base in 60/200 pairs.  
**Qwen web vs base:** mean 9.635 vs 9.945 (Δ ‑0.310), web<base in 35/200 pairs.

**Typical reason:** web plans introduce **unverifiable or misapplied tools**.

**Examples (plan‑level reasons from web rationales)**
- Plan 111 *Host Range Inference from Abortive Infection Gene Presence*  
  web: rationale flags PHISTO as unsupported; base uses standard tools with consistent assumptions.
- Plan 36 *Phage‑Borne Auxiliary Metabolic Gene Cataloging*  
  web: rationale questions EnVhogDB/GECKO 3.0 availability; base uses verifiable toolchain.
- Plan 113 *Host Prediction via Nucleoid‑Associated Protein Binding Sites*  
  web: rationale notes premise lacks support; base treats method as plausible with matching tools.

### task_granularity_atomicity

**DeepSeek web vs base:** mean 8.575 vs 8.540 (Δ +0.035), mixed (web>base 59 / web<base 67).  
**Qwen web vs base:** mean 8.765 vs 8.585 (Δ +0.180), web>base 70 / web<base 56.

**Typical reason:** web plans are sometimes more detailed, but still contain **redundancy** or **high‑level remnants**.

**Examples (plan‑level reasons from web rationales)**
- Plan 74 *Phage DNA Modification System Cataloging*  
  web: rationale notes duplicated access paths and high‑level remnants; base is more atomic.
- Plan 181 *Evolutionary Trajectory Simulation…*  
  web: rationale cites overlap plus broad goals remaining.
- Plan 132 *Time‑Series Phage Community Dynamics Modeling*  
  web: rationale notes broad steps without executable detail; base is more atomic.

### reproducibility_parameterization

**DeepSeek web vs base:** mean 9.200 vs 9.460 (Δ ‑0.260), web<base in 71/200 pairs.  
**Qwen web vs base:** mean 8.955 vs 9.455 (Δ ‑0.500), web<base in 102/200 pairs.

**Typical reason:** web plans **name tools** but miss **parameters / IO formats / versions**.

**Examples (plan‑level reasons from web rationales)**
- Plan 133 *Phage Tail Fiber Gene Clustering…*  
  web: rationale flags missing thresholds (e.g., clustering / pLDDT); base specifies parameters and formats.
- Plan 117 *Host Prediction Using Bacterial Surface Glycan Profiles*  
  web: rationale notes absent docking/ML parameters; base includes versions/formats.
- Plan 165 *ML‑Based Phage Efficacy Ranking*  
  web: rationale cites missing hyperparameters (e.g., k‑mer size); base specifies them.

### scientific_rigor

**DeepSeek web vs base:** mean 8.965 vs 9.695 (Δ ‑0.730), web<base in 97/200 pairs.  
**Qwen web vs base:** mean 8.915 vs 9.700 (Δ ‑0.785), web<base in 102/200 pairs.

**Typical reason:** web plans lack **explicit metrics, baselines, QC thresholds, error analysis**.

**Examples (plan‑level reasons from web rationales)**
- Plan 31 *Phage Defense System Evasion Mechanism Prediction*  
  web: rationale notes missing metrics/baselines; base defines QC and acceptance criteria.
- Plan 117 *Host Prediction Using Bacterial Surface Glycan Profiles*  
  web: rationale flags missing validation protocol; base includes metrics and baselines.
- Plan 165 *ML‑Based Phage Efficacy Ranking*  
  web: rationale notes missing explicit QC/metrics; base includes AUC/PR and baselines.

## Structural Differences (Plan Size)

Average node counts:

| Run | avg nodes |
|---|---:|
| agent_deepseek_web_v3 | 105.0 |
| agent_deepseek_base | 45.4 |
| agent_qwen_web_v2 | 35.7 |
| agent_qwen_base | 45.1 |

## Rationale‑Signal Analysis (Heuristic)

We scanned rationales for “missing/unclear” phrases as a proxy for judge complaints.
This is heuristic, but highlights the dominant negative signals.

| Dimension | DeepSeek web‑base Δ | Qwen web‑base Δ |
|---|---:|---:|
| contextual_completeness | **+27.5%** | +2.0% |
| reproducibility_parameterization | -5.5% | **+13.5%** |
| scientific_rigor | **+25.0%** | **+27.5%** |

## Concrete Examples from Rationales (Web runs)

Below are concrete plan‑level examples extracted from the rationale JSONL (web runs),
showing *why* scores drop for specific dimensions. These are representative patterns,
not exhaustive.

**contextual_completeness (missing tradeoffs / weak “why”)**
- Plan 193 “Antibiotic‑Phage Synergy Prediction…”: rationale notes that most steps have rationale, but **tradeoffs/alternatives are rarely discussed**.
- Plan 10 “Comparative Genomics of Marine Phage Clusters”: strong rationale overall, but **limited discussion of alternatives**.

**accuracy (hallucinated / unverifiable tools)**
- Plan 111 “Host Range Inference from Abortive Infection Gene Presence”: notes **PHISTO appears incorrect or unsupported**.
- Plan 131 “Machine Learning‑Based Phage Lysis Gene Prediction”: **“DeepMineLys” appears hallucinated / unverifiable**.
- Plan 166 “Resistance Evolution Forecasting in Phage Therapy”: **MSDeepAMR / GeneBac appear unverifiable**, reducing feasibility.

**task_granularity_atomicity (redundancy / high‑level steps)**
- Plan 109 “Host Prediction via Secretion System Compatibility”: **redundant data retrieval steps**.
- Plan 181 “Evolutionary Trajectory Simulation for Cocktail Durability”: **overlap between steps + some high‑level remnants**.

**reproducibility_parameterization (parameters/versions missing)**
- Plan 112 “tRNA Mimicry‑Based Host Targeting Prediction”: **tools named but parameter details missing** (e.g., default settings).
- Plan 116 “Phage Lifestyle‑Informed Host Range Modeling”: **some runtime parameters missing**.
- Plan 117 “Host Prediction Using Bacterial Surface Glycan Profiles”: **key parameters absent** (e.g., docking or ML settings).

**scientific_rigor (QC/metrics/baselines missing)**
- Plan 99 “Host Range Inference from Defense System Evasion”: **no explicit QC metrics or baselines**.
- Plan 104 “Operon Structure Compatibility Scoring”: **validation metrics and thresholds not defined**.
- Plan 117 “Host Prediction Using Bacterial Surface Glycan Profiles”: **no explicit validation protocol**.

## Takeaways

- Web search improves **granularity** slightly, but lowers **contextual completeness** and **scientific rigor** across both models.
- For DeepSeek‑web, the main issue is **missing rationale/justification** in longer plans.
- For Qwen‑web, the main issues are **missing parameters/IO** and **missing validation metrics**.

If needed, see the extended report:
`docs/plan_eval_web_vs_base_report.md`.
