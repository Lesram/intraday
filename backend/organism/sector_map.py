"""
Static GICS sector mapping for the organism's 30-symbol universe.

Used by the sector diversification gate in live_engine.py to prevent
over-concentration in a single sector.
"""

from __future__ import annotations

import os

MAX_PER_SECTOR = int(os.getenv("ORGANISM_MAX_PER_SECTOR", "4"))

# GICS sector mapping for all 30 symbols in the universe
SECTOR_MAP: dict[str, str] = {
    # Technology
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "AVGO": "Technology",
    "INTC": "Technology",
    "MU": "Technology",
    "ADBE": "Technology",
    "CRM": "Technology",
    # Communication Services
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "COST": "Consumer Discretionary",
    "WMT": "Consumer Discretionary",
    "UBER": "Consumer Discretionary",
    "ABNB": "Consumer Discretionary",
    # Healthcare
    "LLY": "Healthcare",
    # Energy
    "XOM": "Energy",
    # Industrials
    "CAT": "Industrials",
    # Fintech / Financial
    "COIN": "Financials",
    "SQ": "Financials",
    # Cloud / Software (counted under Technology)
    "SNOW": "Technology",
    "PLTR": "Technology",
    # ETFs — treated as their own "sector" so they don't crowd stock entries
    "SPY": "ETF",
    "QQQ": "ETF",
    "IWM": "ETF",
    "XLK": "ETF",
    "XLE": "ETF",
    # improve9 B4: Inverse ETFs for bearish participation (long-only)
    "SH": "ETF",
    "PSQ": "ETF",
}


def get_sector(symbol: str) -> str:
    """Return the GICS sector for a symbol, or 'Unknown'."""
    return SECTOR_MAP.get(symbol, "Unknown")


def count_sector_positions(
    open_symbols: set[str], sector: str
) -> int:
    """Count how many open positions are in the given sector."""
    return sum(1 for s in open_symbols if SECTOR_MAP.get(s) == sector)


def sector_gate_allows(
    symbol: str,
    open_symbols: set[str],
    planned_symbols: set[str] | None = None,
) -> bool:
    """Return True if opening a position in symbol would not breach the sector limit.

    Parameters
    ----------
    symbol : str
        The symbol we want to enter.
    open_symbols : set[str]
        Symbols with currently open positions at the broker.
    planned_symbols : set[str] | None
        Symbols already selected for entry earlier in this tick but not yet
        submitted.  Including these prevents intra-tick sector-limit violations
        when multiple candidates from the same sector are selected in one tick.
    """
    sector = get_sector(symbol)
    if sector == "Unknown":
        return True  # Don't block unknown symbols
    combined = open_symbols | (planned_symbols or set())
    current = count_sector_positions(combined, sector)
    return current < MAX_PER_SECTOR
