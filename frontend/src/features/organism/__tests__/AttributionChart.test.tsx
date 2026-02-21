import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AttributionPanel, { SectorExposureTable, ConfidenceHistogram, RegimeKellyTable } from '../components/AttributionChart';

describe('SectorExposureTable', () => {
  it('renders sector data', () => {
    const data = [
      { sector: 'Technology', count: 5, symbols: ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO'], total_value: 35000 },
      { sector: 'Energy', count: 1, symbols: ['XOM'], total_value: 5000 },
    ];
    render(<SectorExposureTable data={data} />);
    expect(screen.getByText('Sector Exposure')).toBeInTheDocument();
    expect(screen.getByText('Technology')).toBeInTheDocument();
    expect(screen.getByText('Energy')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<SectorExposureTable data={[]} />);
    expect(screen.getByText('No sector data available')).toBeInTheDocument();
  });

  it('displays position counts correctly', () => {
    const data = [
      { sector: 'Technology', count: 3, symbols: ['AAPL', 'MSFT', 'NVDA'], total_value: 20000 },
    ];
    render(<SectorExposureTable data={data} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});

describe('ConfidenceHistogram', () => {
  it('renders the card title', () => {
    const data = [
      { bin: '0.0-0.2', correct: 0, total: 0 },
      { bin: '0.2-0.4', correct: 5, total: 12 },
      { bin: '0.4-0.6', correct: 10, total: 18 },
      { bin: '0.6-0.8', correct: 15, total: 20 },
      { bin: '0.8-1.0', correct: 8, total: 10 },
    ];
    render(<ConfidenceHistogram data={data} />);
    expect(screen.getByText('ML Confidence Distribution')).toBeInTheDocument();
  });

  it('shows empty state when all totals are zero', () => {
    const data = [
      { bin: '0.0-0.2', correct: 0, total: 0 },
      { bin: '0.2-0.4', correct: 0, total: 0 },
      { bin: '0.4-0.6', correct: 0, total: 0 },
      { bin: '0.6-0.8', correct: 0, total: 0 },
      { bin: '0.8-1.0', correct: 0, total: 0 },
    ];
    render(<ConfidenceHistogram data={data} />);
    expect(screen.getByText(/No confidence data yet/)).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<ConfidenceHistogram data={[]} />);
    expect(screen.getByText(/No confidence data yet/)).toBeInTheDocument();
  });
});

describe('RegimeKellyTable', () => {
  it('renders regime stats', () => {
    const data = {
      normal: { wins: 20, losses: 15, total_pnl: 500, total_win_pnl: 2000, total_loss_pnl: 1500 },
      trending_up: { wins: 10, losses: 3, total_pnl: 800, total_win_pnl: 1000, total_loss_pnl: 200 },
    };
    render(<RegimeKellyTable data={data} />);
    expect(screen.getByText('Regime Performance')).toBeInTheDocument();
    expect(screen.getByText('normal')).toBeInTheDocument();
    expect(screen.getByText('trending_up')).toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<RegimeKellyTable data={{}} />);
    expect(screen.getByText(/No regime-level trade data yet/)).toBeInTheDocument();
  });

  it('calculates win rate correctly', () => {
    const data = {
      normal: { wins: 6, losses: 4, total_pnl: 200 },
    };
    render(<RegimeKellyTable data={data} />);
    expect(screen.getByText('60.0%')).toBeInTheDocument();
  });
});

describe('AttributionPanel', () => {
  it('renders all sub-components', () => {
    render(
      <AttributionPanel
        sectorExposure={[{ sector: 'Tech', count: 2, symbols: ['AAPL', 'MSFT'], total_value: 10000 }]}
        confidenceDist={[{ bin: '0.0-0.2', correct: 0, total: 0 }]}
        regimeKellyStats={{ normal: { wins: 5, losses: 3, total_pnl: 100 } }}
      />
    );
    expect(screen.getByText('Sector Exposure')).toBeInTheDocument();
    expect(screen.getByText('ML Confidence Distribution')).toBeInTheDocument();
    expect(screen.getByText('Regime Performance')).toBeInTheDocument();
  });
});
