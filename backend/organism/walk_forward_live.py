"""Walk-forward evaluation of the LIVE organism scanners.

Audit 2026-06-09 (plan 1.2): the existing ``backend/services/walk_forward.py``
evaluates a LEGACY strategy set (Momentum/MeanReversion/StatArb/Breakout from
``backend.strategies``) — none of which is what actually trades live. Its
verdicts therefore say nothing about the production book.

This module walks forward over the REAL trading stack by driving
``ReplayEngine`` (which calls the genuine ``OrganismLiveEngine.live_tick``)
on chronologically disjoint folds:

- bars are split by SESSION (calendar day), never mid-day;
- folds are evaluated independently with a FRESH brain each (no state
  leakage between folds — each fold is honest out-of-sample for the
  rule-set as configured);
- fills are costed by default (``cost_profile='realistic'``);
- the verdict aggregates per-fold expectancy into a t-statistic and
  applies Gate-2-style acceptance thresholds.

Usage (offline, evidence generation):

    wf = LiveScannerWalkForward(bars_by_symbol, n_folds=4, timeframe="1Min")
    report = await wf.run()
    print(report["verdict"], report["folds"])
"""

from __future__ import annotations

import logging
import math
import statistics
import tempfile
from typing import Any

import pandas as pd

from backend.organism.replay_simulator import ReplayEngine

logger = logging.getLogger(__name__)

# Gate-2-style acceptance thresholds (see AUDIT_2026-06-09_FULL_PLATFORM.md §9)
MIN_FOLDS = 2
MIN_TRADES_TOTAL = 30
MIN_PROFIT_FACTOR = 1.3
MIN_TSTAT = 2.0


def _session_dates(df: pd.DataFrame) -> pd.Series:
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"].astype(str), utc=True)
    else:
        ts = pd.to_datetime(pd.Series(df.index), utc=True)
    return ts.dt.tz_convert("America/New_York").dt.date


def split_sessions_into_folds(
    bars_by_symbol: dict[str, pd.DataFrame],
    n_folds: int,
) -> list[dict[str, pd.DataFrame]]:
    """Split multi-day bars into ``n_folds`` chronologically contiguous,
    disjoint session groups. Sessions are never split mid-day."""
    all_dates: set = set()
    for df in bars_by_symbol.values():
        all_dates.update(_session_dates(df).unique())
    dates = sorted(all_dates)
    if len(dates) < n_folds:
        raise ValueError(
            f"need >= {n_folds} sessions for {n_folds} folds, have {len(dates)}"
        )
    per_fold = len(dates) // n_folds
    folds: list[dict[str, pd.DataFrame]] = []
    for i in range(n_folds):
        start = i * per_fold
        end = (i + 1) * per_fold if i < n_folds - 1 else len(dates)
        fold_dates = set(dates[start:end])
        fold_bars: dict[str, pd.DataFrame] = {}
        for sym, df in bars_by_symbol.items():
            mask = _session_dates(df).isin(fold_dates).values
            sliced = df.loc[mask].reset_index(drop=True)
            if len(sliced) > 0:
                fold_bars[sym] = sliced
        if fold_bars:
            folds.append(fold_bars)
    return folds


class LiveScannerWalkForward:
    """Run the production engine over chronologically disjoint folds."""

    def __init__(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
        n_folds: int = 4,
        timeframe: str = "1Min",
        initial_cash: float = 100_000,
        cost_profile: str = "realistic",
        lookback: int | None = None,
        max_ticks_per_fold: int | None = None,
    ) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.n_folds = n_folds
        self.timeframe = timeframe
        self.initial_cash = initial_cash
        self.cost_profile = cost_profile
        self.lookback = lookback
        self.max_ticks_per_fold = max_ticks_per_fold

    async def run(self) -> dict[str, Any]:
        folds = split_sessions_into_folds(self.bars_by_symbol, self.n_folds)
        fold_reports: list[dict[str, Any]] = []

        for i, fold_bars in enumerate(folds):
            # Fresh brain per fold — no cross-fold state leakage.
            brain_dir = tempfile.mkdtemp(prefix=f"wf_live_fold{i}_")
            engine = ReplayEngine(
                bars_by_symbol=fold_bars,
                initial_cash=self.initial_cash,
                timeframe=self.timeframe,
                brain_dir=brain_dir,
                lookback=self.lookback,
                cost_profile=self.cost_profile,
                slippage_bps=1.0,
            )
            result = await engine.run(max_ticks=self.max_ticks_per_fold)
            pnls = [float(t.get("pnl", 0)) for t in result.trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            gross_loss = abs(sum(losses))
            fold_reports.append({
                "fold": i,
                "ticks": result.ticks,
                "n_trades": len(pnls),
                "total_pnl": round(sum(pnls), 4),
                "expectancy": round(sum(pnls) / len(pnls), 6) if pnls else None,
                "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
                "profit_factor": (
                    round(sum(wins) / gross_loss, 4) if gross_loss > 0
                    else (math.inf if wins else None)
                ),
                "max_drawdown": round(result.max_drawdown, 6),
            })
            logger.info("walk-forward fold %d: %s", i, fold_reports[-1])

        return self._aggregate(fold_reports)

    @staticmethod
    def _aggregate(fold_reports: list[dict[str, Any]]) -> dict[str, Any]:
        all_pnl = [f["total_pnl"] for f in fold_reports]
        n_trades = sum(f["n_trades"] for f in fold_reports)
        expectancies = [
            f["expectancy"] for f in fold_reports if f["expectancy"] is not None
        ]
        # t-stat of per-fold expectancy against zero.
        tstat: float | None = None
        if len(expectancies) >= 2:
            mean = statistics.mean(expectancies)
            sd = statistics.stdev(expectancies)
            if sd > 0:
                tstat = mean / (sd / math.sqrt(len(expectancies)))

        pfs = [
            f["profit_factor"] for f in fold_reports
            if f["profit_factor"] not in (None, math.inf)
        ]
        agg_pf = round(statistics.mean(pfs), 4) if pfs else None

        passed = (
            len(fold_reports) >= MIN_FOLDS
            and n_trades >= MIN_TRADES_TOTAL
            and sum(all_pnl) > 0
            and (tstat is not None and tstat >= MIN_TSTAT)
            and (agg_pf is not None and agg_pf >= MIN_PROFIT_FACTOR)
        )
        reasons = []
        if n_trades < MIN_TRADES_TOTAL:
            reasons.append(f"insufficient trades ({n_trades} < {MIN_TRADES_TOTAL})")
        if sum(all_pnl) <= 0:
            reasons.append(f"net PnL not positive ({sum(all_pnl):.2f})")
        if tstat is None or tstat < MIN_TSTAT:
            reasons.append(f"t-stat below {MIN_TSTAT} ({tstat})")
        if agg_pf is None or agg_pf < MIN_PROFIT_FACTOR:
            reasons.append(f"profit factor below {MIN_PROFIT_FACTOR} ({agg_pf})")

        return {
            "folds": fold_reports,
            "n_folds": len(fold_reports),
            "n_trades": n_trades,
            "total_pnl": round(sum(all_pnl), 4),
            "tstat_expectancy": round(tstat, 4) if tstat is not None else None,
            "mean_profit_factor": agg_pf,
            "verdict": "PASS" if passed else "FAIL",
            "fail_reasons": reasons if not passed else [],
            "thresholds": {
                "min_folds": MIN_FOLDS,
                "min_trades_total": MIN_TRADES_TOTAL,
                "min_profit_factor": MIN_PROFIT_FACTOR,
                "min_tstat": MIN_TSTAT,
            },
        }
