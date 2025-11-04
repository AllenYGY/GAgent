import { BaseApi } from './client';
import type { SimulationRunResponse } from '@/types';

export interface StartSimulationPayload {
  session_id?: string;
  plan_id?: number | null;
  max_turns?: number;
  auto_advance?: boolean;
}

export interface AdvanceSimulationPayload {
  auto_continue?: boolean;
}

class SimulationApi extends BaseApi {
  startRun = async (payload: StartSimulationPayload): Promise<SimulationRunResponse> => {
    return this.post('/simulation/run', payload);
  };

  getRun = async (runId: string): Promise<SimulationRunResponse> => {
    return this.get(`/simulation/run/${runId}`);
  };

  advanceRun = async (runId: string, payload?: AdvanceSimulationPayload): Promise<SimulationRunResponse> => {
    return this.post(`/simulation/run/${runId}/advance`, payload ?? {});
  };

  cancelRun = async (runId: string): Promise<SimulationRunResponse> => {
    return this.post(`/simulation/run/${runId}/cancel`, {});
  };

  downloadTranscript = async (runId: string): Promise<string> => {
    const response = await this.client.request<string>({
      method: 'get',
      url: `/simulation/run/${runId}/export`,
      responseType: 'text',
    });
    return response.data;
  };
}

export const simulationApi = new SimulationApi();
