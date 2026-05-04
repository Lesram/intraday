"""Phase 2 strategy expectancy attribution.

The V12/V13 health work made total PnL visible.  Phase 2 needs the next
layer: which slices are helping or hurting.  This module is intentionally
read-only.  It accepts the same heterogeneous trade shapes as
``strategy_expectancy`` and returns compact, bounded attribution payloads
for manifests and operator APIs.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable


_WINDOWS: tuple[int, ...] = (25, 50, 100)
_SEGMENT_FIELDS: tuple[str, ...] = (
    "exit_reason",
    "entry_source",
    "regime_at_entry",
    "confidence_bucket",
)


def _get(trade: Any, field: str, default: Any = None) -> Any:
    if isinstance(trade, dict):
        return trade.get(field, default)
    return getattr(trade, field, default)


def _finite_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _label(raw: Any) -> str:
    if raw is None:
        return "<blank>"
    text = str(raw).strip()
    return text if text else "<blank>"


def _exit_family(raw: Any) -> str:
    text = _label(raw)
    if text.startswith("pyramid_cut_"):
        return "pyramid_cut"
    return text


def _confidence_bucket(confidence: float) -> str:
    if confidence < 0.4:
        return "<0.4"
    if confidence < 0.5:
        return "0.4-0.5"
    if confidence < 0.6:
        return "0.5-0.6"
    if confidence < 0.7:
        return "0.6-0.7"
    return ">=0.7"


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def _normalise_trades(trades: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in trades:
        pnl = _finite_float(_get(trade, "pnl", None), default=math.nan)
        if not math.isfinite(pnl):
            continue
        confidence = _finite_float(_get(trade, "confidence", 0.0), default=0.0)
        rows.append({
            "pnl": pnl,
            "exit_reason": _exit_family(_get(trade, "exit_reason", "")),
            "entry_source": _label(_get(trade, "entry_source", "")),
            "regime_at_entry": _label(_get(trade, "regime_at_entry", "")),
            "confidence": confidence,
            "confidence_bucket": _confidence_bucket(confidence),
        })
    return rows


def _segment_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "n_trades": 0,
            "total_pnl": 0.0,
            "mean_pnl": 0.0,
            "win_rate": 0.0,
        }
    pnls = [float(r["pnl"]) for r in rows]
    return {
        "n_trades": n,
        "total_pnl": _round(sum(pnls)),
        "mean_pnl": _round(statistics.fmean(pnls)),
        "win_rate": _round(sum(1 for p in pnls if p > 0) / n),
    }


def _segments(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for field in _SEGMENT_FIELDS:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        payloads = [
            {"value": value, **_segment_payload(group_rows)}
            for value, group_rows in groups.items()
        ]
        payloads.sort(key=lambda p: (float(p["total_pnl"]), -int(p["n_trades"])))
        out[field] = payloads[:top_n]
    return out


def _confidence_inversion(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bucket_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        bucket_groups[str(row["confidence_bucket"])].append(row)

    bucket_payloads = {
        bucket: _segment_payload(bucket_groups.get(bucket, []))
        for bucket in ("<0.4", "0.4-0.5", "0.5-0.6", "0.6-0.7", ">=0.7")
    }
    high = bucket_payloads[">=0.7"]
    mid = bucket_payloads["0.5-0.6"]
    enough_samples = high["n_trades"] >= 5 and mid["n_trades"] >= 5
    inverted = bool(
        enough_samples
        and float(high["mean_pnl"]) < 0
        and float(mid["mean_pnl"]) > float(high["mean_pnl"])
    )
    return {
        "flag": inverted,
        "reason": (
            "high-confidence bucket underperforms mid-confidence bucket"
            if inverted
            else "insufficient evidence or no high-confidence underperformance"
        ),
        "buckets": bucket_payloads,
    }


def compute_from_trades(
    trades: Iterable[Any],
    *,
    windows: tuple[int, ...] = _WINDOWS,
    top_n: int = 6,
) -> dict[str, Any]:
    """Compute bounded attribution payloads from closed trades.

    ``top_n`` caps each segment list so manifest writes stay small and
    stable as the trade history grows.
    """
    rows = _normalise_trades(trades)
    full = _segment_payload(rows)
    out: dict[str, Any] = {
        "n_trades": full["n_trades"],
        "total_pnl": full["total_pnl"],
        "segments": _segments(rows, top_n=top_n),
        "confidence_inversion": _confidence_inversion(rows),
        "windows": {},
    }
    for window in windows:
        if window <= 0:
            continue
        window_rows = rows[-min(window, len(rows)):]
        out["windows"][f"last_{window}"] = {
            **_segment_payload(window_rows),
            "segments": _segments(window_rows, top_n=top_n),
            "confidence_inversion": _confidence_inversion(window_rows),
        }
    return out
