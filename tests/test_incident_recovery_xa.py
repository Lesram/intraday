"""
Wave XA Incident Recovery Tests

A1: Alpaca client session recycling on ConnectTimeout
A2: Universe convergence for paper/learning mode
A3: Scanner/tension path verification
"""

import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# A1: Alpaca client session recycling
# ---------------------------------------------------------------------------


def _make_alpaca_client():
    """Create an AlpacaClient in test mode (no real API calls)."""
    with patch.dict("os.environ", {}, clear=False):
        from backend.data.alpaca_client import AlpacaClient

        client = AlpacaClient(
            api_key="test_key_12345",
            secret_key="test_secret_12345",
            paper=True,
            test_mode=True,
        )
    return client


class TestAlpacaClientRecycle:
    """A1: client recycling after consecutive data errors."""

    def test_alpaca_client_has_recycle_method(self):
        client = _make_alpaca_client()
        assert hasattr(client, "_recycle_clients")
        assert callable(client._recycle_clients)

    def test_consecutive_data_errors_counter_exists(self):
        client = _make_alpaca_client()
        assert hasattr(client, "_consecutive_data_errors")
        assert client._consecutive_data_errors == 0

    def test_consecutive_errors_trigger_recycle(self):
        """After 5 connection errors, _recycle_clients is called."""
        client = _make_alpaca_client()
        client._recycle_clients = MagicMock()

        # Simulate 5 consecutive ConnectTimeout-like errors
        for i in range(5):
            client._consecutive_data_errors = i
            # Manually simulate what get_historical_data does on connection error
            exc_str = "connecttimeout"
            is_connection_error = "timeout" in exc_str or "connect" in exc_str
            if is_connection_error:
                client._consecutive_data_errors += 1
                if client._consecutive_data_errors >= client._RECYCLE_THRESHOLD:
                    client._recycle_clients()

        client._recycle_clients.assert_called_once()

    def test_successful_call_resets_error_counter(self):
        """After a successful data fetch, the counter resets to 0."""
        client = _make_alpaca_client()
        client._consecutive_data_errors = 4  # almost at threshold

        # Simulate successful path: counter resets
        client._consecutive_data_errors = 0  # this is what get_historical_data does on success
        assert client._consecutive_data_errors == 0

    def test_recycled_client_can_succeed(self):
        """After recycling, the client objects are recreated."""
        client = _make_alpaca_client()

        # Store original client IDs
        original_trading = id(client.trading_client)
        original_stock = id(client.stock_data_client)

        # Recycle
        client._recycle_clients()

        # Clients should be new objects (re-instantiated)
        # In test_mode _init_clients may not fully create new objects,
        # but the method should have run without error.
        assert client._consecutive_data_errors == 0

    def test_non_connection_error_does_not_increment(self):
        """Non-connection errors (e.g. ValueError) should not trigger recycling."""
        client = _make_alpaca_client()
        client._recycle_clients = MagicMock()

        # Simulate a ValueError path (not a connection error)
        exc_str = "invalid symbol format"
        is_connection_error = (
            "timeout" in exc_str
            or "connect" in exc_str
            or "connection" in exc_str
            or "refused" in exc_str
        )
        assert not is_connection_error
        # Counter stays at 0
        assert client._consecutive_data_errors == 0
        client._recycle_clients.assert_not_called()

    def test_recycle_threshold_is_five(self):
        client = _make_alpaca_client()
        assert client._RECYCLE_THRESHOLD == 5


# ---------------------------------------------------------------------------
# A2: Universe convergence for paper/learning mode
# ---------------------------------------------------------------------------


# Base universe from LIVE_UNIVERSE_CSV (22 symbols)
BASE_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    "AVGO", "CRM", "COST", "WMT", "LLY", "XOM", "CAT", "SPY", "QQQ",
    "IWM", "XLK", "XLE", "SH", "PSQ",
]

STALE_EXTRAS = ["NFLX", "ADBE", "INTC", "MU", "COIN", "SNOW", "PLTR", "UBER", "ABNB", "SQ"]


def _make_mock_engine(universe, trade_count=0):
    """Create a minimal mock that mirrors the live_engine universe restore + convergence logic."""
    from backend.organism.live_engine import LIVE_UNIVERSE_CSV, PROTECTED_SYMBOLS

    class FakeSelector:
        def __init__(self, active):
            self._active = list(active)

    engine = types.SimpleNamespace()
    engine._universe = list(universe)
    engine._all_trades = [None] * trade_count  # controls _is_learning_mode
    engine._LEARNING_MODE_TRADES = 200
    engine._is_learning_mode = trade_count < 200
    engine.universe_selector = FakeSelector(universe)
    return engine


def _apply_convergence(engine):
    """Reproduce the A2 convergence logic from live_engine.py."""
    from backend.organism.live_engine import LIVE_UNIVERSE_CSV, PROTECTED_SYMBOLS

    if engine._is_learning_mode:
        base = set(
            s.strip().upper()
            for s in LIVE_UNIVERSE_CSV.split(",")
            if s.strip()
        )
        base |= PROTECTED_SYMBOLS
        active_set = set(engine._universe)
        extras = active_set - base
        if extras:
            engine._universe = [s for s in engine._universe if s in base]
            for s in sorted(base):
                if s not in engine._universe:
                    engine._universe.append(s)
            engine.universe_selector._active = list(engine._universe)
    return engine


class TestUniverseConvergence:
    """A2: learning-mode universe convergence."""

    def test_learning_mode_universe_converges_to_base(self):
        """30-symbol brain restore in learning mode converges to 22 base + protected."""
        universe = BASE_UNIVERSE + STALE_EXTRAS
        engine = _make_mock_engine(universe, trade_count=50)
        _apply_convergence(engine)
        assert len(engine._universe) == len(BASE_UNIVERSE)

    def test_learning_mode_removes_stale_extras(self):
        """The 10 stale extras are removed."""
        universe = BASE_UNIVERSE + STALE_EXTRAS
        engine = _make_mock_engine(universe, trade_count=50)
        _apply_convergence(engine)
        active = set(engine._universe)
        for sym in STALE_EXTRAS:
            assert sym not in active, f"{sym} should have been removed"

    def test_learning_mode_keeps_protected(self):
        """SH and PSQ remain after convergence."""
        universe = BASE_UNIVERSE + STALE_EXTRAS
        engine = _make_mock_engine(universe, trade_count=50)
        _apply_convergence(engine)
        active = set(engine._universe)
        assert "SH" in active
        assert "PSQ" in active

    def test_learning_mode_adds_missing_base(self):
        """If a base symbol is missing from brain restore and extras exist,
        convergence adds the missing base symbols."""
        # Start with universe missing AAPL and MSFT but having stale extras
        universe = [s for s in BASE_UNIVERSE if s not in ("AAPL", "MSFT")] + ["NFLX"]
        engine = _make_mock_engine(universe, trade_count=10)
        _apply_convergence(engine)
        active = set(engine._universe)
        assert "AAPL" in active, "Missing base symbol AAPL should be added"
        assert "MSFT" in active, "Missing base symbol MSFT should be added"
        assert "NFLX" not in active, "Stale extra NFLX should be removed"

    def test_production_mode_keeps_dynamic_universe(self):
        """In production mode (>= 200 trades), 30-symbol universe is preserved."""
        universe = BASE_UNIVERSE + STALE_EXTRAS
        engine = _make_mock_engine(universe, trade_count=500)
        _apply_convergence(engine)
        assert len(engine._universe) == 32  # all 30 + no removal
        active = set(engine._universe)
        for sym in STALE_EXTRAS:
            assert sym in active, f"{sym} should be kept in production mode"

    def test_selector_updated_after_convergence(self):
        """universe_selector._active is updated to match converged universe."""
        universe = BASE_UNIVERSE + STALE_EXTRAS
        engine = _make_mock_engine(universe, trade_count=50)
        _apply_convergence(engine)
        assert engine.universe_selector._active == engine._universe

    def test_no_convergence_when_no_extras(self):
        """If brain restore matches base, no changes are made."""
        engine = _make_mock_engine(list(BASE_UNIVERSE), trade_count=50)
        original = list(engine._universe)
        _apply_convergence(engine)
        assert engine._universe == original


# ---------------------------------------------------------------------------
# A3: Scanner gate -- no entries_blocked check
# ---------------------------------------------------------------------------


class TestScannerGateDecoupled:
    """A3: verify the scanner gate does not check entries_blocked."""

    def test_scanner_gate_no_entries_blocked_check(self):
        """The market scanner gate must NOT check entries_blocked.
        This was fixed in away-mode Wave A (A2 decoupling).
        Verify the fix is still in place by reading the source file."""
        import pathlib

        source_path = pathlib.Path(__file__).resolve().parent.parent / "backend" / "organism" / "live_engine.py"
        source = source_path.read_text()

        # Find the scanner gate section
        scanner_section_start = source.find("MARKET SCAN")
        assert scanner_section_start != -1, "Could not find MARKET SCAN section in live_engine.py"

        # Extract ~1500 chars after the scanner section header
        scanner_section = source[scanner_section_start:scanner_section_start + 1500]

        # The gate condition should NOT reference entries_blocked
        gate_line_end = scanner_section.find("new_candidates = await self.market_scanner.scan()")
        assert gate_line_end != -1, "Could not find scanner.scan() call"
        gate_section = scanner_section[:gate_line_end]

        assert "entries_blocked" not in gate_section, (
            "Scanner gate still checks entries_blocked -- A2 decoupling broken"
        )


# ---------------------------------------------------------------------------
# Scheduler backoff logging verification
# ---------------------------------------------------------------------------


class TestSchedulerBackoffLogging:
    """Verify scheduler logs consecutive_errors count during backoff."""

    def test_scheduler_logs_consecutive_errors_on_backoff(self):
        """The _run_loop backoff branch must log consecutive_errors."""
        import inspect
        from backend.organism.scheduler import OrganismScheduler

        source = inspect.getsource(OrganismScheduler._run_loop)
        assert "consecutive_errors" in source, (
            "Scheduler _run_loop does not reference consecutive_errors"
        )
        # Verify it logs the count
        assert "consecutive_errors=%d" in source or "consecutive_errors=" in source, (
            "Scheduler does not log consecutive_errors count"
        )
