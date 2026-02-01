You are an expert reviewer. Evaluate plan quality only (not execution). For each criterion,
  output a 0/1/2 value with a short reason and evidence. Do not infer missing details; if not
  stated, score 0. If evidence is weak/implicit, score 1 (not 2).

  Plan metadata:
  - Plan ID: {PLAN_ID}
  - Title: {TITLE}
  - Goal: {GOAL}

  Plan outline:
  {OUTLINE}

  Scoring dimensions:
  - Contextual Completeness (`contextual_completeness`): The availability of rationale or
  context fields that explain why a step is being performed. Missing context reduces
  interpretability and should lower the score.
  - Accuracy (`accuracy`): Methods, tools, and assumptions are technically correct, current,
  and feasible for the stated constraints. No contradictions or hallucinated facts.
  - Task Granularity & Atomicity (`task_granularity_atomicity`): Measures whether tasks are
  broken down into single, unambiguous executable actions rather than broad goals. Higher
  granularity reduces ambiguity for execution.
  - Reproducibility & Execution (`reproducibility_parameterization`): The extent to which the plan specifies how to run tools (parameters standards, formats), not just which tools to use.
  - Scientific Rigor (`scientific_rigor`): Includes evaluation metrics, controls/baselines, data-quality checks, and reproducibility steps (e. g., documentation, validation, error analysis).
  - Innovation & Feasibility


  Each criterion is scored 0/1/2 only.

  SCORING METHOD (applied by the evaluator script):
  - Each criterion value is 0/1/2.
    0 = not stated / missing
    1 = partially implied or vague
    2 = explicitly stated with concrete evidence
  - Dimension score = sum of its five criteria (0–10).
  - If the sum is 0, the script reports it as 1 to keep scores in 1–10.

  DIMENSION RUBRICS (mutually exclusive by design; only score what the dimension covers):

  contextual_completeness (ONLY rationale/why; ignore tools/parameters/QC):
  - C1: At least ~60% of major steps include an explicit 'why' (rationale).
  - C2: Rationale explicitly links steps to the plan goal.
  - C3: Key assumptions/constraints are explicitly stated.
  - C4: Ordering/sequence is explicitly justified.
  - C5: Alternatives or tradeoffs are explicitly mentioned.

  accuracy (ONLY correctness/feasibility of methods/tools/assumptions; ignore missing
  parameters/QC):
  - A1: Methods/tools fit the task and are explicitly justified.
  - A2: Assumptions are explicitly stated and technically plausible.
  - A3: No clear contradictions between steps.
  - A4: Tool capabilities match stated usage (no impossible steps).
  - A5: Explicitly cites a standard/best practice.

  task_granularity_atomicity (ONLY decomposition quality; ignore rationale/parameters/QC):
  - G1: Most steps specify one clear output artifact (file/table/model/report). A step may
  include 1–2 tightly coupled actions only if they lead to the same output.
  - G2: Steps are minimal executable units; they do not combine distinct phases or multiple
  outputs/tools in a single step.
  - G3: Almost no high-level goal-only steps remain.
  - G4: Dependencies are explicit and minimal.
  - G5: No clear redundancy or overlap across steps.
  - IMPORTANT: Do NOT give 2 just because a step starts with a verb.
  - A step may include up to 2 tightly coupled micro-actions ONLY if it produces one explicit
  output and uses a single method/tool context.
  - If a step combines distinct phases (e.g., preprocess + train + evaluate), multiple
  outputs, or multiple tool contexts, it is NOT atomic.
  - Abstract outcomes like “insights/analysis/understanding” do NOT count as concrete
  outputs.
  - For G1/G2=2, the reason must cite a concrete step showing a single explicit output
  artifact.

  reproducibility_parameterization (ONLY tools/parameters/IO/data sources; ignore validation
  rigor):
  - R1: Tool name plus version/implementation is given.
  - R2: Inputs & outputs specify files/formats explicitly.
  - R3: Key parameters/thresholds/decision rules are explicit.
  - R4: Data sources or versions are explicitly identified.
  - R5: Plan-level reproducibility (could implement the workflow).

  scientific_rigor (ONLY QC/validation/metrics/baselines/controls):
  - S1: Explicit QC/validation steps included.
  - S2: Explicit evaluation metrics defined (e.g., F1, N50).
  - S3: Explicit baselines or controls specified.
  - S4: Explicit error/robustness analysis included.
  - S5: Explicit acceptance thresholds/go-no-go criteria defined.

  EVIDENCE REQUIREMENTS:
  - For each criterion, provide a short reason (<=30 words).
  - Cite 1–2 concrete pieces of evidence (node IDs or steps).
  - If information is missing, explicitly name what is missing.

  Return valid JSON ONLY using this schema:
  {
    "plan_id": {PLAN_ID},
    "title": "{TITLE}",
    "criteria": {
      "contextual_completeness": {
        "C1": { "value": 0, "reason": "Short reason (<=30 words)." },
        "C2": { "value": 0, "reason": "Short reason (<=30 words)." },
        "C3": { "value": 0, "reason": "Short reason (<=30 words)." },
        "C4": { "value": 0, "reason": "Short reason (<=30 words)." },
        "C5": { "value": 0, "reason": "Short reason (<=30 words)." }
      },
      "accuracy": {
        "A1": { "value": 0, "reason": "Short reason (<=30 words)." },
        "A2": { "value": 0, "reason": "Short reason (<=30 words)." },
        "A3": { "value": 0, "reason": "Short reason (<=30 words)." },
        "A4": { "value": 0, "reason": "Short reason (<=30 words)." },
        "A5": { "value": 0, "reason": "Short reason (<=30 words)." }
      },
      "task_granularity_atomicity": {
        "G1": { "value": 0, "reason": "Short reason (<=30 words)." },
        "G2": { "value": 0, "reason": "Short reason (<=30 words)." },
        "G3": { "value": 0, "reason": "Short reason (<=30 words)." },
        "G4": { "value": 0, "reason": "Short reason (<=30 words)." },
        "G5": { "value": 0, "reason": "Short reason (<=30 words)." }
      },
      "reproducibility_parameterization": {
        "R1": { "value": 0, "reason": "Short reason (<=30 words)." },
        "R2": { "value": 0, "reason": "Short reason (<=30 words)." },
        "R3": { "value": 0, "reason": "Short reason (<=30 words)." },
        "R4": { "value": 0, "reason": "Short reason (<=30 words)." },
        "R5": { "value": 0, "reason": "Short reason (<=30 words)." }
      },
      "scientific_rigor": {
        "S1": { "value": 0, "reason": "Short reason (<=30 words)." },
        "S2": { "value": 0, "reason": "Short reason (<=30 words)." },
        "S3": { "value": 0, "reason": "Short reason (<=30 words)." },
        "S4": { "value": 0, "reason": "Short reason (<=30 words)." },
        "S5": { "value": 0, "reason": "Short reason (<=30 words)." }
      }
    },
    "comments": ""
  }

  Rules:
  - Utilize the most rigorous standard audit program.
  - Do not include markdown fences or commentary outside the JSON.
  - Every criterion must include {value, reason}.
  - value must be 0, 1, or 2.
  - reason must be a short string (<=30 words).
  - Keep comments under 80 words; use an empty string if there is nothing to add.