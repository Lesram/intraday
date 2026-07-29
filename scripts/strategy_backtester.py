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
        train fold (required once Phase 2 SWEEPS config — see
        `walk_forward_select`, the real tune-on-train/report-on-test holdout).
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


def _tstat(pnl) -> float:
    s = pd.Series(list(pnl), dtype="float64")
    n = len(s)
    if n < 2:
        return 0.0
    sd = s.std(ddof=1)
    return float(s.mean() / (sd / (n ** 0.5))) if sd and sd > 0 else 0.0


def time_train_test_split(n: int, train_frac: float = 0.6, embargo: int = 0):
    """Time-ordered split with an EMBARGO (purge) gap between train and test, so
    overlapping/lagged observations can't leak train info into test."""
    train_end = max(1, int(n * train_frac))
    test_start = min(n, train_end + embargo)
    return list(range(0, train_end)), list(range(test_start, n))


def walk_forward_select(param_grid, pnl_for_param, n: int, *, train_frac: float = 0.6,
                        embargo: int = 0, stat=_tstat) -> dict:
    """The REAL holdout (Phase-2 step-8 / precondition Task 1): SELECT the param on
    TRAIN-fold metrics ONLY, then REPORT on the untouched TEST fold.

    `pnl_for_param(param, idx)` returns the per-trade pnl array for `param` over row
    indices `idx`. Leakage is structurally impossible: selection never sees the test
    fold. This is what makes "tune a param" honest — contrast with restricting the
    eval window (`eval_tail_frac`), which does NOT close leakage. The teeth-test
    plants a param that overfits train (train_stat≥2) and shows test_stat collapses.
    """
    train_idx, test_idx = time_train_test_split(n, train_frac, embargo)
    best, best_train = None, float("-inf")
    for p in param_grid:
        t = stat(pnl_for_param(p, train_idx))     # SELECTION: train only
        if t > best_train:
            best_train, best = t, p
    test_stat = stat(pnl_for_param(best, test_idx))  # REPORT: test only
    return {"selected": best, "train_stat": best_train, "test_stat": test_stat,
            "n_train": len(train_idx), "n_test": len(test_idx)}


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
    eval_tail_frac: float = 0.0          # >0 ⇒ evaluate only the FINAL fraction of bars.
                                         # This is a WINDOW RESTRICTION, NOT a holdout — it does
                                         # not enforce OOS on its own (renamed from holdout_frac so
                                         # it can't be mistaken for one). The REAL tune-on-train /
                                         # report-on-test holdout is walk_forward_select() below.
    capture_feature_cols: tuple = ()     # 5b: feature columns snapshotted per trade at the
                                         # SIGNAL bar (causal — same row the scanner saw) as
                                         # feat_<col>. Default () = no extra columns, output
                                         # unchanged. Consumed by confidence_lab (Task 2/5b).


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
                 data_source: str = "real", only: set | None = None,
                 precomputed_feats: dict | None = None) -> BacktestResult:
    """`only` restricts the selector to a strategy subset (e.g. {"momentum"}).
    `precomputed_feats` reuses features across calls (param sweeps) so they're
    computed once per corpus, not once per config — features don't depend on the
    strategy params being swept."""
    cfg = config or BacktestConfig()
    feats = precomputed_feats if precomputed_feats is not None else \
        _compute_all_features(bars_by_symbol, cfg.bars_per_day)
    spy_feats = feats.get("SPY")

    n = min(len(f) for f in feats.values())
    detector = RegimeDetector(is_intraday=True, bars_per_day=cfg.bars_per_day)
    selector = StrategySelector.from_config(mode="backtest", only=only)

    start = max(cfg.warmup, int(n * cfg.eval_tail_frac))  # window restriction (NOT a holdout)
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
            row = {
                "strategy": c.strategy_name, "symbol": c.symbol,
                "signal_idx": t, "entry_idx": entry_idx, "exit_idx": exit_idx,
                "entry_price": entry_price, "exit_price": exit_price,
                "shares": shares, "direction": c.direction, "pnl": pnl,
                "confidence": c.confidence, "regime": regime,
            }
            if cfg.capture_feature_cols:
                snap = feats[c.symbol].iloc[t]       # signal bar — causal
                for col in cfg.capture_feature_cols:
                    row[f"feat_{col}"] = float(snap.get(col, float("nan")))
            rows.append(row)

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
    p.add_argument("--eval-tail-frac", type=float, default=0.0,
                   help="evaluate only the final fraction of bars (window restriction, NOT a holdout)")
    p.add_argument("--notional", type=float, default=10_000.0)
    args = p.parse_args()

    cfg = BacktestConfig(cost_bps=args.cost_bps, horizon=args.horizon,
                         entry_lag=args.entry_lag, notional=args.notional,
                         max_bars=args.max_bars, eval_tail_frac=args.eval_tail_frac)
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
