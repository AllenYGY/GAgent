# Phase 2 Follow-up Plan

## Vision

- Close the remaining Phase 2 gaps by expanding bridge providers, strengthening alignment diagnostics, and enriching CLI artefacts so that every mock scenario (paired → hierarchical) runs with Phase 2 features enabled and produces actionable outputs.
- Establish validation tooling (metrics, plots, tests) that makes bridge/alignment behaviour observable and reproducible from the CLI.

## Scope & Guiding Principles

1. **Provider completeness:** bridge integration should support multiple strategies (MNN, seeded anchors, dictionary mapping) with consistent configuration and diagnostics.
2. **Observable alignment:** every alignment/bridge decision should surface quantitative signals (loss trends, batch variance, cohort edge stats) in CLI outputs.
3. **Robust scheduling:** schedules must cover additional patterns (piecewise, per-step) and persist state so runs are restartable.
4. **Documentation-first:** configs, docs, and tests must demonstrate the Phase 2 feature set across problem types.

## Deliverables

### 1. Bridge provider expansion

- Implement providers in `remadom/bridges`:
  - `SeededBridge` for seed-based matching;
  - `DictionaryBridge` (ridge regression);
  - batched `BridgeProvider.build()` to handle large cohorts.
- Register providers via `build_bridge_provider`.
- Update `BridgeHead` to accept `normalize`, `max_edges`, cohort filters.
- Add unit tests ensuring each provider builds edges for balanced/unbalanced cohorts and respects masks.

### 2. Alignment diagnostics & metrics

- Add `remadom/eval/alignment_metrics.py`:
  - batch variance in latent space,
  - silhouette score,
  - pairwise cross-modality distances,
  - optional trustworthiness.
- Extend `Trainer` to optionally compute diagnostics each epoch (config toggle).
- Emit diagnostics into `metrics.final.json` and per-epoch summaries.
- Provide utilities (e.g., `remadom/eval/plots.py`) for quick scatter/heatmap plots.

### 3. Scheduling & optimisation enhancements

- Expand `remadom/utils/schedules` with:
  - piecewise linear,
  - stepped decay,
  - cosine restarts,
  - step-based schedules (`mode: epoch|step`).
- Allow per-modality gradient clipping; expose config key `optim.grad_clip_modality`.
- Extend checkpoint payload to include:
  - head schedule state (current epsilon/weight),
  - modality schedule progress,
  - bridge configuration snapshot.
- Implement resume support restoring schedule counters.

### 4. CLI & configuration ecosystem

- Provide Phase 2 configs for every mock problem type (paired, unpaired, bridge, mosaic, prediction, hierarchical):
  - enable relevant heads,
  - configure schedules,
  - set bridge parameters where applicable.
- Enhance CLI output:
  - per-head loss trace printouts,
  - optional `--no-plot`, `--force-cpu`, `--metrics-only` flags,
  - logging of bridge/alignment metrics every `log_interval`.
- Generate artefacts under each run dir:
  - `bridge_edges.png`, `bridge_degree_hist.png`,
  - `alignment_metrics.json`,
  - optional latent UMAP/TSNE plots.
- Update `scripts/run_all_examples.sh` to:
  - accept overrides (`--epochs=50`, etc.),
  - produce aggregated comparison table (`runs/mock/summary.txt`).

### 5. Documentation & tests

- Documentation:
  - Expand `docs/bridge_mnn.md` with diagrams, provider comparison table, config snippets.
  - Add `docs/checklists/phase2_validation.md` capturing QA steps (commands, expected outputs).
  - Update `docs/PLAN.md`, `docs/problem_types.md`, `docs/network_architecture.md` to reference Phase 2 features, link to new configs.
  - Add CLI quickstart section describing new flags/artefacts.
- Tests:
  - New integration tests:
    - `test_bridge_training.py`: ensures bridge loss decreases, metrics files exist.
    - `test_alignment_metrics.py`: checks diagnostics output values for mock datasets.
    - `test_cli_phase2_artifacts.py`: runs CLI on bridge config and validates generated files.
  - Update unit tests for schedules and bridge providers.
  - Ensure `pytest tests` passes without needing manual monkeypatch workarounds.

## Milestones

1. **M2-F1 – Bridge provider suite**
   - Seeded & dictionary bridges implemented with tests.
   - BridgeHead exposes extra knobs (filters, normalization).

2. **M2-F2 – Diagnostics & schedules**
   - Alignment metrics recorded in CLI outputs.
   - New schedule types and per-modality clipping integrated.
   - Checkpoints capture schedule state.

3. **M2-F3 – CLI & docs complete**
   - Phase 2 configs run end-to-end (run script green).
   - Documentation refreshed; validation checklist published.
   - Artefact plots (bridge/metrics) generated for mock scenarios.

## Acceptance Criteria

- `./scripts/run_all_examples.sh` succeeds, producing metrics + plots for all mock cases.
- `python -m pytest tests` passes with new bridge/alignment diagnostics tests.
- Config docs clearly explain how to toggle providers and schedules.
- CLI outputs include bridge/alignment summaries and artefacts by default (with opt-outs).

## Open Questions & Risks

- Computational cost of additional diagnostics on large datasets—may need sampling options.
- Scalability of complex bridge providers (dictionary, seeded) for high-dimensional data.
- Visualisation dependencies (matplotlib) might need headless support in CI environments.
- Decision on default schedule behaviour (per-step vs per-epoch) across modalities.
