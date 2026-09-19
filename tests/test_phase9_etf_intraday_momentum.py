from __future__ import annotations

import pandas as pd


def _bars(*, direction: int = 1, current_volume: int = 10_000) -> pd.DataFrame:
    previous_ts = pd.date_range(
        "2026-05-07 13:30:00+00:00",
        periods=390,
        freq="min",
    )
    current_ts = pd.date_range(
        "2026-05-08 13:30:00+00:00",
        periods=356,
        freq="min",
    )
    previous_close = [100.0 + i * 0.001 for i in range(len(previous_ts))]
    start = previous_close[-1]
    current_close = []
    for i in range(len(current_ts)):
        trend = direction * (0.015 * i)
        oscillation = direction * (0.08 if i % 2 == 0 else -0.04)
        current_close.append(start + trend + oscillation)
    ts = list(previous_ts) + list(current_ts)
    close = previous_close + current_close
    return pd.DataFrame({
        "timestamp": [t.isoformat() for t in ts],
        "open": close,
        "close": close,
        "volume": [1_000] * len(previous_ts) + [current_volume] * len(current_ts),
    })


def _lookahead_trap_bars() -> pd.DataFrame:
    previous_ts = pd.date_range(
        "2026-05-07 13:30:00+00:00",
        periods=390,
        freq="min",
    )
    current_ts = pd.date_range(
        "2026-05-08 13:30:00+00:00",
        periods=390,
        freq="min",
    )
    previous_close = [100.0 + i * 0.001 for i in range(len(previous_ts))]
    start = previous_close[-1]
    current_close = []
    for i in range(len(current_ts)):
        if i < 30:
            current_close.append(start + 0.01 * i)
        elif i <= 355:
            current_close.append(start - 0.10)
        else:
            current_close.append(start + 2.00)
    ts = list(previous_ts) + list(current_ts)
    close = previous_close + current_close
    return pd.DataFrame({
        "timestamp": [t.isoformat() for t in ts],
        "open": close,
        "close": close,
        "volume": [1_000] * len(previous_ts) + [20_000] * len(current_ts),
    })


def test_gamma_vol_proxy_flags_high_vol_trend_day() -> None:
    from backend.organism.engines.gamma_vol_proxy import GammaVolProxy

    state = GammaVolProxy(
        vol_z_threshold=-1.0,
        volume_z_threshold=-1.0,
        trend_bps_threshold=5.0,
    ).evaluate("QQQ", _bars(), "2026-05-08T19:25:00+00:00")

    assert state is not None
    assert state.symbol == "QQQ"
    assert state.direction == 1
    assert state.high_vol_trend_day is True
    assert state.rest_of_day_trend_bps > 0


def test_etf_intraday_momentum_generates_shadow_candidate_in_decision_window() -> None:
    from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine
    from backend.organism.engines.gamma_vol_proxy import GammaVolProxy

    engine = ETFIntradayMomentumEngine(
        universe=("QQQ",),
        gamma_proxy=GammaVolProxy(
            vol_z_threshold=-1.0,
            volume_z_threshold=-1.0,
            trend_bps_threshold=5.0,
        ),
    )

    signals = engine.generate_signals({
        "features_by_symbol": {"QQQ": _bars()},
        "now": "2026-05-08T19:25:00+00:00",
        "regime": "high_vol",
    })

    assert len(signals) == 1
    signal = signals[0]
    assert signal.strategy_id == "etf_intraday_momentum"
    assert signal.shadow_only is True
    assert signal.evidence_tier == 0
    assert signal.risk_budget_bps == 0.0
    assert signal.side == "long"
    assert signal.features["variant"] == "mim_a_first_30m_confirmed_rest_of_day"
    assert signal.features["live_enabled"] is False


def test_etf_intraday_momentum_short_signal_marks_inverse_route_but_stays_shadow() -> None:
    from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine
    from backend.organism.engines.gamma_vol_proxy import GammaVolProxy

    engine = ETFIntradayMomentumEngine(
        universe=("QQQ",),
        gamma_proxy=GammaVolProxy(
            vol_z_threshold=-1.0,
            volume_z_threshold=-1.0,
            trend_bps_threshold=5.0,
        ),
    )

    signals = engine.generate_signals({
        "features_by_symbol": {"QQQ": _bars(direction=-1)},
        "now": "2026-05-08T19:25:00+00:00",
        "regime": "high_vol",
    })

    assert len(signals) == 1
    assert signals[0].side == "short"
    assert signals[0].shadow_only is True
    assert signals[0].features["inverse_route_symbol"] == "PSQ"


def test_etf_intraday_momentum_does_not_emit_outside_decision_window() -> None:
    from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine
    from backend.organism.engines.gamma_vol_proxy import GammaVolProxy

    engine = ETFIntradayMomentumEngine(
        universe=("QQQ",),
        gamma_proxy=GammaVolProxy(
            vol_z_threshold=-1.0,
            volume_z_threshold=-1.0,
            trend_bps_threshold=5.0,
        ),
    )

    signals = engine.generate_signals({
        "features_by_symbol": {"QQQ": _bars()},
        "now": "2026-05-08T18:00:00+00:00",
        "regime": "high_vol",
    })

    assert signals == []


def test_etf_intraday_momentum_ignores_future_bars_after_now() -> None:
    from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine
    from backend.organism.engines.gamma_vol_proxy import GammaVolProxy

    engine = ETFIntradayMomentumEngine(
        universe=("QQQ",),
        gamma_proxy=GammaVolProxy(
            vol_z_threshold=-1.0,
            volume_z_threshold=-1.0,
            trend_bps_threshold=5.0,
        ),
    )

    signals = engine.generate_signals({
        "features_by_symbol": {"QQQ": _lookahead_trap_bars()},
        "now": "2026-05-08T19:25:00+00:00",
        "regime": "high_vol",
    })

    assert signals == []


def test_etf_intraday_momentum_requires_previous_close() -> None:
    from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine

    current_only = _bars().iloc[390:].reset_index(drop=True)
    engine = ETFIntradayMomentumEngine(universe=("QQQ",))

    assert engine.generate_signals({
        "features_by_symbol": {"QQQ": current_only},
        "now": "2026-05-08T19:25:00+00:00",
        "regime": "high_vol",
    }) == []
