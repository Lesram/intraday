import { apiClient } from './api';
import type { OptimizationRun, OptimizationStrategyCreate } from '@/types/optimization';
import type { Strategy } from '@/types/strategy';

export const optimizationsService = {
  getRuns: async (): Promise<OptimizationRun[]> => {
    const response = await apiClient.get<OptimizationRun[]>('/optimizations');
    return response.data;
  },

  getRun: async (runId: string): Promise<OptimizationRun> => {
    const response = await apiClient.get<OptimizationRun>(`/optimizations/${runId}`);
    return response.data;
  },

  createStrategyFromRun: async (
    runId: string,
    payload: OptimizationStrategyCreate = {}
  ): Promise<Strategy> => {
    const response = await apiClient.post<Strategy>(
      `/optimizations/${runId}/strategy`,
      payload
    );
    return response.data;
  },
};
