# Track DD v7 — Strategy Logic Correctness (NEW SURFACE — never audited)

V1-V6 audited infrastructure: timing, persistence, telemetry, replay
determinism, alerts, numerical precision. V7 Track DD audits the **actual
trading logic** for the first time. This is the strategy itself: alpha
factors, regime classification, exit logic, risk math, performance
attribution.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Files in scope

- `backend/organism/alpha_scanner.py` — alpha factor scoring
- `backend/organism/regime.py` — regime classification
- `backend/organism/adaptive_exits.py` — exit logic (ATR stops, FTF, horizon)
- `backend/organism/kelly_sizer.py` — position sizing
- `backend/organism/mean_reversion.py` — Ferrari v1 mean-reversion engine
- `backend/organism/orb_scanner.py` — opening-range breakout
- `backend/organism/eod_scanner.py` — end-of-day momentum
- `backend/organism/ml_features.py` — feature engineering
- `backend/organism/ml_signal.py` — ML inference + calibration
- `backend/organism/self_evolution.py` — evolution / fitness
- `backend/organism/walk_forward.py` — Sharpe / fitness gating
- `backend/organism/continuous_learner.py` — accept/reject + drift

## Method

### 1. Alpha factor correctness

For each alpha factor in `alpha_scanner.py`:
- What is the factor's intended *economic intuition*?
- Does the implementation match the intuition? (e.g. is "tension" computed
  from the right inputs at the right horizon?)
- Edge cases:
  - First N bars (warmup) — does the factor return NaN, 0, or a
    propagated nonsense value?
  - Constant-price bars (zero variance) — division by zero?
  - Single-day data — short-window factor with insufficient lookback?
- Is the score normalized? Bounded? If unbounded, what's the realistic range?
- Are scores comparable across symbols (cross-sectional)?
- **Lookahead bias**: any factor reading future data?
  - Bar-aligned features should use only `df.iloc[:-1]` or guard against
    in-progress-bar contamination.

### 2. Regime classification

`regime.py:RegimeDetector`:
- Pre-V3 regression: SMA normalization issue (V3 fixed). Re-verify on
  current state.
- Edge cases:
  - All bars at same price (zero variance) → which regime fires?
  - Stress regime threshold — when does it actually trigger?
  - Regime hysteresis — does it ping-pong on borderline inputs?
- Cross-sectional regime: `_aggregate_state` aggregates across symbols.
  Is the aggregation weight scheme defensible?
- Drift detection (DriftDetector at line 583): PSI threshold = 0.10. Is
  that calibrated? Or arbitrary?

### 3. Exit logic precedence

`adaptive_exits.py` plus exit-gating in `live_engine.py`. Multiple exit
signals can fire simultaneously:
- ATR stop
- FTF (fade-the-fade) stop tightening
- Trailing stop
- Horizon timeout (learning mode only)
- EOD flatten (15:58 ET)
- Min-hold time (mean-reversion)
- Safety net (15% loss, no features)

Build the precedence table. When two fire on the same tick:
- Which wins?
- Is the precedence consistent (deterministic)?
- Can a "soft exit" (trailing) preempt a "hard exit" (safety net) anywhere?
- The pyramid logic: when does tightening trigger vs adding?

### 4. Kelly sizing math review

`kelly_sizer.py`:
- B-T-7 fixed atr_var=0 saturation (V5/wave-18). Re-verify.
- Half-Kelly: applied uniformly?
- Per-position notional cap: enforced after Kelly fraction?
- Correlation adjustment: does the sizer account for correlated positions?
- Drawdown scaling: does Kelly shrink during drawdown?
- Confidence scaling: does Kelly scale linearly with confidence?
  (Should it?)

### 5. ML calibration logic

`continuous_learner.py:acceptance_gate`:
- New model accepted iff (a) better than old by `improvement_threshold` AND
  (b) calibration not regressed.
- What's "calibration"? Reliability diagram math correct?
- Over-fit check: training-set vs holdout-set delta — is the gate strict
  enough to prevent over-fit?
- Confidence anti-predictivity: memory.md noted
  `corr(confidence, correct_direction) = -0.112`. Has post-Ferrari-v1 changed?
  Re-measure.

### 6. Feature engineering correctness

`ml_features.py`:
- Each feature's economic intuition vs implementation.
- Lookahead bias detection: any feature that uses future bars?
- NaN propagation: how is NaN handled in feature → model pipeline?
- Feature scale: are features standardized before training? At what window?
- Categorical features: encoded how? Stable across symbols?

### 7. Risk model sanity

`live_engine.py` daily-loss circuit breaker, drawdown-kill, per-symbol
ban thresholds:
- `MAX_DAILY_LOSS` value: defensible? Hardcoded? Env-driven?
- Drawdown limit (5% default per `governance.py`): policy alignment?
- Per-symbol consecutive-loss threshold: where set, where consumed?
  (V4 Q-Q1 / V5 R-F-3 found counter-vs-reset asymmetry; re-verify.)
- Sector cap: are sectors actually mapped correctly (V6 wave-16a fixed
  SPY → "Index" but how about other symbols)?

### 8. Walk-forward fitness gating

`walk_forward.py:WalkForwardEvaluator`:
- B-T-5 fixed Sharpe-of-empty (V5). Re-verify.
- Is the look-back window (`-100:` last trades) the right size?
- Is the Sharpe comparison apples-to-apples with the prior model?
- regression_threshold=0.95 — what does 0.95 mean in this context?

### 9. Performance attribution

For trades closed today, can we attribute P&L to:
- Entry source (alpha / breakout / MR / ORB / EOD)?
- Regime at entry?
- ML confidence bucket?
- Symbol?

Verify the attribution math is consistent across reports
(`/api/v1/observability/attribution`, `_save_trade_history`,
trade_history.csv).

### 10. Lookahead bias systematic scan

A platform-wide grep for patterns that often cause lookahead:
- `.shift(-1)`, `.shift(-N)` in any feature definition.
- `df.iloc[i+1:]` reads inside a per-bar loop.
- Feature using `bars` argument that may include the current bar.

For each: triage as benign (pre-computation, e.g. labels) or bug.

## Output

`artifacts/audit/v7_reports/track_dd_strategy_logic.md` with:
- Per-component analysis (alpha, regime, exits, Kelly, ML, features, risk, fitness, attribution)
- Lookahead bias scan results
- Exit precedence table
- Edge-case verdicts (warmup, zero-variance, single-day, etc.)
- "Bugs found: N" by severity
- TL;DR

## Constraints

Read-only. `./venv/bin/python` ok for synthetic edge-case probes.

## Quality bar

This is the FIRST audit of the trading logic itself. Expect 5-12 findings.
Especially:
- A factor that returns nonsense on warm-up data
- An exit that can't fire when it should (precedence inversion)
- A Kelly path that under/over-sizes a known scenario
- A lookahead bias somewhere in feature engineering
- A regime that ping-pongs on a borderline input

End with a one-paragraph summary including the single highest-impact
strategy-logic finding.
