from __future__ import annotations

import pytest
import pandas as pd


def _session_bars(
    *,
    symbol_move: float = 0.05,
    base: float = 100.0,
    volume: int = 100_000,
    periods: int = 360,
) -> pd.DataFrame:
    previous_ts = pd.date_range("2026-05-07 13:30:00+00:00", periods=390, freq="min")
    current_ts = pd.date_range("2026-05-08 13:30:00+00:00", periods=periods, freq="min")
    previous_close = [base + i * 0.001 for i in range(len(previous_ts))]
    start = previous_close[-1]
    current_close = [start + symbol_move * i for i in range(len(current_ts))]
    ts = list(previous_ts) + list(current_ts)
    close = previous_close + current_close
    highs = [price + 0.04 for price in close]
    lows = [price - 0.04 for price in close]
    volumes = [10_000] * len(previous_ts) + [volume] * len(current_ts)
    return pd.DataFrame({
        "timestamp": [t.isoformat() for t in ts],
        "open": close,
        "high": highs,
        "low": lows,
        "close": close,
        "volume": volumes,
        "spread_bps": [5.0] * len(ts),
    })


def test_stocks_in_play_ranks_liquid_catalyst_symbols() -> None:
    from backend.organism.universe.stocks_in_play import StocksInPlayScanner

    scanner = StocksInPlayScanner()
    ranked = scanner.rank(
        {
            "AMD": _session_bars(symbol_move=0.10, volume=250_000),
            "TSLA": _session_bars(symbol_move=0.01, volume=5_000),
        },
        now="2026-05-08T14:00:00+00:00",
        metadata_by_symbol={
            "AMD": {
                "avg_volume_14d": 8_000_000,
                "avg_first_window_volume": 100_000,
                "earnings_or_news_score": 1.0,
                "spread_bps": 4.0,
            },
            "TSLA": {
                "avg_volume_14d": 8_000_000,
                "avg_first_window_volume": 100_000,
                "spread_bps": 4.0,
            },
        },
        sector_returns_bps={"Technology": 95.0},
    )

    assert ranked[0].symbol == "AMD"
    assert ranked[0].passed_liquidity is True
    assert ranked[0].first_window_rvol > 1.25


def test_orb_sip_v2_emits_long_shadow_signal_after_vwap_breakout() -> None:
    from backend.organism.engines.orb_sip_v2 import ORBSIPV2Engine

    bars = _session_bars(symbol_move=0.08, volume=200_000)
    now = "2026-05-08T14:05:00+00:00"
    now_ts = pd.Timestamp(now)
    ts = pd.to_datetime(bars["timestamp"], utc=True)
    known_idx = bars.index[ts <= now_ts]
    bars.loc[known_idx[-5:], "volume"] = 400_000
    engine = ORBSIPV2Engine()
    signals = engine.generate_signals({
        "features_by_symbol": {"AMD": bars},
        "metadata_by_symbol": {
            "AMD": {
                "avg_volume_14d": 10_000_000,
                "avg_first_window_volume": 60_000,
                "spread_bps": 3.0,
                "earnings_or_news_score": 0.8,
            },
        },
        "sector_returns_bps": {"Technology": 80.0},
        "market_return_bps": 15.0,
        "now": now,
        "regime": "event_vol",
    })

    assert len(signals) == 1
    assert signals[0].strategy_id == "orb_sip_v2"
    assert signals[0].shadow_only is True
    assert signals[0].risk_budget_bps == 0.0
    assert signals[0].features["live_enabled"] is False


def test_orb_sip_v2_ignores_future_breakout_bars_after_now() -> None:
    from backend.organism.engines.orb_sip_v2 import ORBSIPV2Engine

    now = "2026-05-08T14:05:00+00:00"
    now_ts = pd.Timestamp(now)
    bars = _session_bars(symbol_move=0.0, volume=200_000)
    ts = pd.to_datetime(bars["timestamp"], utc=True)
    future = ts > now_ts
    bars.loc[future, ["open", "high", "low", "close"]] = 130.0
    bars.loc[future, "volume"] = 600_000
    engine = ORBSIPV2Engine()

    signals = engine.generate_signals({
        "features_by_symbol": {"AMD": bars},
        "metadata_by_symbol": {
            "AMD": {
                "avg_volume_14d": 10_000_000,
                "avg_first_window_volume": 60_000,
                "spread_bps": 3.0,
                "earnings_or_news_score": 0.8,
            },
        },
        "sector_returns_bps": {"Technology": 80.0},
        "market_return_bps": 15.0,
        "now": now,
        "regime": "event_vol",
    })

    assert signals == []


def test_residual_mean_reversion_emits_only_in_chop_for_residual_laggard() -> None:
    from backend.organism.engines.residual_mean_reversion import ResidualMeanReversionEngine

    now = "2026-05-08T17:00:00+00:00"
    spy = _session_bars(symbol_move=0.01, base=500.0, volume=200_000)
    qqq = _session_bars(symbol_move=0.012, base=400.0, volume=200_000)
    xlk = _session_bars(symbol_move=0.011, base=250.0, volume=200_000)
    amd = _session_bars(symbol_move=0.011, base=120.0, volume=200_000)
    ts = pd.to_datetime(amd["timestamp"], utc=True)
    known_idx = amd.index[ts <= pd.Timestamp(now)]
    amd.loc[known_idx[-1], "close"] = float(amd.loc[known_idx[-1], "close"]) * 0.98
    engine = ResidualMeanReversionEngine(universe=("AMD",))

    assert engine.generate_signals({
        "features_by_symbol": {"AMD": amd, "SPY": spy, "QQQ": qqq, "XLK": xlk},
        "now": now,
        "regime": "trending_up",
    }) == []

    signals = engine.generate_signals({
        "features_by_symbol": {"AMD": amd, "SPY": spy, "QQQ": qqq, "XLK": xlk},
        "now": now,
        "regime": "chop",
    })

    assert len(signals) == 1
    assert signals[0].strategy_id == "residual_mean_reversion"
    assert signals[0].side == "long"
    assert signals[0].shadow_only is True
    assert signals[0].features["residual_z"] < 0


def test_residual_mean_reversion_ignores_future_residual_shock() -> None:
    from backend.organism.engines.residual_mean_reversion import ResidualMeanReversionEngine

    now = "2026-05-08T17:00:00+00:00"
    spy = _session_bars(symbol_move=0.01, base=500.0, volume=200_000)
    qqq = _session_bars(symbol_move=0.012, base=400.0, volume=200_000)
    xlk = _session_bars(symbol_move=0.011, base=250.0, volume=200_000)
    amd = _session_bars(symbol_move=0.011, base=120.0, volume=200_000)
    ts = pd.to_datetime(amd["timestamp"], utc=True)
    future = ts > pd.Timestamp(now)
    amd.loc[future, "close"] = amd.loc[future, "close"].astype(float) * 0.95
    engine = ResidualMeanReversionEngine(universe=("AMD",))

    signals = engine.generate_signals({
        "features_by_symbol": {"AMD": amd, "SPY": spy, "QQQ": qqq, "XLK": xlk},
        "now": now,
        "regime": "chop",
    })

    assert signals == []


def test_eod_reversal_emits_long_shadow_for_late_day_loser_reversal() -> None:
    from backend.organism.engines.eod_reversal_shadow import EODReversalShadowEngine

    bars = _session_bars(symbol_move=-0.04, base=100.0, volume=80_000)
    bars.loc[bars.index[-3]:, "volume"] = 200_000
    bars.loc[bars.index[-1], "close"] = float(bars["close"].iloc[-2]) + 0.25
    engine = EODReversalShadowEngine(universe=("AAPL",))

    signals = engine.generate_signals({
        "features_by_symbol": {"AAPL": bars},
        "now": "2026-05-08T19:35:00+00:00",
        "regime": "chop",
    })

    assert len(signals) == 1
    assert signals[0].strategy_id == "eod_reversal_shadow"
    assert signals[0].side == "long"
    assert signals[0].shadow_only is True
    assert signals[0].features["live_enabled"] is False


def test_eod_reversal_ignores_future_reversal_bars_after_now() -> None:
    from backend.organism.engines.eod_reversal_shadow import EODReversalShadowEngine

    now = "2026-05-08T19:35:00+00:00"
    bars = _session_bars(symbol_move=-0.04, base=100.0, volume=80_000, periods=420)
    ts = pd.to_datetime(bars["timestamp"], utc=True)
    future = ts > pd.Timestamp(now)
    bars.loc[future, "volume"] = 250_000
    future_idx = bars.index[future]
    bars.loc[future_idx[-1], "close"] = float(bars.loc[future_idx[-2], "close"]) + 0.35
    engine = EODReversalShadowEngine(universe=("AAPL",))

    signals = engine.generate_signals({
        "features_by_symbol": {"AAPL": bars},
        "now": now,
        "regime": "chop",
    })

    assert signals == []


def test_microstructure_schema_validates_top_of_book_contract() -> None:
    from backend.organism.features.microstructure_schema import MicrostructureSnapshot

    snapshot = MicrostructureSnapshot(
        symbol="spy",
        timestamp="2026-05-08T14:00:00Z",
        bid_price_1=500.00,
        ask_price_1=500.02,
        bid_size_1=1_000,
        ask_size_1=900,
        spread_bps=0.4,
        order_flow_imbalance=0.1,
        trade_imbalance=-0.1,
        aggressive_buy_ratio=0.2,
        aggressive_sell_ratio=-0.2,
        quote_update_rate=12.0,
        depth_imbalance=0.05,
    )

    assert snapshot.symbol == "SPY"
    assert snapshot.mid_price == 500.01
    assert snapshot.to_dict()["spread_bps"] == 0.4

    with pytest.raises(ValueError, match="below ask"):
        MicrostructureSnapshot(
            symbol="SPY",
            timestamp="2026-05-08T14:00:00Z",
            bid_price_1=500.02,
            ask_price_1=500.01,
            bid_size_1=1_000,
            ask_size_1=900,
            spread_bps=0.4,
            order_flow_imbalance=0.1,
            trade_imbalance=-0.1,
            aggressive_buy_ratio=0.2,
            aggressive_sell_ratio=-0.2,
            quote_update_rate=12.0,
            depth_imbalance=0.05,
        )
