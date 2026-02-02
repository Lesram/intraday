from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DriftResult:
    psi_score: float
    feature_psi: dict[str, float]
    affected_features: list[str]


def _safe_props(props: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.asarray(props, dtype=float)
    p = np.clip(p, eps, None)
    return p / p.sum()


def psi_from_proportions(ref_props: np.ndarray, cur_props: np.ndarray, eps: float = 1e-6) -> float:
    ref = _safe_props(ref_props, eps=eps)
    cur = _safe_props(cur_props, eps=eps)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def build_quantile_bins(x: np.ndarray, n_bins: int = 10) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        # Degenerate bins
        return np.array([-np.inf, np.inf], dtype=float)

    qs = np.linspace(0.0, 1.0, int(n_bins) + 1)
    edges = np.quantile(x, qs)

    # Ensure strictly increasing edges
    edges = np.unique(edges)
    if edges.size < 2:
        return np.array([-np.inf, np.inf], dtype=float)

    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges.astype(float)


def proportions_in_bins(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        # All mass into first bin (arbitrary but stable)
        out = np.zeros(max(1, len(edges) - 1), dtype=float)
        out[0] = 1.0
        return out

    counts, _ = np.histogram(x, bins=edges)
    total = max(1, int(counts.sum()))
    return counts.astype(float) / float(total)


def build_drift_baseline(
    X: pd.DataFrame,
    *,
    n_bins: int = 10,
    max_features: int = 50,
) -> dict[str, Any]:
    if X is None or X.empty:
        return {"n_bins": int(n_bins), "features": {}}

    Xn = X.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).dropna(axis=0, how="any")
    if Xn.empty:
        return {"n_bins": int(n_bins), "features": {}}

    # Prefer features with larger variance (more informative for drift)
    stds = Xn.std(axis=0, ddof=0).sort_values(ascending=False)
    selected = list(stds.head(int(max_features)).index)

    features: dict[str, Any] = {}
    for col in selected:
        arr = Xn[col].to_numpy(dtype=float)
        edges = build_quantile_bins(arr, n_bins=int(n_bins))
        ref_props = proportions_in_bins(arr, edges)
        features[col] = {
            "edges": edges.tolist(),
            "ref_props": ref_props.tolist(),
        }

    return {
        "n_bins": int(n_bins),
        "features": features,
    }


def compute_drift(
    baseline: dict[str, Any],
    X_current: pd.DataFrame,
    *,
    top_k: int = 10,
) -> DriftResult:
    if not baseline or not baseline.get("features"):
        return DriftResult(psi_score=0.0, feature_psi={}, affected_features=[])

    if X_current is None or X_current.empty:
        return DriftResult(psi_score=0.0, feature_psi={}, affected_features=[])

    Xn = X_current.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)

    feature_psi: dict[str, float] = {}
    for col, cfg in (baseline.get("features") or {}).items():
        if col not in Xn.columns:
            continue

        edges = np.asarray(cfg.get("edges", [-np.inf, np.inf]), dtype=float)
        ref_props = np.asarray(cfg.get("ref_props", []), dtype=float)
        cur_props = proportions_in_bins(Xn[col].to_numpy(dtype=float), edges)

        if ref_props.size == 0 or cur_props.size == 0 or ref_props.size != cur_props.size:
            continue

        feature_psi[col] = psi_from_proportions(ref_props, cur_props)

    if not feature_psi:
        return DriftResult(psi_score=0.0, feature_psi={}, affected_features=[])

    # Overall PSI: mean across tracked features
    psi_score = float(np.mean(list(feature_psi.values())))

    affected = [k for k, _ in sorted(feature_psi.items(), key=lambda kv: kv[1], reverse=True)[: int(top_k)]]
    return DriftResult(psi_score=psi_score, feature_psi=feature_psi, affected_features=affected)
