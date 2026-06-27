"""Dynamic in-play universe feed (Phase 1 step 9).

ORB and other catalyst strategies want the day's most "in-play" names — high
relative-volume movers — not a static 22-symbol list. The live engine even notes
it lowered ORB's RV gate 1.5→1.0 because the static universe lacks RV>=1.5
catalyst names. This module is the SELECTION mechanism: given per-symbol bars,
rank by relative volume and return the top-K in-play names so a strategy can be
pointed at them with the canonical 1.5 threshold.

SCOPE (honest boundary): this is the ranking/selection LOGIC. Actually SOURCING a
wider symbol set (>the 22) from the live data provider each session is a
data-infrastructure follow-on (Phase 1 adds no new live feeds) — named in
docs/architecture/intra_2.0_phase1.md. The selector works on whatever pool it is
given; widen the pool upstream and the canonical RV gate becomes viable.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_RECENT_BARS = 5      # ~the opening-range window
DEFAULT_BASELINE_BARS = 390  # ~one RTH session of 1-min bars


def relative_volume(df: pd.DataFrame, recent_bars: int = DEFAULT_RECENT_BARS,
                    baseline_bars: int = DEFAULT_BASELINE_BARS) -> float:
    """recent average volume / trailing baseline average volume.

    1.0 = normal; >1 = trading hotter than its own recent baseline. Returns 0.0
    when there is not enough data or the baseline is empty (⇒ ranked last)."""
    if df is None or "volume" not in df.columns or len(df) < recent_bars + 1:
        return 0.0
    vol = pd.to_numeric(df["volume"], errors="coerce")
    recent = vol.iloc[-recent_bars:].mean()
    base = vol.iloc[-(baseline_bars + recent_bars):-recent_bars]
    if len(base) == 0:
        base = vol.iloc[:-recent_bars]
    base_mean = base.mean()
    if not base_mean or base_mean <= 0 or recent != recent:  # nan/zero guard
        return 0.0
    return float(recent / base_mean)


def rank_in_play(features: dict, recent_bars: int = DEFAULT_RECENT_BARS,
                 baseline_bars: int = DEFAULT_BASELINE_BARS,
                 exclude: set | None = None) -> list[tuple[str, float]]:
    """All symbols ranked by relative volume, descending. Excludes benchmarks."""
    exclude = exclude or {"SPY"}
    ranked = [
        (sym, relative_volume(df, recent_bars, baseline_bars))
        for sym, df in features.items() if sym not in exclude
    ]
    ranked.sort(key=lambda kv: kv[1], reverse=True)
    return ranked


def select_in_play_universe(features: dict, top_k: int = 50, min_rv: float = 1.5,
                            recent_bars: int = DEFAULT_RECENT_BARS,
                            baseline_bars: int = DEFAULT_BASELINE_BARS,
                            exclude: set | None = None) -> list[str]:
    """Top-K most in-play symbols with relative volume >= min_rv (the canonical
    ORB gate). Empty if nothing clears the gate — i.e. stand down, don't force
    entries into a quiet tape."""
    ranked = rank_in_play(features, recent_bars, baseline_bars, exclude)
    return [sym for sym, rv in ranked if rv >= min_rv][:top_k]
