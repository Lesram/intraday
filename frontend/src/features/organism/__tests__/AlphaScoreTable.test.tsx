import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AlphaScoreTable from '../components/AlphaScoreTable';
import type { AlphaFactorScore } from '../organismApi';

const mockData: AlphaFactorScore[] = [
  {
    symbol: 'AAPL',
    composite_score: 0.42,
    factors: { ml: 0.6, breakout: 0.3, institutional: 0.5, momentum: 0.5, momentum_quality: 0.4, vol_price_div: 0.3, regime: 0.7 },
    weights: { ml: 0.25, breakout: 0.20 },
    direction: 1,
    threshold: 0.15,
    distance_to_threshold: 0.27,
    passed_threshold: true,
    symbol_fitness: 0.65,
    fitness_gate: 0.35,
    passed_fitness: true,
  },
  {
    symbol: 'TSLA',
    composite_score: 0.10,
    factors: { ml: 0.2, breakout: 0.1, institutional: 0.3, momentum: 0.2, momentum_quality: 0.1, vol_price_div: 0.1, regime: 0.3 },
    weights: {},
    direction: -1,
    threshold: 0.15,
    distance_to_threshold: -0.05,
    passed_threshold: false,
    symbol_fitness: 0.30,
    fitness_gate: 0.35,
    passed_fitness: false,
  },
];

describe('AlphaScoreTable', () => {
  it('renders symbol names', () => {
    render(<AlphaScoreTable data={mockData} />);
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('TSLA')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<AlphaScoreTable data={[]} />);
    expect(screen.getByText('No alpha scores available')).toBeInTheDocument();
  });

  it('calls onRowClick when row is clicked', () => {
    const onClick = vi.fn();
    render(<AlphaScoreTable data={mockData} onRowClick={onClick} />);
    const aaplRow = screen.getByText('AAPL').closest('tr');
    if (aaplRow) fireEvent.click(aaplRow);
    expect(onClick).toHaveBeenCalledWith('AAPL');
  });

  it('displays fitness values', () => {
    render(<AlphaScoreTable data={mockData} />);
    expect(screen.getByText('0.65')).toBeInTheDocument();
    // 0.30 appears in multiple columns (fitness + factors), check at least one exists
    expect(screen.getAllByText('0.30').length).toBeGreaterThan(0);
  });
});
