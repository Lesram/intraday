import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import RegimeTimeline from '../components/RegimeTimeline';

describe('RegimeTimeline', () => {
  it('renders the card title', () => {
    render(<RegimeTimeline data={[{ regime: 'normal', timestamp: '2025-02-20T10:00:00Z' }]} />);
    expect(screen.getByText('Regime Timeline')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<RegimeTimeline data={[]} />);
    expect(screen.getByText('No regime history yet')).toBeInTheDocument();
  });

  it('renders regime legend for active regimes', () => {
    const data = [
      { regime: 'normal', timestamp: '2025-02-20T10:00:00Z' },
      { regime: 'trending_up', timestamp: '2025-02-20T11:00:00Z' },
      { regime: 'chop', timestamp: '2025-02-20T12:00:00Z' },
    ];
    render(<RegimeTimeline data={data} />);
    expect(screen.getByText('normal')).toBeInTheDocument();
    expect(screen.getByText('trending up')).toBeInTheDocument();
    expect(screen.getByText('chop')).toBeInTheDocument();
  });

  it('renders canvas element', () => {
    const data = [
      { regime: 'normal', timestamp: '2025-02-20T10:00:00Z' },
      { regime: 'normal', timestamp: '2025-02-20T10:01:00Z' },
    ];
    const { container } = render(<RegimeTimeline data={data} />);
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });
});
