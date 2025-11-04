import { create } from 'zustand';
import { message } from 'antd';
import { simulationApi, StartSimulationPayload, AdvanceSimulationPayload } from '@api/simulation';
import { useChatStore } from '@store/chat';
import type {
  SimulationRun,
  SimulationRunStatus,
  SimulationTurn,
  ChatMessage as ChatMessageType,
} from '@/types';

interface SimulationState {
  enabled: boolean;
  isLoading: boolean;
  currentRun: SimulationRun | null;
  error: string | null;
  maxTurns: number;
  autoAdvance: boolean;
  pollingRunId: string | null;
  transcript: ChatMessageType[];
  lastUpdatedAt: Date | null;

  setEnabled: (enabled: boolean) => void;
  setMaxTurns: (turns: number) => void;
  setAutoAdvance: (auto: boolean) => void;

  startRun: (payload: StartSimulationPayload) => Promise<void>;
  advanceRun: (payload?: AdvanceSimulationPayload) => Promise<void>;
  refreshRun: (runId?: string, options?: { silent?: boolean }) => Promise<SimulationRun | null>;
  cancelRun: () => Promise<void>;
  clearRun: () => void;

  startPolling: (runId: string) => void;
  stopPolling: () => void;
}

const clampTurns = (value: number) => Math.min(Math.max(Math.round(value), 1), 20);

export const useSimulationStore = create<SimulationState>((set, get) => {
  const POLL_INTERVAL = 1500;
  const POLL_MAX_DELAY = 10000;
  const ERROR_TOAST_KEY = 'simulation-refresh-error';
  const TERMINAL_STATUSES: SimulationRunStatus[] = ['finished', 'cancelled', 'error'];
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  const safeParseTimestamp = (value: unknown): Date => {
    if (value instanceof Date) {
      const copy = new Date(value.getTime());
      return Number.isNaN(copy.getTime()) ? new Date() : copy;
    }
    if (typeof value === 'number') {
      const dateFromNumber = new Date(value);
      if (!Number.isNaN(dateFromNumber.getTime())) {
        return dateFromNumber;
      }
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed.length > 0) {
        const parsed = new Date(trimmed);
        if (!Number.isNaN(parsed.getTime())) {
          return parsed;
        }
        const isoNoTzPattern = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/;
        if (!trimmed.endsWith('Z') && isoNoTzPattern.test(trimmed)) {
          const normalized = `${trimmed}Z`;
          const parsedWithZ = new Date(normalized);
          if (!Number.isNaN(parsedWithZ.getTime())) {
            return parsedWithZ;
          }
        }
      }
    }
    console.warn('Simulation store: unable to parse timestamp, using current time.', value);
    return new Date();
  };
  const syncTranscript = (runId: string | undefined, transcript: ChatMessageType[]) => {
    try {
      const chatStore = useChatStore.getState();
      chatStore.setSimulationTranscript(transcript);
      chatStore.mergeSimulationTranscript(runId ?? null, transcript);
    } catch (error) {
      console.warn('Failed to sync simulation transcript to chat store:', error);
    }
    return transcript;
  };

  const stopPollingInternal = () => {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  };

  const schedulePoll = (runId: string, delay = POLL_INTERVAL) => {
    stopPollingInternal();
    pollTimer = setTimeout(async () => {
      try {
        const run = await get().refreshRun(runId, { silent: true });
        if (!run) {
          stopPollingInternal();
          set({ pollingRunId: null });
          return;
        }
        message.destroy(ERROR_TOAST_KEY);
        if (TERMINAL_STATUSES.includes(run.status)) {
          stopPollingInternal();
          set({ pollingRunId: null });
          return;
        }
        schedulePoll(run.run_id, POLL_INTERVAL);
      } catch (error: any) {
        console.error('Simulation polling failed:', error);
        const msg = error?.message || 'Failed to refresh simulation status. Retrying…';
        message.error({ content: msg, key: ERROR_TOAST_KEY });
        schedulePoll(runId, Math.min(delay * 2, POLL_MAX_DELAY));
      }
    }, delay);
  };

  const stopPolling = () => {
    stopPollingInternal();
    message.destroy(ERROR_TOAST_KEY);
    set({ pollingRunId: null });
  };

  const startPolling = (runId: string) => {
    if (!runId) return;
    stopPollingInternal();
    message.destroy(ERROR_TOAST_KEY);
    set({ pollingRunId: runId });
    schedulePoll(runId);
  };

  return {
    enabled: false,
    isLoading: false,
    currentRun: null,
    error: null,
    maxTurns: 5,
    autoAdvance: true,
    pollingRunId: null,
    transcript: [],
    lastUpdatedAt: null,

    setEnabled: (enabled: boolean) => {
      set((state) => ({
        enabled,
        error: enabled ? state.error : null,
        currentRun: state.currentRun,
        pollingRunId: enabled ? state.pollingRunId : null,
        transcript: state.transcript,
      }));
      if (!enabled) {
        stopPolling();
      }
    },

    setMaxTurns: (turns: number) => set({ maxTurns: clampTurns(turns) }),
    setAutoAdvance: (auto: boolean) => set({ autoAdvance: auto }),

    startRun: async (payload) => {
      set({ isLoading: true, error: null });
      try {
        const { maxTurns, autoAdvance } = get();
        const mergedPayload: StartSimulationPayload = {
          max_turns: maxTurns,
          auto_advance: autoAdvance,
          ...payload,
        };
        stopPolling();
        const response = await simulationApi.startRun(mergedPayload);
        set({
          currentRun: response.run,
          isLoading: false,
          enabled: true,
          error: null,
          transcript: syncTranscript(response.run.run_id, []),
          lastUpdatedAt: new Date(),
        });
        message.destroy(ERROR_TOAST_KEY);

        if (response.run?.config?.auto_advance) {
          startPolling(response.run.run_id);
        }
      } catch (error: any) {
        const msg = error?.message || 'Failed to start simulation run.';
        set({ error: msg, isLoading: false });
        throw error;
      }
    },

    advanceRun: async (payload) => {
      const { currentRun } = get();
      if (!currentRun) {
        return;
      }
      set({ isLoading: true, error: null });
      try {
        const response = await simulationApi.advanceRun(currentRun.run_id, payload);
        set({
          currentRun: response.run,
          isLoading: false,
          error: null,
          transcript: syncTranscript(
            response.run.run_id,
            buildTranscript(response.run.turns, response.run.run_id, safeParseTimestamp),
          ),
          lastUpdatedAt: new Date(),
        });
        message.destroy(ERROR_TOAST_KEY);

        const shouldAuto = response.run.config?.auto_advance || Boolean(payload?.auto_continue);
        if (shouldAuto) {
          if (TERMINAL_STATUSES.includes(response.run.status)) {
            stopPolling();
          } else {
            startPolling(response.run.run_id);
          }
        } else if (TERMINAL_STATUSES.includes(response.run.status)) {
          stopPolling();
        }
      } catch (error: any) {
        const msg = error?.message || 'Failed to advance simulation run.';
        set({ error: msg, isLoading: false });
        throw error;
      }
    },

    refreshRun: async (runId, options) => {
      const activeRun = runId ?? get().currentRun?.run_id;
      if (!activeRun) {
        return null;
      }
      const silent = options?.silent ?? false;
      if (!silent) {
        set({ isLoading: true, error: null });
      }
      try {
        const response = await simulationApi.getRun(activeRun);
        const run = response.run;
        set((state) => ({
          currentRun: run,
          isLoading: silent ? state.isLoading : false,
          error: null,
          transcript: syncTranscript(
            run.run_id,
            buildTranscript(run.turns, run.run_id, safeParseTimestamp),
          ),
          lastUpdatedAt: new Date(),
        }));
        if (TERMINAL_STATUSES.includes(run.status)) {
          stopPollingInternal();
          message.destroy(ERROR_TOAST_KEY);
          set({ pollingRunId: null });
        } else if (!silent) {
          message.destroy(ERROR_TOAST_KEY);
        }
        return run;
      } catch (error: any) {
        const msg = error?.message || 'Failed to fetch simulation status.';
        if (!silent) {
          set({ error: msg, isLoading: false });
          message.error({ content: msg, key: ERROR_TOAST_KEY });
        }
        throw error;
      }
    },

    cancelRun: async () => {
      const { currentRun } = get();
      if (!currentRun) {
        return;
      }
      set({ isLoading: true, error: null });
      try {
        const response = await simulationApi.cancelRun(currentRun.run_id);
        set({
          currentRun: response.run,
          isLoading: false,
          error: null,
          transcript: syncTranscript(
            response.run.run_id,
            buildTranscript(response.run.turns, response.run.run_id, safeParseTimestamp),
          ),
          lastUpdatedAt: new Date(),
        });
        stopPolling();
      } catch (error: any) {
        const msg = error?.message || 'Failed to cancel simulation run.';
        set({ error: msg, isLoading: false });
        throw error;
      }
    },

    clearRun: () => {
      stopPolling();
      set({
        currentRun: null,
        error: null,
        isLoading: false,
        transcript: syncTranscript(undefined, []),
        lastUpdatedAt: null,
      });
    },

    startPolling,
    stopPolling,
  };
});

function buildTranscript(
  turns: SimulationTurn[] | undefined,
  runId: string | undefined,
  parseTimestamp: (value: unknown) => Date,
): ChatMessageType[] {
  if (!turns || !turns.length) {
    return [];
  }
  const items: ChatMessageType[] = [];
  turns.forEach((turn) => {
    const timestamp = parseTimestamp(turn.created_at);
    items.push({
      id: `sim-user-${runId ?? "run"}-${turn.index}`,
      type: 'user',
      content: turn.simulated_user.message,
      timestamp,
      metadata: {
        simulation: true,
        simulation_run_id: runId,
        simulation_turn_index: turn.index,
        simulation_role: 'simulated_user',
        simulation_goal: turn.goal,
        simulation_desired_action: turn.simulated_user.desired_action,
      },
    });
    items.push({
      id: `sim-assistant-${runId ?? "run"}-${turn.index}`,
      type: 'assistant',
      content: turn.chat_agent.reply,
      timestamp,
      metadata: {
        simulation: true,
        simulation_run_id: runId,
        simulation_turn_index: turn.index,
        simulation_role: 'chat_agent',
        simulation_goal: turn.goal,
        simulation_actions: turn.chat_agent.actions,
        simulation_judge: turn.judge,
      },
    });
  });
  return items;
}
