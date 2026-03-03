import { Typography, Card } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import FormulaBlock from '../components/FormulaBlock';
import ThresholdTable from '../components/ThresholdTable';
import {
  mlSignalGeneration, alphaScanner, breakoutScanner,
  kellySizer, adaptiveExitCascade, regimeDetection, selfEvolution,
  stateDependentCost,
} from '../data/mermaidDefinitions';
import { exitRegimeParams, regimeScales, evolutionBounds } from '../data/thresholds';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const featureCategories = [
  { category: 'Price Action', count: 15, examples: 'ret_1d..ret_20d, log_ret_1d, momentum_accel, range_pct, gap_pct, body_ratio' },
  { category: 'Trend', count: 8, examples: 'sma_5/10/20/50 (ratio to price), macd/signal/hist, adx_14' },
  { category: 'Mean Reversion', count: 8, examples: 'rsi_14, rsi_5, bb_position/width, z_score_20/50, stoch_k/d' },
  { category: 'Volatility', count: 10, examples: 'atr_14, atr_ratio, realized_vol_5/20, parkinson/garman_klass, bb_squeeze' },
  { category: 'Volume', count: 8, examples: 'vol_sma_ratio, obv_slope, mfi_14, vwap_distance, volume_breakout' },
  { category: 'Cross-Sectional', count: 5, examples: 'rel_strength_spy, beta_20d, corr_to_market, idio_vol, sector_momentum' },
  { category: 'Microstructure', count: 5, examples: 'spread_proxy, price_impact, tick_direction, close_location, true_range_pct' },
  { category: 'Temporal', count: 5, examples: 'day_of_week, month_sin/cos, pct_from_52w_high/low' },
  { category: 'Regime', count: 4, examples: 'trend_strength, choppiness, hurst, regime_encoded' },
  { category: 'Momentum Persistence', count: 4, examples: 'ret_autocorr_1/5/10, hurst_exponent' },
  { category: 'Composite Indicators', count: 7, examples: 'squeeze_momentum, vol_price_div, trend_alignment, institutional_acc, breakout_readiness' },
];

const sectorMap = [
  { sector: 'Technology', symbols: 'AAPL, MSFT, NVDA, AMD, AVGO, INTC, MU, ADBE, CRM, SNOW, PLTR', max: '4' },
  { sector: 'Communication', symbols: 'GOOGL, META, NFLX', max: '4' },
  { sector: 'Consumer Disc.', symbols: 'AMZN, TSLA, COST, WMT, UBER, ABNB', max: '4' },
  { sector: 'ETF', symbols: 'SPY, QQQ, IWM, XLK, XLE', max: '4' },
  { sector: 'Healthcare', symbols: 'LLY', max: '4' },
  { sector: 'Energy', symbols: 'XOM', max: '4' },
  { sector: 'Industrials', symbols: 'CAT', max: '4' },
  { sector: 'Financials', symbols: 'COIN, SQ', max: '4' },
  { sector: 'Unknown', symbols: 'New scanner finds', max: 'Never blocked' },
];

const AlgorithmEngineTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <Title level={4} style={{ margin: 0 }}>Algorithm Engine Deep Dives</Title>

    <CollapsibleSection title="ML Signal Generation" subtitle="Dual XGB → ensemble → blend → direction" defaultOpen>
      <MermaidDiagram definition={mlSignalGeneration} />
      <FormulaBlock
        label="Confidence Calibration"
        formula={`raw_confidence = abs(p_up - 0.5) × 2     → [0, 1]
bin_idx = int(raw_confidence × 5)          → 5 bins
multiplier = actual_accuracy / bin_midpoint → capped at 2.0
calibrated = raw_confidence × multiplier   → capped at 1.0`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Alpha Scanner" subtitle="7-factor weighted composite score">
      <MermaidDiagram definition={alphaScanner} />
      <FormulaBlock
        label="7-Factor Composite Formula"
        formula={`COMPOSITE = 0.25 × ml_score
          + 0.20 × breakout_score
          + 0.15 × institutional_score
          + 0.15 × momentum_score (cross-sectional rank)
          + 0.10 × momentum_quality
          + 0.10 × volume_score
          + 0.05 × regime_alignment

Modifiers:
  ML Hold penalty:  direction == 0 → composite × 0.30
  Symbol fitness:   composite × (0.5 + fitness) → [0.6×, 1.45×]
  Min composite:    0.15 | Top-N: 3 candidates (live_engine override)`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Breakout Scanner" subtitle="6-detector weighted composite">
      <MermaidDiagram definition={breakoutScanner} />
      <FormulaBlock
        label="6-Detector Composite Formula"
        formula={`COMPOSITE = 0.25 × squeeze
          + 0.25 × volume_surge
          + 0.15 × range_contraction
          + 0.15 × relative_strength
          + 0.15 × pivot_breakout
          + 0.05 × institutional_flow

Bonuses: Squeeze + Volume fired → ×1.30
Post-filter: composite < 0.20 → filtered out
Top-N: MAX_OPEN_POSITIONS breakout signals (code: 8, docker: 15)`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Kelly Position Sizer" subtitle="7-step multiplication chain + cost model">
      <MermaidDiagram definition={kellySizer} />
      <FormulaBlock
        label="Kelly Sizing Formula"
        formula={`target_weight = (kelly_raw × 0.5)                    # Half-Kelly (requires edge-over-cost gate)
              × drawdown_scale(dd)                     # [0.1, 1.0]
              × vol_scale(stock_vol, bars_per_day)     # [0, 2.0] — ann_vol = std × √(252 × bpd)
              × regime_scale(regime)                   # [0.40, 1.20] hardcoded / [0.05, 1.50] evolved
              × confidence_scale(conf, ml_trained)     # [0.3, 1.5]
              × breakout_bonus(brk_score, ml_trained)  # [1.0, 2.0]

Caps: 10% per position (intraday: 8%) | 95% portfolio | Min $2,000 (intraday: $500)
Intraday seasonality: Last 15 min (3:45-4:00 ET) → ALL sizes × 0.60`}
      />
      <ThresholdTable
        data={regimeScales}
        columns={[
          { title: 'Regime', dataIndex: 'regime', key: 'regime' },
          { title: 'Kelly Scale', dataIndex: 'scale', key: 'scale' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="State-Dependent Cost Model" subtitle="Per-symbol dynamic spread cost → edge-over-cost gate">
      <MermaidDiagram definition={stateDependentCost} />
      <FormulaBlock
        label="Edge-Over-Cost Gate"
        formula={`spread_cost = _estimate_spread_cost(symbol, quote_provider, features)
           = base_spread × time_mult × liquidity_mult
           → Clamped to [3bps, 50bps]

edge_clears_cost = predicted_return >= spread_cost × 2

If NOT edge_clears_cost AND kelly < 0.005 → kelly = 0 (skip)
Breakout floor: kelly < 0.005 AND score >= 0.55 AND edge_clears_cost
  → kelly_half = max(kelly, 0.003 × breakout_score)
ML floor: kelly < 0.005 AND conf >= 0.5 AND regime_has_edge AND edge_clears_cost
  → Trained:   kelly_half = max(kelly, 0.04 × confidence)
  → Untrained: kelly_half = max(kelly, 0.02 × confidence)`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Adaptive Exit Engine" subtitle="8-priority cascade with regime thresholds">
      <MermaidDiagram definition={adaptiveExitCascade} />
      <ThresholdTable
        data={exitRegimeParams}
        columns={[
          { title: 'Regime', dataIndex: 'regime', key: 'regime' },
          { title: 'Stop ATR', dataIndex: 'stopATR', key: 'stopATR' },
          { title: 'TP R-Multiple', dataIndex: 'tpRMultiple', key: 'tpRMultiple' },
          { title: 'Trail ATR', dataIndex: 'trailATR', key: 'trailATR' },
          { title: 'Max Bars', dataIndex: 'maxBars', key: 'maxBars' },
          { title: 'Decay Start', dataIndex: 'decayStart', key: 'decayStart' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Regime Detection" subtitle="signals → softmax → EMA → label">
      <MermaidDiagram definition={regimeDetection} />
      <FormulaBlock
        label="Regime Detection Pipeline"
        formula={`4 Signals → Raw Scores (additive):
  trending_up:   +2 (strong trend) or +1 (above SMA)
  trending_down: +2 or +1
  chop:          +1.5 (no trend) or +0.5 (near SMA)
  high_vol:      +2 (high ATR) or +1 (high returns vol)
  low_vol:       +1.5 (low ATR)
  stress:        +2 (vol anomaly + high ATR) or +1

Scores → Softmax → EMA Smoothing (α=0.3) → argmax → Label`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Self-Evolution Engine" subtitle="10-step parameter evolution loop">
      <MermaidDiagram definition={selfEvolution} />
      <FormulaBlock
        label="EMA Update (Safety-Bounded)"
        formula={`delta = α × new + (1-α) × old - old
max_delta = |old| × 0.20 + 0.005     # max 20% shift per step
clamped_delta = clamp(delta, -max_delta, max_delta)
result = old + clamped_delta`}
      />
      <ThresholdTable
        data={evolutionBounds}
        columns={[
          { title: 'Parameter', dataIndex: 'parameter', key: 'parameter', render: (v: string) => <code>{v}</code> },
          { title: 'Lower Bound', dataIndex: 'lower', key: 'lower' },
          { title: 'Upper Bound', dataIndex: 'upper', key: 'upper' },
        ]}
      />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 12 }}>
        <Text style={{ color: colors.text.secondary, fontSize: 13 }}>
          Hard floor enforcement on restore: high_vol {'>='} 0.70, stress {'>='} 0.30.
          Breakout weights re-normalized to sum=1.0 after each step, clamped to [0.10, 0.40].
        </Text>
      </Card>
    </CollapsibleSection>

    <CollapsibleSection title="Universe & Sector Management" subtitle="Dynamic rotation + 8 GICS sectors + market scanner">
      <FormulaBlock
        label="Universe Rotation (on retrain)"
        formula={`fitness = 0.6 × win_rate + 0.4 × (0.5 + pnl_norm/2)
Decay all fitness toward 0.50 (×0.95)
DROP: up to 5 symbols (no open position, >= 3 trades, fitness < 0.40)
ADD:  up to 10 symbols (not active, fitness >= 0.50, >= 3 rotations)
Bounds: [15, 80] symbols — NEVER drop with open positions`}
      />
      <ThresholdTable
        data={sectorMap}
        columns={[
          { title: 'Sector', dataIndex: 'sector', key: 'sector' },
          { title: 'Symbols', dataIndex: 'symbols', key: 'symbols', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
          { title: 'Max Positions', dataIndex: 'max', key: 'max' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Feature Engineering (79 Features)" subtitle="11 categories across ml_features.py + composite_indicators.py">
      <ThresholdTable
        data={featureCategories}
        columns={[
          { title: 'Category', dataIndex: 'category', key: 'category', render: (v: string) => <Text strong>{v}</Text> },
          { title: 'Count', dataIndex: 'count', key: 'count', width: 70 },
          { title: 'Examples', dataIndex: 'examples', key: 'examples', render: (v: string) => <Text style={{ fontSize: 12, color: colors.text.secondary }}>{v}</Text> },
        ]}
      />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 12 }}>
        <Text style={{ color: colors.text.secondary, fontSize: 13 }}>
          Global NaN safety: inf → NaN → 0.0 (end of compute_ml_features).
          QA gates: missing bars {'>'} 10% = issue, NaN rate {'>'} 20% = issue, outliers {'>'} 5 (10 std) = issue.
        </Text>
      </Card>
    </CollapsibleSection>
  </div>
);

export default AlgorithmEngineTab;
