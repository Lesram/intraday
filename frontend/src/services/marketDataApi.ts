/**
 * Market Data API Service
 * Service for fetching historical market data
 */

import { apiClient } from './api';
import type { Bar, Timeframe } from '../types/chart.types';

/**
 * Fetch historical bars
 */
export async function fetchHistoricalBars(
  symbol: string,
  timeframe: Timeframe,
  options?: {
    start?: string;
    end?: string;
    limit?: number;
  }
): Promise<Bar[]> {
  try {
    const params = new URLSearchParams({
      symbol: symbol.toUpperCase(),
      timeframe,
      ...(options?.start && { start: options.start }),
      ...(options?.end && { end: options.end }),
      ...(options?.limit && { limit: options.limit.toString() }),
    });

    const response = await apiClient.get(`/market-data/bars?${params}`);
    
    if (response.data && Array.isArray(response.data.bars)) {
      return response.data.bars.map((bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => ({
        time: bar.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
      }));
    }

    return [];
  } catch (error: unknown) {
    // Silently return empty array for 401 errors (user not logged in)
    const axiosError = error as { response?: { status?: number } };
    if (axiosError?.response?.status === 401) {
      return [];
    }
    // Log other errors
    console.error('Failed to fetch historical bars:', error);
    throw error;
  }
}

/**
 * Get market data statistics
 */
export async function getMarketDataStats(): Promise<unknown> {
  try {
    const response = await apiClient.get('/market-data/stats');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch market data stats:', error);
    throw error;
  }
}

/**
 * Health check
 */
export async function checkMarketDataHealth(): Promise<boolean> {
  try {
    const response = await apiClient.get('/market-data/health');
    return response.data.status === 'healthy';
  } catch (_error) {
    return false;
  }
}
