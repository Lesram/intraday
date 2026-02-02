/**
 * React Query hooks for backtesting operations
 * 
 * Provides hooks for running backtests, fetching history and results,
 * and managing backtest lifecycle.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { apiClient } from '@/services/api';
import type { 
  BacktestRequest, 
  BacktestResult, 
  BacktestSummary 
} from '../../../types/backtest';

// Query keys
export const backtestKeys = {
  all: ['backtests'] as const,
  lists: () => [...backtestKeys.all, 'list'] as const,
  list: (filters: string) => [...backtestKeys.lists(), { filters }] as const,
  details: () => [...backtestKeys.all, 'detail'] as const,
  detail: (id: string) => [...backtestKeys.details(), id] as const,
};

/**
 * Hook to run a backtest
 */
export function useRunBacktest() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: async (params: { strategyId: string; request: BacktestRequest }) => {
      const { strategyId, request } = params;
      const response = await apiClient.post<BacktestResult>(
        `/backtests/strategies/${strategyId}/backtest`,
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      message.success(`Backtest started successfully: ${data.strategy_name}`);
      // Invalidate history to show the new backtest
      queryClient.invalidateQueries({ queryKey: backtestKeys.lists() });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const errorMsg = axiosError.response?.data?.detail || 'Failed to start backtest';
      message.error(errorMsg);
      console.error('Backtest error:', error);
    },
  });
}

/**
 * Hook to fetch backtest history with pagination
 */
interface BacktestHistoryParams {
  page?: number;
  pageSize?: number;
  strategyId?: string;
}

interface BacktestHistoryResponse {
  items: BacktestSummary[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export function useBacktestHistory(params: BacktestHistoryParams = {}) {
  const { page = 1, pageSize = 20, strategyId } = params;

  return useQuery({
    queryKey: backtestKeys.list(`page=${page}&size=${pageSize}&strategy=${strategyId || ''}`),
    queryFn: async () => {
      const queryParams = new URLSearchParams({
        skip: String((page - 1) * pageSize),
        limit: String(pageSize),
      });
      
      if (strategyId) {
        queryParams.append('strategy_id', strategyId);
      }

      const response = await apiClient.get<BacktestHistoryResponse>(
        `/backtests/history?${queryParams}`
      );
      return response.data;
    },
    placeholderData: (previousData) => previousData, // Keep previous data while loading
  });
}

/**
 * Hook to fetch a specific backtest result
 */
export function useBacktestResult(backtestId: string | null) {
  return useQuery({
    queryKey: backtestKeys.detail(backtestId || ''),
    queryFn: async () => {
      if (!backtestId) return null;
      const response = await apiClient.get<BacktestResult>(
        `/backtests/${backtestId}`
      );
      return response.data;
    },
    enabled: !!backtestId, // Only run query if backtestId is provided
    refetchInterval: (query) => {
      // Auto-refetch every 2 seconds if status is pending or running
      const data = query.state.data;
      if (data && (data.status === 'pending' || data.status === 'running')) {
        return 2000;
      }
      return false;
    },
  });
}

/**
 * Hook to delete a backtest
 */
export function useDeleteBacktest() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: async (backtestId: string) => {
      await apiClient.delete(`/backtests/${backtestId}`);
      return backtestId;
    },
    onSuccess: (backtestId) => {
      message.success('Backtest deleted successfully');
      // Invalidate both history and the specific detail
      queryClient.invalidateQueries({ queryKey: backtestKeys.lists() });
      queryClient.removeQueries({ queryKey: backtestKeys.detail(backtestId) });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const errorMsg = axiosError.response?.data?.detail || 'Failed to delete backtest';
      message.error(errorMsg);
      console.error('Delete backtest error:', error);
    },
  });
}

/**
 * Hook to export backtest results
 */
export function useExportBacktest() {
  const { message } = App.useApp();
  
  return useMutation({
    mutationFn: async (params: { backtestId: string; format: 'csv' | 'json' }) => {
      const { backtestId, format } = params;
      const response = await apiClient.get(
        `/backtests/${backtestId}/export?format=${format}`,
        {
          responseType: format === 'csv' ? 'blob' : 'json',
        }
      );

      // Create download
      const blob = format === 'csv' 
        ? new Blob([response.data], { type: 'text/csv' })
        : new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `backtest_${backtestId}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      return { backtestId, format };
    },
    onSuccess: (data) => {
      message.success(`Backtest exported as ${data.format.toUpperCase()}`);
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      const errorMsg = err.response?.data?.detail || 'Failed to export backtest';
      message.error(errorMsg);
      console.error('Export backtest error:', error);
    },
  });
}
