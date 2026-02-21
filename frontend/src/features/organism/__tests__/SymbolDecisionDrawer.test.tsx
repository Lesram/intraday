import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SymbolDecisionDrawer from '../components/SymbolDecisionDrawer';
import type { AlphaFactorScore, BreakoutFactorScore, ExitProximity, KellySizingStage } from '../organismApi';

const mockAlpha: AlphaFactorScore = {
  symbol: 'AAPL',
  composite_score: 0.42,
  factors: { ml: 0.6, breakout: 0.3, institutional: 0.5, momentum: 0.5, momentum_quality: 0.4, vol_price_div: 0.3, regime: 0.7 },
  weights: {},
  direction: 1,
  threshold: 0.15,
  distance_to_threshold: 0.27,
  passed_threshold: true,
  symbol_fitness: 0.65,
  fitness_gate: 0.35,
  passed_fitness: true,
};

const mockBreakout: BreakoutFactorScore = {
  symbol: 'AAPL',
  composite_score: 0.35,
  factors: { squeeze: 0.5, volume: 0.4, contraction: 0.3, rs: 0.6, pivot: 0.2, flow: 0.1 },
  weights: {},
  direction: 1,
  squeeze_fired: false,
  volume_ratio: 1.5,
  threshold: 0.20,
  distance_to_threshold: 0.15,
  passed_threshold: true,
};

describe('SymbolDecisionDrawer', () => {
  it('renders drawer with symbol name', () => {
    render(
      <SymbolDecisionDrawer
        open={true}
        symbol="AAPL"
        alpha={mockAlpha}
        breakout={mockBreakout}
        exit={null}
        kelly={null}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('Decision Detail: AAPL')).toBeInTheDocument();
  });

  it('shows symbol info', () => {
    render(
      <SymbolDecisionDrawer
        open={true}
        symbol="AAPL"
        alpha={mockAlpha}
        breakout={mockBreakout}
        exit={null}
        kelly={null}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('LONG')).toBeInTheDocument();
  });

  it('calls onClose', () => {
    const onClose = vi.fn();
    render(
      <SymbolDecisionDrawer
        open={true}
        symbol="AAPL"
        alpha={mockAlpha}
        breakout={null}
        exit={null}
        kelly={null}
        onClose={onClose}
      />
    );
    const closeBtn = screen.getByRole('button', { name: /close/i });
    if (closeBtn) fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('shows no symbol state when symbol is null', () => {
    render(
      <SymbolDecisionDrawer
        open={true}
        symbol={null}
        alpha={null}
        breakout={null}
        exit={null}
        kelly={null}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('No symbol selected')).toBeInTheDocument();
  });
});
