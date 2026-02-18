import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from 'antd';

import { BacktestHistory } from './BacktestHistory';
import type { BacktestSummary } from '../../../types/backtest';

const baseBacktest: BacktestSummary = {
  id: 'bt-1',
  strategy_id: 'strategy-1',
  strategy_name: 'Strategy One',
  start_date: '2025-01-01',
  end_date: '2025-12-31',
  initial_capital: 10000,
  final_equity: 12000,
  total_return: 0.2,
  sharpe_ratio: 1.5,
  max_drawdown: 0.1,
  total_trades: 10,
  status: 'completed',
  created_at: '2026-02-03T00:00:00Z',
  completed_at: '2026-02-03T01:00:00Z',
};

const renderHistory = (backtests: BacktestSummary[]) => {
  return render(
    <App>
      <BacktestHistory
        backtests={backtests}
        total={backtests.length}
        page={1}
        pageSize={10}
        onPageChange={vi.fn()}
        onView={vi.fn()}
        onDelete={vi.fn()}
      />
    </App>
  );
};

describe('BacktestHistory origin tags', () => {
  it('shows origin tags for backtests', () => {
    renderHistory([
      { ...baseBacktest, id: 'bt-optuna', origin: 'optuna' },
      { ...baseBacktest, id: 'bt-backend', origin: 'backend', strategy_name: 'Backend Strategy' },
      { ...baseBacktest, id: 'bt-ui', origin: 'ui', strategy_name: 'UI Strategy' },
    ]);

    expect(screen.getByText('Optuna')).toBeInTheDocument();
    expect(screen.getByText('Backend')).toBeInTheDocument();
    expect(screen.getByText('UI')).toBeInTheDocument();
  });
});
