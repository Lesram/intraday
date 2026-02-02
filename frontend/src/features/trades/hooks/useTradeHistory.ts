/**
 * Trade History & Analytics React Query Hooks
 * Hooks for fetching and caching trade data
 */

import { useQuery } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import { tradesService } from '@/services/tradesService';
import type {
  TradeHistoryResponse,
  TradeAnalytics,
  TradeFilters,
  Trade,
} from '@/types/trades';

/**
 * Hook to fetch trade history with filters and pagination
 */
export const useTradeHistory = (
  filters: TradeFilters = {},
  enabled: boolean = true
): UseQueryResult<TradeHistoryResponse> => {
  return useQuery({
    queryKey: ['trades', 'history', filters],
    queryFn: () => tradesService.getTradeHistory(filters),
    enabled,
    staleTime: 5000, // Reduced from 30s - data is fresh for 5 seconds
    refetchOnWindowFocus: true, // Re-fetch when user returns to tab
  });
};

/**
 * Hook to fetch trade analytics
 */
export const useTradeAnalytics = (
  filters: Omit<TradeFilters, 'limit' | 'offset'> = {},
  enabled: boolean = true
): UseQueryResult<TradeAnalytics> => {
  return useQuery({
    queryKey: ['trades', 'analytics', filters],
    queryFn: () => tradesService.getAnalytics(filters),
    enabled,
    staleTime: 10000, // Reduced from 60s - recalculate more frequently
    refetchOnWindowFocus: true, // Re-fetch when user returns to tab
  });
};

/**
 * Hook to get a single trade by ID from cached data
 */
export const useTrade = (_orderId: string): Trade | undefined => {
  // This would need access to cached trade history data
  // For now, return undefined - can be implemented with queryClient
  return undefined;
};

/**
 * Helper hook to check if there are any trades
 */
export const useHasTrades = (): boolean => {
  const { data } = useTradeHistory({ limit: 1 }, true);
  return (data?.total ?? 0) > 0;
};
