/**
 * Portfolio Service
 * API endpoints for portfolio and positions
 */

import { apiClient } from './api';
import type { Portfolio, Position } from '@/store/portfolioStore';

export const portfolioService = {
  /**
   * Get current portfolio summary
   */
  getPortfolio: async (): Promise<Portfolio> => {
    const response = await apiClient.get<Portfolio>('/portfolio');
    return response.data;
  },

  /**
   * Get all positions
   */
  getPositions: async (): Promise<Position[]> => {
    const response = await apiClient.get<Position[]>('/portfolio/positions');
    return response.data;
  },

  /**
   * Get position by symbol
   */
  getPosition: async (symbol: string): Promise<Position> => {
    const response = await apiClient.get<Position>(`/portfolio/positions/${symbol}`);
    return response.data;
  },

  /**
   * Get portfolio history
   */
  getPortfolioHistory: async (params?: {
    startDate?: string;
    endDate?: string;
    interval?: '1m' | '5m' | '15m' | '1h' | '1d';
  }): Promise<unknown> => {
    const response = await apiClient.get('/portfolio/history', { params });
    return response.data;
  },
};
