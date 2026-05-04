"""
Module 4 — Kelly Position Sizer **v2**.

v2 changes (per BREAKOUT_ALPHA_BLUEPRINT.md §Module-D):
    * max_position_pct  5% → 10%  (bigger bets on high-conviction; was 12%, reduced)
    * min_position_usd  $500 → $2 000  (no micro-positions)
    * Breakout-score bonus sizing: 1.5× if score >0.7, 2.0× if >0.85
    * Confidence scaling widened: [0.3, 1.5] (was [0.5, 1.0])
    * Regime scaling more aggressive in trending (1.2× trending_up)
    * Pyramid-aware: initial entry = 60% of target (pyramider adds rest)

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §Module-D
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Computed position sizing recommendation."""
    symbol: str
    target_weight: float        # % of portfolio
    shares: int                 # Discrete share count
    notional: float             # Dollar value
    kelly_raw: float            # Raw Kelly fraction
    kelly_half: float           # Half-Kelly (what we actually use)
    drawdown_scale: float       # [0, 1] drawdown multiplier
    vol_scale: float            # Volatility-target multiplier
    regime_scale: float         # Regime-based multiplier
    direction: float            # +1 long, -1 short
    confidence: float = 0.0
    predicted_return: float = 0.0
    breakout_score: float = 0.0
    regime_scale_source: str = "static"        # "static_frozen" or "evolved"
    regime_trade_count: int = 0                # trades in current regime
    expected_return_source: str = "heuristic"  # "ml", "calibrated_breakout", "heuristic"
    dollar_risk_cap_applied: bool = False
    # M3-bug-fix: ORB/EOD candidates pass through cand_dict["entry_source_override"]
    # to tag the trade as orb_sip / eod_momentum / orb_sip_inverse / eod_momentum_inverse.
    # Without this field on PositionSize, the override silently fell through to
    # the breakout-score-inference fallback, mis-tagging ORB/EOD trades as
    # "alpha+breakout" or "breakout" in trade_history. Hidden bug found in M3-5
    # audit when B3 (alpha disabled) still showed "alpha+breakout" tags.
    entry_source_override: str = ""

    def to_dict(self) -> dict[str, Any]:
        # Audit-I finding I-4 (2026-05-02): cast every numeric through
        # native float() so np.float64/np.bool_ values from inference
        # don't poison JSON serialization. The decision_telemetry.py
        # equivalent was patched in commit a1713d7; this sister method
        # carried the same un-cast pattern.
        return {
            "symbol": self.symbol,
            "target_weight": round(float(self.target_weight), 4),
            "shares": int(self.shares),
            "notional": round(float(self.notional), 2),
            "kelly_raw": round(float(self.kelly_raw), 4),
            "kelly_half": round(float(self.kelly_half), 4),
            "drawdown_scale": round(float(self.drawdown_scale), 4),
            "vol_scale": round(float(self.vol_scale), 4),
            "regime_scale": round(float(self.regime_scale), 4),
            "direction": float(self.direction),
            "confidence": round(float(self.confidence), 4),
            "predicted_return": round(float(self.predicted_return), 6),
            "breakout_score": round(float(self.breakout_score), 4),
            "regime_scale_source": str(self.regime_scale_source),
            "regime_trade_count": int(self.regime_trade_count),
            "expected_return_source": str(self.expected_return_source),
            "dollar_risk_cap_applied": bool(self.dollar_risk_cap_applied),
        }


class KellySizer:
    """Half-Kelly position sizing with breakout bonuses + regime stratification.

    v2 pipeline:
        1. Raw Kelly  = mean_return / variance
        2. Half-Kelly = Kelly × 0.5
        3. Scale by drawdown level
        4. Scale by volatility target (15 % annualised)
        5. Scale by regime (more aggressive in trending)
        6. Scale by confidence [0.3 … 1.5] (wider than v1)
        7. **NEW** — breakout score bonus (1.5× / 2.0×)
        8. Enforce per-position max (10 %), total portfolio max (95 %)
        9. Convert to shares; min position $2 000

    v3 addition: regime-stratified Kelly — per-regime win_rate/payoff tracking.
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,      # 10 % max per position (was 12 %)
        max_portfolio_pct: float = 0.95,      # 95 % max total invested
        vol_target: float = 0.15,             # 15 % annualised vol target
        drawdown_floor: float = 0.1,          # Scale to 10 % at max dd
        max_drawdown_cutoff: float = 0.25,    # Full risk-off threshold
        min_position_usd: float = 2000.0,     # Min position (was $500)
        bars_per_day: int = 1,                # 390 for 1Min, 78 for 5Min, etc.
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_pct = max_portfolio_pct
        self.vol_target = vol_target
        self.drawdown_floor = drawdown_floor
        self.max_drawdown_cutoff = max_drawdown_cutoff
        self.min_position_usd = min_position_usd
        self._bars_per_day = bars_per_day

        # ML confidence floor: when trained ML has confidence >= _ML_CONFIDENCE_MIN,
        # allow a small position so signals aren't silenced.
        # Trained: 0.04 × conf, Untrained: 0.02 × conf (inline in size_positions)
        # Both require edge_clears_cost gate to pass.
        self._ML_CONFIDENCE_MIN = 0.5

        # Regime-stratified Kelly stats: {regime: {wins, losses, total_pnl, total_win_pnl, total_loss_pnl}}
        self._regime_stats: dict[str, dict[str, float]] = {}
        # Last sizing intermediates for telemetry (confidence_scale, breakout_bonus per symbol)
        self._last_intermediates: dict[str, dict[str, float]] = {}

    def _estimate_spread_cost(
        self,
        symbol: str,
        quote_provider: Callable[[str], dict[str, Any]] | None,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> float:
        """Per-symbol dynamic spread cost from live quote, time-of-day, and liquidity.

        Returns spread_cost_pct clamped to [3bps, 50bps].
        """
        from backend.utils.market_hours import get_slippage_multiplier

        # 1. Base spread from live bid/ask (fallback: 10bps)
        base_spread = 0.0010
        if quote_provider is not None:
            try:
                quote = quote_provider(symbol)
                bid = quote.get("bid")
                ask = quote.get("ask")
                if bid and ask and bid > 0 and ask > 0:
                    mid = (bid + ask) / 2.0
                    base_spread = (ask - bid) / mid
            except Exception:
                pass  # keep default

        # 2. Time-of-day multiplier
        time_mult = get_slippage_multiplier()

        # 3. Liquidity adjustment from vol_sma_ratio
        liquidity_mult = 1.0
        df = features_by_symbol.get(symbol)
        if df is not None and "vol_sma_ratio" in df.columns and len(df) > 0:
            vol_ratio = float(df["vol_sma_ratio"].iloc[-1])
            if math.isfinite(vol_ratio) and vol_ratio > 0:
                liquidity_mult = 1.0 + max(0.0, 1.0 - vol_ratio) * 0.5

        cost = base_spread * time_mult * liquidity_mult
        return max(0.0003, min(cost, 0.0050))

    # Pre-Kelly risk-budget sizing constants
    _RISK_BUDGET_PER_TRADE = 0.0025   # 0.25% of equity risked per trade (production)
    _RISK_BUDGET_PER_TRADE_LEARNING = 0.0010  # 0.10% of equity risked per trade (learning mode)
    _RISK_BUDGET_STOP_ATR = 1.5       # Assumed stop distance in ATR multiples
    # H4 FIX: Use shared threshold from trading_phase module
    from backend.organism.trading_phase import LEARNING_MODE_TRADES as _RISK_BUDGET_TRADE_THRESHOLD

    def size_positions(
        self,
        candidates: list[dict[str, Any]],
        portfolio_value: float,
        current_drawdown: float,
        features_by_symbol: dict[str, pd.DataFrame],
        current_regime: str = "unknown",
        ml_is_trained: bool = True,
        quote_provider: Callable[[str], dict[str, Any]] | None = None,
        trade_count: int | None = None,
    ) -> list[PositionSize]:
        """Size positions for a list of alpha candidates.

        Parameters
        ----------
        candidates : list of dicts with keys:
            symbol, direction, confidence, predicted_return,
            breakout_score (optional, 0-1 from BreakoutScanner)
        portfolio_value : current portfolio equity
        current_drawdown : current drawdown as positive fraction (0.10 = 10 %)
        features_by_symbol : {symbol: feature DataFrame} for vol data
        current_regime : from regime detector

        Returns
        -------
        List of PositionSize objects, sorted by target_weight descending.
        """
        if portfolio_value <= 0 or current_drawdown >= self.max_drawdown_cutoff:
            return []

        # Sort candidates by conviction (highest first) so best entries
        # get allocation priority before portfolio cap is consumed.
        # Learning mode: predicted_return is heuristic noise — sort by
        # breakout quality + confidence instead of predicted_return * confidence.
        # Production mode: full predicted_return * confidence ranking.
        _is_learning_mode = (trade_count is not None and trade_count < self._RISK_BUDGET_TRADE_THRESHOLD)
        if _is_learning_mode:
            # Preserve upstream ranking_score when available (set by
            # live_engine from alpha/breakout composite scores). Only
            # fall back to local heuristic if ranking_score is absent.
            _has_ranking = any(c.get("ranking_score") is not None for c in candidates)
            if _has_ranking:
                candidates = sorted(
                    candidates,
                    key=lambda c: c.get("ranking_score", 0.0),
                    reverse=True,
                )
            else:
                candidates = sorted(
                    candidates,
                    key=lambda c: c.get("breakout_score", 0.0) * 0.6 + c.get("confidence", 0.0) * 0.4,
                    reverse=True,
                )
        else:
            candidates = sorted(
                candidates,
                key=lambda c: abs(c.get("predicted_return", 0.0)) * c.get("confidence", 0.5),
                reverse=True,
            )

        sizes: list[PositionSize] = []
        total_weight = 0.0
        self._last_intermediates = {}
        self._exploration_rejects: list[dict[str, Any]] = []

        for cand in candidates:
            symbol = cand["symbol"]
            direction = cand.get("direction", 0.0)
            predicted_return = abs(cand.get("predicted_return", 0.0))
            confidence = cand.get("confidence", 0.5)
            breakout_score = cand.get("breakout_score", 0.0)

            # Floor predicted_return: when ML is untrained, breakout signals
            # arrive with predicted_return=0. Use a conservative default so
            # the sizer can still allocate based on breakout score + confidence.
            untrained_floor = 0.005 if not ml_is_trained else 0.01
            if predicted_return < 1e-6 and breakout_score > 0:
                predicted_return = untrained_floor

            # Guard against NaN / Inf / invalid values
            if (
                direction == 0
                or predicted_return < 1e-6
                or math.isnan(direction)
                or math.isnan(predicted_return)
                or math.isinf(direction)
                or math.isinf(predicted_return)
            ):
                continue

            # Get recent returns for Kelly calculation
            df = features_by_symbol.get(symbol)
            if df is None or len(df) < 30:
                continue

            ret_col = "ret_1d" if "ret_1d" in df.columns else None
            if ret_col is None:
                if "close" in df.columns:
                    returns = df["close"].pct_change().dropna().values[-60:]
                else:
                    continue
            else:
                returns = df[ret_col].dropna().values[-60:]

            if len(returns) < 20:
                continue

            # Directional returns based on signal
            dir_returns = returns * direction

            # Compute ATR-derived risk measure for sizing.
            # Prefer true ATR from OHLC (true_range_pct feature) when available;
            # fall back to return volatility if OHLC columns are missing.
            _atr_from_ohlc = False
            if (
                df is not None
                and "high" in df.columns
                and "low" in df.columns
                and "close" in df.columns
                and len(df) >= 20
            ):
                _high = df["high"].values[-20:]
                _low = df["low"].values[-20:]
                _close = df["close"].values[-20:]
                _prev_close = np.concatenate(([_close[0]], _close[:-1]))
                _true_ranges = np.maximum(
                    _high - _low,
                    np.maximum(
                        np.abs(_high - _prev_close),
                        np.abs(_low - _prev_close),
                    ),
                )
                _avg_tr = float(np.mean(_true_ranges))
                _last_close = float(_close[-1])
                if _last_close > 0 and np.isfinite(_avg_tr) and _avg_tr > 0:
                    atr_pct = _avg_tr / _last_close
                    _atr_from_ohlc = True

            if not _atr_from_ohlc:
                # Fallback: return volatility (stddev of returns).
                # This is NOT true ATR but provides a reasonable risk
                # estimate when OHLC data is unavailable.
                atr_pct = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01

            # ── Learning mode vs Production sizing ──
            # improve9: In learning mode, Kelly is OFF. Predicted returns are
            # 22x overstated and ML is uncalibrated — feeding these into Kelly
            # produces noise-driven leverage, not edge-driven sizing.
            # Instead: fixed ATR-dollar risk sizing only.
            _is_learning = (trade_count is not None and trade_count < self._RISK_BUDGET_TRADE_THRESHOLD)
            ml_floor_applied = False
            _risk_budget_applied = False
            _dollar_risk_cap_applied = False
            kelly_raw = 0.0
            kelly_half = 0.0
            confidence_scale = 1.0
            breakout_bonus = 1.0
            regime_scale = 1.0
            vol_scale = 1.0
            _regime_scale_source = "static_frozen"
            _regime_trade_count = 0
            spread_cost_pct = 0.0

            # 3. Drawdown scaling (always active)
            drawdown_scale = self._drawdown_scale(current_drawdown)

            # 5. Regime scaling (always active for safety).
            # V11 prep / Wave-60 (DD4-3 closure): use the symbol-aware
            # effective regime so SH/PSQ/DOG/RWM (inverse ETFs) get
            # sized against the flipped regime label — matching the
            # AlphaScanner score and the AdaptiveExits stop math.
            from backend.organism.regime import effective_regime_for_symbol
            _eff_regime = effective_regime_for_symbol(current_regime, symbol)
            regime_scale, _regime_scale_source, _regime_trade_count = self._regime_scale(_eff_regime)

            if _is_learning:
                # ── LEARNING MODE: Fixed ATR-dollar risk sizing ──
                # No Kelly, no confidence scaling, no breakout bonus.
                # Size = risk_budget / stop_distance, capped by notional.
                _risk_rate = self._RISK_BUDGET_PER_TRADE_LEARNING  # 0.10% equity
                _stop_dist = atr_pct * self._RISK_BUDGET_STOP_ATR
                if _stop_dist > 1e-6:
                    target_weight = _risk_rate / _stop_dist
                else:
                    target_weight = _risk_rate / 0.01  # fallback
                target_weight *= drawdown_scale
                target_weight *= regime_scale
                _risk_budget_applied = True

            else:
                # ── PRODUCTION MODE: Full Kelly stack ──
                # 1. Raw Kelly (try regime-stratified first, fallback to global).
                # V7 DD-4 / Wave-24 (2026-05-03): the previous
                # `regime_kelly` shortcut bypassed the spread-cost gate,
                # ML-confidence floor, and breakout floor — once a
                # regime accumulated ≥10 trades, ANY candidate sized
                # from regime_kelly regardless of current edge. Now:
                # only use regime_kelly when (a) the candidate has a
                # positive predicted return, (b) confidence clears the
                # production-mode threshold, AND (c) the unconditional
                # Kelly path also computes a positive size. This makes
                # regime_kelly an UPPER bound (when present) rather
                # than a bypass — current-edge floors still apply.
                _PROD_CONFIDENCE_FLOOR = 0.5
                regime_kelly = self.get_regime_kelly(current_regime)
                # V8 DD2-5 / Wave-34 (2026-05-03): the regime_eligible branch
                # was bypassing wave-18's zero-vol refusal entirely (refer to
                # the else branch _ATR_VAR_MIN check below).  When regime
                # stats existed and a candidate cleared the production-mode
                # gates, kelly_raw was sized from regime_kelly even on a bar
                # with effectively no measured volatility.  Now: check
                # zero-vol up-front; if it engages, fall through to the
                # unconditional path which already refuses to size.
                _horizon_bars = 15
                _ATR_VAR_MIN = 1e-6
                _atr_var_squared_pre = (atr_pct * math.sqrt(_horizon_bars)) ** 2
                _regime_eligible = (
                    regime_kelly is not None
                    and predicted_return > 0
                    and confidence >= _PROD_CONFIDENCE_FLOOR
                    and _atr_var_squared_pre >= _ATR_VAR_MIN
                )
                if _regime_eligible:
                    kelly_raw = min(regime_kelly, 1.0)
                else:
                    mean_r = float(np.mean(dir_returns))
                    var_r = float(np.var(dir_returns, ddof=1))

                    if var_r < 1e-8 or mean_r <= 0 or not math.isfinite(mean_r) or not math.isfinite(var_r):
                        unconditional_kelly = 0.0
                    else:
                        unconditional_kelly = min(mean_r / var_r, 1.0)

                    atr_pct_horizon = atr_pct * math.sqrt(_horizon_bars)
                    # V5 B-T-7 / Wave-18 (2026-05-03): the previous
                    # `atr_var = max(atr_pct_horizon**2, 1e-6)` floor
                    # let near-zero-vol bars saturate signal_kelly to
                    # the per-position max (1.0) — `predicted_return /
                    # 1e-6` is huge, then clamped to 1.0. Result: Kelly
                    # commits the maximum allowed size on a bar with
                    # essentially no measured volatility, exactly when
                    # we have the LEAST signal. Refuse-to-size instead
                    # by zeroing signal_kelly when the floor would
                    # have engaged. We still keep the unconditional
                    # Kelly path (mean/var of historical returns) for
                    # the regime so the sizer isn't crippled — only
                    # the no-vol shortcut is closed.
                    _ATR_VAR_MIN = 1e-6
                    atr_var_squared = atr_pct_horizon ** 2
                    if atr_var_squared < _ATR_VAR_MIN:
                        # Zero-volatility bar: refuse to size from this
                        # signal; rely on unconditional Kelly only.
                        signal_kelly = 0.0
                    elif predicted_return > 0:
                        signal_kelly = min(predicted_return / atr_var_squared, 1.0)
                    else:
                        signal_kelly = 0.0
                    kelly_raw = min(max(signal_kelly, unconditional_kelly), 1.0)

                # 2. Half-Kelly
                kelly_half = kelly_raw * 0.5

                # Edge-over-cost gate
                spread_cost_pct = self._estimate_spread_cost(
                    symbol, quote_provider, features_by_symbol,
                )
                _COST_MULT = 2.0
                edge_clears_cost = predicted_return >= spread_cost_pct * _COST_MULT

                # Breakout floor
                if kelly_half < 0.005 and breakout_score >= 0.55:
                    if edge_clears_cost:
                        kelly_half = max(kelly_half, 0.003 * breakout_score)

                # ML confidence floor
                _regime_has_edge = True
                _rs = self._regime_stats.get(current_regime)
                if _rs:
                    _total_trades = _rs["wins"] + _rs["losses"]
                    if _total_trades >= 5 and _rs["total_pnl"] <= 0:
                        _regime_has_edge = False

                if kelly_half < 0.005 and confidence >= self._ML_CONFIDENCE_MIN and _regime_has_edge and edge_clears_cost:
                    ml_floor = 0.04 * confidence
                    kelly_half = max(kelly_half, ml_floor)
                    ml_floor_applied = True

                if not edge_clears_cost and kelly_half < 0.005:
                    # H3 INSTRUMENTATION: Log candidates rejected solely by
                    # edge-over-cost gate for post-session analysis.
                    _other_gates_would_pass = (
                        confidence >= 0.25
                        and breakout_score >= 0.0
                        and _regime_has_edge
                    )
                    if _other_gates_would_pass:
                        _logger.info(
                            "EDGE_COST_REJECT: %s regime=%s conf=%.3f "
                            "breakout=%.3f pred_ret=%.6f spread_cost=%.6f "
                            "ratio=%.2f other_gates_pass=%s",
                            symbol, current_regime, confidence,
                            breakout_score, predicted_return,
                            spread_cost_pct, (
                                predicted_return / (spread_cost_pct * _COST_MULT)
                                if spread_cost_pct * _COST_MULT > 0 else 0
                            ),
                            _other_gates_would_pass,
                        )
                    kelly_half = 0.0

                # 4. Volatility targeting
                ann_vol = float(np.std(returns, ddof=1)) * np.sqrt(252 * self._bars_per_day)
                vol_scale = min(self.vol_target / max(ann_vol, 0.01), 2.0)

                # 6. Confidence scaling
                _eff_conf = cand.get("effective_confidence", confidence)
                confidence_scale = 0.3 + min(_eff_conf, 1.0) * 1.2

                # 7. Breakout bonus
                breakout_bonus = self._breakout_bonus(breakout_score)

                target_weight = (
                    kelly_half
                    * drawdown_scale
                    * vol_scale
                    * regime_scale
                    * confidence_scale
                    * breakout_bonus
                )

            # Store intermediates for telemetry
            self._last_intermediates[symbol] = {
                "confidence_scale": confidence_scale,
                "breakout_bonus": breakout_bonus,
                "ml_floor_applied": ml_floor_applied,
                "risk_budget_applied": _risk_budget_applied,
                "kelly_raw": kelly_raw,
                "kelly_half": kelly_half,
                "spread_cost_pct": spread_cost_pct,
                "regime_scale_source": _regime_scale_source,
                "regime_trade_count": _regime_trade_count,
                "expected_return_source": cand.get("expected_return_source", "heuristic"),
                "dollar_risk_cap_applied": _dollar_risk_cap_applied,
            }

            # Enforce per-position cap
            target_weight = max(0.0, min(target_weight, self.max_position_pct))

            # Check portfolio-level cap
            if total_weight + target_weight > self.max_portfolio_pct:
                target_weight = max(0.0, self.max_portfolio_pct - total_weight)

            if target_weight < 0.0005:  # was 0.001 — too aggressive in stress
                self._exploration_rejects.append({
                    "symbol": symbol, "reason": "weight_too_small",
                    "confidence": confidence, "breakout_score": breakout_score,
                    "predicted_return": predicted_return, "direction": direction,
                })
                continue

            # Convert to shares
            current_price = float(df["close"].iloc[-1]) if "close" in df.columns else 0
            if current_price <= 0:
                continue

            notional = portfolio_value * target_weight
            if notional < self.min_position_usd:
                _logger.info("Kelly skip %s: notional=%.0f < min=%d", symbol, notional, self.min_position_usd)
                self._exploration_rejects.append({
                    "symbol": symbol, "reason": "below_min_notional",
                    "confidence": confidence, "breakout_score": breakout_score,
                    "predicted_return": predicted_return, "direction": direction,
                })
                continue

            shares = int(notional / current_price)
            if shares < 1:
                continue

            # A4 (improve8): Learning-mode dollar-risk cap + notional cap
            if _is_learning:
                # Dollar-risk cap: max risk = 0.10% of equity
                _max_risk_dollars = portfolio_value * 0.0010
                _stop_dist_price = atr_pct * self._RISK_BUDGET_STOP_ATR * current_price
                if _stop_dist_price > 0:
                    _risk_capped_shares = int(_max_risk_dollars / _stop_dist_price)
                    if shares > _risk_capped_shares and _risk_capped_shares >= 1:
                        shares = _risk_capped_shares
                        _dollar_risk_cap_applied = True
                # Notional cap: max 5% of equity per position in learning mode
                _max_notional = portfolio_value * 0.05
                _notional_capped_shares = int(_max_notional / current_price)
                if shares > _notional_capped_shares and _notional_capped_shares >= 1:
                    shares = _notional_capped_shares
                    _dollar_risk_cap_applied = True

            # H1: Production-mode per-trade risk-budget cap.
            # The learning-mode cap (0.10% equity, lines 488-502) only
            # applies when _is_learning=True. In production mode, Kelly
            # sizing is uncapped beyond per-position % limits. This
            # leaves a real-money gap: no per-trade dollar-risk limit.
            #
            # Fix: apply _RISK_BUDGET_PER_TRADE (0.25% equity) as a
            # hard cap on shares, using the same ATR-stop-distance
            # formula as the learning-mode cap.
            if not _is_learning and not _risk_budget_applied:
                _prod_max_risk = portfolio_value * self._RISK_BUDGET_PER_TRADE
                _prod_stop_dist = atr_pct * self._RISK_BUDGET_STOP_ATR * current_price
                if _prod_stop_dist > 0:
                    _prod_risk_shares = int(_prod_max_risk / _prod_stop_dist)
                    if shares > _prod_risk_shares and _prod_risk_shares >= 1:
                        shares = _prod_risk_shares
                        _dollar_risk_cap_applied = True

            actual_notional = shares * current_price
            actual_weight = actual_notional / portfolio_value

            total_weight += actual_weight

            sizes.append(PositionSize(
                symbol=symbol,
                target_weight=actual_weight,
                shares=shares,
                notional=actual_notional,
                kelly_raw=kelly_raw,
                kelly_half=kelly_half,
                drawdown_scale=drawdown_scale,
                vol_scale=vol_scale,
                regime_scale=regime_scale,
                direction=direction,
                confidence=confidence,
                predicted_return=predicted_return,
                breakout_score=breakout_score,
                regime_scale_source=_regime_scale_source,
                regime_trade_count=_regime_trade_count,
                expected_return_source=cand.get("expected_return_source", "heuristic"),
                dollar_risk_cap_applied=_dollar_risk_cap_applied,
                entry_source_override=cand.get("entry_source_override", ""),
            ))

        sizes.sort(key=lambda s: s.target_weight, reverse=True)
        return sizes

    def _drawdown_scale(self, drawdown: float) -> float:
        """Map current drawdown to position scale factor.

        Linear scale: 0% dd → 1.0, max_drawdown_cutoff → drawdown_floor
        """
        if drawdown <= 0:
            return 1.0
        if drawdown >= self.max_drawdown_cutoff:
            return self.drawdown_floor

        frac = drawdown / self.max_drawdown_cutoff
        return 1.0 - frac * (1.0 - self.drawdown_floor)

    def _regime_scale(self, regime: str) -> tuple[float, str, int]:
        """Reduce sizing in unfavorable regimes — v2 more aggressive in trends.

        If EvolutionEngine has set ``_evolved_regime_scales``, those
        override the static defaults (EvolutionEngine learns which
        regimes are truly profitable from trade outcomes).

        v4 (improve7): Freeze evolved scales until we have 200+ trades
        AND 30+ trades in each major regime. Early evolved scales are
        statistically unstable and can cause mis-sizing.

        Returns (scale, source, regime_trade_count).
        """
        _regime_trades = 0
        if regime in self._regime_stats:
            rs = self._regime_stats[regime]
            _regime_trades = int(rs["wins"] + rs["losses"])

        # Use evolved scales if available AND statistically stable
        if hasattr(self, "_evolved_regime_scales") and self._evolved_regime_scales:
            _total_trades = sum(
                s["wins"] + s["losses"] for s in self._regime_stats.values()
            ) if self._regime_stats else 0
            # Only use evolved scales with 200+ total trades and 30+ in this regime
            if _total_trades >= 200 and _regime_trades >= 30:
                scale = self._evolved_regime_scales.get(regime)
                if scale is not None:
                    return (float(scale), "evolved", _regime_trades)

        scales = {
            "trending_up": 1.2,
            "trending_down": 0.6,
            "chop": 0.5,
            "high_vol": 0.8,    # was 0.5 — winners undersized while stops deliver full-sized losses
            "low_vol": 1.0,         # calm market → full sizing
            "stress": 0.4,           # was 0.3 — still 60% reduction, avoids 0-sizing cascade
            "unknown": 0.7,         # insufficient data → conservative
        }
        return (scales.get(regime, 0.7), "static_frozen", _regime_trades)

    @staticmethod
    def _breakout_bonus(breakout_score: float) -> float:
        """Bonus sizing multiplier for high breakout scores.

        Returns
        -------
        1.0 if score < 0.5 (no bonus)
        1.5 if score >= 0.7 (confirmed breakout)
        2.0 if score >= 0.85 (high-conviction breakout)
        Linear interpolation in between.
        """
        if breakout_score < 0.5:
            return 1.0
        if breakout_score >= 0.85:
            return 2.0
        if breakout_score >= 0.7:
            # Interpolate 1.5 → 2.0 for 0.7 → 0.85
            return 1.5 + (breakout_score - 0.7) / 0.15 * 0.5
        # Interpolate 1.0 → 1.5 for 0.5 → 0.7
        return 1.0 + (breakout_score - 0.5) / 0.2 * 0.5

    # ── Regime-stratified Kelly ──────────────────────────────────

    def record_trade(self, regime: str, pnl: float) -> None:
        """Record a completed trade outcome for regime-stratified Kelly."""
        if regime not in self._regime_stats:
            self._regime_stats[regime] = {
                "wins": 0, "losses": 0,
                "total_pnl": 0.0, "total_win_pnl": 0.0, "total_loss_pnl": 0.0,
            }
        stats = self._regime_stats[regime]
        stats["total_pnl"] += pnl
        if pnl > 0:
            stats["wins"] += 1
            stats["total_win_pnl"] += pnl
        else:
            stats["losses"] += 1
            stats["total_loss_pnl"] += abs(pnl)

    def get_regime_kelly(self, regime: str) -> float | None:
        """Compute Kelly fraction for a specific regime.

        Returns None if insufficient data (< 10 trades in regime).
        """
        stats = self._regime_stats.get(regime)
        if not stats:
            return None
        total = stats["wins"] + stats["losses"]
        if total < 10:
            return None
        win_rate = stats["wins"] / total
        if stats["losses"] == 0 or stats["total_loss_pnl"] < 1e-8:
            return None
        avg_win = stats["total_win_pnl"] / max(stats["wins"], 1)
        avg_loss = stats["total_loss_pnl"] / max(stats["losses"], 1)
        payoff_ratio = avg_win / avg_loss
        if payoff_ratio <= 0:
            return None  # No wins in this regime — cannot compute Kelly
        # Kelly: W - (1-W)/B
        kelly = win_rate - (1 - win_rate) / payoff_ratio
        return max(kelly, 0.0)

    def regime_stats_to_dict(self) -> dict[str, Any]:
        """Serialize regime stats for brain persistence."""
        return dict(self._regime_stats)

    def load_regime_stats(self, data: dict[str, Any]) -> None:
        """Restore regime stats from brain."""
        if data and isinstance(data, dict):
            self._regime_stats = {
                k: {
                    "wins": float(v.get("wins", 0)),
                    "losses": float(v.get("losses", 0)),
                    "total_pnl": float(v.get("total_pnl", 0)),
                    "total_win_pnl": float(v.get("total_win_pnl", 0)),
                    "total_loss_pnl": float(v.get("total_loss_pnl", 0)),
                }
                for k, v in data.items()
                if isinstance(v, dict)
            }
