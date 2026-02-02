/**
 * Watchlist API Service
 * Handles all watchlist-related API calls
 */

import axios from 'axios';
import { useAuthStore } from '@/store/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
 * Get authorization headers
 */
const getAuthHeaders = () => {
  const token = useAuthStore.getState().accessToken;
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };
};

/**
 * List all watchlists for the current user
 */
export const listWatchlists = async (): Promise<Watchlist[]> => {
  const response = await axios.get(
    `${API_BASE_URL}/api/v1/watchlists/`,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Create a new watchlist
 */
export const createWatchlist = async (
  data: CreateWatchlistRequest
): Promise<Watchlist> => {
  const response = await axios.post(
    `${API_BASE_URL}/api/v1/watchlists/`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Get a specific watchlist by ID
 */
export const getWatchlist = async (id: number): Promise<Watchlist> => {
  const response = await axios.get(
    `${API_BASE_URL}/api/v1/watchlists/${id}`,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Update a watchlist
 */
export const updateWatchlist = async (
  id: number,
  data: UpdateWatchlistRequest
): Promise<Watchlist> => {
  const response = await axios.put(
    `${API_BASE_URL}/api/v1/watchlists/${id}`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Delete a watchlist
 */
export const deleteWatchlist = async (id: number): Promise<void> => {
  await axios.delete(
    `${API_BASE_URL}/api/v1/watchlists/${id}`,
    getAuthHeaders()
  );
};

/**
 * Add a symbol to a watchlist
 */
export const addSymbolToWatchlist = async (
  id: number,
  data: AddSymbolRequest
): Promise<Watchlist> => {
  const response = await axios.post(
    `${API_BASE_URL}/api/v1/watchlists/${id}/symbols`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Remove a symbol from a watchlist
 */
export const removeSymbolFromWatchlist = async (
  id: number,
  symbol: string
): Promise<Watchlist> => {
  const response = await axios.delete(
    `${API_BASE_URL}/api/v1/watchlists/${id}/symbols/${symbol}`,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Reorder symbols in a watchlist (drag-drop)
 */
export const reorderWatchlistSymbols = async (
  id: number,
  data: ReorderSymbolsRequest
): Promise<Watchlist> => {
  const response = await axios.put(
    `${API_BASE_URL}/api/v1/watchlists/${id}/symbols/reorder`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Get real-time quotes for all symbols in a watchlist
 */
export const getWatchlistQuotes = async (
  id: number
): Promise<Record<string, QuoteData>> => {
  const response = await axios.get(
    `${API_BASE_URL}/api/v1/watchlists/${id}/quotes`,
    getAuthHeaders()
  );
  return response.data;
};
