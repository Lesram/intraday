"""Phase 3 Task 2 (deferred step 5b) — confidence REDESIGN evaluation lab.

The live confidence composite (0.39*readiness + 0.26*squeeze + 0.35*tension) is
ANTI-predictive: corr(confidence, correct_direction) = -0.112. Porting it into
the framework would enshrine a known defect, so 5b is an open redesign with one
pre-registered acceptance rule (docs/architecture/INTRA_2.0_FINAL_BUILDOUT_PLAN.md
Task 2):

    A confidence model routes into live sizing/ranking ONLY if it beats FLAT
    sizing on costed, out-of-sample expectancy at t>=2 on the test fold.
    If nothing beats flat, FLAT SHIPS — a valid, honest outcome that removes
    the anti-predictive composite from the decision path.

Protocol (leakage-impossible by construction, same shape as walk_forward_select):
  1. Trades come from the causal, costed backtester (scripts/strategy_backtester)
     with per-trade feature snapshots captured at the SIGNAL bar.
  2. Time-ordered train/test split on signal_idx with an embargo gap.
  3. Every candidate model is FIT on the train fold only (fit() never sees test).
  4. Confidence maps to a sizing weight via the live Kelly scale w = 0.3 + 1.2*c,
     normalized by the TRAIN-fold mean weight (exposure-neutral vs flat; the
     normalizer is a train-fold constant, never recomputed on test).
  5. SELECTION among models uses train-fold t-stat only; the selected model's
     TEST-fold read is the verdict. Ship iff test_t >= 2 AND test expectancy
     beats flat's test expectancy.

Cross-strategy comparability: models are fit PER STRATEGY and their outputs are
calibrated train-fold rank-CDF values, so c=0.8 means "top-quintile conviction
within this strategy's own train distribution" for every strategy — one scale,
one meaning. Flat is trivially comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Kelly's live confidence->size scale (0.3x..1.5x) — reuse the live range so a
# shipped model drops into the sizing path without a second calibration.
W_LO, W_SPAN = 0.3, 1.2

#: Feature columns candidate models may read (all in the 79-col live contract).
MODEL_FEATURES = [
    "comp_breakout_readiness", "comp_squeeze_momentum", "comp_momentum_quality",
    "vol_sma_ratio", "atr_ratio", "trend_strength", "choppiness",
    "rel_strength_spy", "z_score_20", "rsi_14",
]


def _rank_cdf(train_vals: np.ndarray):
    """Return a scorer mapping raw values -> train-fold rank CDF in [0,1].

    Fit artifact is just the sorted train values — evaluating a test value never
    updates it (no leakage)."""
    ref = np.sort(train_vals[np.isfinite(train_vals)])

    def score(v: np.ndarray) -> np.ndarray:
        v = np.nan_to_num(np.asarray(v, dtype=float), nan=float(np.median(ref)) if len(ref) else 0.0)
        if len(ref) == 0:
            return np.full(len(v), 0.5)
        return np.searchsorted(ref, v, side="right") / len(ref)

    return score


@dataclass
class ConfidenceModel:
    """A candidate: fit(train) -> per-trade confidence in [0,1]."""
    name: str
    kind: str                      # "flat" | "native" | "feature" | "logit"
    feature: str | None = None     # for kind == "feature"
    _scorer: object = field(default=None, repr=False)

    def fit(self, train: pd.DataFrame) -> "ConfidenceModel":
        if self.kind == "flat":
            self._scorer = lambda df: np.full(len(df), 1.0)
        elif self.kind == "native":
            cdf = _rank_cdf(train["confidence"].to_numpy(dtype=float))
            self._scorer = lambda df: cdf(df["confidence"].to_numpy(dtype=float))
        elif self.kind == "feature":
            col = f"feat_{self.feature}"
            cdf = _rank_cdf(train[col].to_numpy(dtype=float))
            self._scorer = lambda df: cdf(df[col].to_numpy(dtype=float))
        elif self.kind == "logit":
            self._fit_logit(train)
        else:
            raise ValueError(f"unknown kind {self.kind}")
        return self

    def _fit_logit(self, train: pd.DataFrame) -> None:
        from sklearn.linear_model import LogisticRegression
        cols = [f"feat_{f}" for f in MODEL_FEATURES if f"feat_{f}" in train.columns]
        X = train[cols].apply(pd.to_numeric, errors="coerce")
        mu, sd = X.mean(), X.std(ddof=0).replace(0.0, 1.0)
        y = (train["net_pnl"].to_numpy(dtype=float) > 0).astype(int)
        if y.sum() in (0, len(y)) or len(y) < 20:      # degenerate train fold
            self._scorer = lambda df: np.full(len(df), 0.5)
            return
        clf = LogisticRegression(max_iter=1000, C=0.5, random_state=7)
        clf.fit(((X - mu) / sd).fillna(0.0).to_numpy(), y)
        # Calibrate output through the train-fold rank CDF -> comparable scale.
        p_train = clf.predict_proba(((X - mu) / sd).fillna(0.0).to_numpy())[:, 1]
        cdf = _rank_cdf(p_train)

        def score(df: pd.DataFrame) -> np.ndarray:
            Xs = ((df[cols].apply(pd.to_numeric, errors="coerce") - mu) / sd).fillna(0.0)
            return cdf(clf.predict_proba(Xs.to_numpy())[:, 1])

        self._scorer = score

    def confidence(self, trades: pd.DataFrame) -> np.ndarray:
        if self._scorer is None:
            raise RuntimeError(f"model {self.name} not fit")
        return np.clip(np.asarray(self._scorer(trades), dtype=float), 0.0, 1.0)


def default_models() -> list[ConfidenceModel]:
    ms = [ConfidenceModel("flat", "flat"), ConfidenceModel("native", "native")]
    ms += [ConfidenceModel(f"rank:{f}", "feature", feature=f) for f in MODEL_FEATURES]
    ms.append(ConfidenceModel("logit_pwin", "logit"))
    return ms


def _tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        return 0.0
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else 0.0


def _cluster_tstat(x: np.ndarray, clusters: np.ndarray) -> float:
    """Session-cluster-robust t (CR1, same estimator family as phase2_gate):
    same-session trades share regime/news shocks, so iid SEs overstate
    precision. Mean is the plain mean; the variance is computed over cluster
    sums (CR1 small-sample scaling G/(G-1))."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        return 0.0
    cl = pd.Series(clusters[:n])
    sums = pd.Series(x - x.mean()).groupby(cl.values).sum()
    G = len(sums)
    if G < 2:
        return _tstat(x)
    var_mean = (G / (G - 1)) * float((sums ** 2).sum()) / (n ** 2)
    se = np.sqrt(var_mean)
    return float(x.mean() / se) if se > 0 else 0.0


def _weights(c: np.ndarray, train_mean_w: float) -> np.ndarray:
    return (W_LO + W_SPAN * c) / train_mean_w


def evaluate_models(trades: pd.DataFrame, *, train_frac: float = 0.6,
                    embargo_bars: int = 300, models: list[ConfidenceModel] | None = None,
                    t_gate: float = 2.0, min_n_train: int = 30,
                    min_n_test: int = 20) -> dict:
    """Run the 5b protocol for ONE strategy's trades. Returns the verdict dict.

    trades: backtester output rows (needs net_pnl or pnl+cost applied upstream,
    signal_idx, confidence, feat_* columns). Time-split on signal_idx.
    """
    if "net_pnl" not in trades.columns:
        raise ValueError("trades must be costed (net_pnl) before evaluation")
    trades = trades.sort_values("signal_idx").reset_index(drop=True)
    cut = trades["signal_idx"].quantile(train_frac)
    train = trades[trades["signal_idx"] <= cut]
    test = trades[trades["signal_idx"] > cut + embargo_bars]
    out = {"n_train": len(train), "n_test": len(test), "train_frac": train_frac,
           "embargo_bars": embargo_bars, "t_gate": t_gate, "models": {}}
    if len(train) < min_n_train or len(test) < min_n_test:
        out["verdict"] = "INSUFFICIENT"
        out["ship"] = "flat"
        out["reason"] = f"n_train={len(train)}<{min_n_train} or n_test={len(test)}<{min_n_test}"
        return out

    flat_test_exp = float(test["net_pnl"].mean())
    net_tr = train["net_pnl"].to_numpy(dtype=float)
    net_te = test["net_pnl"].to_numpy(dtype=float)

    rows = {}
    for m in (models if models is not None else default_models()):
        m.fit(train)                                   # TRAIN ONLY — never test
        c_tr, c_te = m.confidence(train), m.confidence(test)
        mean_w_tr = float(np.mean(W_LO + W_SPAN * c_tr)) or 1.0
        w_tr = _weights(c_tr, mean_w_tr)
        w_te = _weights(c_te, mean_w_tr)               # train-fold normalizer on test
        wins_te = (net_te > 0).astype(float)
        # Session id for cluster-robust SEs: signal_idx // bars_per_day.
        sess_te = (test["signal_idx"].to_numpy() // 390).astype(int)
        rows[m.name] = {
            "train_exp": float(np.mean(w_tr * net_tr)), "train_t": _tstat(w_tr * net_tr),
            "test_exp": float(np.mean(w_te * net_te)), "test_t": _tstat(w_te * net_te),
            "test_t_clustered": _cluster_tstat(w_te * net_te, sess_te),
            "corr_conf_win_test": float(np.corrcoef(c_te, wins_te)[0, 1])
            if len(set(c_te)) > 1 and len(set(wins_te)) > 1 else 0.0,
        }
    out["models"] = rows
    out["flat_test_exp"] = flat_test_exp

    # SELECT on train t only (flat excluded — it's the bar, not a contender).
    contenders = {k: v for k, v in rows.items() if k != "flat"}
    sel = max(contenders, key=lambda k: contenders[k]["train_t"])
    s = rows[sel]
    out["selected_on_train"] = sel
    # Two-step decision (repo protocol, cf. phase2_param_sweep + phase2_gate):
    # the plain t is LENIENT, so failing it is conclusive; passing it must ALSO
    # survive the session-cluster-robust t at the same gate, or the "pass" is
    # an iid-SE artifact of correlated same-session trades.
    passed_simple = s["test_t"] >= t_gate and s["test_exp"] > flat_test_exp
    passed = passed_simple and s["test_t_clustered"] >= t_gate
    out["verdict"] = "MODEL_SHIPS" if passed else "FLAT_SHIPS"
    out["ship"] = sel if passed else "flat"
    detail = (f"train-selected '{sel}' test_t={s['test_t']:+.2f} "
              f"(clustered {s['test_t_clustered']:+.2f}) "
              f"test_exp={s['test_exp']:+.4f} vs flat_test_exp={flat_test_exp:+.4f} "
              f"@ gate t>={t_gate}")
    if passed_simple and not passed:
        detail += " — simple-t pass KILLED by cluster-robust re-check"
    out["reason"] = detail
    return out


def report(name: str, res: dict) -> str:
    lines = ["=" * 78,
             f"5b CONFIDENCE REDESIGN — {name}  (fit/select on TRAIN, verdict on TEST)",
             "=" * 78,
             f"n_train={res['n_train']}  n_test={res['n_test']}  "
             f"embargo={res['embargo_bars']} bars  gate: test_t>={res['t_gate']} "
             f"AND test_exp > flat"]
    if res.get("models"):
        lines.append(f"{'model':28s} {'train_t':>8s} {'test_t':>8s} {'t_clust':>8s} "
                     f"{'test_exp':>10s} {'corr(c,win)':>12s}")
        for k, v in sorted(res["models"].items(), key=lambda kv: -kv[1]["train_t"]):
            lines.append(f"{k:28s} {v['train_t']:+8.2f} {v['test_t']:+8.2f} "
                         f"{v.get('test_t_clustered', 0.0):+8.2f} "
                         f"{v['test_exp']:+10.4f} {v['corr_conf_win_test']:+12.3f}")
    lines.append(f"VERDICT: {res['verdict']}  ->  ship '{res['ship']}'")
    lines.append(f"  {res.get('reason', '')}")
    lines.append("=" * 78)
    return "\n".join(lines)
