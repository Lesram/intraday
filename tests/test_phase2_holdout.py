"""Phase 2 PRECONDITION — Task 1 acceptance: the REAL holdout has teeth.

The teeth are only real if the planted overfit is GENUINELY predictive on the
train fold (clears train_t≥2) and useless out of it — a spurious signal fit to
train, not a param degenerate everywhere (which would pass vacuously). So the
acceptance is the PAIR: train_stat≥2 AND test_stat≈0. The control test shows a
same-window report (the eval-window-restriction trap) would have reported the
inflated stat as real.
"""
from __future__ import annotations

import numpy as np

from scripts.strategy_backtester import (
    _tstat, time_train_test_split, walk_forward_select,
)


def test_split_is_disjoint_with_embargo():
    train, test = time_train_test_split(100, train_frac=0.6, embargo=5)
    assert set(train).isdisjoint(test)            # no overlap
    assert max(train) < min(test)                 # time-ordered
    assert min(test) - max(train) - 1 >= 5        # embargo/purge gap honored


def test_walk_forward_catches_overfit_and_has_teeth():
    rng = np.random.default_rng(0)
    N, M, kstar = 250, 20, 0
    target = rng.normal(0, 1, N)                  # "returns"
    signals = rng.normal(0, 1, (N, M))            # M random candidate signals
    train_idx, test_idx = time_train_test_split(N, 0.6, embargo=5)
    # PLANT: column kstar = sign(target) on TRAIN (perfect in-sample fit to train),
    # left random on TEST -> spurious overfit that REALLY clears the bar on train.
    signals[np.array(train_idx), kstar] = np.sign(target[np.array(train_idx)])

    def pnl(col, idx):
        ix = np.array(idx)
        return signals[ix, col] * target[ix]

    res = walk_forward_select(range(M), pnl, N, train_frac=0.6, embargo=5)

    # The sweep selects the train-overfit column...
    assert res["selected"] == kstar
    # ...and it GENUINELY worked in-sample (teeth requirement, not vacuous)...
    assert res["train_stat"] >= 2.0
    # ...but the untouched test fold catches it: edge collapses OOS.
    assert abs(res["test_stat"]) < 1.5

    # CONTROL — the trap this exists to close: select on train, REPORT ON THE SAME
    # WINDOW (what a mere eval-window restriction does). The inflated stat survives,
    # i.e. you'd believe a fake edge. The holdout's whole value is that test_stat
    # above did NOT.
    same_window_stat = _tstat(pnl(kstar, train_idx))
    assert same_window_stat >= 2.0
    assert same_window_stat - abs(res["test_stat"]) > 2.0   # holdout collapses it
