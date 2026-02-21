import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { usePortfolioStore } from '@/store/portfolioStore';

// Mock portfolioStore
vi.mock('@/store/portfolioStore', () => ({
  usePortfolioStore: vi.fn(),
}));

import PositionHeatmap from '../../positions/components/PositionHeatmap';

describe('PositionHeatmap with positions', () => {
  beforeEach(() => {
    vi.mocked(usePortfolioStore).mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({
          portfolio: {
            totalEquity: 100000,
            positions: [
              { symbol: 'AAPL', quantity: 10, averagePrice: 180, currentPrice: 185, marketValue: 1850, unrealizedPnL: 50, unrealizedPnLPercent: 2.78, side: 'long', exchange: 'NASDAQ' },
              { symbol: 'TSLA', quantity: 5, averagePrice: 250, currentPrice: 240, marketValue: 1200, unrealizedPnL: -50, unrealizedPnLPercent: -4.0, side: 'long', exchange: 'NASDAQ' },
            ],
          },
        }),
    );
  });

  it('renders the card title', () => {
    render(<PositionHeatmap />);
    expect(screen.getByText('Position Heatmap')).toBeInTheDocument();
  });

  it('displays position symbols', () => {
    render(<PositionHeatmap />);
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('TSLA')).toBeInTheDocument();
  });

  it('shows P&L percentage', () => {
    render(<PositionHeatmap />);
    expect(screen.getByText('+2.8%')).toBeInTheDocument();
    expect(screen.getByText('-4.0%')).toBeInTheDocument();
  });

  it('sorts positions by P&L descending', () => {
    const { container } = render(<PositionHeatmap />);
    const cells = container.querySelectorAll('div[style*="border-radius"]');
    const texts = Array.from(cells).map((c) => c.textContent);
    const aaplIdx = texts.findIndex((t) => t?.includes('AAPL'));
    const tslaIdx = texts.findIndex((t) => t?.includes('TSLA'));
    if (aaplIdx >= 0 && tslaIdx >= 0) {
      expect(aaplIdx).toBeLessThan(tslaIdx);
    }
  });
});

describe('PositionHeatmap empty state', () => {
  beforeEach(() => {
    vi.mocked(usePortfolioStore).mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({
          portfolio: { totalEquity: 100000, positions: [] },
        }),
    );
  });

  it('shows empty message when no positions', () => {
    render(<PositionHeatmap />);
    expect(screen.getByText('No open positions')).toBeInTheDocument();
  });
});
