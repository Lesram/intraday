import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ExitProximityTable from '../components/ExitProximityTable';
import type { ExitProximity } from '../organismApi';

const mockData: ExitProximity[] = [
  {
    symbol: 'MSFT',
    current_price: 350.0,
    entry_price: 340.0,
    direction: 1,
    pnl_pct: 0.0294,
    exits: {
      stop_loss: { level: 330, distance_pct: 5.71 },
      take_profit: { level: 380, distance_pct: 8.57 },
      trailing_stop: { level: 345, distance_pct: 1.43, active: true },
      partial_tp: { level: 360, distance_pct: 2.86, taken: false },
      time: { bars_held: 25, max_bars: 40, distance_pct: 37.5 },
    },
    atr_at_entry: 3.5,
    regime_at_entry: 'normal',
    highest_favorable: 352.0,
    nearest_exit: 'trailing_stop',
    nearest_exit_distance_pct: 1.43,
  },
];

describe('ExitProximityTable', () => {
  it('renders symbol and P&L', () => {
    render(<ExitProximityTable data={mockData} />);
    expect(screen.getByText('MSFT')).toBeInTheDocument();
    expect(screen.getByText('2.9%')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<ExitProximityTable data={[]} />);
    expect(screen.getByText('No open positions')).toBeInTheDocument();
  });

  it('calls onRowClick', () => {
    const onClick = vi.fn();
    render(<ExitProximityTable data={mockData} onRowClick={onClick} />);
    const row = screen.getByText('MSFT').closest('tr');
    if (row) fireEvent.click(row);
    expect(onClick).toHaveBeenCalledWith('MSFT');
  });

  it('shows nearest exit condition', () => {
    render(<ExitProximityTable data={mockData} />);
    expect(screen.getByText(/trailing stop/i)).toBeInTheDocument();
  });
});
