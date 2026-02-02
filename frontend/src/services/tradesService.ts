/**
 * Trades Service - API client for trade history and analytics
 * Handles HTTP requests to trade endpoints
 */

import { apiClient } from './api';
import type {
  TradeHistoryResponse,
  TradeAnalytics,
  TradeFilters,
} from '@/types/trades';

export const tradesService = {
  /**
   * Fetch trade history with filters and pagination
   */
  getTradeHistory: async (filters: TradeFilters = {}): Promise<TradeHistoryResponse> => {
    const params: Record<string, string | number | undefined> = {};
    
    if (filters.startDate) params.start_date = filters.startDate;
    if (filters.endDate) params.end_date = filters.endDate;
    if (filters.symbol) params.symbol = filters.symbol;
    if (filters.strategyId) params.strategy_id = filters.strategyId;
    if (filters.side) params.side = filters.side;
    if (filters.limit !== undefined) params.limit = filters.limit;
    if (filters.offset !== undefined) params.offset = filters.offset;

    const response = await apiClient.get<TradeHistoryResponse>(
      '/trades/history',
      { params }
    );

    return response.data;
  },

  /**
   * Get trade analytics with filters
   */
  getAnalytics: async (filters: Omit<TradeFilters, 'limit' | 'offset'> = {}): Promise<TradeAnalytics> => {
    const params: Record<string, string | undefined> = {};
    
    if (filters.startDate) params.start_date = filters.startDate;
    if (filters.endDate) params.end_date = filters.endDate;
    if (filters.symbol) params.symbol = filters.symbol;
    if (filters.strategyId) params.strategy_id = filters.strategyId;

    const response = await apiClient.get<TradeAnalytics>(
      '/trades/analytics',
      { params }
    );

    return response.data;
  },

  /**
   * Export trades to CSV
   */
  exportCSV: async (filters: Omit<TradeFilters, 'limit' | 'offset'> = {}): Promise<Blob> => {
    const params: Record<string, string | undefined> = {};
    
    if (filters.startDate) params.start_date = filters.startDate;
    if (filters.endDate) params.end_date = filters.endDate;
    if (filters.symbol) params.symbol = filters.symbol;
    if (filters.strategyId) params.strategy_id = filters.strategyId;
    if (filters.side) params.side = filters.side;

    const response = await apiClient.get(
      '/trades/export/csv',
      {
        params,
        responseType: 'blob',
      }
    );

    return response.data;
  },

  /**
   * Helper function to trigger CSV download
   */
  downloadCSV: async (filters: Omit<TradeFilters, 'limit' | 'offset'> = {}, filename?: string): Promise<void> => {
    const blob = await tradesService.exportCSV(filters);
    
    // Create download link
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || `trades_export_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};
