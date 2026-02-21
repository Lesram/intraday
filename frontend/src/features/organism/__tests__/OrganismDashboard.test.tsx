import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock all API calls
vi.mock('../organismApi', () => ({
  organismApi: {
    getStatus: vi.fn().mockResolvedValue({
      enabled: true,
      governance: { frozen: false, halted: false },
      regime: { current: 'normal', last_regime: 'normal' },
      live_engine: {
        running: true,
        engine: {
          initialized: true,
          tick_count: 100,
          total_trades: 50,
          brain_generation: 3,
          current_equity: 106800,
          peak_equity: 107000,
          cumulative_pnl: 1500,
          win_rate: 0.55,
          winning_trades: 28,
          losing_trades: 22,
          avg_win: 120,
          avg_loss: -80,
          ml_accuracy: 0.58,
          ml_trained: true,
          universe_size: 30,
          positions_tracked: 15,
        },
        tick_history: [],
      },
    }),
    getRuns: vi.fn().mockResolvedValue({
      enabled: true,
      running: true,
      runs: [
        {
          timestamp: '2025-02-20T14:30:00Z',
          regime: 'normal',
          signals_generated: 3,
          orders_submitted: 1,
          exits_checked: 15,
          duration_s: 1.234,
          errors: [],
          activity: [],
        },
      ],
    }),
    getPolicy: vi.fn().mockResolvedValue({ enabled: true, weights: {} }),
    getBrain: vi.fn().mockResolvedValue({}),
    getAttribution: vi.fn().mockResolvedValue({ attribution: null }),
    getScanner: vi.fn().mockResolvedValue({ enabled: true, scan_count: 5, candidate_count: 3, candidates: [] }),
    getUniverse: vi.fn().mockResolvedValue({ active_symbols: [], universe_size: 30, fitness_table: [], scanner_candidates: [], rotation_count: 0, config: { min_universe: 20, max_universe: 40 } }),
    getAnalytics: vi.fn().mockResolvedValue({
      sector_exposure: [{ sector: 'Technology', count: 5, symbols: ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO'], total_value: 35000 }],
      regime_timeline: [{ regime: 'normal', timestamp: '2025-02-20T10:00:00Z' }],
      confidence_distribution: [
        { bin: '0.0-0.2', correct: 0, total: 0 },
        { bin: '0.2-0.4', correct: 5, total: 12 },
        { bin: '0.4-0.6', correct: 10, total: 18 },
        { bin: '0.6-0.8', correct: 15, total: 20 },
        { bin: '0.8-1.0', correct: 8, total: 10 },
      ],
      regime_kelly_stats: { normal: { wins: 20, losses: 15, total_pnl: 500 } },
      calibration: { counts: [[0, 0], [5, 12], [10, 18], [15, 20], [8, 10]], map: [1.0, 0.83, 1.11, 0.94, 0.89] },
    }),
    action: vi.fn().mockResolvedValue({}),
  },
}));

// Mock WebSocket hook
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn().mockReturnValue({
    isConnected: true,
    subscribe: vi.fn().mockReturnValue(vi.fn()),
  }),
}));

// Mock usePortfolio hook
vi.mock('@/hooks/useData', () => ({
  usePortfolio: vi.fn().mockReturnValue({
    data: null,
    isLoading: false,
    error: null,
  }),
}));

// Mock portfolioStore
vi.mock('@/store/portfolioStore', () => ({
  usePortfolioStore: vi.fn((selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      portfolio: {
        totalEquity: 106800,
        positions: [
          { symbol: 'AAPL', quantity: 10, averagePrice: 180, currentPrice: 185, marketValue: 1850, unrealizedPnL: 50, unrealizedPnLPercent: 2.78, side: 'long', exchange: 'NASDAQ' },
          { symbol: 'MSFT', quantity: 5, averagePrice: 400, currentPrice: 395, marketValue: 1975, unrealizedPnL: -25, unrealizedPnLPercent: -1.25, side: 'long', exchange: 'NASDAQ' },
        ],
      },
      setPortfolio: vi.fn(),
    }),
  ),
}));

import OrganismDashboard from '../OrganismDashboard';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('OrganismDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the dashboard title', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText(/Living Organism/i)).toBeInTheDocument();
    });
  });

  it('displays engine performance stats', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText(/Cumulative P&L/i)).toBeInTheDocument();
      expect(screen.getByText(/Win Rate/i)).toBeInTheDocument();
      expect(screen.getByText(/Total Trades/i)).toBeInTheDocument();
    });
  });

  it('shows regime tag', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Normal')).toBeInTheDocument();
    });
  });

  it('renders the tabs', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Runs History')).toBeInTheDocument();
    });
  });

  it('shows the position heatmap', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Position Heatmap')).toBeInTheDocument();
    });
  });

  it('shows position symbols in heatmap', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('MSFT')).toBeInTheDocument();
    });
  });

  it('shows the P&L waterfall', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('P&L Waterfall')).toBeInTheDocument();
    });
  });

  it('shows the regime timeline', async () => {
    render(<OrganismDashboard />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Regime Timeline')).toBeInTheDocument();
    });
  });
});
