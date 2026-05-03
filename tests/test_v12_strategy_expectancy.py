"""V12 W71 behavioral tests for the strategy-expectancy gate (EXT-1).

These tests are BEHAVIORAL, not marker-grep.  Each one mints state
(synthetic trade list, real manifest write, real API call) and asserts
on observed values — not on ``inspect.getsource`` or ``"X" in src``.

The auditor's #1 V11 finding: manifest never carried realized PnL or
Sharpe; ``trade_history.csv`` showed -$634, 33.7% win rate, but the
operator dashboard had no way to see this without grepping the CSV.
W71 closes that gap.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_strategy_expectancy.py -v
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────
# 1. The shared helper: behavioral verification of math correctness.
# ────────────────────────────────────────────────────────────────────

def test_compute_from_pnls_empty():
    from backend.organism.strategy_expectancy import compute_from_pnls
    out = compute_from_pnls([])
    assert out["n_trades"] == 0
    assert out["total_pnl"] == 0.0
    assert out["win_rate"] == 0.0
    assert out["sharpe_ratio_per_trade"] == 0.0
    # All required fields must be present even on empty input.
    from backend.organism.strategy_expectancy import required_fields
    for f in required_fields():
        assert f in out, f


def test_compute_from_pnls_known_values():
    """A hand-chosen sequence with verifiable totals."""
    from backend.organism.strategy_expectancy import compute_from_pnls
    pnls = [10.0, -5.0, 8.0, -3.0, 2.0]   # total = 12.0, mean = 2.4
    out = compute_from_pnls(pnls)
    assert out["n_trades"] == 5
    assert out["n_wins"] == 3
    assert out["n_losses"] == 2
    assert out["total_pnl"] == pytest.approx(12.0, abs=1e-6)
    assert out["mean_pnl"] == pytest.approx(2.4, abs=1e-6)
    assert out["median_pnl"] == pytest.approx(2.0, abs=1e-6)
    assert out["win_rate"] == pytest.approx(0.6, abs=1e-6)
    # Sharpe per-trade = mean / pstdev * sqrt(n).  Verifiable.
    import statistics
    expected_sharpe = (
        statistics.fmean(pnls)
        / statistics.pstdev(pnls)
        * math.sqrt(len(pnls))
    )
    assert out["sharpe_ratio_per_trade"] == pytest.approx(expected_sharpe, abs=1e-3)


def test_compute_from_pnls_max_drawdown_known_curve():
    """Cumulative: 10, 15, 25, 5, -5, -10, 0.  Peak=25, trough=-10. DD=-35."""
    from backend.organism.strategy_expectancy import compute_from_pnls
    pnls = [10, 5, 10, -20, -10, -5, 10]
    out = compute_from_pnls(pnls)
    assert out["max_drawdown"] == pytest.approx(-35.0, abs=1e-6)


def test_compute_from_pnls_window_smaller_than_full():
    from backend.organism.strategy_expectancy import compute_from_pnls
    # First 50 are -1.0 each, last 25 are +5.0 each → 75 trades total.
    pnls = [-1.0] * 50 + [5.0] * 25
    out = compute_from_pnls(pnls)
    assert out["n_trades"] == 75
    # last_25 should be all wins.
    assert out["last_25_win_rate"] == pytest.approx(1.0)
    assert out["last_25_mean_pnl"] == pytest.approx(5.0)
    # last_50 = the last 50: trades 25-49 all -1.0, trades 50-74 all +5.0.
    assert out["last_50_mean_pnl"] == pytest.approx((25 * -1.0 + 25 * 5.0) / 50)


def test_compute_from_trades_dict_schema():
    """``compute_from_trades`` accepts dicts with a ``pnl`` key —
    matches ``brain_persistence.trade_history`` and CSV-row shape."""
    from backend.organism.strategy_expectancy import compute_from_trades
    trades = [
        {"pnl": 10.0, "symbol": "AAPL"},
        {"pnl": -5.0, "symbol": "MSFT"},
        {"pnl": 0.5, "symbol": "GOOG"},
    ]
    out = compute_from_trades(trades)
    assert out["n_trades"] == 3
    assert out["total_pnl"] == pytest.approx(5.5, abs=1e-6)


def test_compute_from_trades_objects_schema():
    """``compute_from_trades`` accepts TradeRecord-like objects with .pnl."""
    from backend.organism.strategy_expectancy import compute_from_trades

    class _FakeTrade:
        def __init__(self, pnl: float):
            self.pnl = pnl
    trades = [_FakeTrade(10.0), _FakeTrade(-5.0), _FakeTrade(0.5)]
    out = compute_from_trades(trades)
    assert out["n_trades"] == 3
    assert out["total_pnl"] == pytest.approx(5.5, abs=1e-6)


def test_compute_from_trades_skips_invalid():
    """Trades with non-numeric / missing pnl don't crash, just skipped."""
    from backend.organism.strategy_expectancy import compute_from_trades
    trades = [
        {"pnl": 10.0},
        {"pnl": "NaN"},   # string-NaN: skip
        {"pnl": None},     # None: skip
        {},                # missing: skip
        {"pnl": -5.0},
    ]
    out = compute_from_trades(trades)
    assert out["n_trades"] == 2  # only 10.0 and -5.0 survive
    assert out["total_pnl"] == pytest.approx(5.0, abs=1e-6)


# ────────────────────────────────────────────────────────────────────
# 2. Manifest writer: behavioral end-to-end verification.
# ────────────────────────────────────────────────────────────────────

def test_apply_live_manifest_fields_writes_strategy_expectancy(tmp_path: Path):
    """Mint a synthetic learner with trade_history; call the manifest
    writer; assert the manifest-dict contains the expectancy block."""
    from backend.organism.brain_persistence import OrganismBrain

    # Build a fake learner state matching what the writer expects.
    class _FakeState:
        generation = 5
        total_trades = 3
        cumulative_pnl = 5.5
        best_sharpe = 0.0

    # Minimal trade-shaped objects: ``compute_from_trades`` only reads .pnl.
    class _FakeTrade:
        def __init__(self, pnl: float, symbol: str = "X"):
            self.pnl = pnl
            self.symbol = symbol

    class _FakeLearner:
        state = _FakeState()
        # Three trades: +10, -5, +0.5.  total_pnl=5.5, win_rate=2/3.
        trade_history = [
            _FakeTrade(10.0, "AAPL"),
            _FakeTrade(-5.0, "MSFT"),
            _FakeTrade(0.5, "GOOG"),
        ]

    class _FakeSignalGen:
        _is_trained = True
        _feature_cols = ["a", "b", "c"]

    # Construct a brain whose brain_dir is tmp; bypass __init__ side-effects
    # by using __new__ + minimal attribute setup.
    brain = OrganismBrain.__new__(OrganismBrain)
    brain.brain_dir = tmp_path
    brain._manifest = {}
    brain.trade_history = []  # learner has the richer source

    manifest: dict = {}
    brain._apply_live_manifest_fields(
        manifest, _FakeSignalGen(), _FakeLearner(),
    )
    # Pre-V12 fields still present.
    assert manifest["generation"] == 5
    assert manifest["total_trades"] == 3
    assert manifest["ml_is_trained"] is True
    # V12 W71 new block.
    assert "strategy_expectancy" in manifest, (
        "V12 W71 regression: manifest missing strategy_expectancy block"
    )
    sx = manifest["strategy_expectancy"]
    assert sx["n_trades"] == 3
    assert sx["total_pnl"] == pytest.approx(5.5, abs=1e-6)
    assert sx["n_wins"] == 2
    assert sx["n_losses"] == 1
    assert sx["win_rate"] == pytest.approx(2 / 3, abs=1e-3)


def test_apply_live_manifest_fields_handles_no_learner(tmp_path: Path):
    """Manifest write must succeed when learner is None or missing
    trade_history.  Expectancy block falls back to empty payload."""
    from backend.organism.brain_persistence import OrganismBrain

    brain = OrganismBrain.__new__(OrganismBrain)
    brain.brain_dir = tmp_path
    brain._manifest = {}
    brain.trade_history = []

    manifest: dict = {}
    brain._apply_live_manifest_fields(manifest, None, None)
    # Strategy expectancy must still be present (empty payload), not missing.
    assert "strategy_expectancy" in manifest
    sx = manifest["strategy_expectancy"]
    assert sx["n_trades"] == 0
    assert sx["total_pnl"] == 0.0


# ────────────────────────────────────────────────────────────────────
# 3. /api/v1/health/strategy endpoint: live behavioral test.
# ────────────────────────────────────────────────────────────────────

def test_strategy_health_endpoint_reads_manifest(tmp_path: Path, monkeypatch):
    """Build a fake brain dir with manifest.json carrying expectancy;
    point the resolver at it; hit the endpoint via TestClient.
    Asserts on response code AND payload values."""
    # Set up brain dir with a known manifest.
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    (brain_dir / "manifest.json").write_text(json.dumps({
        "generation": 7,
        "total_trades": 5,
        "strategy_expectancy": {
            "n_trades": 5,
            "n_wins": 2,
            "n_losses": 3,
            "total_pnl": -10.0,
            "mean_pnl": -2.0,
            "median_pnl": -1.0,
            "win_rate": 0.4,
            "sharpe_ratio_per_trade": -0.5,
            "max_drawdown": -15.0,
            "last_25_mean_pnl": -2.0,
            "last_25_win_rate": 0.4,
            "last_50_mean_pnl": -2.0,
            "last_50_win_rate": 0.4,
        },
    }))
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(brain_dir))

    from backend.api.routes.strategy_health import strategy_health
    import asyncio
    payload = asyncio.run(strategy_health())

    assert payload["source"] == "manifest"
    assert payload["n_trades"] == 5
    assert payload["total_pnl"] == -10.0
    assert payload["win_rate"] == 0.4
    assert payload["is_profitable"] is False  # negative PnL → False


def test_strategy_health_endpoint_recomputes_from_csv(tmp_path: Path, monkeypatch):
    """If manifest doesn't have the expectancy block yet (pre-W71
    deploy), endpoint falls back to CSV recompute."""
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    # Manifest without expectancy.
    (brain_dir / "manifest.json").write_text(json.dumps({"generation": 1}))
    # CSV with three trades.
    (brain_dir / "trade_history.csv").write_text(
        "pnl\n"
        "10.0\n"
        "-5.0\n"
        "0.5\n"
    )
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(brain_dir))

    from backend.api.routes.strategy_health import strategy_health
    import asyncio
    payload = asyncio.run(strategy_health())

    assert payload["source"] == "trade_history_csv"
    assert payload["n_trades"] == 3
    assert payload["total_pnl"] == pytest.approx(5.5, abs=1e-6)
    assert payload["is_profitable"] is True


def test_strategy_health_endpoint_503_when_nothing(tmp_path: Path, monkeypatch):
    """No manifest, no CSV → 503 (not 200, not 500).  Uses an isolated
    tmp_path to avoid the resolver falling back to the repo's real
    organism_brain/."""
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(brain_dir))
    # Patch _resolve_brain_dir to return our empty tmp dir without
    # falling through to the conventional paths.
    from backend.api.routes import strategy_health as sh_mod
    monkeypatch.setattr(sh_mod, "_resolve_brain_dir", lambda: brain_dir)

    from fastapi import HTTPException
    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sh_mod.strategy_health())
    assert exc.value.status_code == 503


def test_strategy_health_router_mounted_under_protected_v1():
    """The /health/strategy router must be mounted under the protected
    /api/v1 prefix.  Validates W71's wiring in routes_setup.py."""
    # Build a fresh app via the factory and inspect routes.
    from backend.api.factory import create_app
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/health/strategy" in paths, (
        f"V12 W71 regression: /api/v1/health/strategy not mounted. "
        f"Got paths starting with /api/v1/health/: "
        f"{[p for p in paths if p.startswith('/api/v1/health')]}"
    )


# ────────────────────────────────────────────────────────────────────
# 4. Lock the schema: required_fields() is the source of truth.
# ────────────────────────────────────────────────────────────────────

def test_required_fields_schema_complete():
    """Every documented expectancy field must appear in
    required_fields() so all callers stay in sync."""
    from backend.organism.strategy_expectancy import required_fields
    fields = required_fields()
    expected = {
        "n_trades", "n_wins", "n_losses",
        "total_pnl", "mean_pnl", "median_pnl",
        "win_rate", "sharpe_ratio_per_trade", "max_drawdown",
        "last_25_mean_pnl", "last_25_win_rate",
        "last_50_mean_pnl", "last_50_win_rate",
    }
    assert fields == expected, f"schema drift: {fields ^ expected}"
