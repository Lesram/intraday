import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from 'antd';
import { MemoryRouter } from 'react-router-dom';

import { StrategiesList } from './StrategiesList';
import { useStrategiesStore } from '@/store/strategiesStore';
import type { Strategy } from '@/types/strategy';
import { optimizationsService } from '@/services/optimizationsService';

const mockNavigate = vi.fn();

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => {},
  useWebSocketConnection: () => ({ isConnected: true }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/services/optimizationsService', () => ({
  optimizationsService: {
    getRuns: vi.fn(),
    createStrategyFromRun: vi.fn(),
  },
}));

const mockStrategy: Strategy = {
  strategyId: 'strategy-1',
  name: 'Optuna Strategy',
  description: 'Imported from Optuna',
  status: 'stopped',
  strategyType: 'technical_analysis',
  symbols: ['AAPL'],
  parameters: {
    _origin: 'optuna',
  },
  performance: {
    totalTrades: 0,
    winRate: 0,
    totalPnL: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
  },
  createdAt: '2026-02-03T00:00:00Z',
  updatedAt: '2026-02-03T00:00:00Z',
};

const renderWithProviders = (ui: ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <App>{ui}</App>
      </QueryClientProvider>
    </MemoryRouter>
  );
};

describe('StrategiesList optimization import', () => {
  beforeEach(() => {
    useStrategiesStore.getState().setStrategies([mockStrategy]);

    (optimizationsService.getRuns as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 'optuna_best_run',
        name: 'optuna_best_run',
        created_at: '2026-02-03T00:00:00Z',
        source_log: 'test_results/optuna_run.txt',
        symbols: ['AAPL'],
        range: null,
        holdout: null,
        strategy_type: 'technical_analysis',
        parameters: { rsi_buy: 42 },
        origin: 'optuna',
      },
    ]);

    (optimizationsService.createStrategyFromRun as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...mockStrategy,
      strategyId: 'new-strategy',
      name: 'Imported Strategy',
    });

    mockNavigate.mockClear();
  });

  it('creates a strategy from an optimization run', async () => {
    renderWithProviders(<StrategiesList />);

    expect(await screen.findByText('Optuna')).toBeInTheDocument();

    const createButton = await screen.findByRole('button', {
      name: /create strategy from optimization/i,
    });
    expect(createButton).toBeDisabled();

    const selectPlaceholder = screen.getByText(/select an optimization run/i);
    fireEvent.mouseDown(selectPlaceholder);

    const option = await screen.findByText(/optuna_best_run \(optuna\)/i);
    fireEvent.click(option);

    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(optimizationsService.createStrategyFromRun).toHaveBeenCalledWith('optuna_best_run');
      expect(mockNavigate).toHaveBeenCalledWith('/strategies/new-strategy');
    });
  });
});
