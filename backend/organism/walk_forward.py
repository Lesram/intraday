"""
Phase 3 — Walk-Forward Evaluation Engine.

Validates any candidate policy/model/parameter set via strict chronological
walk-forward testing before promotion.

Protocol:
  For each window of size ``train_window`` rolling by ``step``:
    1. Train on [t−N, t−k]  (or load candidate policy)
    2. Evaluate on [t−k, t]  (out-of-sample)
    3. Record per-window metrics
  Aggregate across windows and compare to baseline.

Evaluation includes:
- Per-window returns, drawdown, turnover, Sharpe
- Stability of weights/params across windows
- Sensitivity to cost assumptions
- Acceptance gates (minimum improvement, no drawdown regression, no instability)

Contract: walk_forward is an OFFLINE-ONLY evaluation tool. It is not used
in the live model promotion path. Live acceptance uses a simpler composite
quality gate (ContinuousLearner._validate_new_model) that can run
synchronously in the tick loop or inside the background training process.
Walk-forward is intended for manual strategy evaluation, parameter sweeps,
and pre-deployment validation — not for gating individual model retrains.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from backend.features.feature_engineering import FeatureEngineer
from backend.strategies.trading_strategies import (
    BreakoutStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    RegimeFilteredMomentumStrategy,
    StatisticalArbitrageStrategy,
    SignalType,
)
from backend.risk.risk_manager import RiskManager
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WindowResult:
    """Evaluation result for a single walk-forward window."""
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    # Metrics
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0
    turnover: float = 0.0
    win_rate: float = 0.0
    # Applied weights
    weights_used: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_idx": self.window_idx,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "total_return": round(self.total_return, 6),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown": round(self.max_drawdown, 6),
            "trade_count": self.trade_count,
            "turnover": round(self.turnover, 4),
            "win_rate": round(self.win_rate, 4),
            "weights_used": self.weights_used,
        }


@dataclass
class WalkForwardReport:
    """Full walk-forward evaluation report."""
    candidate_id: str
    baseline_id: str
    windows: list[WindowResult] = field(default_factory=list)
    # Aggregates
    mean_return: float = 0.0
    mean_sharpe: float = 0.0
    worst_drawdown: float = 0.0
    total_trades: int = 0
    mean_turnover: float = 0.0
    weight_stability: float = 0.0  # std of weight vectors across windows
    # Acceptance
    accepted: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "window_count": len(self.windows),
            "mean_return": round(self.mean_return, 6),
            "mean_sharpe": round(self.mean_sharpe, 4),
            "worst_drawdown": round(self.worst_drawdown, 6),
            "total_trades": self.total_trades,
            "mean_turnover": round(self.mean_turnover, 4),
            "weight_stability": round(self.weight_stability, 4),
            "accepted": self.accepted,
            "rejection_reasons": self.rejection_reasons,
            "windows": [w.to_dict() for w in self.windows],
            "created_at": self.created_at,
        }


# ── Acceptance gate thresholds ──────────────────────────────────────

@dataclass
class AcceptanceGates:
    """Thresholds a candidate must beat to be promoted."""
    min_sharpe: float = 0.3
    max_drawdown: float = 0.15       # 15% max DD
    min_improvement_pct: float = 0.05  # candidate must beat baseline by 5%
    max_turnover: float = 5.0        # max avg daily turnover ratio
    min_trades: int = 5              # need at least N trades
    max_weight_std: float = 0.40     # weight stability (low = stable)


class WalkForwardEvaluator:
    """Run walk-forward evaluation on historical price data.

    Uses the same strategy classes + FeatureEngineer as the live runner,
    ensuring online/offline parity.
    """

    def __init__(
        self,
        *,
        train_window_days: int = 60,
        test_window_days: int = 10,
        step_days: int = 5,
        slippage_bps: float = 5.0,
        commission_bps: float = 1.0,
        gates: AcceptanceGates | None = None,
    ) -> None:
        self.train_window = train_window_days
        self.test_window = test_window_days
        self.step = step_days
        self.slippage_bps = slippage_bps
        self.commission_bps = commission_bps
        self.gates = gates or AcceptanceGates()
        self._engineer = FeatureEngineer(
            config={
                "feature_mode": "realtime_light",
                "enable_heavy_features": False,
                "enable_autocorr_features": False,
            }
        )

    async def evaluate(
        self,
        *,
        price_data: dict[str, pd.DataFrame],  # {symbol: OHLCV df with 'timestamp'}
        candidate_weights: dict[str, float],
        baseline_weights: dict[str, float],
        candidate_id: str = "candidate",
        baseline_id: str = "baseline",
    ) -> WalkForwardReport:
        """Run full walk-forward evaluation comparing candidate vs baseline.

        ``price_data`` maps symbol → DataFrame with columns
        [timestamp, open, high, low, close, volume].
        """
        report = WalkForwardReport(
            candidate_id=candidate_id,
            baseline_id=baseline_id,
            created_at=datetime.now(UTC).isoformat(),
        )

        # Build unified date index
        all_dates = self._build_date_index(price_data)
        if len(all_dates) < self.train_window + self.test_window:
            report.rejection_reasons.append("Insufficient data for walk-forward")
            return report

        # Generate windows
        windows = self._generate_windows(all_dates)
        if not windows:
            report.rejection_reasons.append("No valid windows generated")
            return report

        # Run candidate evaluation per window
        for idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
            window_result = await self._evaluate_window(
                idx=idx,
                price_data=price_data,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                weights=candidate_weights,
            )
            report.windows.append(window_result)

        # Run baseline evaluation to compare improvement
        baseline_sharpes: list[float] = []
        for idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
            baseline_result = await self._evaluate_window(
                idx=idx,
                price_data=price_data,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                weights=baseline_weights,
            )
            baseline_sharpes.append(baseline_result.sharpe)
        report._baseline_sharpe = float(np.mean(baseline_sharpes)) if baseline_sharpes else None  # type: ignore[attr-defined]

        # Aggregate metrics
        self._aggregate(report)

        # Run acceptance gates
        self._check_gates(report, baseline_weights)

        return report

    # ── internal ─────────────────────────────────────────────────────

    def _build_date_index(self, price_data: dict[str, pd.DataFrame]) -> list:
        """Build a sorted unique date index across all symbols."""
        all_ts = set()
        for df in price_data.values():
            if "timestamp" in df.columns:
                for v in df["timestamp"]:
                    try:
                        all_ts.add(pd.Timestamp(v).date())
                    except Exception:
                        pass
        return sorted(all_ts)

    def _generate_windows(self, dates: list) -> list[tuple]:
        """Generate (train_start, train_end, test_start, test_end) tuples."""
        windows = []
        total = len(dates)
        i = 0
        while i + self.train_window + self.test_window <= total:
            train_s = dates[i]
            train_e = dates[i + self.train_window - 1]
            test_s = dates[i + self.train_window]
            test_e_idx = min(i + self.train_window + self.test_window - 1, total - 1)
            test_e = dates[test_e_idx]
            windows.append((train_s, train_e, test_s, test_e))
            i += self.step
        return windows

    async def _evaluate_window(
        self,
        *,
        idx: int,
        price_data: dict[str, pd.DataFrame],
        train_start,
        train_end,
        test_start,
        test_end,
        weights: dict[str, float],
    ) -> WindowResult:
        """Evaluate a single walk-forward window."""
        result = WindowResult(
            window_idx=idx,
            train_start=str(train_start),
            train_end=str(train_end),
            test_start=str(test_start),
            test_end=str(test_end),
            weights_used=dict(weights),
        )

        # Slice test data per symbol
        daily_pnls: list[float] = []
        trades = 0
        wins = 0
        turnover = 0.0

        for symbol, df in price_data.items():
            if "timestamp" not in df.columns:
                continue

            # Convert to date for slicing
            df = df.copy()
            df["_date"] = pd.to_datetime(df["timestamp"]).dt.date
            test_df = df[(df["_date"] >= test_start) & (df["_date"] <= test_end)].copy()
            if len(test_df) < 2:
                continue

            # Compute features on the full data up to the test point (no leakage)
            full_up_to_test = df[df["_date"] <= test_end].tail(200)  # lookback window
            if len(full_up_to_test) < 20:
                continue

            features_df = self._engineer.compute_technical_indicators(full_up_to_test)

            # Generate signals on the test portion
            risk_mgr = RiskManager()
            strategies = {
                "momentum": MomentumStrategy(risk_mgr),
                "mean_reversion": MeanReversionStrategy(risk_mgr),
                "stat_arb": StatisticalArbitrageStrategy(risk_mgr),
                "regime_momentum": RegimeFilteredMomentumStrategy(risk_mgr),
                "breakout": BreakoutStrategy(risk_mgr),
            }

            prev_position = 0.0  # flat start each window

            for bar_idx in range(len(test_df) - 1):
                # For each bar, evaluate strategies
                bar_row = test_df.iloc[bar_idx]
                next_bar_row = test_df.iloc[bar_idx + 1]

                close = float(bar_row["close"])
                next_close = float(next_bar_row["close"])

                weighted_exposure = 0.0
                total_weight = 0.0

                for name, strategy in strategies.items():
                    w = weights.get(name, 1.0)
                    try:
                        sig = await strategy.generate_signal(
                            symbol,
                            full_up_to_test.iloc[: len(full_up_to_test) - len(test_df) + bar_idx + 1],
                            features_df.iloc[: len(features_df) - len(test_df) + bar_idx + 1],
                        )
                        if sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                            direction = 1.0
                        elif sig.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                            direction = -1.0
                        else:
                            direction = 0.0

                        confidence = float(sig.confidence)
                        weighted_exposure += w * direction * confidence
                        total_weight += w
                    except Exception as exc:
                        logger.debug(
                            "Walk-forward strategy signal failed",
                            extra={"strategy": name, "symbol": symbol, "error": str(exc)},
                        )
                        continue

                if total_weight > 0:
                    target = max(-1.0, min(1.0, weighted_exposure / total_weight))
                else:
                    target = 0.0

                # Transaction cost
                delta = abs(target - prev_position)
                cost_pct = delta * (self.slippage_bps + self.commission_bps) / 10000
                turnover += delta

                # PnL for this bar
                bar_return = (next_close - close) / close if close > 0 else 0.0
                pnl = target * bar_return - cost_pct
                daily_pnls.append(pnl)

                if target != prev_position and delta > 0.01:
                    trades += 1
                    if pnl > 0:
                        wins += 1

                prev_position = target

        # Fill result
        result.trade_count = trades
        result.turnover = turnover
        result.win_rate = wins / trades if trades > 0 else 0.0

        if daily_pnls:
            result.total_return = float(np.sum(daily_pnls))

            mean = float(np.mean(daily_pnls))
            std = float(np.std(daily_pnls, ddof=1)) if len(daily_pnls) > 1 else 1.0
            result.sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0

            cumulative = np.cumsum(daily_pnls)
            peak = np.maximum.accumulate(cumulative)
            dd = peak - cumulative
            result.max_drawdown = float(np.max(dd)) if len(dd) > 0 else 0.0

        return result

    def _aggregate(self, report: WalkForwardReport) -> None:
        """Aggregate per-window metrics into the report."""
        if not report.windows:
            return

        returns = [w.total_return for w in report.windows]
        sharpes = [w.sharpe for w in report.windows]
        drawdowns = [w.max_drawdown for w in report.windows]
        turnovers = [w.turnover for w in report.windows]

        report.mean_return = float(np.mean(returns))
        report.mean_sharpe = float(np.mean(sharpes))
        report.worst_drawdown = float(np.max(drawdowns))
        report.total_trades = sum(w.trade_count for w in report.windows)
        report.mean_turnover = float(np.mean(turnovers))

        # Weight stability: avg std of weight values across windows
        if report.windows:
            all_weight_vecs = []
            for w in report.windows:
                if w.weights_used:
                    all_weight_vecs.append(list(w.weights_used.values()))
            if all_weight_vecs:
                arr = np.array(all_weight_vecs)
                report.weight_stability = float(np.mean(np.std(arr, axis=0)))

    def _check_gates(
        self,
        report: WalkForwardReport,
        baseline_weights: dict[str, float],
    ) -> None:
        """Apply acceptance gates and set report.accepted."""
        reasons: list[str] = []

        if report.mean_sharpe < self.gates.min_sharpe:
            reasons.append(f"Sharpe {report.mean_sharpe:.3f} < min {self.gates.min_sharpe}")

        if report.worst_drawdown > self.gates.max_drawdown:
            reasons.append(f"Max DD {report.worst_drawdown:.4f} > limit {self.gates.max_drawdown}")

        if report.total_trades < self.gates.min_trades:
            reasons.append(f"Only {report.total_trades} trades < min {self.gates.min_trades}")

        if report.mean_turnover > self.gates.max_turnover:
            reasons.append(f"Turnover {report.mean_turnover:.2f} > max {self.gates.max_turnover}")

        if report.weight_stability > self.gates.max_weight_std:
            reasons.append(f"Weight instability {report.weight_stability:.3f} > max {self.gates.max_weight_std}")

        # Baseline improvement gate: candidate must beat baseline by min %
        if (
            baseline_weights
            and self.gates.min_improvement_pct > 0
            and hasattr(report, '_baseline_sharpe')
            and report._baseline_sharpe is not None
        ):
            if report._baseline_sharpe > 0:
                improvement = (report.mean_sharpe - report._baseline_sharpe) / abs(report._baseline_sharpe)
            else:
                improvement = report.mean_sharpe - report._baseline_sharpe
            if improvement < self.gates.min_improvement_pct:
                reasons.append(
                    f"Improvement {improvement:.2%} < min {self.gates.min_improvement_pct:.2%} "
                    f"(candidate Sharpe {report.mean_sharpe:.3f} vs baseline {report._baseline_sharpe:.3f})"
                )

        report.rejection_reasons = reasons
        report.accepted = len(reasons) == 0
