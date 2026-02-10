
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
  - Accept placeholders for plan outline, prior turns, and rubric guidance.
  - Automatically fall back to a default “refine the currently bound plan” goal when none is provided.
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
- `POST /simulation/run`: body includes session id, optional plan id/turn budget (goal auto-inferred); returns run id and initial state.
  - `POST /simulation/{run_id}/advance`: triggers next turn (used for manual, step-by-step control).
  - `POST /simulation/{run_id}/cancel`: stops a run.
  - `GET /simulation/{run_id}`: returns run transcript, verdicts, status (`idle`, `running`, `finished`, `cancelled`, `error`).
  - All responses share `SimulatedTurn` schema pieces so frontend can render without extra mapping.
  - Use FastAPI background tasks for multi-turn auto progression to avoid blocking requests.

### Configuration & Logging
- Extend `app/config/__init__.py` to expose `SIM_USER_MODEL`, `SIM_JUDGE_MODEL`, `SIM_DEFAULT_TURNS`, `SIM_MAX_TURNS`.
- Centralize a constant/default (e.g., `SIM_DEFAULT_GOAL`) so backend prompts consistently describe “refine the current plan” when no explicit goal is provided.
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
  - Controls for starting runs (selected session plan, max turns if needed later; goal defaults internally).
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
  - Display the default goal description (“Improve current plan”) so observers know the simulator’s intent even without user input.
- DAG Sidebar (`web-ui/src/components/layout/DAGSidebar.tsx`)
  - Show current plan context, explain that the simulator automatically aims to improve the bound plan, and expose run controls while inspecting the plan tree.
- Provide toast/notification feedback on run completion, alignment success, mismatches, or errors.
- Ensure strings remain English (per prior UI migration).

### Simulation Run Refresh Reliability (Follow-up)
- **Centralised transcript state**
  - Extend `SimulationState` with a persistent `transcript: ChatMessage[]` array generated from `SimulationRun.turns` via a helper (`buildTranscript`).
  - Ensure `startRun`, `refreshRun`, `advanceRun`, and `cancelRun` all rebuild the transcript so UI always reflects the latest chat.
  - When toggling simulated mode off (`setEnabled(false)`), freeze `currentRun` and `transcript` instead of clearing them, allowing users to review the most recent simulation without rerunning it.
  - Add a selector to retrieve `transcript` as well as a derived flag `hasSimulationHistory` used by the chat panel.
- **Reliable polling loop**
  - Replace the two one-off `setTimeout` calls with a reusable scheduler that polls `/simulation/run/{id}` every 1–2 seconds while status is `idle`/`running`.
  - Implement exponential backoff on errors (initial 1.5s, cap at 10s) and surface failures via `message.error` with a persistent key so users know the UI is retrying.
  - Automatically stop polling once the run hits a terminal state (`finished`, `cancelled`, `error`) or when the user disables simulated mode.
  - Expose `startPolling(runId)` / `stopPolling()` on the store so sidebar buttons and chat panel can control lifecycle.
- **Chat panel integration**
  - `ChatPanel` should always render the transcript when `transcript.length > 0`, even if simulated mode is toggled off later; fall back to regular messages only when there is no simulation history.
  - Show a breathing indicator (“Running simulation…”) whenever polling or `isLoading` is true so users know more turns may arrive.
  - Keep scroll-to-bottom keyed on `transcript.length` to auto-scroll when a new turn is added.
- **Sidebar controls & feedback**
  - Add/retain a visible status badge (`Auto refreshing`) when polling is active.
  - Provide a manual “Refresh simulation status” button that calls `refreshRun(run_id)` for cases where auto polling is disabled or paused.
  - Display a toast when polling stops due to completion or cancellation, including the total number of turns processed.
- **Local persistence & exportability**
  - Continue writing full run state to `data/simulation_runs/<run_id>.json`; add a parallel human-readable `.txt` (or extend JSON with `transcript`) summarising each turn (`Sim User -> Chat Agent -> Judge`).
  - Make the output directory configurable via `SIMULATION_RUN_OUTPUT_DIR` and document it.
  - Optionally provide an API/CLI helper to download the transcript so users can inspect simulations without digging through the filesystem.
- **Testing & validation**
  - Extend backend tests to assert the JSON/TXT dump contains all turns and judge verdicts after auto-run completes.
  - Add frontend unit tests verifying the store builds transcripts correctly and the chat panel renders them when toggled off/on.
  - Update manual QA checklist: run an auto-advance simulation, verify transcript grows to expected turn count, toggle mode off and confirm history remains visible, open the persisted JSON/TXT file and ensure contents match UI.

### Chat Agent Action Execution Review & Transparency
- **Execution contract**
  - Ensure `SimulationOrchestrator` calls `StructuredChatAgent.handle()` so that Chat Agent ACTIONS are actually executed (plan/task mutations, tool calls, etc.).
  - Log each executed step with `kind/name/success` and capture any error messages so the execution path is auditable.
- **Data capture**
  - Persist execution metadata inside `SimulationRun.turns[].chat_agent.actions[]` (fields: `success`, `result_message`, parameters). Reuse the same structure in the JSON/TXT outputs for offline review.
  - When `_persist_run` writes the run to disk, include a human-readable `.txt` summary that lists, per turn, the simulated user message, chat agent reply, executed actions, and judge verdict.
- **Front-end integration**
  - Maintain a transcript array (list of chat messages) inside the simulation store; rebuild it whenever new turns arrive via polling.
  - Sync the transcript into the global chat store so the standard `ChatPanel` renders simulated user & chat agent messages alongside normal conversation history.
  - Highlight executed actions with success/failure tags and execution summaries directly in the chat bubbles for quick inspection.
  - Keep the transcript visible even after toggling simulated mode off, allowing retroactive audit.
- **Polling & feedback**
  - Continue fixed-interval polling with error backoff; while polling is active, show an in-UI indicator (“Running simulation…”) and expose a manual “Refresh” button for forced sync.
- **Validation & QA**
  - Backend: write tests that run a simulated turn containing an executable action (e.g., `plan_operation/create_task`), then assert the PlanRepository reflects the change and `actions[0].success` is true in the recorded turn.
  - Frontend: add unit tests for transcript generation (`buildTranscript`) and snapshot tests verifying the chat message renders action success/error states correctly.
  - Manual QA: for a real plan, run the simulator, confirm chat actions modify the plan, review logs/toast messages, check the generated JSON/TXT files, and confirm the chat UI displays the same information.

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

## Implementation Update (2024-07-16)
- Simulation registry now persists each run to `data/simulation_runs/` as JSON and TXT summaries; datetime payloads and action metadata are serialized safely.
- Chat orchestration captures execution outcomes (`success`, `result_message`) for every action step; the orchestrator test suite verifies both judge alignment and action logging.
- The frontend simulation store rebuilds transcripts on every poll and mirrors them into the main chat store, keeping simulated conversations visible even after toggling the mode.
- `ChatPanel` surfaces a dedicated simulation banner (status, remaining turns, auto-refresh, manual refresh/stop controls) and renders the simulated user/chat agent exchange inline with judge verdicts.
- Added regression tests ensuring runtime persistence tolerates datetime-rich payloads and that orchestrator turns retain execution details.

### Follow-up Fixes (Safari timestamp parsing) – 2024-07-17
- **Backend timestamp normalisation**
  - Emit all `SimulationRunState.created_at/updated_at` and `SimulatedTurn.created_at` values as timezone-aware UTC strings (e.g. `datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')`) to avoid browser parsing discrepancies.
  - Ensure `_json_default` and the TXT summary formatter reuse the same helper so persisted transcripts also contain `Z`-suffixed timestamps.
  - Extend the runtime persistence test to read the generated JSON and assert that every `created_at` parses cleanly via `datetime.fromisoformat(...).tzinfo is not None`.

- **Frontend defensive parsing**
  - Update `buildTranscript` to run timestamps through a utility `safeParseTimestamp(value)` which:
    1. Accepts already-valid `Date` objects.
    2. Adds a trailing `Z` when the backend string lacks timezone info.
    3. Falls back to `new Date()` (current time) and logs a warning if parsing still fails.
  - Adjust `ChatMessage.formatTime` to check `Number.isNaN(date.getTime())`; display `'--:--'` instead of throwing when a timestamp is invalid.
  - Add a small badge or tooltip in the simulation banner showing the timestamp of the last successful poll so users know when data last refreshed.

- **Persistence visibility**
  - Document the storage directory (`data/simulation_runs/`) in the README and expose it via environment variable `SIMULATION_RUN_OUTPUT_DIR`.
  - Provide a quick “Download transcript” action in the sidebar that calls a new `/simulation/run/{id}/export` endpoint (or links directly to the TXT file once the endpoint is wired).

- **Testing & QA**
  - Backend: new unit test covering the timestamp helper and verifying Safari-compatible formatting.
  - Frontend: Jest test for `safeParseTimestamp` with Safari-problematic input (`YYYY-MM-DDTHH:MM:SS.mmmmmm`) plus a component test ensuring `ChatMessage` renders when timestamp parsing fails.
  - Manual QA checklist: run a simulation in Safari/WebKit, confirm chat bubbles appear, inspect persisted JSON/TXT for `Z` suffix, verify the “Download transcript” flow.
- ✅ Implemented: backend timestamps now persist with `Z` suffixes, transcript exports are available via `/simulation/run/{id}/export`, the sidebar offers a “Download transcript” control, and the frontend uses a defensive parser plus graceful time rendering (`--:--`) for invalid timestamps.

## Open Questions / Follow-ups
- When to promote from in-memory runs to persisted history? (depends on user feedback.)
- Do we need explicit judge scoring categories (precision/recall) beyond alignment text? (collect feedback during pairing.)
- Should simulations auto-create dedicated chat sessions or reuse the current one? (initial assumption: reuse current session plan binding; validate with product.)
- Explore analytics hooks once the workflow stabilizes.

## Unified Conversation Persistence (Planned 2024-07-18)

### Objectives
- Store simulated user ↔ chat agent dialogue exactly like a human conversation so that transcripts, exports, websockets, and analytics all reuse the existing chat infrastructure.
- Guarantee every simulated turn executes real actions (`StructuredChatAgent.handle`) and leaves a durable audit trail (chat history, plan changes, run metadata) without parallel storage paths.
- Simplify the frontend: a single chat feed renders both normal and simulated turns, distinguished only by metadata/visual tags.

### Backend Changes
1. **Conversation persistence**
   - Extend `SimulationOrchestrator.run_turn` to call a new helper (`record_simulated_exchange`) that reuses `ChatService.create_message` (the same service used by `/chat/message`).
   - Persist two chat records per turn inside the active session:
     - Simulated user message (`role='user'`, `content=output.message`, `metadata.simulation=true`, `simulation_role='simulated_user'`, `simulation_run_id`, `simulation_turn_index`).
     - Chat agent reply (`role='assistant'`, `content=result.reply`, metadata includes `actions_summary`, `raw_response`, judge verdict when available).
   - Store returned `message_id`s on the `SimulatedTurn` model (`simulated_user_message_id`, `chat_agent_message_id`) for quick lookup when fetching a run.
2. **Execution contract**
   - Continue invoking `StructuredChatAgent.handle` to execute actions immediately. After persistence, refresh the plan session so subsequent turns see updated state.
   - Record action outcomes inside both the run state and assistant message metadata (mirroring existing behaviour for human conversations).
3. **API updates**
   - Update `/simulation/run` & `/simulation/run/{id}` responses to include the stored chat message IDs.
   - Add a convenience endpoint `/simulation/run/{id}/messages` that simply proxies the existing chat history filtered by `simulation_run_id` (optional but useful for debugging).
4. **Websocket / events**
   - Because messages flow through the standard `chat.message` creation pipeline, they automatically broadcast via the existing websocket channels—no extra work required.
5. **Data retention & export**
   - Keep JSON/TXT persistence as-is, but enrich the export with the chat message IDs so analysts can correlate disk dumps with the canonical conversation.
   - No new database tables; everything lives in `chat_messages`. Ensure migration doc mentions no schema impact.

### Frontend Changes
1. **Store simplification**
   - Remove the dedicated `simulationTranscript` array. `useChatStore.messages` becomes the single source of truth; simulated messages remain in history until the user clears the session.
   - Replace `mergeSimulationTranscript` with a lightweight badge decorator that marks `metadata.simulation` messages and optionally groups them by run.
2. **Chat panel UX**
   - Keep the simulation banner (status, remaining turns, last update).
   - Highlight simulated messages using existing `ChatMessage` metadata tags (e.g., add a subtle “Simulated user” / “Simulated assistant” label).
   - Rely on normal chat polling/websocket updates; no extra polling hook needed once the backend persists messages.
3. **Sidebar controls**
   - Start/Stop/Refresh buttons continue to call the simulation API.
   - Add a quick “Scroll to latest simulation” action that jumps the chat feed to the newest message tagged with the active run ID.
4. **Download/export**
   - Keep the transcript download button (TXT/JSON). Because chats are now stored centrally, the standard chat export (if available) already includes the same content.

### Testing & QA
- **Backend**
  - Unit test `record_simulated_exchange` to ensure two chat messages are created with correct metadata and linked to the run.
  - Integration test: start a run with an auto-advance turn, assert plan mutations applied, chat history contains the messages, and run payload exposes their IDs.
- **Frontend**
  - Jest test verifying the chat store correctly merges websocket-delivered simulation messages and that `ChatMessage` renders simulation badges.
  - Cypress/manual: trigger a simulation, watch the chat stream to verify real-time updates, confirm action tags and judge verdicts render.
- **Manual checklist**
  - Run with auto/step modes, verify chat UI mirrors the conversation.
  - Download transcript, cross-check with chat export and persisted JSON/TXT.
  - Clear session history, ensure simulated messages disappear alongside human ones.

### Rollout Considerations
- Feature flag remains (`ENV.features.simulatedUserMode`).
- Document in README how simulated conversations are stored and how to retrieve them (API + filesystem path).
- Coordinate with analytics team—simulation data now flows into any dashboards built atop `chat_messages`.
