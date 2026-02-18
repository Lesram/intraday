/**
 * Watchlist API Service
 * Handles all watchlist-related API calls using the centralized apiClient
 */

import { apiClient } from './api';

export interface WatchlistSymbol {
  id: number;
  watchlist_id: number;
  symbol: string;
  order: number;
  added_at: string;
}

export interface Watchlist {
  id: number;
  user_id: number;
  name: string;
  description?: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  symbols: WatchlistSymbol[];
}

export interface CreateWatchlistRequest {
  name: string;
  description?: string;
  is_default?: boolean;
}

export interface UpdateWatchlistRequest {
  name?: string;
  description?: string;
  is_default?: boolean;
}

export interface AddSymbolRequest {
  symbol: string;
}

export interface ReorderSymbolsRequest {
  symbol_orders: { symbol: string; order: number }[];
}

export interface QuoteData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume?: number;
  timestamp: string;
}

/**
 * List all watchlists for the current user
 */
export const listWatchlists = async (): Promise<Watchlist[]> => {
  const response = await apiClient.get<Watchlist[]>('/watchlists/');
  return response.data;
};

/**
 * Create a new watchlist
 */
export const createWatchlist = async (
  data: CreateWatchlistRequest
): Promise<Watchlist> => {
  const response = await apiClient.post<Watchlist>('/watchlists/', data);
  return response.data;
};

/**
 * Get a specific watchlist by ID
 */
export const getWatchlist = async (id: number): Promise<Watchlist> => {
  const response = await apiClient.get<Watchlist>(`/watchlists/${id}`);
  return response.data;
};

/**
 * Update a watchlist
 */
export const updateWatchlist = async (
  id: number,
  data: UpdateWatchlistRequest
): Promise<Watchlist> => {
  const response = await apiClient.put<Watchlist>(`/watchlists/${id}`, data);
  return response.data;
};

/**
 * Delete a watchlist
 */
export const deleteWatchlist = async (id: number): Promise<void> => {
  await apiClient.delete(`/watchlists/${id}`);
};

/**
 * Add a symbol to a watchlist
 */
export const addSymbolToWatchlist = async (
  id: number,
  data: AddSymbolRequest
): Promise<Watchlist> => {
  const response = await apiClient.post<Watchlist>(`/watchlists/${id}/symbols`, data);
  return response.data;
};

/**
 * Remove a symbol from a watchlist
 */
export const removeSymbolFromWatchlist = async (
  id: number,
  symbol: string
): Promise<Watchlist> => {
  const response = await apiClient.delete<Watchlist>(`/watchlists/${id}/symbols/${symbol}`);
  return response.data;
};

/**
 * Reorder symbols in a watchlist (drag-drop)
 */
export const reorderWatchlistSymbols = async (
  id: number,
  data: ReorderSymbolsRequest
): Promise<Watchlist> => {
  const response = await apiClient.put<Watchlist>(`/watchlists/${id}/symbols/reorder`, data);
  return response.data;
};

/**
 * Get real-time quotes for all symbols in a watchlist
 */
export const getWatchlistQuotes = async (
  id: number
): Promise<Record<string, QuoteData>> => {
  const response = await apiClient.get<Record<string, QuoteData>>(`/watchlists/${id}/quotes`);
  return response.data;
};
