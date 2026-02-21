import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import RegimeProbabilityPanel from '../components/RegimeProbabilityPanel';
import type { RegimeProbabilities } from '../organismApi';

describe('RegimeProbabilityPanel', () => {
  it('renders regime labels', () => {
    const data: RegimeProbabilities = {
      primary: 'trending_up',
      probabilities: { trending_up: 0.6, normal: 0.25, chop: 0.15 },
      confidence: 0.8,
      features: {},
    };
    render(<RegimeProbabilityPanel regime={data} />);
    expect(screen.getByText('Regime Probabilities')).toBeInTheDocument();
    expect(screen.getByText(/trending up/i)).toBeInTheDocument();
    expect(screen.getByText(/normal/i)).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<RegimeProbabilityPanel regime={null} />);
    expect(screen.getByText('No regime probability data')).toBeInTheDocument();
  });

  it('displays confidence value', () => {
    const data: RegimeProbabilities = {
      primary: 'normal',
      probabilities: { normal: 0.8 },
      confidence: 0.75,
      features: {},
    };
    render(<RegimeProbabilityPanel regime={data} />);
    expect(screen.getByText(/75\.0%/)).toBeInTheDocument();
  });
});
