import { create } from 'zustand';
import { message } from 'antd';
import { simulationApi, StartSimulationPayload, AdvanceSimulationPayload } from '@api/simulation';
import { useChatStore } from '@store/chat';
import type {
  SimulationRun,
  SimulationRunStatus,
} from '@/types';

interface SimulationState {
  enabled: boolean;
  isLoading: boolean;
  currentRun: SimulationRun | null;
  error: string | null;
  maxTurns: number;
  autoAdvance: boolean;
  pollingRunId: string | null;
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
  const maybeSyncHistory = async (
    nextRun: SimulationRun,
    previousRun: SimulationRun | null,
    options?: { force?: boolean }
  ) => {
    const sessionId = nextRun?.config?.session_id ?? null;
    if (!sessionId) {
      return;
    }
    const force = options?.force ?? false;
    const previousTurns = previousRun?.turns.length ?? 0;
    const nextTurns = nextRun.turns.length;
    const statusChanged = previousRun ? previousRun.status !== nextRun.status : false;
    if (!force && !statusChanged && previousTurns === nextTurns) {
      return;
    }
    try {
      await useChatStore.getState().loadChatHistory(sessionId);
    } catch (error) {
      console.warn('Failed to synchronize chat history for simulation run:', error);
    }
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
    lastUpdatedAt: null,

    setEnabled: (enabled: boolean) => {
      set((state) => ({
        enabled,
        error: enabled ? state.error : null,
        currentRun: state.currentRun,
        pollingRunId: enabled ? state.pollingRunId : null,
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
        const previousRun = get().currentRun;
        const nextRun = response.run;
        set({
          currentRun: nextRun,
          isLoading: false,
          enabled: true,
          error: null,
          lastUpdatedAt: new Date(),
        });
        message.destroy(ERROR_TOAST_KEY);

        await maybeSyncHistory(nextRun, previousRun);

        if (response.run?.config?.auto_advance) {
          startPolling(nextRun.run_id);
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
        const previousRun = currentRun;
        const nextRun = response.run;
        set({
          currentRun: nextRun,
          isLoading: false,
          error: null,
          lastUpdatedAt: new Date(),
        });
        message.destroy(ERROR_TOAST_KEY);

        await maybeSyncHistory(nextRun, previousRun);

        const shouldAuto = nextRun.config?.auto_advance || Boolean(payload?.auto_continue);
        if (shouldAuto) {
          if (TERMINAL_STATUSES.includes(nextRun.status)) {
            stopPolling();
          } else {
            startPolling(nextRun.run_id);
          }
        } else if (TERMINAL_STATUSES.includes(nextRun.status)) {
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
        const previousRun = get().currentRun;
        set((state) => ({
          currentRun: run,
          isLoading: silent ? state.isLoading : false,
          error: null,
          lastUpdatedAt: new Date(),
        }));
        await maybeSyncHistory(run, previousRun);
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
        const previousRun = currentRun;
        const nextRun = response.run;
        set({
          currentRun: nextRun,
          isLoading: false,
          error: null,
          lastUpdatedAt: new Date(),
        });
        await maybeSyncHistory(nextRun, previousRun, { force: true });
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
        lastUpdatedAt: null,
      });
    },

    startPolling,
    stopPolling,
  };
});
