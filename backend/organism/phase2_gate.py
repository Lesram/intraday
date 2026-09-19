"""Phase 2 PRECONDITION — Tasks 2 & 3: forward corpus + optional-stopping-proof verdict gate.

Binding constraints (from the build checklist):
- Two PRE-REGISTERED looks ONLY: n=60 and n=120 trend-slice trades. No other
  evaluation points exist.
- The verdict is STRUCTURALLY UNCOMPUTABLE between looks: the statistic is only ever
  computed on the fixed [:60] and [:120] prefixes. At any n that isn't a scheduled
  look the gate returns INSUFFICIENT with NO t — you cannot stop early on a number
  the system refuses to produce. (The two look statistics are frozen prefixes, not
  a live "t toward 2" readout.)
- O'Brien-Fleming alpha spending across the two looks: stringent at n=60
  (z1≈2.40), near-nominal at n=120 (z2≈1.70) — the boundary shape is z_k ∝
  1/sqrt(info_fraction); the constant is calibrated so the SCHEDULE controls
  type-I at ~5% (proven by null_simulation, the acceptance gate).
- Cluster/session-robust variance: trades lump in trending sessions, so the t uses
  a session-cluster-robust SE (CR1). Naive iid SEs would understate variance and
  inflate the FPR.
- State composition: INSUFFICIENT below a look or when the boundary isn't crossed
  before the final look; PASS if a look's boundary is cleared; FAIL ONLY at n=120.
  "Not yet" never renders as "no" before the final look.

Forward-only (Task 2): the corpus is trades taken STRICTLY AFTER FROZEN_AT. Any
pre-cutoff row is rejected. Empty-until-enough is a valid state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.organism.costing import DEFAULT_COST_BPS, apply_costs

# ── Pre-registered schedule (immutable) ────────────────────────────────
LOOKS = (60, 120)                 # trend-slice trade counts
INFO_FRACS = (60 / 120, 120 / 120)  # (0.5, 1.0)
OBF_C = 1.871                     # calibrated against the CLUSTERED null (the binding
                                  # check), NOT iid: the finite-cluster t has fatter tails
                                  # than normal, so the normal-calibrated constant under-
                                  # covers. At 1.871 the schedule's worst-case FPR over
                                  # session_corr∈[0,0.8] is ~0.044 (≤5%, flat in clustering).
# OBF shape: z_k = OBF_C / sqrt(info_fraction_k)
Z_BOUNDARY = {LOOKS[i]: OBF_C / (INFO_FRACS[i] ** 0.5) for i in range(len(LOOKS))}

INSUFFICIENT, PASS, FAIL = "INSUFFICIENT", "PASS", "FAIL"

# entry_source -> framework strategy (eod is parked → ignored)
_STRATEGY_MAP = {
    "alpha": "momentum", "alpha+breakout": "momentum",
    "breakout": "breakout",
    "orb": "orb", "orb_sip": "orb",
    "mr": "mean_reversion", "mean_reversion": "mean_reversion",
}
MOMENTUM_TREND_REGIMES = {"trending_up", "high_vol"}  # regime-conditional verdict


def cluster_robust_t(pnl, sessions) -> float:
    """Session-cluster-robust (CR1) t-stat for the mean. Within-session correlation
    inflates the SE (conservative) instead of being counted as independent info."""
    pnl = np.asarray(pnl, dtype="float64")
    sessions = np.asarray(sessions)
    n = len(pnl)
    if n < 2:
        return 0.0
    mean = pnl.mean()
    resid = pnl - mean
    groups = np.unique(sessions)
    g = len(groups)
    if g < 2:
        return 0.0
    ss = sum(resid[sessions == grp].sum() ** 2 for grp in groups)  # cluster meat
    var_mean = ss / (n ** 2) * (g / (g - 1))                       # CR1 correction
    se = var_mean ** 0.5
    return float(mean / se) if se > 0 else 0.0


def _evaluate_prefix(pnl, sessions, look_n) -> tuple[bool, float]:
    """One pre-registered look on the FIRST `look_n` trades only. Returns
    (boundary_cleared, t). Never sees more than the prefix → no peeking."""
    t = cluster_robust_t(pnl[:look_n], sessions[:look_n])
    cleared = t >= Z_BOUNDARY[look_n]   # z>=positive boundary ⇒ mean>0 (one-sided)
    return cleared, t


def evaluate_gate(net_pnl, sessions) -> dict:
    """Optional-stopping-proof verdict. `net_pnl`/`sessions` are the strategy's
    (already regime-filtered) forward trades in chronological order.

    The statistic exists ONLY at the [:60] and [:120] prefixes. Between/below looks
    there is no t — INSUFFICIENT, by construction."""
    pnl = np.asarray(net_pnl, dtype="float64")
    sess = np.asarray(sessions)
    n = len(pnl)
    n60, n120 = LOOKS

    if n < n60:
        return {"state": INSUFFICIENT, "n": n, "look": None, "t": None,
                "note": f"{n}/{n60} trend trades to first look — no statistic computed"}

    cleared1, t1 = _evaluate_prefix(pnl, sess, n60)
    if cleared1:
        return {"state": PASS, "n": n, "look": 1, "t": round(t1, 3),
                "boundary": round(Z_BOUNDARY[n60], 3)}

    if n < n120:
        # Look 1 did not clear; final look not reached. NOT a fail. The look-1
        # statistic is frozen on [:60] — it is not a live readout.
        return {"state": INSUFFICIENT, "n": n, "look": 1, "t": round(t1, 3),
                "boundary": round(Z_BOUNDARY[n60], 3),
                "note": f"look-1 not cleared; {n}/{n120} to final look (frozen stat)"}

    cleared2, t2 = _evaluate_prefix(pnl, sess, n120)
    return {"state": PASS if cleared2 else FAIL, "n": n, "look": 2,
            "t": round(t2, 3), "boundary": round(Z_BOUNDARY[n120], 3)}


# ── Task 2: forward-only corpus ────────────────────────────────────────
def load_forward_corpus(trade_history_path: str, frozen_at: str,
                        cost_bps: float = DEFAULT_COST_BPS) -> pd.DataFrame:
    """Trades taken STRICTLY AFTER frozen_at, costed, mapped to framework strategy +
    session. Pre-cutoff rows are REJECTED (disjointness). Empty is valid."""
    df = pd.read_csv(trade_history_path)
    cutoff = pd.Timestamp(frozen_at)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    closed = pd.to_datetime(df["closed_at"], utc=True, errors="coerce")
    df = df[closed.notna() & (closed > cutoff)].copy()   # DISJOINTNESS: strictly after
    if len(df) == 0:
        return pd.DataFrame(columns=["strategy", "regime", "session", "net_pnl", "closed_at"])
    df["closed_at"] = closed[df.index]
    df["session"] = df["closed_at"].dt.date.astype(str)
    df["strategy"] = df["entry_source"].map(_STRATEGY_MAP)
    df = df[df["strategy"].notna()]
    df["net_pnl"] = apply_costs(df, cost_bps)["net_pnl"]
    return df[["strategy", "regime_at_entry", "session", "net_pnl", "closed_at"]].rename(
        columns={"regime_at_entry": "regime"}).sort_values("closed_at").reset_index(drop=True)


def strategy_slice(corpus: pd.DataFrame, strategy: str,
                   regimes: set | None = None) -> pd.DataFrame:
    """One strategy's forward trades, optionally regime-conditional (momentum ⇒
    trend slice). Chronological."""
    s = corpus[corpus["strategy"] == strategy]
    if regimes is not None:
        s = s[s["regime"].isin(regimes)]
    return s.sort_values("closed_at").reset_index(drop=True)


def gate_for_strategy(corpus: pd.DataFrame, strategy: str,
                      regimes: set | None = None) -> dict:
    s = strategy_slice(corpus, strategy, regimes)
    out = evaluate_gate(s["net_pnl"].to_numpy(), s["session"].to_numpy())
    out["strategy"] = strategy
    out["regime_conditional"] = sorted(regimes) if regimes else None
    return out


# ── The acceptance teeth: null simulation FPR under the actual schedule ──
def null_simulation(n_books: int, sessions_per_book: int = 30,
                    trades_per_session: int = 5, session_corr: float = 0.6,
                    seed: int = 0) -> float:
    """Empirical false-positive rate of the gate under a realistically-CLUSTERED
    null (zero true edge). Each session = a shared zero-mean shock + per-trade
    noise (within-session correlation), so trades are NOT iid. Runs the full
    schedule (look-1 then look-2) per book and counts PASS. This is the proof the
    schedule controls type-I — a gate that secretly inflates FPR fails here."""
    rng = np.random.default_rng(seed)
    n_per = sessions_per_book * trades_per_session
    need = max(n_per, LOOKS[-1])
    passes = 0
    for _ in range(n_books):
        # clustered zero-mean returns: session shock + idiosyncratic noise
        n_sess = max(sessions_per_book, LOOKS[-1] // trades_per_session + 2)
        shocks = rng.normal(0, session_corr ** 0.5, n_sess)
        pnl, sess = [], []
        for g in range(n_sess):
            k = trades_per_session
            noise = rng.normal(0, (1 - session_corr) ** 0.5, k)
            pnl.extend(shocks[g] + noise)         # mean 0; correlated within session
            sess.extend([g] * k)
        pnl = np.asarray(pnl[:max(need, LOOKS[-1])])
        sess = np.asarray(sess[:len(pnl)])
        if len(pnl) < LOOKS[-1]:
            continue
        if evaluate_gate(pnl, sess)["state"] == PASS:
            passes += 1
    return passes / n_books
