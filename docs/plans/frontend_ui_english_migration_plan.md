# Frontend English-Only UI Migration Plan

## Objective
Convert every user-facing string in the web UI to English while keeping behaviour, prompts, and tests aligned with the backend’s new language defaults.

## Scope
- `web-ui/src/**` components, stores, utilities, and services.
- Frontend tests, fixtures, and snapshots.
- Developer documentation that references UI copy or instructions.
- Excludes data assets that are intentionally bilingual (e.g., sample datasets); those require explicit opt-in.

## Work Breakdown

1. **Inventory Existing Chinese Copy**
   - Run `rg "[\u4e00-\u9fff]" web-ui/src` and save the output as a checklist.
   - Classify each hit as UI copy, LLM/tool prompt, validation/error message, comment/test fixture, or mock/demo data.
   - Align with stakeholders on any strings that should remain bilingual.

2. **Decide String Management Approach**
   - Choose whether to centralise copy in an English constants module or keep inline literals for now.
   - Document tone guidelines (concise, sentence case, action-first) so translations stay consistent.

3. **Translate Component & Store Copy**
   - Work through high-visibility surfaces first (chat workspace, plan tree, job log panel, settings).
   - Replace Chinese literals with English, including `aria-*`, tooltips, and toast/notification text.
   - Adjust conditional logic that relies on the old Chinese literals (e.g., status comparisons).
   - Update state stores (`web-ui/src/store/**`) and helper utilities (intent analysis prompts, auto summaries) to emit English.

4. **Handle Tests and Fixtures**
   - Use `rg "[\u4e00-\u9fff]" web-ui/test web-ui/src/**/*.test.tsx` to find remaining Chinese in assertions and snapshots.
   - Translate expectations and refresh snapshots (`npm run test -- --updateSnapshot`), manually reviewing diffs.
   - Decide how to treat demo/mock data; translate or annotate intentionally bilingual entries.

5. **Documentation Updates**
   - Revise `docs/frontend_api_usage.md`, onboarding docs, and any README sections that quote UI text.
   - Add guidance on adding new English copy (and why Chinese is no longer allowed) to the developer docs.

6. **Validation & QA**
   - Re-run `rg "[\u4e00-\u9fff]" web-ui/src` to confirm no unintended Chinese remains.
   - Execute `npm run lint`, `npm run type-check`, and `npm run test` to ensure build stability.
   - Smoke-test the UI in a browser, verifying chat flow, plan editing, job logs, tool outputs, and error states render English strings.
   - Coordinate a focused UX/QA pass for readability and tone consistency.

7. **Guardrails Against Regression**
   - Add (or plan) a CI lint/check script that fails when Chinese characters appear in the frontend source.
   - Document the policy in `CONTRIBUTING.md`, instructing contributors to run the locale check before committing.

## Deliverables
- Code changes translating all targeted UI copy to English.
- Updated tests and snapshots that reflect the new strings.
- Documentation updates outlining the English-only policy.
- Optional CI check or script enforcing the absence of Chinese characters in the frontend source.

## Verification Checklist
- [ ] `rg "[\u4e00-\u9fff]" web-ui/src` returns only approved datasets.
- [ ] `npm run lint`, `npm run type-check`, and `npm run test` pass.
- [ ] Manual smoke test confirms English copy in critical flows.
- [ ] QA sign-off on tone and clarity.
