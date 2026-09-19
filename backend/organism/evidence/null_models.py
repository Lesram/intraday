"""Null model helpers for strategy research."""

from __future__ import annotations

import random
from statistics import fmean
from typing import Sequence

from backend.organism.evidence.benchmark_report import directional_return_bps


def delayed_entry_return_bps(
    prices: Sequence[float],
    *,
    entry_index: int,
    exit_index: int,
    delay_bars: int,
    side: str = "long",
) -> float | None:
    """Return directional bps for entering later while keeping the same exit."""
    delayed_index = entry_index + delay_bars
    if delayed_index < 0 or exit_index < 0:
        return None
    if delayed_index >= len(prices) or exit_index >= len(prices):
        return None
    if delayed_index >= exit_index:
        return None
    return directional_return_bps(prices[delayed_index], prices[exit_index], side)


def random_same_hold_return_bps(
    prices: Sequence[float],
    *,
    hold_bars: int,
    side: str = "long",
    samples: int = 100,
    seed: int = 0,
) -> float | None:
    """Average random-entry return with the same hold duration."""
    if hold_bars <= 0 or len(prices) <= hold_bars:
        return None
    rng = random.Random(seed)
    max_entry = len(prices) - hold_bars - 1
    if max_entry < 0:
        return None
    draws = []
    for _ in range(max(samples, 1)):
        entry = rng.randint(0, max_entry)
        exit_ = entry + hold_bars
        draws.append(directional_return_bps(prices[entry], prices[exit_], side))
    return round(fmean(draws), 6)


def side_flip_return_bps(entry_price: float, exit_price: float, side: str = "long") -> float:
    flipped = "short" if str(side).lower() == "long" else "long"
    return directional_return_bps(entry_price, exit_price, flipped)
