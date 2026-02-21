import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import DecisionHeader from '../components/DecisionHeader';
import type { DecisionSnapshot } from '../organismApi';

const mockSnapshot: DecisionSnapshot = {
  tick_number: 42,
  timestamp: '2026-02-21T10:00:00Z',
  duration_s: 1.234,
  regime: {
    primary: 'trending_up',
    probabilities: { trending_up: 0.7, normal: 0.2, chop: 0.1 },
    confidence: 0.85,
    features: {},
  },
  governance: { equity: 106000, peak_equity: 107000, drawdown_pct: 0.009, is_halted: false, is_frozen: false },
  evolution: { generation: 5, params: {} },
  alpha_scores: [{ symbol: 'AAPL', composite_score: 0.5, factors: { ml: 0.5, breakout: 0.3, institutional: 0.4, momentum: 0.6, momentum_quality: 0.5, vol_price_div: 0.3, regime: 0.7 }, weights: {}, direction: 1, threshold: 0.15, distance_to_threshold: 0.35, passed_threshold: true, symbol_fitness: 0.6, fitness_gate: 0.35, passed_fitness: true }],
  breakout_scores: [],
  exit_proximity: [],
  kelly_sizing: [],
  filtering: { total_universe: 30, had_features: 0, alpha_scored: 25, above_alpha_threshold: 8, breakout_scored: 20, above_breakout_threshold: 5, passed_sector_gate: 0, passed_fitness_gate: 0, passed_cooldown: 0, passed_position_limit: 0, kelly_sized: 3, orders_submitted: 2 },
  open_positions: 12,
  max_positions: 15,
};

describe('DecisionHeader', () => {
  it('renders tick number', () => {
    render(<DecisionHeader snapshot={mockSnapshot} />);
    expect(screen.getByText('Decision Header')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('renders position count', () => {
    render(<DecisionHeader snapshot={mockSnapshot} />);
    expect(screen.getByText('12/15')).toBeInTheDocument();
  });

  it('shows empty state when no snapshot', () => {
    render(<DecisionHeader snapshot={null} />);
    expect(screen.getByText('No decision data yet')).toBeInTheDocument();
  });
});
