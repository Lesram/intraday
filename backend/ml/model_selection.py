from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

TargetKind = Literal["next_close", "direction_up"]


@dataclass(frozen=True)
class BacktestEvalResult:
    n_samples: int
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float


def _to_numpy_float(series: pd.Series) -> np.ndarray:
    arr = series.to_numpy(dtype=float, copy=False)
    return np.asarray(arr, dtype=float)


def time_split_by_fraction(df: pd.DataFrame, eval_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df is None or df.empty:
        return df, df
    if not (0.0 < float(eval_fraction) < 1.0):
        raise ValueError("eval_fraction must be in (0,1)")

    df_sorted = df.sort_index()
    n = len(df_sorted)
    n_eval = max(1, int(round(n * float(eval_fraction))))
    n_train = max(1, n - n_eval)
    train_df = df_sorted.iloc[:n_train]
    eval_df = df_sorted.iloc[n_train:]
    return train_df, eval_df


def positions_from_predictions(
    *,
    predictions: np.ndarray,
    target_kind: TargetKind,
    prob_threshold: float = 0.5,
) -> np.ndarray:
    preds = np.asarray(predictions, dtype=float)

    if target_kind == "direction_up":
        # long (1) if prob(up) >= threshold else flat (0)
        return (preds >= float(prob_threshold)).astype(float)

    # Regression: predictions are next_close. Convert to sign(next_close - close) later.
    # Here we just pass through; caller should convert using close.
    return preds


def simulate_pnl_long_flat(
    *,
    close: pd.Series,
    next_close: pd.Series,
    position_long: np.ndarray,
    transaction_cost_bps: float = 1.0,
) -> pd.Series:
    """Simple bar-to-bar PnL: position in {0,1} times next_close/close - 1.

    Applies transaction costs on position changes: cost = (bps/10_000) * abs(delta_position).
    """
    if close is None or next_close is None:
        raise ValueError("close and next_close are required")

    close_s = close.astype(float)
    next_close_s = next_close.astype(float)
    idx = close_s.index.intersection(next_close_s.index)
    close_s = close_s.loc[idx]
    next_close_s = next_close_s.loc[idx]

    pos = np.asarray(position_long, dtype=float)
    if len(pos) != len(close_s):
        raise ValueError("position_long length must match close length")

    rets = (next_close_s.to_numpy(dtype=float) / close_s.to_numpy(dtype=float)) - 1.0

    delta_pos = np.zeros_like(pos)
    delta_pos[1:] = np.abs(pos[1:] - pos[:-1])
    costs = (float(transaction_cost_bps) / 10_000.0) * delta_pos

    pnl = (pos * rets) - costs
    return pd.Series(pnl, index=close_s.index)


def compute_backtest_metrics(returns: pd.Series, periods_per_year: int = 252) -> BacktestEvalResult:
    if returns is None or returns.empty:
        return BacktestEvalResult(n_samples=0, total_return=0.0, cagr=0.0, sharpe=0.0, max_drawdown=0.0)

    r = returns.astype(float)
    n = int(r.shape[0])

    equity = (1.0 + r).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)

    years = max(1e-9, n / float(periods_per_year))
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0)

    mean = float(r.mean())
    std = float(r.std(ddof=0))
    sharpe = float((mean / std) * np.sqrt(periods_per_year)) if std > 1e-12 else 0.0

    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1.0
    max_dd = float(drawdown.min())

    return BacktestEvalResult(
        n_samples=n,
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_dd,
    )


def evaluate_model_on_ohlcv(
    *,
    model: Any,
    X_eval: pd.DataFrame,
    close_eval: pd.Series,
    next_close_eval: pd.Series,
    target_kind: TargetKind,
    transaction_cost_bps: float = 1.0,
) -> BacktestEvalResult:
    if X_eval is None or X_eval.empty:
        return BacktestEvalResult(n_samples=0, total_return=0.0, cagr=0.0, sharpe=0.0, max_drawdown=0.0)

    if target_kind == "direction_up" and hasattr(model, "predict_proba"):
        proba = model.predict_proba(X_eval)
        # assume binary ordering [0,1]
        preds = np.asarray(proba)[:, 1].astype(float)
        pos = positions_from_predictions(predictions=preds, target_kind=target_kind)
    else:
        preds_raw = np.asarray(model.predict(X_eval), dtype=float)
        if target_kind == "direction_up":
            # some classifiers return {0,1}
            pos = (preds_raw >= 0.5).astype(float)
        else:
            # regression predicts next_close; go long if predicted up
            close_arr = _to_numpy_float(close_eval)
            if len(close_arr) != len(preds_raw):
                raise ValueError("close_eval length must match predictions")
            pos = (preds_raw > close_arr).astype(float)

    returns = simulate_pnl_long_flat(
        close=close_eval,
        next_close=next_close_eval,
        position_long=pos,
        transaction_cost_bps=transaction_cost_bps,
    )
    return compute_backtest_metrics(returns)


def evaluate_baseline_buy_and_hold(
    *,
    close_eval: pd.Series,
    next_close_eval: pd.Series,
    transaction_cost_bps: float = 0.0,
) -> BacktestEvalResult:
    pos = np.ones(len(close_eval), dtype=float)
    returns = simulate_pnl_long_flat(
        close=close_eval,
        next_close=next_close_eval,
        position_long=pos,
        transaction_cost_bps=transaction_cost_bps,
    )
    return compute_backtest_metrics(returns)
