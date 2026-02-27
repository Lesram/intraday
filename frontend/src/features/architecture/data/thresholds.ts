export interface Threshold {
  threshold: string;
  value: string;
  location: string;
  purpose: string;
}

export const thresholds: Threshold[] = [
  { threshold: 'Alpha composite minimum', value: '0.15', location: 'alpha_scanner', purpose: 'Minimum score to be a candidate' },
  { threshold: 'Breakout composite minimum', value: '0.20', location: 'breakout_scanner', purpose: 'Minimum breakout score' },
  { threshold: 'Pure breakout entry threshold', value: '0.55', location: 'live_engine', purpose: 'Breakout-only entries need high score' },
  { threshold: 'Symbol fitness gate', value: '0.35', location: 'live_engine', purpose: 'Chronic loser rejection' },
  { threshold: 'ML confidence reversal', value: '0.30', location: 'live_engine', purpose: 'ML reversal exit confidence floor' },
  { threshold: 'Max loss safety net', value: '15%', location: 'adaptive_exits', purpose: 'Absolute loss limit' },
  { threshold: 'Kelly ML floor', value: '0.08 x conf', location: 'kelly_sizer', purpose: 'Minimum sizing when ML confident' },
  { threshold: 'Kelly breakout floor', value: '0.01 x score', location: 'kelly_sizer', purpose: 'Minimum sizing on strong breakout' },
  { threshold: 'Kelly min notional', value: '$2,000', location: 'kelly_sizer', purpose: 'Minimum position size' },
  { threshold: 'Kelly max per position', value: '10%', location: 'kelly_sizer', purpose: 'Position concentration limit' },
  { threshold: 'Kelly max portfolio', value: '95%', location: 'kelly_sizer', purpose: 'Total exposure limit' },
  { threshold: 'Drawdown risk-off', value: '25%', location: 'kelly_sizer', purpose: 'No new positions at all' },
  { threshold: 'Drawdown kill switch', value: '8%', location: 'governance', purpose: 'Halt all entries' },
  { threshold: 'Intraday size reduction', value: '40%', location: 'live_engine', purpose: 'First/last 15 min of session' },
  { threshold: 'Equity-zero threshold', value: '3 consecutive', location: 'live_engine', purpose: 'Block entries on stale data' },
  { threshold: 'Walk-forward regression', value: '0.95', location: 'brain_persistence', purpose: "Don't persist regressing model" },
  { threshold: 'Feature QA NaN rate', value: '20%', location: 'feature_store', purpose: 'Reject feature set' },
  { threshold: 'Feature QA missing bars', value: '10%', location: 'feature_store', purpose: 'Flag data quality issue' },
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
  { variable: 'ORGANISM_MAX_POSITIONS', default: '15', production: '15', effect: 'Max simultaneous positions' },
  { variable: 'ORGANISM_LONG_ONLY', default: 'true', production: 'true', effect: 'Block all short entries' },
  { variable: 'ORGANISM_RETRAIN_INTERVAL', default: '60', production: '200', effect: 'Ticks between retrains' },
  { variable: 'ORGANISM_ML_DECAY_RATE', default: '0.005', production: '0.005', effect: 'Time-decay on training samples' },
  { variable: 'ORGANISM_MAX_PER_SECTOR', default: '4', production: '4', effect: 'Sector concentration limit' },
  { variable: 'ORGANISM_DRAWDOWN_KILL_PCT', default: '0.03', production: '0.08', effect: 'Drawdown kill switch' },
  { variable: 'ORGANISM_LIVE_LOOKBACK', default: '500', production: '500', effect: 'Bars of history to fetch' },
  { variable: 'ORGANISM_MIN_BARS', default: '200', production: '50', effect: 'Minimum bars for a symbol' },
  { variable: 'ORGANISM_NIGHTLY_ENABLED', default: '0', production: '0', effect: 'Nightly training cycle' },
  { variable: 'ORGANISM_HALT_TRADING', default: '0', production: '0', effect: 'Manual trading halt' },
  { variable: 'ORGANISM_FREEZE_ADAPTATION', default: '0', production: '0', effect: 'Freeze all adaptation' },
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
