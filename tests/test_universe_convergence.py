"""Tests for universe convergence fix — protected symbols survive brain restore."""

from types import SimpleNamespace

from backend.organism.universe_selector import DynamicUniverseSelector


def _make_trade(symbol, pnl):
    return SimpleNamespace(symbol=symbol, pnl=pnl, confidence=0.5)


class TestProtectedMergeOnRestore:
    """Protected symbols must be merged into active universe on from_dict restore."""

    def test_missing_protected_merged_on_restore(self):
        """30-symbol universe missing SH/PSQ -> after restore both are present."""
        old_active = [
            "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN", "GOOGL",
            "SPY", "QQQ", "IWM", "XLK", "XLE", "AVGO", "CRM", "COST",
            "WMT", "LLY", "XOM", "CAT", "NFLX", "ADBE", "INTC", "MU",
            "COIN", "SNOW", "PLTR", "UBER", "ABNB", "SQ",
        ]
        assert "SH" not in old_active
        assert "PSQ" not in old_active

        saved = {"active": old_active, "rotation_count": 5, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH", "PSQ"},
        )
        active = selector.active_universe
        assert "SH" in active, f"SH missing after restore. Active: {active}"
        assert "PSQ" in active, f"PSQ missing after restore. Active: {active}"

    def test_existing_symbols_preserved(self):
        """All 30 original symbols remain after merge."""
        old_active = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]
        saved = {"active": old_active, "rotation_count": 1, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH", "PSQ"},
        )
        active = selector.active_universe
        for sym in old_active:
            assert sym in active, f"{sym} lost during merge"
        assert len(active) == 7  # 5 original + SH + PSQ

    def test_no_duplicates_when_already_present(self):
        """If SH/PSQ already in active, no duplicates after merge."""
        old_active = ["AAPL", "SH", "PSQ", "MSFT"]
        saved = {"active": old_active, "rotation_count": 1, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH", "PSQ"},
        )
        active = selector.active_universe
        assert active.count("SH") == 1
        assert active.count("PSQ") == 1
        assert len(active) == 4  # No growth

    def test_fitness_entry_created_for_merged_symbols(self):
        """Merged protected symbols get a default fitness entry."""
        saved = {"active": ["AAPL"], "rotation_count": 1, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH"},
        )
        assert "SH" in selector.fitness_table
        assert selector.fitness_table["SH"].fitness == 0.50  # DEFAULT_FITNESS

    def test_merge_survives_save_load_roundtrip(self):
        """After merge -> save -> load, protected symbols still present."""
        saved = {"active": ["AAPL", "MSFT"], "rotation_count": 1, "fitness": {}}

        sel1 = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH", "PSQ"},
        )
        assert "SH" in sel1.active_universe

        # Save and restore
        d = sel1.to_dict()
        sel2 = DynamicUniverseSelector.from_dict(
            d, protected_symbols={"SH", "PSQ"},
        )
        assert "SH" in sel2.active_universe
        assert "PSQ" in sel2.active_universe

    def test_merge_with_no_protected_symbols(self):
        """When protected_symbols is empty, no merge happens."""
        saved = {"active": ["AAPL"], "rotation_count": 0, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(saved, protected_symbols=set())
        assert selector.active_universe == ["AAPL"]

    def test_protected_not_dropped_after_rotation(self):
        """After merge + rotation with bad trades, protected symbols stay."""
        saved = {"active": ["AAPL", "MSFT", "GOOGL"], "rotation_count": 0, "fitness": {}}

        selector = DynamicUniverseSelector.from_dict(
            saved, protected_symbols={"SH", "PSQ"}, seed_symbols=["AAPL", "MSFT", "GOOGL"],
        )
        assert "SH" in selector.active_universe

        # Give SH terrible trades and rotate multiple times
        bad_trades = [_make_trade("SH", -100.0) for _ in range(10)]
        for _ in range(5):
            selector.rotate(trades=bad_trades, generation=1)

        assert "SH" in selector.active_universe, "SH should be protected from rotation"
        assert "PSQ" in selector.active_universe, "PSQ should be protected from rotation"
