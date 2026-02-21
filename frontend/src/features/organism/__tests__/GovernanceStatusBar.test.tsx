import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import GovernanceStatusBar from '../components/GovernanceStatusBar';
import type { DecisionSnapshot } from '../organismApi';

const baseSnapshot: DecisionSnapshot = {
  tick_number: 1,
  timestamp: '2026-02-21T10:00:00Z',
  duration_s: 0.5,
  regime: { primary: 'normal', probabilities: {}, confidence: 0.5, features: {} },
  governance: { equity: 106000, peak_equity: 107000, drawdown_pct: 0.009, is_halted: false, is_frozen: false },
  evolution: { generation: 5, params: {} },
  alpha_scores: [],
  breakout_scores: [],
  exit_proximity: [],
  kelly_sizing: [],
  filtering: { total_universe: 0, had_features: 0, alpha_scored: 0, above_alpha_threshold: 0, breakout_scored: 0, above_breakout_threshold: 0, passed_sector_gate: 0, passed_fitness_gate: 0, passed_cooldown: 0, passed_position_limit: 0, kelly_sized: 0, orders_submitted: 0 },
  open_positions: 0,
  max_positions: 15,
};

describe('GovernanceStatusBar', () => {
  it('renders governance title', () => {
    render(<GovernanceStatusBar snapshot={baseSnapshot} />);
    expect(screen.getByText('Governance')).toBeInTheDocument();
  });

  it('shows ACTIVE tag when not halted or frozen', () => {
    render(<GovernanceStatusBar snapshot={baseSnapshot} />);
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
  });

  it('shows HALTED tag when halted', () => {
    const halted = { ...baseSnapshot, governance: { ...baseSnapshot.governance, is_halted: true } };
    render(<GovernanceStatusBar snapshot={halted} />);
    expect(screen.getByText('HALTED')).toBeInTheDocument();
  });

  it('shows empty state when no snapshot', () => {
    render(<GovernanceStatusBar snapshot={null} />);
    expect(screen.getByText('No governance data')).toBeInTheDocument();
  });
});
