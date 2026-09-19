# Track DD2 v8 — Strategy Logic Deeper Pass

V7 DD found 11 strategy-logic bugs in 1 round (DD-1 _safe_div(0,0)=NaN, DD-2 regime UNKNOWN on missing ATR, DD-7 system anti-predictivity, etc.). **DD2 drills into harder edges**: Kelly under partial fills, regime hysteresis at boundaries, exit precedence under partial fills, ML feature staleness, confidence calibration drift.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Method

This is the deepest track. Read each subsystem with the lens "what edge case would the tests miss but production would hit?"

### 1. Kelly under partial fills

`backend/organism/kelly_sizer.py`. Read top-to-bottom. Specifically:
- If a partial fill comes in at qty=3 of a planned 10, does Kelly recalc on remaining 7 use stale or fresh edge stats?
- If edge stats were computed at signal time but now market moved, is the unfilled portion still sized at the original Kelly?
- Edge case: planned_qty=10, filled=10 instantly, but 9 of those are partials with progressively worse fill prices → does the realized average price feed back into the next Kelly call or are stats based on the original signal price?

Construct 2-3 unit-test scenarios in your head; compare against actual code paths. Report any that diverge.

### 2. Regime hysteresis at boundaries

`backend/organism/regime.py` — `RegimeDetector.detect()`. Specifically:
- If ATR is right at the trending↔chop boundary, does the detector flap on every bar?
- Is there hysteresis (sticky state) or does it freely transition?
- DD-2 wave-24 fix returns UNKNOWN on missing ATR; what about partial-NaN ATR (e.g. window not full)?
- Inverse-ETF regime flip in `_regime_alignment(symbol)` — verify SH/PSQ flip works correctly at trending_down→trending_up boundary.

### 3. Exit precedence under partial fills

`backend/organism/adaptive_exits.py` + `live_engine.py` exit path. Specifically:
- If stop-loss and time-stop both fire on the same bar, which wins?
- If a TP order is partially filled and the remainder hits stop, does the position close cleanly or leak qty=remainder?
- ExitLevels v4 (H5) restored ftf_stop_tightened; verify it survives a restart mid-trade (state in JSON?).
- Pending-exit cooldown (wave-29 stage 0a extracted): does it correctly clear on terminal IDs?

### 4. ML feature staleness

`backend/features/feature_engineering.py` + `backend/organism/brain.py` ML path:
- If a feature returns NaN (e.g. divide-by-zero in indicator), is it imputed or does it propagate to predict()?
- Are features computed in the same order as training? (Order-sensitive ML drift.)
- ML AUDIT noted `corr(confidence, correct_direction) = -0.112` (anti-predictive). DD-7 flagged this. Is there now a system-level acceptance gate that catches anti-predictivity? Or is it still memory-only?

### 5. Confidence calibration drift

V6/V7 noted `effective_confidence` blends multiple signals. Specifically:
- In learning-mode, H2 says `_eff_conf = 0.65×breakout + 0.35×tension` (no ML). Verify in code that NO ML term sneaks in.
- In production-mode, `0.50×ml + 0.30×breakout + 0.20×tension`. Verify weights sum to 1.0 (no normalization bug).
- Threshold = 0.65 in learning, 0.55 in production (per memory). Confirm in source.
- What happens when ML throws (returns None or 0)? Does the blend silently lose its biggest contributor and still trade?

### 6. Burst cap + cooldown precedence (improve8)

If 3 trades within 15min cap is hit, but a 4th has BOTH high confidence AND a stop already armed → does cap reject it cleanly or does an exit-cooldown bug let it through?

### 7. Inverse ETF specifics

SH (S&P short) and PSQ (Nasdaq short) added in V4. Verify:
- Do they get the same liquidity gate treatment? (Memory says liquidity gate is share-count and blocks high-priced names — not the same issue here, both are <$15.)
- regime alignment flip is symbol-specific. Verify SH and PSQ both flip; what about UPRO/SQQQ if added later?

### 8. Self-evolution + warm-start interaction

H4 gates warm-start on 300-trade freeze. Specifically:
- If trades=299 and a warm-start fires, does the 300th trade unfreeze and immediately re-warm-start? (Race.)
- If warm-start params land mid-tick, do live signals using those params see the old or new values within the tick?

### 9. EOD flatten + opening cross

improve7 added EOD flatten. Verify:
- 16:00:00 ET sharp — is there a window where flatten orders submit AFTER market close?
- If flatten fails (e.g. broker rejects), is there a retry or does the position carry overnight?
- Opening cross (9:30:00) — does the first bar trigger any time-based signal that wasn't intended?

### 10. Subtle replay-determinism gaps

- `_now_fn` injection — wave-27 added `default_now_fn` helper. Are all 9 listed classes using it, or are some still using `datetime.now(UTC)` directly?
- A grep for `datetime\.now\(UTC\)` in `backend/organism/` should yield only legitimate one-shot reads (e.g. logging timestamps), not control-path uses.

## Output

`artifacts/audit/v8_reports/track_dd2_strategy_logic_deeper.md` with:
- Findings table per subsystem (1-9 above) with severity + description + reproduction
- Specific source-file:line citations
- For each finding, a behavioral test the audit would write to lock the regression (no need to write the test — describe it)
- "DD2 findings: N (Critical/High/Medium/Low breakdown)" + TL;DR

Quality bar: 3-7 findings. If DD2 finds <3, V8 confirms strategy logic is converging. If >7, the cycle has more strategy debt than V7 disclosed. End with one-paragraph summary.
