#!/usr/bin/env python3
"""Intra 2.0 Phase 1 — STEP 8: causal, cost-disciplined strategy backtester (checkpoint #2).

Measures each registered Strategy's signal edge through the framework. It is the
scoreboard that decides whether a `live_routing:false` strategy (mean_reversion,
later ORB) has earned a routing flip — and re-confirms momentum/breakout.

WHAT THIS GUARANTEES (by construction):
  * CAUSAL — no look-ahead: at bar t the strategy scans only features[t-W+1:t+1];
    regime is detected causally from SPY (stateful detector fed bar-by-bar like
    live); entry is the OPEN of bar t+entry_lag (entry_lag>=1 ⇒ strictly after the
    signal bar, no same-bar fill); exit is `horizon` bars later.
  * COST-DISCIPLINED — every trade pays a round-trip cost (backend.organism.costing).
  * Features come from the SAME live function (compute_ml_features) — online/offline
    parity.

WHAT THIS IS *NOT* (read before quoting any number):
  * NOT out-of-sample in the held-out sense. The strategies use FIXED params tuned
    on historical real data; there is no train/test split here. So:
      - On a corpus that OVERLAPS the tuning period, the read is IN-SAMPLE and
        flatters. A genuine OOS edge verdict needs a corpus DISJOINT from tuning
        (forward / shadow data), or walk-forward folds that re-fit params per
        train fold (required once Phase 2 SWEEPS config through this harness —
        see `holdout_frac`).
      - "causal" is necessary but not sufficient for "OOS". Do not conflate them.
  * NOT an edge measurement on SYNTHETIC data. make_features_dict is a drifting
    random walk; momentum wins on it BY CONSTRUCTION (the drift IS the signal).
    Synthetic mode is a SMOKE TEST of the harness mechanics ONLY — it never
    renders an ACCEPT verdict. Use --bars-pickle (real bars) for any edge claim.

SIZING: trades are sized FLAT (fixed notional) ⇒ the output is SIGNAL significance,
NOT live-P&L significance. Live sizing uses the confidence/Kelly composite, a
DEFERRED redesign (step 5b) that is known anti-predictive (corr=-0.112) — sizing
by it would measure a defect. Flat sizing answers "does the signal have edge?"
comparably across strategies; it does not predict live dollars.
"""
from __future__ import annotations

import argparse
import pickle
from dataclasses import dataclass, field

import pandas as pd

from backend.organism.costing import DEFAULT_COST_BPS, costed_summary
from backend.organism.ml_features import compute_ml_features
from backend.organism.regime import RegimeDetector
from backend.organism.strategy_selector import StrategySelector

SIZING_LABEL = ("SIGNAL significance (flat notional sizing) — NOT live-P&L "
                "significance; live sizing (confidence/Kelly) is deferred step 5b")
OOS_CAVEAT = ("CAUSAL + costed, but NOT held-out OOS: fixed params, no train/test "
              "split. In-sample if the corpus overlaps tuning. Genuine OOS needs a "
              "disjoint/forward corpus or walk-forward refit (Phase 2).")


@dataclass
class BacktestConfig:
    cost_bps: float = DEFAULT_COST_BPS   # round-trip, costing.DEFAULT_COST_BPS
    notional: float = 10_000.0           # flat per-trade notional (signal-significance)
    entry_lag: int = 1                   # bars after signal to enter (>=1 ⇒ causal next-bar open)
    horizon: int = 20                    # bars held before exit
    warmup: int = 60                     # min bars before the strategy may scan
    lookback_window: int = 500           # trailing bars handed to scanners (bounds cost; live has finite history)
    max_bars: int | None = None          # cap evaluated bars (None = all)
    bars_per_day: int = 390              # 1-min RTH
    t_stat_gate: float = 2.0             # acceptance: t_stat >= this
    holdout_frac: float = 0.0            # >0 ⇒ evaluate only the FINAL fraction (test window).
                                         # SCAFFOLD ONLY: this restricts the eval window; it does
                                         # NOT by itself enforce OOS. A Phase-2 sweep must tune
                                         # params on the earlier (train) portion and report on this
                                         # test window — that tune-on-train step is not built yet.
                                         # See the Phase-2 PRECONDITION in docs/architecture/intra_2.0_phase1.md.


@dataclass
class BacktestResult:
    per_strategy: dict = field(default_factory=dict)   # name -> costed_summary + accepted
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_bars: int = 0
    regimes_seen: list = field(default_factory=list)
    data_source: str = "real"            # "real" | "synthetic"
    sizing_label: str = SIZING_LABEL
    oos_caveat: str = OOS_CAVEAT

    @property
    def is_smoke(self) -> bool:
        return self.data_source == "synthetic"

    def report(self) -> str:
        banner = ("SMOKE TEST (synthetic data — harness mechanics only, NOT an edge "
                  "verdict)" if self.is_smoke else "REAL bars")
        lines = ["=" * 74, "STRATEGY BACKTEST — causal, cost-disciplined (Phase 1 step 8)", "=" * 74,
                 f"DATA: {banner}",
                 f"bars={self.n_bars}  regimes={sorted(set(self.regimes_seen))}",
                 f"SIZING: {self.sizing_label}",
                 f"OOS:    {self.oos_caveat}", "-" * 74]
        if not self.per_strategy:
            lines.append("no trades produced.")
        for name, s in sorted(self.per_strategy.items()):
            if s.get("n", 0) == 0:
                lines.append(f"{name:16s} n=0  (no trades)")
                continue
            if self.is_smoke:
                verdict = "SMOKE (no verdict on synthetic)"
            else:
                verdict = ("ACCEPT" if s["accepted"] else "reject") + f" @t>={s['t_stat_gate']}"
            lines.append(
                f"{name:16s} n={s['n']:<4d} net_exp={s['expectancy']:+.4f} "
                f"t={s['t_stat']:+.2f} win={s['win_rate']:.0%} "
                f"pf={s['profit_factor']} net_pnl={s['net_pnl']:+.2f}  [{verdict}]")
        lines.append("=" * 74)
        return "\n".join(lines)


def load_bars_pickle(path: str) -> dict:
    """Load a cached real-bar corpus (artifacts/**/bars.pkl): dict[symbol -> df
    with open/high/low/close/volume(/timestamp)]."""
    with open(path, "rb") as fh:
        bars = pickle.load(fh)
    out = {}
    need = {"open", "high", "low", "close", "volume"}
    for sym, df in bars.items():
        if df is None or not need <= set(df.columns):
            continue
        out[sym] = df.reset_index(drop=True)
    if not out:
        raise ValueError(f"no usable OHLCV symbols in {path}")
    return out


def _compute_all_features(bars_by_symbol, bars_per_day):
    spy_raw = bars_by_symbol.get("SPY")
    feats = {}
    for sym, df in bars_by_symbol.items():
        raw = df.copy()
        if "timestamp" not in raw.columns:
            # Synthetic smoke corpus: synthesize causal 1-min ET-session stamps
            # (needed for the time-gated MR scanner; harmless for the others).
            raw["timestamp"] = pd.date_range(
                "2026-06-01 13:45", periods=len(raw), freq="1min", tz="UTC")
        f = compute_ml_features(raw, spy_raw, bars_per_day=bars_per_day)
        feats[sym] = f.reset_index(drop=True)
    return feats


def run_backtest(bars_by_symbol, config: BacktestConfig | None = None,
                 data_source: str = "real") -> BacktestResult:
    cfg = config or BacktestConfig()
    feats = _compute_all_features(bars_by_symbol, cfg.bars_per_day)
    spy_feats = feats.get("SPY")

    n = min(len(f) for f in feats.values())
    detector = RegimeDetector(is_intraday=True, bars_per_day=cfg.bars_per_day)
    selector = StrategySelector.from_config(mode="backtest")

    start = max(cfg.warmup, int(n * cfg.holdout_frac))  # holdout: skip the train portion
    last_t = n - cfg.entry_lag - cfg.horizon - 1
    if cfg.max_bars is not None:
        last_t = min(last_t, start + cfg.max_bars)

    rows, regimes_seen = [], []
    W = cfg.lookback_window
    for t in range(start, max(start, last_t)):
        lo = max(0, t - W + 1)
        regime = "unknown"
        if spy_feats is not None:
            regime = detector.detect(spy_feats.iloc[lo: t + 1]).primary
        regimes_seen.append(regime)

        features_t = {s: f.iloc[lo: t + 1] for s, f in feats.items()}
        cands = selector.select(features_t, regime)

        entry_idx = t + cfg.entry_lag
        exit_idx = entry_idx + cfg.horizon
        for c in cands:
            bars = bars_by_symbol.get(c.symbol)
            if bars is None or exit_idx >= len(bars):
                continue
            entry_price = float(bars["open"].iloc[entry_idx])   # next-bar open ⇒ causal
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
        # An ACCEPT verdict is only meaningful on REAL bars (synthetic is a
        # data-generator artifact, never an edge verdict).
        summ["accepted"] = bool(
            data_source == "real" and summ.get("n", 0) > 0
            and summ.get("expectancy", 0) > 0
            and summ.get("t_stat", 0) >= cfg.t_stat_gate)
        per_strategy[name] = summ

    return BacktestResult(per_strategy=per_strategy, trades=trades, n_bars=n,
                          regimes_seen=regimes_seen, data_source=data_source)


def _synthetic_bars(symbols, n, seed, trend):
    from backend.organism.replay_simulator import make_features_dict
    return make_features_dict(symbols, n=n, seed=seed, trend=trend)


def main() -> int:
    p = argparse.ArgumentParser(description="Intra 2.0 causal strategy backtester (step 8)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--bars-pickle", help="real cached corpus (artifacts/**/bars.pkl) — for edge claims")
    src.add_argument("--synthetic", action="store_true",
                     help="SMOKE TEST on synthetic data (harness mechanics only, no verdict)")
    p.add_argument("--symbols", default="AAPL,MSFT,NVDA,GOOGL,SPY")
    p.add_argument("--n", type=int, default=600)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--trend", default="up", choices=["up", "down", "chop", "crash"])
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--entry-lag", type=int, default=1)
    p.add_argument("--max-bars", type=int, default=None)
    p.add_argument("--holdout-frac", type=float, default=0.0)
    p.add_argument("--notional", type=float, default=10_000.0)
    args = p.parse_args()

    cfg = BacktestConfig(cost_bps=args.cost_bps, horizon=args.horizon,
                         entry_lag=args.entry_lag, notional=args.notional,
                         max_bars=args.max_bars, holdout_frac=args.holdout_frac)
    if args.bars_pickle:
        bars = load_bars_pickle(args.bars_pickle)
        res = run_backtest(bars, cfg, data_source="real")
    else:
        if not args.synthetic:
            print("Refusing to render a verdict without real bars. Pass --bars-pickle "
                  "PATH for an edge read, or --synthetic for a harness smoke test.")
            return 2
        bars = _synthetic_bars(args.symbols.split(","), args.n, args.seed, args.trend)
        res = run_backtest(bars, cfg, data_source="synthetic")
    print(res.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
