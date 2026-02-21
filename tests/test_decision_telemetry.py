"""Tests for decision telemetry — ring buffer, serialization, snapshot building, API."""

import pytest

from backend.organism.decision_telemetry import (
    DecisionSnapshot,
    DecisionTelemetryStore,
    FilteringSummary,
    KellySizingDetail,
    PositionExitDetail,
    SymbolAlphaDetail,
    SymbolBreakoutDetail,
)


# ── DecisionTelemetryStore ring buffer ─────────────────────────────

class TestDecisionTelemetryStore:
    def test_empty_store_latest_returns_none(self):
        store = DecisionTelemetryStore()
        assert store.latest is None

    def test_empty_store_history_returns_empty(self):
        store = DecisionTelemetryStore()
        assert store.history() == []

    def test_append_and_latest(self):
        store = DecisionTelemetryStore()
        snap = DecisionSnapshot(tick_number=1, timestamp="2026-02-21T10:00:00Z")
        store.append(snap)
        assert store.latest is snap
        assert len(store) == 1

    def test_maxlen_eviction(self):
        store = DecisionTelemetryStore(maxlen=5)
        for i in range(10):
            store.append(DecisionSnapshot(tick_number=i))
        assert len(store) == 5
        assert store.latest.tick_number == 9
        # Oldest should be tick 5
        history = store.history(limit=10)
        assert history[-1].tick_number == 5

    def test_history_returns_newest_first(self):
        store = DecisionTelemetryStore()
        for i in range(5):
            store.append(DecisionSnapshot(tick_number=i))
        history = store.history(limit=5)
        assert [h.tick_number for h in history] == [4, 3, 2, 1, 0]

    def test_history_limit(self):
        store = DecisionTelemetryStore()
        for i in range(20):
            store.append(DecisionSnapshot(tick_number=i))
        history = store.history(limit=3)
        assert len(history) == 3
        assert history[0].tick_number == 19

    def test_clear(self):
        store = DecisionTelemetryStore()
        store.append(DecisionSnapshot(tick_number=1))
        assert len(store) == 1
        store.clear()
        assert len(store) == 0
        assert store.latest is None


# ── Symbol history ─────────────────────────────────────────────────

class TestSymbolHistory:
    def test_symbol_history_returns_matching_entries(self):
        store = DecisionTelemetryStore()
        snap1 = DecisionSnapshot(tick_number=1, timestamp="t1")
        snap1.alpha_details.append(SymbolAlphaDetail(symbol="AAPL", composite_score=0.5))
        snap1.alpha_details.append(SymbolAlphaDetail(symbol="MSFT", composite_score=0.3))
        snap2 = DecisionSnapshot(tick_number=2, timestamp="t2")
        snap2.alpha_details.append(SymbolAlphaDetail(symbol="AAPL", composite_score=0.6))
        store.append(snap1)
        store.append(snap2)

        history = store.symbol_history("AAPL")
        assert len(history) == 2
        assert history[0]["tick_number"] == 2  # newest first
        assert history[0]["alpha"]["composite_score"] == 0.6

    def test_symbol_history_no_match(self):
        store = DecisionTelemetryStore()
        snap = DecisionSnapshot(tick_number=1)
        snap.alpha_details.append(SymbolAlphaDetail(symbol="AAPL"))
        store.append(snap)
        assert store.symbol_history("TSLA") == []

    def test_symbol_history_includes_exit_data(self):
        store = DecisionTelemetryStore()
        snap = DecisionSnapshot(tick_number=1)
        snap.exit_details.append(PositionExitDetail(symbol="AAPL", current_price=150.0))
        store.append(snap)
        history = store.symbol_history("AAPL")
        assert len(history) == 1
        assert "exit" in history[0]


# ── Exits snapshot ─────────────────────────────────────────────────

class TestExitsSnapshot:
    def test_exits_snapshot_empty(self):
        store = DecisionTelemetryStore()
        assert store.exits_snapshot() == []

    def test_exits_snapshot_returns_latest(self):
        store = DecisionTelemetryStore()
        snap = DecisionSnapshot(tick_number=1)
        snap.exit_details.append(PositionExitDetail(symbol="AAPL", current_price=150.0))
        snap.exit_details.append(PositionExitDetail(symbol="MSFT", current_price=350.0))
        store.append(snap)
        exits = store.exits_snapshot()
        assert len(exits) == 2
        assert exits[0]["symbol"] == "AAPL"


# ── DecisionSnapshot serialization ────────────────────────────────

class TestDecisionSnapshotSerialization:
    def test_empty_snapshot_to_dict(self):
        snap = DecisionSnapshot()
        d = snap.to_dict()
        assert d["tick_number"] == 0
        assert d["regime"]["primary"] == "unknown"
        assert d["alpha_scores"] == []
        assert d["exit_proximity"] == []
        assert d["kelly_sizing"] == []
        assert d["filtering"]["total_universe"] == 0

    def test_full_snapshot_to_dict(self):
        snap = DecisionSnapshot(
            tick_number=42,
            timestamp="2026-02-21T10:00:00Z",
            regime="trending_up",
            regime_probabilities={"trending_up": 0.7, "normal": 0.2},
            equity=106000.0,
            peak_equity=107000.0,
            drawdown_pct=0.0093,
            evolution_generation=5,
        )
        snap.alpha_details.append(SymbolAlphaDetail(symbol="AAPL", composite_score=0.55))
        snap.breakout_details.append(SymbolBreakoutDetail(symbol="NVDA", composite_score=0.4))
        snap.exit_details.append(PositionExitDetail(symbol="MSFT", current_price=350.0, stop_loss=340.0))
        snap.kelly_details.append(KellySizingDetail(symbol="AAPL", kelly_raw=0.08))

        d = snap.to_dict()
        assert d["tick_number"] == 42
        assert d["regime"]["primary"] == "trending_up"
        assert d["regime"]["probabilities"]["trending_up"] == 0.7
        assert d["governance"]["equity"] == 106000.0
        assert d["governance"]["drawdown_pct"] == 0.0093
        assert d["evolution"]["generation"] == 5
        assert len(d["alpha_scores"]) == 1
        assert d["alpha_scores"][0]["symbol"] == "AAPL"
        assert len(d["breakout_scores"]) == 1
        assert len(d["exit_proximity"]) == 1
        assert len(d["kelly_sizing"]) == 1


# ── Individual detail serialization ───────────────────────────────

class TestAlphaDetailSerialization:
    def test_to_dict_structure(self):
        ad = SymbolAlphaDetail(
            symbol="AAPL",
            composite_score=0.42,
            ml_score=0.6,
            breakout_score=0.3,
            momentum_score=0.5,
            regime_score=0.7,
            direction=1.0,
            min_composite_threshold=0.15,
            distance_to_threshold=0.27,
            passed_threshold=True,
            symbol_fitness=0.65,
        )
        d = ad.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["composite_score"] == 0.42
        assert d["factors"]["ml"] == 0.6
        assert d["passed_threshold"] is True
        assert d["distance_to_threshold"] == 0.27


class TestBreakoutDetailSerialization:
    def test_to_dict_structure(self):
        bd = SymbolBreakoutDetail(
            symbol="NVDA",
            composite_score=0.55,
            squeeze_score=0.8,
            volume_score=0.6,
            squeeze_fired=True,
            volume_ratio=2.5,
        )
        d = bd.to_dict()
        assert d["symbol"] == "NVDA"
        assert d["factors"]["squeeze"] == 0.8
        assert d["squeeze_fired"] is True
        assert d["volume_ratio"] == 2.5


class TestExitDetailSerialization:
    def test_to_dict_structure(self):
        ed = PositionExitDetail(
            symbol="MSFT",
            current_price=350.0,
            entry_price=340.0,
            direction=1.0,
            pnl_pct=0.0294,
            stop_loss=330.0,
            take_profit=380.0,
            trailing_stop=345.0,
            stop_loss_distance_pct=5.71,
            take_profit_distance_pct=8.57,
            trailing_active=True,
            bars_held=25,
            max_bars=40,
            nearest_exit="trailing_stop",
            nearest_exit_distance_pct=1.43,
        )
        d = ed.to_dict()
        assert d["symbol"] == "MSFT"
        assert d["exits"]["stop_loss"]["distance_pct"] == 5.71
        assert d["exits"]["trailing_stop"]["active"] is True
        assert d["nearest_exit"] == "trailing_stop"


class TestKellyDetailSerialization:
    def test_to_dict_structure(self):
        kd = KellySizingDetail(
            symbol="AAPL",
            kelly_raw=0.08,
            kelly_half=0.04,
            drawdown_scale=0.95,
            vol_scale=1.2,
            regime_scale=1.0,
            confidence_scale=0.9,
            breakout_bonus=1.5,
            final_weight=0.06,
            shares=15,
            notional=2500.0,
        )
        d = kd.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["pipeline"]["kelly_raw"] == 0.08
        assert d["pipeline"]["breakout_bonus"] == 1.5
        assert d["shares"] == 15


class TestFilteringSummarySerialization:
    def test_to_dict(self):
        f = FilteringSummary(
            total_universe=30,
            alpha_scored=25,
            above_alpha_threshold=8,
            orders_submitted=3,
        )
        d = f.to_dict()
        assert d["total_universe"] == 30
        assert d["orders_submitted"] == 3


# ── Scanner _last_full_scan capture ───────────────────────────────

class TestScannerInstrumentation:
    def test_alpha_scanner_captures_full_scan(self):
        from backend.organism.alpha_scanner import AlphaScanner
        import pandas as pd
        import numpy as np

        scanner = AlphaScanner(top_n=2)
        # Create minimal features
        n = 60
        features = {
            "AAPL": pd.DataFrame({
                "close": np.random.uniform(140, 160, n),
                "ret_20d": [0.05] * n,
                "comp_breakout_readiness": [0.3] * n,
                "comp_squeeze_momentum": [0.2] * n,
                "comp_institutional_acc": [0.5] * n,
                "comp_momentum_quality": [0.5] * n,
                "comp_vol_price_div": [0.5] * n,
                "vol_sma_ratio": [1.5] * n,
                "adx_14": [25.0] * n,
                "trend_strength": [0.5] * n,
                "vol_regime": [1] * n,
            }),
            "MSFT": pd.DataFrame({
                "close": np.random.uniform(340, 360, n),
                "ret_20d": [0.03] * n,
                "comp_breakout_readiness": [0.2] * n,
                "comp_squeeze_momentum": [0.1] * n,
                "comp_institutional_acc": [0.4] * n,
                "comp_momentum_quality": [0.4] * n,
                "comp_vol_price_div": [0.4] * n,
                "vol_sma_ratio": [1.0] * n,
                "adx_14": [20.0] * n,
                "trend_strength": [0.3] * n,
                "vol_regime": [1] * n,
            }),
        }
        from backend.organism.ml_signal import MLSignal
        ml_signals = {
            "AAPL": MLSignal(symbol="AAPL", direction=1.0, confidence=0.6, predicted_return=0.02),
            "MSFT": MLSignal(symbol="MSFT", direction=1.0, confidence=0.4, predicted_return=0.01),
        }
        result = scanner.scan(features, ml_signals)
        assert hasattr(scanner, "_last_full_scan")
        assert len(scanner._last_full_scan) >= len(result)

    def test_breakout_scanner_captures_full_scan(self):
        from backend.organism.breakout_scanner import BreakoutScanner
        import pandas as pd
        import numpy as np

        scanner = BreakoutScanner(top_n=2)
        n = 80
        data = {}
        for sym in ["AAPL", "MSFT", "NVDA"]:
            data[sym] = pd.DataFrame({
                "open": np.random.uniform(100, 110, n),
                "high": np.random.uniform(110, 120, n),
                "low": np.random.uniform(90, 100, n),
                "close": np.random.uniform(100, 110, n),
                "volume": np.random.uniform(1e6, 5e6, n),
            })
        result = scanner.scan(data)
        assert hasattr(scanner, "_last_full_scan")
        assert len(scanner._last_full_scan) >= len(result)


# ── API endpoint response structure tests ─────────────────────────

class TestAPIResponseStructure:
    """Test that to_dict() output matches what the API endpoints would return."""

    def test_decisions_response_structure(self):
        snap = DecisionSnapshot(
            tick_number=10,
            timestamp="2026-02-21T10:00:00Z",
            regime="normal",
            equity=100000.0,
        )
        d = snap.to_dict()
        # Verify nested structure
        assert "regime" in d
        assert "governance" in d
        assert "evolution" in d
        assert "alpha_scores" in d
        assert "breakout_scores" in d
        assert "exit_proximity" in d
        assert "kelly_sizing" in d
        assert "filtering" in d

    def test_symbol_history_structure(self):
        store = DecisionTelemetryStore()
        snap = DecisionSnapshot(tick_number=1, timestamp="t1", regime="normal")
        snap.alpha_details.append(SymbolAlphaDetail(symbol="AAPL", composite_score=0.5))
        snap.breakout_details.append(SymbolBreakoutDetail(symbol="AAPL", composite_score=0.3))
        snap.exit_details.append(PositionExitDetail(symbol="AAPL", current_price=150.0))
        snap.kelly_details.append(KellySizingDetail(symbol="AAPL", kelly_raw=0.05))
        store.append(snap)

        history = store.symbol_history("AAPL")
        assert len(history) == 1
        entry = history[0]
        assert "alpha" in entry
        assert "breakout" in entry
        assert "exit" in entry
        assert "kelly" in entry
        assert entry["tick_number"] == 1
        assert entry["regime"] == "normal"
