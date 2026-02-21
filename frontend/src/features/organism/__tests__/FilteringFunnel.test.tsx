import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import FilteringFunnel from '../components/FilteringFunnel';
import type { FilteringSummary } from '../organismApi';

describe('FilteringFunnel', () => {
  it('renders card title', () => {
    const data: FilteringSummary = {
      total_universe: 30,
      had_features: 25,
      alpha_scored: 25,
      above_alpha_threshold: 8,
      breakout_scored: 20,
      above_breakout_threshold: 5,
      passed_sector_gate: 4,
      passed_fitness_gate: 4,
      passed_cooldown: 3,
      passed_position_limit: 3,
      kelly_sized: 3,
      orders_submitted: 2,
    };
    render(<FilteringFunnel data={data} />);
    expect(screen.getByText('Filtering Funnel')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<FilteringFunnel data={null} />);
    expect(screen.getByText('No filtering data yet')).toBeInTheDocument();
  });

  it('renders canvas element', () => {
    const data: FilteringSummary = {
      total_universe: 30,
      had_features: 0,
      alpha_scored: 25,
      above_alpha_threshold: 8,
      breakout_scored: 0,
      above_breakout_threshold: 0,
      passed_sector_gate: 0,
      passed_fitness_gate: 0,
      passed_cooldown: 0,
      passed_position_limit: 0,
      kelly_sized: 3,
      orders_submitted: 2,
    };
    const { container } = render(<FilteringFunnel data={data} />);
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });
});
