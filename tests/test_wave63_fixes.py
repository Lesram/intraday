"""V11 prep / Wave-63 (2026-05-03): HH2-N-1 calculate_indicator partial split.

Locks the regression for V8 HH2-N-1 (deferred since V8): the
calculate_indicator route at backend/api/routes/indicators.py was
614 LOC of intermixed concerns.  Wave-63 extracts the Alpaca
timeframe + date-range resolution as a pure helper.

Run with: ./venv/bin/python -m pytest tests/test_wave63_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_hh2_n_1_helper_extracted():
    from backend.api.routes import indicators
    assert hasattr(indicators, "_resolve_alpaca_date_range"), (
        "HH2-N-1 regression: extracted helper missing."
    )


def test_hh2_n_1_route_uses_helper():
    from backend.api.routes import indicators
    src = inspect.getsource(indicators.calculate_indicator)
    assert "_resolve_alpaca_date_range" in src, (
        "HH2-N-1 regression: calculate_indicator no longer uses the "
        "extracted helper."
    )
    assert "Wave-63" in src, "Wave-63 marker missing"


def test_hh2_n_1_route_loc_reduced():
    """The route function should be <580 LOC after the wave-63 extraction
    (was 614 LOC pre-wave)."""
    from backend.api.routes import indicators
    src = inspect.getsource(indicators.calculate_indicator)
    n = src.count("\n") + 1
    assert n < 580, (
        f"HH2-N-1 regression: calculate_indicator is {n} LOC; "
        "expected < 580 after wave-63 split."
    )
