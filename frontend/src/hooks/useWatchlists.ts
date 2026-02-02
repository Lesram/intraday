/**
 * React Query hooks for Watchlist management
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import {
  addSymbolToWatchlist,
  createWatchlist,
  deleteWatchlist,
  getWatchlist,
  getWatchlistQuotes,
  listWatchlists,
  removeSymbolFromWatchlist,
  reorderWatchlistSymbols,
  updateWatchlist,
  type AddSymbolRequest,
  type CreateWatchlistRequest,
  type ReorderSymbolsRequest,
  type UpdateWatchlistRequest,
} from '../services/watchlistApi';

// Query keys
export const watchlistKeys = {
  all: ['watchlists'] as const,
  lists: () => [...watchlistKeys.all, 'list'] as const,
  detail: (id: number) => [...watchlistKeys.all, 'detail', id] as const,
  quotes: (id: number) => [...watchlistKeys.all, 'quotes', id] as const,
};

/**
 * Hook to fetch all watchlists
 */
export const useWatchlists = () => {
  return useQuery({
    queryKey: watchlistKeys.lists(),
    queryFn: listWatchlists,
    staleTime: 30000, // Consider data fresh for 30 seconds
  });
};

/**
 * Hook to fetch a specific watchlist
 */
export const useWatchlist = (id: number) => {
  return useQuery({
    queryKey: watchlistKeys.detail(id),
    queryFn: () => getWatchlist(id),
    enabled: !!id,
  });
};

/**
 * Hook to fetch quotes for a watchlist
 */
export const useWatchlistQuotes = (id: number, enabled = true) => {
  return useQuery({
    queryKey: watchlistKeys.quotes(id),
    queryFn: () => getWatchlistQuotes(id),
    enabled: !!id && enabled,
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    staleTime: 3000, // Consider stale after 3 seconds
  });
};

/**
 * Hook to create a new watchlist
 */
export const useCreateWatchlist = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateWatchlistRequest) => createWatchlist(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      message.success('Watchlist created successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to create watchlist');
    },
  });
};

/**
 * Hook to update a watchlist
 */
export const useUpdateWatchlist = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateWatchlistRequest }) =>
      updateWatchlist(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(variables.id) });
      message.success('Watchlist updated successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to update watchlist');
    },
  });
};

/**
 * Hook to delete a watchlist
 */
export const useDeleteWatchlist = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteWatchlist(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      message.success('Watchlist deleted successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to delete watchlist');
    },
  });
};

/**
 * Hook to add a symbol to a watchlist
 */
export const useAddSymbol = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AddSymbolRequest }) =>
      addSymbolToWatchlist(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      message.success('Symbol added to watchlist');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to add symbol');
    },
  });
};

/**
 * Hook to remove a symbol from a watchlist
 */
export const useRemoveSymbol = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, symbol }: { id: number; symbol: string }) =>
      removeSymbolFromWatchlist(id, symbol),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      message.success('Symbol removed from watchlist');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to remove symbol');
    },
  });
};

/**
 * Hook to reorder symbols in a watchlist (drag-drop)
 */
export const useReorderSymbols = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ReorderSymbolsRequest }) =>
      reorderWatchlistSymbols(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to reorder symbols');
    },
  });
};
