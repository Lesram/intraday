import numpy as np
import pandas as pd
import pytest

from backend.ml.model_selection import (
    evaluate_baseline_buy_and_hold,
    evaluate_model_on_ohlcv,
    time_split_by_fraction,
)


class AlwaysUpClassifier:
    def predict_proba(self, X):
        # always 100% up
        n = len(X)
        return np.column_stack([np.zeros(n), np.ones(n)])


class AlwaysDownClassifier:
    def predict_proba(self, X):
        # always 0% up
        n = len(X)
        return np.column_stack([np.ones(n), np.zeros(n)])


@pytest.mark.unit
def test_time_split_is_monotonic():
    idx = pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC")
    df = pd.DataFrame({"a": range(10)}, index=idx)

    train_df, eval_df = time_split_by_fraction(df, 0.3)
    assert len(train_df) == 7
    assert len(eval_df) == 3
    assert train_df.index.max() < eval_df.index.min()


@pytest.mark.unit
def test_backtest_eval_prefers_better_model_profitwise():
    idx = pd.date_range("2025-01-01", periods=20, freq="D", tz="UTC")

    # strictly increasing prices => buy-and-hold is positive
    close = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
    next_close = close.shift(-1).dropna()
    close_eval = close.loc[next_close.index]

    X = pd.DataFrame({"f1": np.random.RandomState(0).rand(len(close_eval))}, index=close_eval.index)

    good = AlwaysUpClassifier()
    bad = AlwaysDownClassifier()

    good_res = evaluate_model_on_ohlcv(
        model=good,
        X_eval=X,
        close_eval=close_eval,
        next_close_eval=next_close,
        target_kind="direction_up",
        transaction_cost_bps=0.0,
    )
    bad_res = evaluate_model_on_ohlcv(
        model=bad,
        X_eval=X,
        close_eval=close_eval,
        next_close_eval=next_close,
        target_kind="direction_up",
        transaction_cost_bps=0.0,
    )
    baseline = evaluate_baseline_buy_and_hold(
        close_eval=close_eval,
        next_close_eval=next_close,
        transaction_cost_bps=0.0,
    )

    assert good_res.total_return > bad_res.total_return
    assert good_res.total_return == baseline.total_return
    assert bad_res.total_return == 0.0
