export interface Threshold {
  threshold: string;
  value: string;
  location: string;
  purpose: string;
}

export const thresholds: Threshold[] = [
  // ── Scanner Thresholds ──
  { threshold: 'Alpha composite minimum', value: '0.15', location: 'alpha_scanner', purpose: 'Minimum score to be a candidate' },
  { threshold: 'Breakout composite minimum', value: '0.20', location: 'breakout_scanner', purpose: 'Minimum breakout score' },
  { threshold: 'Pure breakout entry threshold', value: '0.55', location: 'live_engine', purpose: 'Breakout-only entries need high score' },
  { threshold: 'Pure breakout cap', value: '2 per tick', location: 'live_engine', purpose: '_MAX_PURE_BREAKOUT limit' },
  { threshold: 'Symbol fitness gate', value: '0.45', location: 'live_engine', purpose: 'Chronic loser rejection' },
  { threshold: 'Liquidity gate', value: '10K avg vol/bar', location: 'live_engine', purpose: 'Block illiquid symbols (per-bar, not daily)' },

  // ── ML Signal Thresholds ──
  { threshold: 'ML confidence reversal', value: '0.60 (intraday) / 0.65 (daily)', location: 'live_engine', purpose: 'ML reversal exit — partial exit 30%/25% of position' },
  { threshold: 'ML reversal partial exit', value: '30% (intraday) / 25% (daily)', location: 'live_engine', purpose: 'Partial position exit on ML reversal' },
  { threshold: 'Predicted return ML floor', value: '0.3%', location: 'live_engine', purpose: 'Min predicted_return when ML signal present' },
  { threshold: 'Predicted return no-ML range', value: '0.5%–2.0%', location: 'live_engine', purpose: '0.005 + 0.015×breakout_score when no ML' },

  // ── Exit Thresholds ──
  { threshold: 'Max loss safety net', value: '8% (via for_timeframe; base 15%)', location: 'adaptive_exits', purpose: 'Absolute loss limit' },
  { threshold: 'Min hold before profit exits', value: '18 bars (~3 min)', location: 'adaptive_exits', purpose: 'MIN_HOLD_BARS_PROFIT — suppresses all profit exits' },
  { threshold: 'Failure-to-follow fallback', value: '30 bars', location: 'adaptive_exits', purpose: 'Used when max_bars=0 (trending_up, low_vol)' },
  { threshold: 'Loser time-stop fallback', value: '200 bars', location: 'adaptive_exits', purpose: 'Used when max_bars=0 (~33 min @10s ticks)' },

  // ── Kelly Sizer Thresholds ──
  { threshold: 'Edge-over-cost gate', value: '2× spread_cost (dynamic)', location: 'kelly_sizer', purpose: 'Predicted return must clear 2× per-symbol cost [3-50bps]' },
  { threshold: 'Kelly ML confidence min', value: '0.5', location: 'kelly_sizer', purpose: '_ML_CONFIDENCE_MIN — minimum confidence to trigger ML floor' },
  { threshold: 'Kelly ML floor', value: '0.04×conf (trained) / 0.02×conf (untrained)', location: 'kelly_sizer', purpose: 'Minimum sizing when ML confident + edge clears cost' },
  { threshold: 'Kelly breakout floor', value: '0.003×score (kelly<0.005, score>=0.55)', location: 'kelly_sizer', purpose: 'Minimum sizing on strong breakout + edge clears cost' },
  { threshold: 'Kelly raw cap', value: '1.0 (100%)', location: 'kelly_sizer', purpose: 'Prevents oversized raw Kelly fractions' },
  { threshold: 'Kelly min notional', value: '$2,000 (intraday: $500)', location: 'kelly_sizer', purpose: 'Minimum position size' },
  { threshold: 'Kelly max per position', value: '10% (intraday: 8%)', location: 'kelly_sizer', purpose: 'Position concentration limit' },
  { threshold: 'Kelly max portfolio', value: '95%', location: 'kelly_sizer', purpose: 'Total exposure limit' },
  { threshold: 'Drawdown risk-off', value: '25%', location: 'kelly_sizer', purpose: 'No new positions at all' },

  // ── Governance Thresholds ──
  { threshold: 'Drawdown kill switch', value: 'code: 5%, docker: 3%, .env: 8%', location: 'governance', purpose: 'Halt all entries' },
  { threshold: 'Intraday size reduction', value: '40% (×0.60)', location: 'live_engine', purpose: 'Last 15 min of session (3:45-4:00 ET)' },
  { threshold: 'Opening block window', value: '30 min (9:30-10:00 ET)', location: 'live_engine', purpose: 'No entries during open auction (intraday only)' },
  { threshold: 'Regime sit-out', value: 'high_vol/stress + all bearish ML', location: 'live_engine', purpose: 'Block entries when all ML signals are short' },
  { threshold: 'Entry throttle', value: '3 entries/hour', location: 'live_engine', purpose: 'Prevents rapid-fire entry cascades' },
  { threshold: 'Warmup gate', value: '5 ticks', location: 'live_engine', purpose: 'Block entries on cold start' },
  { threshold: 'Equity-zero threshold', value: '3 consecutive', location: 'live_engine', purpose: 'Block entries on stale data' },
  { threshold: 'NaN missingness gate', value: '25%', location: 'live_engine', purpose: 'Block entries when >25% features are NaN/Inf' },
  { threshold: 'BG training timeout', value: '30 ticks', location: 'live_engine', purpose: 'Force-reset stuck background training' },

  // ── Brain & ML Thresholds ──
  { threshold: 'Walk-forward regression', value: '0.95', location: 'brain_persistence', purpose: "Don't persist regressing model" },
  { threshold: 'Feature QA NaN rate', value: '20%', location: 'feature_store', purpose: 'Reject feature set' },
  { threshold: 'Feature QA missing bars', value: '10%', location: 'feature_store', purpose: 'Flag data quality issue' },

  // ── Infrastructure Thresholds ──
  { threshold: 'Circuit breaker failures', value: '5', location: 'resilience', purpose: 'Open circuit breaker' },
  { threshold: 'Circuit breaker recovery', value: '60s', location: 'resilience', purpose: 'Try half-open' },
  { threshold: 'Alert dedup window', value: '300s', location: 'alerting', purpose: 'Suppress duplicates' },
  { threshold: 'Alert rate limit', value: '30/min', location: 'alerting', purpose: 'Cap alert volume' },
  { threshold: 'Stale order pending', value: '5 min', location: 'order_guardrails', purpose: 'Mark as failed' },
  { threshold: 'Stale order accepted', value: '24 hr', location: 'order_guardrails', purpose: 'Flag for reconciliation' },
];

export interface EngineConfig {
  variable: string;
  default: string;
  production: string;
  effect: string;
}

export const engineConfig: EngineConfig[] = [
  { variable: 'ORGANISM_TICK_INTERVAL_SECONDS', default: '60', production: '10', effect: 'Tick frequency' },
  { variable: 'ORGANISM_LIVE_TIMEFRAME', default: '1Day', production: '1Min', effect: 'Bar timeframe' },
  { variable: 'ORGANISM_MAX_POSITIONS', default: '8', production: '15', effect: 'Max simultaneous positions' },
  { variable: 'ORGANISM_LONG_ONLY', default: 'true', production: 'true', effect: 'Block all short entries' },
  { variable: 'ORGANISM_RETRAIN_INTERVAL', default: '60 (200 intraday auto)', production: '600 (docker) / 180 (.env)', effect: 'Ticks between retrains' },
  { variable: 'ORGANISM_ML_DECAY_RATE', default: '0.005', production: '0.005', effect: 'Time-decay on training samples' },
  { variable: 'ORGANISM_MAX_PER_SECTOR', default: '4', production: '4', effect: 'Sector concentration limit' },
  { variable: 'ORGANISM_DRAWDOWN_KILL_PCT', default: '0.05', production: '0.03 (docker) / 0.08 (.env)', effect: 'Drawdown kill switch' },
  { variable: 'ORGANISM_DRAWDOWN_COOLDOWN_S', default: '3600', production: '300 (docker)', effect: 'Base cooldown after kill' },
  { variable: 'ORGANISM_MAX_CHANGES_PER_DAY', default: '100', production: '500 (docker)', effect: 'Daily evolution budget' },
  { variable: 'ORGANISM_LIVE_LOOKBACK', default: '500', production: '100 (docker)', effect: 'Bars of history to fetch' },
  { variable: 'ORGANISM_LIVE_SYMBOLS', default: '20 symbols', production: '30 symbols (.env)', effect: 'Universe CSV' },
  { variable: 'ORGANISM_TRAIN_WINDOW', default: '200', production: '100 (docker)', effect: 'Training window size' },
  { variable: 'ORGANISM_MIN_BARS', default: '200 (50 intraday auto)', production: '50', effect: 'Minimum bars for a symbol' },
  { variable: 'ORGANISM_NIGHTLY_ENABLED', default: '0', production: '0', effect: 'Nightly training cycle' },
  { variable: 'ORGANISM_NIGHTLY_INTERVAL_S', default: '86400', production: '—', effect: 'Nightly training interval (seconds)' },
  { variable: 'ORGANISM_HALT_TRADING', default: '0', production: '0', effect: 'Manual trading halt' },
  { variable: 'ORGANISM_FREEZE_ADAPTATION', default: '0', production: '1', effect: 'Freeze all adaptation' },
  { variable: 'SCANNER_ENABLED', default: 'true', production: '—', effect: 'Enable market scanner' },
  { variable: 'ORGANISM_USE_STREAMING', default: 'false', production: '0 (docker)', effect: 'Use streaming data provider' },
];

export interface ExitRegimeParam {
  regime: string;
  stopATR: string;
  tpRMultiple: string;
  trailATR: string;
  maxBars: string;
  decayStart: string;
}

export const exitRegimeParams: ExitRegimeParam[] = [
  { regime: 'trending_up', stopATR: '2.0', tpRMultiple: '6.0', trailATR: '3.5', maxBars: 'Infinite', decayStart: 'none' },
  { regime: 'trending_down', stopATR: '1.3', tpRMultiple: '3.0', trailATR: '2.0', maxBars: '30', decayStart: 'bar 20' },
  { regime: 'chop', stopATR: '1.2', tpRMultiple: '2.5', trailATR: '1.5', maxBars: '25', decayStart: 'bar 15' },
  { regime: 'high_vol', stopATR: '2.0', tpRMultiple: '3.0', trailATR: '2.5', maxBars: '30', decayStart: 'bar 20' },
  { regime: 'low_vol', stopATR: '1.8', tpRMultiple: '5.0', trailATR: '3.0', maxBars: 'Infinite', decayStart: 'none' },
  { regime: 'stress', stopATR: '1.2', tpRMultiple: '2.0', trailATR: '1.5', maxBars: '20', decayStart: 'bar 10' },
  { regime: 'unknown', stopATR: '1.5', tpRMultiple: '4.0', trailATR: '2.5', maxBars: '40', decayStart: 'bar 30' },
];

export interface RegimeScale {
  regime: string;
  scale: string;
}

export const regimeScales: RegimeScale[] = [
  { regime: 'trending_up', scale: '1.20' },
  { regime: 'trending_down', scale: '0.60' },
  { regime: 'chop', scale: '0.50' },
  { regime: 'high_vol', scale: '0.80' },
  { regime: 'low_vol', scale: '1.00' },
  { regime: 'stress', scale: '0.40' },
  { regime: 'unknown', scale: '0.70' },
];

export interface CooldownConfig {
  cooldown: string;
  ticks: string;
  realTime: string;
  purpose: string;
}

export const cooldowns: CooldownConfig[] = [
  { cooldown: '_EXIT_COOLDOWN_TICKS', ticks: '10', realTime: '~100s', purpose: 'Prevents re-entering a recently exited symbol' },
  { cooldown: '_PENDING_ENTRY_TICKS', ticks: '30', realTime: '~5 min', purpose: 'Prevents duplicate entry submissions' },
  { cooldown: '_PENDING_EXIT_TICKS', ticks: '3', realTime: '~30s', purpose: 'Prevents duplicate exit submissions' },
];

export interface EvolutionBound {
  parameter: string;
  lower: string;
  upper: string;
}

export const evolutionBounds: EvolutionBound[] = [
  { parameter: 'stop_atr_scale', lower: '0.6', upper: '1.8' },
  { parameter: 'trailing_distance_scale', lower: '0.5', upper: '1.6' },
  { parameter: 'partial_tp_r_scale', lower: '—', upper: '1.8' },
  { parameter: 'partial_tp_pct', lower: '0.15', upper: '0.50' },
  { parameter: 'regime_size_scales (each)', lower: '0.05', upper: '1.50' },
  { parameter: 'direction_threshold_buy', lower: '0.50', upper: '0.70' },
  { parameter: 'direction_threshold_sell', lower: '1.0 - buy', upper: '—' },
  { parameter: 'symbol_fitness', lower: '0.10', upper: '0.95' },
  { parameter: 'breakout_weight_* (each)', lower: '0.10', upper: '0.40' },
  { parameter: 'alpha_weight_momentum', lower: '0.05', upper: '0.35' },
  { parameter: 'alpha_weight_regime', lower: '—', upper: '0.25' },
  { parameter: 'xgb_n_estimators', lower: '100', upper: '500' },
  { parameter: 'xgb_max_depth', lower: '3', upper: '8' },
  { parameter: 'xgb_learning_rate', lower: '0.01', upper: '0.15' },
  { parameter: 'xgb_subsample', lower: '0.60', upper: '1.0' },
  { parameter: 'xgb_colsample_bytree', lower: '0.60', upper: '1.0' },
];
