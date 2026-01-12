import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { SystemStatus } from '@/types';

interface SystemState {
  // System status
  systemStatus: SystemStatus;
  apiConnected: boolean;
  loading: boolean;
  
  // WebSocket connection state
  wsConnected: boolean;
  wsReconnecting: boolean;
  
  // Actions
  setSystemStatus: (status: SystemStatus) => void;
  setApiConnected: (connected: boolean) => void;
  setLoading: (loading: boolean) => void;
  setWsConnected: (connected: boolean) => void;
  setWsReconnecting: (reconnecting: boolean) => void;
  
  // System statistics
  incrementApiCalls: () => void;
  refreshApiCallRate: () => void;
  updateSystemLoad: (load: Partial<SystemStatus['system_load']>) => void;
}

const API_CALL_WINDOW_MS = 60_000;
const apiCallTimestamps: number[] = [];

const pruneApiCalls = (now: number): number => {
  const cutoff = now - API_CALL_WINDOW_MS;
  while (apiCallTimestamps.length > 0 && apiCallTimestamps[0] < cutoff) {
    apiCallTimestamps.shift();
  }
  return apiCallTimestamps.length;
};

export const useSystemStore = create<SystemState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    systemStatus: {
      api_connected: false,
      database_status: 'disconnected',
      active_tasks: 0,
      total_plans: 0,
      system_load: {
        cpu: 0,
        memory: 0,
        api_calls_per_minute: 0,
      },
    },
    apiConnected: false,
    loading: false,
    wsConnected: false,
    wsReconnecting: false,

    // Set system status
    setSystemStatus: (status) => set({ systemStatus: status }),
    
    // Set API connection status
    setApiConnected: (connected) => set((state) => ({ 
      apiConnected: connected,
      systemStatus: { ...state.systemStatus, api_connected: connected }
    })),
    
    // Set loading state
    setLoading: (loading) => set({ loading }),
    
    // Set WebSocket connection status
    setWsConnected: (connected) => set({ wsConnected: connected }),
    
    // Set WebSocket reconnect state
    setWsReconnecting: (reconnecting) => set({ wsReconnecting: reconnecting }),
    
    // Increment API call count
    incrementApiCalls: () => set((state) => ({
      systemStatus: {
        ...state.systemStatus,
        system_load: {
          ...state.systemStatus.system_load,
          api_calls_per_minute: (() => {
            const now = Date.now();
            apiCallTimestamps.push(now);
            return pruneApiCalls(now);
          })(),
        },
      },
    })),

    refreshApiCallRate: () => set((state) => {
      const nextCount = pruneApiCalls(Date.now());
      if (nextCount === state.systemStatus.system_load.api_calls_per_minute) {
        return state;
      }
      return {
        systemStatus: {
          ...state.systemStatus,
          system_load: {
            ...state.systemStatus.system_load,
            api_calls_per_minute: nextCount,
          },
        },
      };
    }),
    
    // Update system load
    updateSystemLoad: (load) => set((state) => ({
      systemStatus: {
        ...state.systemStatus,
        system_load: {
          ...state.systemStatus.system_load,
          ...load,
        },
      },
    })),
  }))
);
