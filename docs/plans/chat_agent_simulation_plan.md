# Simulated User & Judge Agent Mode Plan

## Objectives
- Simulate an end-user interacting with the chat agent using current plan context, producing both natural-language utterances and desired `ACTION` suggestions without executing them.
- Collect the chat agent’s structured actions in response and compare them against the simulated user’s expectations via an independent judge agent.
- Surface a “Simulated User Mode” in the frontend so teams can observe turn-by-turn transcripts, structured actions, and judge verdicts.
- Keep the whole workflow in memory for now (no new database tables), but design the APIs so persistence can be added later.

## Scope
- Backend orchestration and prompt plumbing for the simulated user agent, the judge agent, and the multi-turn controller.
- FastAPI endpoints and CLI helper for starting, advancing, canceling, and inspecting simulation runs.
- Frontend mode toggle, transcript rendering, and control surface within the existing chat/plan UI.
- Default LLM model for both agents: `qwen3-max` (configurable).
- Pairing with the frontend to finalize prompt rubric and UI copy before launch.

Out of scope for this iteration: durable persistence, analytics dashboards, or automated deployment hooks.

## Backend Design

### Module Layout
- `app/services/agents/simulation/models.py`
  - Define `ActionSpec` (reuse fields compatible with `LLMAction`).
  - Define `SimulatedTurn`, `JudgeVerdict`, `SimulationRunState`.
  - Use Pydantic models for validation and serialization.
- `app/services/agents/simulation/prompts.py`
  - Hold template strings (Jinja or f-strings) for simulated user and judge prompts.
  - Accept placeholders for plan outline, improvement goal, prior turns, and rubric guidance.
  - Export defaults referencing `SIM_USER_MODEL`/`SIM_JUDGE_MODEL` environment overrides (default `qwen3-max`).
- `app/services/agents/simulation/sim_user_agent.py`
  - Wrap `PlanSession` (`app/services/plans/plan_session.py:12`) to refresh/bind the active plan and render outlines via `PlanTree.to_outline()` (`app/services/plans/plan_models.py:84`).
  - Call `LLMService.chat()` (`app/services/llm/llm_service.py:46`) with the user prompt template.
  - Parse JSON payload into `ActionSpec` + human-style utterance, handle validation errors gracefully.
- `app/services/agents/simulation/judge_agent.py`
  - Accept both simulated and chat agent actions, call `LLMService.chat()` with judge prompt template.
  - Parse verdict (`alignment: aligned/misaligned/unclear`, `explanation`, optional rubric scores).
- `app/services/agents/simulation/orchestrator.py`
  - Manage turn loop: refresh plan, ask simulated user, call `StructuredChatAgent.get_structured_response()` (`app/routers/chat_routes.py:1688`) to capture chat actions, run judge, append to run state.
  - Respect stop conditions: max turns, judge alignment success, judge rejection, or manual cancellation.
  - Provide hooks to serialize run state for API/UI.
- `app/services/agents/simulation/runtime.py`
  - Maintain in-memory registry of runs (`Dict[str, SimulationRunState]`) with `asyncio.Lock` for thread safety.
  - Provide methods to start, fetch, list, advance (single turn), and cancel runs.

### FastAPI Endpoints
- New router `app/routers/simulation_routes.py` registered under `/simulation`.
  - `POST /simulation/run`: body includes session id, optional plan id/goal/turn budget; returns run id and initial state.
  - `POST /simulation/{run_id}/advance`: triggers next turn (used for manual, step-by-step control).
  - `POST /simulation/{run_id}/cancel`: stops a run.
  - `GET /simulation/{run_id}`: returns run transcript, verdicts, status (`idle`, `running`, `finished`, `cancelled`, `error`).
  - All responses share `SimulatedTurn` schema pieces so frontend can render without extra mapping.
  - Use FastAPI background tasks for multi-turn auto progression to avoid blocking requests.

### Configuration & Logging
- Extend `app/config/__init__.py` to expose `SIM_USER_MODEL`, `SIM_JUDGE_MODEL`, `SIM_DEFAULT_TURNS`, `SIM_MAX_TURNS`.
- Log each LLM prompt/response (with truncation) under a dedicated logger namespace for debugging.
- Add error states to run registry so UI can show friendly error banners.

### Testing
- Unit tests under `test/simulation/` with stubbed `LLMService.chat` responses for:
  - Simulated user action parsing success/failure.
  - Judge verdict mapping.
  - Orchestrator stop conditions and run-state transitions.
  - Registry concurrency (start → fetch → cancel).
- Integration-style async test covering orchestrator + endpoints with a fake `StructuredChatAgent`.

## Frontend Design

### State Management
- New store `web-ui/src/store/simulation.ts` using Zustand (with selector middleware) to track:
  - Mode toggle (`simulatedModeEnabled`), `currentRunId`, transcript data, loading/error states.
  - Controls for starting runs (selected session plan, improvement goal, max turns).
  - Methods to poll backend, advance manually, cancel, and reset state on toggle off.
- Store integrates with existing chat/task stores to fetch plan metadata and session context.

### API Layer
- Extend `web-ui/src/api/chat.ts` (or new `simulation.ts`) with:
  - `startSimulationRun(payload)`
  - `advanceSimulationRun(runId)`
  - `cancelSimulationRun(runId)`
  - `getSimulationStatus(runId)`
  - Share Axios instance/config used by existing chat APIs.

### UI Changes
- Chat Panel (`web-ui/src/components/chat/ChatPanel.tsx`)
  - Add toggle (“Simulated User Mode”) in header or via mode switcher.
  - When enabled, input box becomes read-only; simulated user utterances appear automatically with a distinct avatar/bubble.
  - Display judge verdict badges on each pair of turns.
- New component `SimulatedTranscript` within chat folder:
  - Render timeline of turns: simulated user message + desired ACTION (collapsible JSON), chat agent reply + actions, judge verdict explanation.
  - Provide manual “Step” and “Stop” buttons when auto-run is paused.
- DAG Sidebar (`web-ui/src/components/layout/DAGSidebar.tsx`)
  - Show current plan context, improvement goal input, and run controls so users can manage simulations while inspecting the plan tree.
- Provide toast/notification feedback on run completion, alignment success, mismatches, or errors.
- Ensure strings remain English (per prior UI migration).

### Frontend Collaboration
- Schedule pairing session with frontend engineers to:
  - Iterate on prompt rubric UI (e.g., optional sliders or preset goals).
  - Agree on layout for action JSON and judge verdict display.
  - Validate accessibility and responsive behavior before general release.
- Gate feature behind config flag `ENV.features.simulatedUserMode` for staged rollout.

### Frontend Testing
- Add Jest/RTL tests for store actions and API integration.
- Component tests for `SimulatedTranscript` verifying rendering of verdict states.
- Optional Storybook stories demonstrating aligned vs. misaligned runs.

## Prompt Strategy
- Draft prompts in English with placeholders for:
  - Plan outline (limited depth to avoid prompt bloat).
  - Desired improvement goal (entered by user in UI).
  - Prior simulated user text and judge verdict summary.
  - Action schema reminder referencing `LLM_ACTIONS.md`.
- Provide configuration hooks so future iterations can swap rubrics or import alternative templates without code changes.

## CLI Helper
- `scripts/run_simulation.py` to trigger runs from the command line:
  - Accept session id, plan id, goal, turn limit.
  - Stream transcript to console for quick smoke tests.

## Rollout Steps
1. Implement backend modules, registry, and endpoints; add unit tests.
2. Draft prompts and review with frontend/product in the pairing session.
3. Build frontend store, API integrations, and UI components; add tests.
4. Integrate feature flag, perform manual QA with mock LLM responses, then with real `qwen3-max`.
5. Document usage in README or developer guide, update onboarding docs, and coordinate enablement per environment.

## Open Questions / Follow-ups
- When to promote from in-memory runs to persisted history? (depends on user feedback.)
- Do we need explicit judge scoring categories (precision/recall) beyond alignment text? (collect feedback during pairing.)
- Should simulations auto-create dedicated chat sessions or reuse the current one? (initial assumption: reuse current session plan binding; validate with product.)
- Explore analytics hooks once the workflow stabilizes.

