/**
 * usePositions Hook
 * React Query hook for fetching and managing positions data
 * Integrates with WebSocket for real-time updates
 */

import { useQuery } from '@tanstack/react-query';
import { usePortfolioStore, type Position } from '@/store/portfolioStore';
import { portfolioService } from '@/services/portfolioService';

/**
 * Hook for fetching positions with automatic real-time updates
 * - Fetches from API via React Query
 * - Syncs with Zustand store
 * - WebSocket updates automatically trigger re-renders
 * - Automatic refetch every 30 seconds
 */
export const usePositions = () => {
  const positions = usePortfolioStore((state) => state.positions);
  const setPositions = usePortfolioStore((state) => state.setPositions);

  const query = useQuery<Position[]>({
    queryKey: ['positions'],
    queryFn: async () => {
      const data = await portfolioService.getPositions();
      // Sync API data with Zustand store
      setPositions(data);
      return data;
    },
    // Refetch every 30 seconds for stale data
    refetchInterval: 30000,
    // Consider data stale after 5 seconds
    staleTime: 5000,
  });

  // Use store data (which includes WebSocket updates) as the source of truth
  return {
    ...query,
    data: positions, // Use store data instead of query data for real-time updates
  };
};

/**
 * Hook for fetching a single position by symbol
 */
export const usePosition = (symbol: string) => {
  const positions = usePortfolioStore((state) => state.positions);
  const position = positions.find((p) => p.symbol === symbol);

  return {
    data: position,
    isLoading: false,
    error: null,
  };
};

/**
 * Hook for computed position statistics
 */
export const usePositionStatistics = () => {
  const positions = usePortfolioStore((state) => state.positions);

  const stats = {
    totalPositions: positions.length,
    openPositions: positions.filter((p) => p.quantity !== 0).length,
    totalMarketValue: positions.reduce((sum, p) => sum + p.marketValue, 0),
    totalUnrealizedPl: positions.reduce((sum, p) => sum + p.unrealizedPnL, 0),
    totalCostBasis: positions.reduce((sum, p) => sum + (p.averagePrice * p.quantity), 0),
    winningPositions: positions.filter((p) => p.unrealizedPnL > 0).length,
    losingPositions: positions.filter((p) => p.unrealizedPnL < 0).length,
    winRate:
      positions.length > 0
        ? (positions.filter((p) => p.unrealizedPnL > 0).length / positions.length) * 100
        : 0,
  };

  return stats;
};
