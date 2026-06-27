#!/usr/bin/env python3
"""Intra 2.0 Phase 1 — STEP 8: OOS, cost-disciplined strategy backtester (checkpoint #2).

Measures each registered Strategy's edge through the framework, OOS and costed BY
CONSTRUCTION (Rule B). It is the scoreboard that decides whether a `live_routing:
false` strategy (mean_reversion, and later ORB) has earned a routing flip — and
re-confirms momentum/breakout.

METHODOLOGY (no look-ahead by construction):
  * Features come from the SAME live function (compute_ml_features) — online/
    offline parity.
  * At bar t the strategy scans ONLY features[:t+1] (causal). Regime is detected
    causally from SPY, feeding the stateful detector bar-by-bar like live.
  * Entry is the OPEN of bar t+entry_lag (entry_lag>=1 ⇒ strictly after the
    signal bar ⇒ out-of-sample, no same-bar fill). Exit is `horizon` bars later.
  * Every trade is COSTED (round-trip bps via backend.organism.costing).
  * Acceptance gate (Rule B): net expectancy > 0 AND t_stat >= 2 on the costed
    OOS trades.

SIZING — read this before quoting any number. Trades are sized FLAT (fixed
notional), so the output is **SIGNAL significance, NOT live-P&L significance**.
This is the deliberate step-8 guardrail choice: live sizing uses the
confidence/Kelly composite, which is a DEFERRED redesign (step 5b) and is known
anti-predictive (corr=-0.112) — sizing by it would measure a defect, not edge.
Flat sizing answers "does the signal have edge?" comparably across strategies;
it does NOT predict live dollar P&L. Routing-grade live-P&L significance is a
later step once 5b lands.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import pandas as pd

from backend.organism.costing import DEFAULT_COST_BPS, costed_summary
from backend.organism.ml_features import compute_ml_features
from backend.organism.regime import RegimeDetector
from backend.organism.strategy_selector import StrategySelector

SIZING_LABEL = ("SIGNAL significance (flat notional sizing) — NOT live-P&L "
                "significance; live sizing (confidence/Kelly) is deferred step 5b")


@dataclass
class BacktestConfig:
    cost_bps: float = DEFAULT_COST_BPS   # round-trip, costing.DEFAULT_COST_BPS
    notional: float = 10_000.0           # flat per-trade notional (signal-significance)
    entry_lag: int = 1                   # bars after signal to enter (>=1 ⇒ OOS, next-bar open)
    horizon: int = 20                    # bars held before exit
    warmup: int = 60                     # min bars before the strategy may scan
    bars_per_day: int = 390              # 1-min RTH
    t_stat_gate: float = 2.0             # Rule B acceptance: t_stat >= this


@dataclass
class BacktestResult:
    per_strategy: dict = field(default_factory=dict)   # name -> costed_summary + accepted
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_bars: int = 0
    regimes_seen: list = field(default_factory=list)
    sizing_label: str = SIZING_LABEL

    def report(self) -> str:
        lines = ["=" * 70, "STRATEGY BACKTEST — OOS, COST-DISCIPLINED (Phase 1 step 8)", "=" * 70,
                 f"bars={self.n_bars}  regimes={sorted(set(self.regimes_seen))}",
                 f"SIZING: {self.sizing_label}", "-" * 70]
        if not self.per_strategy:
            lines.append("no trades produced.")
        for name, s in sorted(self.per_strategy.items()):
            if s.get("n", 0) == 0:
                lines.append(f"{name:16s} n=0  (no trades)")
                continue
            gate = "ACCEPT" if s["accepted"] else "reject"
            lines.append(
                f"{name:16s} n={s['n']:<4d} net_exp={s['expectancy']:+.4f} "
                f"t={s['t_stat']:+.2f} win={s['win_rate']:.0%} "
                f"pf={s['profit_factor']} net_pnl={s['net_pnl']:+.2f} "
                f"[{gate} @t>={s['t_stat_gate']}]")
        lines.append("=" * 70)
        return "\n".join(lines)


def _compute_all_features(bars_by_symbol, bars_per_day):
    spy_raw = bars_by_symbol.get("SPY")
    feats = {}
    for sym, df in bars_by_symbol.items():
        raw = df.copy()
        if "timestamp" not in raw.columns:
            # Synthesize causal 1-min ET-session timestamps (needed for the
            # time-gated MR scanner; harmless for the others).
            raw["timestamp"] = pd.date_range(
                "2026-06-01 13:45", periods=len(raw), freq="1min", tz="UTC")
        f = compute_ml_features(raw, spy_raw, bars_per_day=bars_per_day)
        feats[sym] = f.reset_index(drop=True)
    return feats


def run_backtest(bars_by_symbol, config: BacktestConfig | None = None) -> BacktestResult:
    cfg = config or BacktestConfig()
    feats = _compute_all_features(bars_by_symbol, cfg.bars_per_day)
    spy_feats = feats.get("SPY")

    n = min(len(f) for f in feats.values())
    detector = RegimeDetector(is_intraday=True, bars_per_day=cfg.bars_per_day)
    selector = StrategySelector.from_config(mode="backtest")

    rows = []
    regimes_seen = []
    last_t = n - cfg.entry_lag - cfg.horizon - 1
    for t in range(cfg.warmup, max(cfg.warmup, last_t)):
        # Causal regime from SPY (stateful detector fed bar-by-bar like live).
        regime = "unknown"
        if spy_feats is not None:
            regime = detector.detect(spy_feats.iloc[: t + 1]).primary
        regimes_seen.append(regime)

        features_t = {s: f.iloc[: t + 1] for s, f in feats.items()}
        cands = selector.select(features_t, regime)

        entry_idx = t + cfg.entry_lag
        exit_idx = entry_idx + cfg.horizon
        for c in cands:
            bars = bars_by_symbol.get(c.symbol)
            if bars is None or exit_idx >= len(bars):
                continue
            entry_price = float(bars["open"].iloc[entry_idx])   # next-bar open ⇒ OOS
            exit_price = float(bars["close"].iloc[exit_idx])
            if entry_price <= 0:
                continue
            shares = cfg.notional / entry_price                  # FLAT sizing
            pnl = (exit_price - entry_price) * shares * c.direction
            rows.append({
                "strategy": c.strategy_name, "symbol": c.symbol,
                "signal_idx": t, "entry_idx": entry_idx, "exit_idx": exit_idx,
                "entry_price": entry_price, "exit_price": exit_price,
                "shares": shares, "direction": c.direction, "pnl": pnl,
                "confidence": c.confidence, "regime": regime,
            })

    trades = pd.DataFrame(rows)
    per_strategy = {}
    names = set(trades["strategy"]) if len(trades) else set()
    for name in names:
        sub = trades[trades["strategy"] == name]
        summ = costed_summary(sub, cfg.cost_bps)
        summ["t_stat_gate"] = cfg.t_stat_gate
        summ["accepted"] = bool(
            summ.get("n", 0) > 0 and summ.get("expectancy", 0) > 0
            and summ.get("t_stat", 0) >= cfg.t_stat_gate)
        per_strategy[name] = summ

    return BacktestResult(per_strategy=per_strategy, trades=trades, n_bars=n,
                          regimes_seen=regimes_seen)


def _synthetic_bars(symbols, n, seed, trend):
    from backend.organism.replay_simulator import make_features_dict
    return make_features_dict(symbols, n=n, seed=seed, trend=trend)


def main() -> int:
    p = argparse.ArgumentParser(description="Intra 2.0 OOS strategy backtester (step 8)")
    p.add_argument("--symbols", default="AAPL,MSFT,NVDA,GOOGL,SPY")
    p.add_argument("--n", type=int, default=600)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--trend", default="up", choices=["up", "down", "chop", "crash"])
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--entry-lag", type=int, default=1)
    p.add_argument("--notional", type=float, default=10_000.0)
    args = p.parse_args()

    bars = _synthetic_bars(args.symbols.split(","), args.n, args.seed, args.trend)
    cfg = BacktestConfig(cost_bps=args.cost_bps, horizon=args.horizon,
                         entry_lag=args.entry_lag, notional=args.notional)
    res = run_backtest(bars, cfg)
    print(res.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
