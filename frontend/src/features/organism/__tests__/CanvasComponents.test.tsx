import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AlphaFactorRadar from '../components/AlphaFactorRadar';
import BreakoutFactorRadar from '../components/BreakoutFactorRadar';
import KellyPipelineWaterfall from '../components/KellyPipelineWaterfall';
import ExitProximityGauges from '../components/ExitProximityGauges';
import EvolutionTimeline from '../components/EvolutionTimeline';
import type { AlphaFactorScore, BreakoutFactorScore, ExitProximity, KellySizingStage, EvolutionSnapshot } from '../organismApi';

describe('AlphaFactorRadar', () => {
  it('renders empty state', () => {
    render(<AlphaFactorRadar data={null} />);
    expect(screen.getByText('Alpha Factors')).toBeInTheDocument();
    expect(screen.getByText('Select a symbol to see alpha factors')).toBeInTheDocument();
  });

  it('renders with data', () => {
    const data: AlphaFactorScore = {
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
    const { container } = render(<AlphaFactorRadar data={data} threshold={0.15} />);
    expect(screen.getByText(/Alpha Factors: AAPL/)).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });
});

describe('BreakoutFactorRadar', () => {
  it('renders empty state', () => {
    render(<BreakoutFactorRadar data={null} />);
    expect(screen.getByText('Breakout Factors')).toBeInTheDocument();
  });

  it('renders with data', () => {
    const data: BreakoutFactorScore = {
      symbol: 'NVDA',
      composite_score: 0.55,
      factors: { squeeze: 0.8, volume: 0.6, contraction: 0.3, rs: 0.7, pivot: 0.4, flow: 0.2 },
      weights: {},
      direction: 1,
      squeeze_fired: true,
      volume_ratio: 2.5,
      threshold: 0.20,
      distance_to_threshold: 0.35,
      passed_threshold: true,
    };
    const { container } = render(<BreakoutFactorRadar data={data} />);
    expect(screen.getByText(/Breakout Factors: NVDA/)).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeInTheDocument();
    expect(screen.getByText('Squeeze Fired')).toBeInTheDocument();
  });
});

describe('KellyPipelineWaterfall', () => {
  it('renders empty state', () => {
    render(<KellyPipelineWaterfall data={null} />);
    expect(screen.getByText('Kelly Pipeline')).toBeInTheDocument();
    expect(screen.getByText('Select a symbol to see Kelly pipeline')).toBeInTheDocument();
  });

  it('renders with data', () => {
    const data: KellySizingStage = {
      symbol: 'AAPL',
      pipeline: {
        kelly_raw: 0.08,
        kelly_half: 0.04,
        drawdown_scale: 0.95,
        vol_scale: 1.2,
        regime_scale: 1.0,
        confidence_scale: 0.9,
        breakout_bonus: 1.5,
        final_weight: 0.06,
      },
      position_cap: 0.12,
      shares: 15,
      notional: 2500,
      direction: 1,
    };
    const { container } = render(<KellyPipelineWaterfall data={data} />);
    expect(screen.getByText(/Kelly Pipeline: AAPL/)).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });
});

describe('ExitProximityGauges', () => {
  it('renders empty state', () => {
    render(<ExitProximityGauges data={null} />);
    expect(screen.getByText('Exit Proximity')).toBeInTheDocument();
    expect(screen.getByText('Select a position to see exit proximity')).toBeInTheDocument();
  });

  it('renders with position data', () => {
    const data: ExitProximity = {
      symbol: 'MSFT',
      current_price: 350,
      entry_price: 340,
      direction: 1,
      pnl_pct: 0.029,
      exits: {
        stop_loss: { level: 330, distance_pct: 5.71 },
        take_profit: { level: 380, distance_pct: 8.57 },
        trailing_stop: { level: 345, distance_pct: 1.43, active: true },
        partial_tp: { level: 360, distance_pct: 2.86, taken: false },
        time: { bars_held: 25, max_bars: 40, distance_pct: 37.5 },
      },
      atr_at_entry: 3.5,
      regime_at_entry: 'normal',
      highest_favorable: 352,
      nearest_exit: 'trailing_stop',
      nearest_exit_distance_pct: 1.43,
    };
    render(<ExitProximityGauges data={data} />);
    expect(screen.getByText(/Exit Proximity: MSFT/)).toBeInTheDocument();
    expect(screen.getByText('Stop Loss')).toBeInTheDocument();
    expect(screen.getByText('Take Profit')).toBeInTheDocument();
    expect(screen.getByText('Trailing Stop')).toBeInTheDocument();
  });
});

describe('EvolutionTimeline', () => {
  it('renders insufficient data message', () => {
    render(<EvolutionTimeline data={[]} />);
    expect(screen.getByText('Evolution Timeline')).toBeInTheDocument();
    expect(screen.getByText(/Insufficient evolution data/)).toBeInTheDocument();
  });

  it('renders with data', () => {
    const data: EvolutionSnapshot[] = [
      { tick_number: 2, timestamp: 't2', generation: 5, regime: 'normal', equity: 106000, drawdown_pct: 0.009, params: {} },
      { tick_number: 1, timestamp: 't1', generation: 5, regime: 'normal', equity: 105500, drawdown_pct: 0.014, params: {} },
    ];
    const { container } = render(<EvolutionTimeline data={data} />);
    expect(screen.getByText('Evolution Timeline')).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeInTheDocument();
    expect(screen.getByText(/2 ticks/)).toBeInTheDocument();
  });
});
