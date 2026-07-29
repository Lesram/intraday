#!/usr/bin/env python3
"""Pre-open readiness smoke for Phase 9 first-class evidence capture.

This does not create market evidence and does not touch production telemetry.
It generates synthetic minute bars, runs the shadow-only Phase 9 engines, writes
their CandidateSignal rows through the production recorder into an artifact
JSONL, and verifies the rows satisfy the first-class event contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.organism.candidate_shadow_telemetry import CandidateShadowTelemetryRecorder
from backend.organism.engines.eod_reversal_shadow import EODReversalShadowEngine
from backend.organism.engines.etf_intraday_momentum import ETFIntradayMomentumEngine
from backend.organism.engines.gamma_vol_proxy import GammaVolProxy
from backend.organism.engines.orb_sip_v2 import ORBSIPV2Engine
from backend.organism.engines.residual_mean_reversion import ResidualMeanReversionEngine
from scripts.ci.platform_truth_observer import is_first_class_event, is_phase9_event


DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase9_preopen_readiness"
REQUIRED_STRATEGIES = {
    "etf_intraday_momentum",
    "orb_sip_v2",
    "residual_mean_reversion",
    "eod_reversal_shadow",
}


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _market_minutes(day: str, periods: int = 390) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
    return pd.date_range(start.tz_convert("UTC"), periods=periods, freq="min")


def _bars_for(
    *,
    symbol: str,
    previous_day: str,
    session_day: str,
    profile: str,
) -> pd.DataFrame:
    prev_ts = _market_minutes(previous_day)
    session_ts = _market_minutes(session_day)
    rows: list[dict[str, Any]] = []

    for i, ts in enumerate(prev_ts):
        price = 100.0 + (i % 5) * 0.002
        rows.append(_bar(ts, price, volume=1000, spread_bps=2.0))

    for i, ts in enumerate(session_ts):
        if profile == "etf_trend":
            price = 100.0 + i * 0.010 + ((i % 7) - 3) * 0.025
            volume = 6000 + (i % 10) * 80
        elif profile == "orb_breakout":
            price = 105.0 + min(i, 5) * 0.12 + max(i - 5, 0) * 0.018
            if i >= 350:
                price += (i - 349) * 0.05
            volume = 45_000 if i < 15 or i >= 350 else 12_000
        elif profile == "residual_drop":
            price = 100.0 + i * 0.004
            if i >= 355:
                price -= (i - 354) * 0.18
            volume = 8500
        elif profile == "eod_reversal":
            price = 100.0 - i * 0.008
            if i >= 358:
                price += (i - 357) * 0.10
            volume = 5000 if i < 358 else 14_000
        else:
            price = 100.0 + i * 0.003
            volume = 5000
        rows.append(_bar(ts, price, volume=volume, spread_bps=2.0, symbol=symbol))
    return pd.DataFrame(rows)


def _bar(
    ts: pd.Timestamp,
    close: float,
    *,
    volume: float,
    spread_bps: float = 2.0,
    symbol: str = "",
) -> dict[str, Any]:
    del symbol
    open_price = close * 0.9995
    return {
        "timestamp": ts.isoformat(),
        "open": round(open_price, 4),
        "high": round(close * 1.0015, 4),
        "low": round(close * 0.9985, 4),
        "close": round(close, 4),
        "volume": float(volume),
        "spread_bps": float(spread_bps),
    }


def _build_context(now: pd.Timestamp) -> dict[str, Any]:
    features_by_symbol = {
        "SPY": _bars_for(
            symbol="SPY",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="etf_trend",
        ),
        "QQQ": _bars_for(
            symbol="QQQ",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="etf_trend",
        ),
        "IWM": _bars_for(
            symbol="IWM",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="etf_trend",
        ),
        "XLK": _bars_for(
            symbol="XLK",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="etf_trend",
        ),
        "XLE": _bars_for(
            symbol="XLE",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="etf_trend",
        ),
        "NVDA": _bars_for(
            symbol="NVDA",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="orb_breakout",
        ),
        "MSFT": _bars_for(
            symbol="MSFT",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="residual_drop",
        ),
        "AAPL": _bars_for(
            symbol="AAPL",
            previous_day="2026-05-08",
            session_day="2026-05-11",
            profile="eod_reversal",
        ),
    }
    return {
        "features_by_symbol": features_by_symbol,
        "now": now,
        "timestamp": now,
        "regime": "chop",
        "market_return_bps": 35.0,
        "metadata_by_symbol": {
            "NVDA": {
                "avg_volume_14d": 80_000_000,
                "avg_first_window_volume": 40_000,
                "spread_bps": 2.0,
                "earnings_or_news_score": 1.0,
            },
        },
        "sector_returns_bps": {"Technology": 35.0},
    }


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_readiness_report(*, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp("2026-05-11T19:30:00Z")
    context = _build_context(now)
    engines = [
        ETFIntradayMomentumEngine(
            gamma_proxy=GammaVolProxy(
                vol_z_threshold=-10.0,
                volume_z_threshold=-10.0,
            ),
        ),
        ORBSIPV2Engine(),
        ResidualMeanReversionEngine(universe=("MSFT",)),
        EODReversalShadowEngine(universe=("AAPL",)),
    ]

    signals = []
    for engine in engines:
        signals.extend(engine.generate_signals(context))

    telemetry_path = out_dir / "synthetic_strategy_evidence_events.jsonl"
    if telemetry_path.exists():
        telemetry_path.unlink()
    recorder = CandidateShadowTelemetryRecorder(
        telemetry_path,
        runtime_identity={
            "git_sha": _git_head(),
            "runtime_config_hash": "synthetic-preopen-readiness",
            "image_sha": "synthetic-preopen-readiness",
            "build_time": datetime.now(UTC).isoformat(),
        },
    )
    written = recorder.record_signals(signals, tick=1, timestamp=now.isoformat())
    rows = _load_rows(telemetry_path) if telemetry_path.exists() else []
    counts = Counter(str(row.get("strategy_id")) for row in rows)
    missing = sorted(REQUIRED_STRATEGIES - set(counts))
    malformed = [
        row.get("signal_id", "<missing>")
        for row in rows
        if not is_first_class_event(row) or not is_phase9_event(row)
    ]

    ready = written == len(signals) and not missing and not malformed
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "phase9_preopen_evidence_readiness",
        "ready": ready,
        "promotion_evidence": False,
        "production_telemetry_mutated": False,
        "telemetry_path": str(telemetry_path),
        "signals_generated": len(signals),
        "events_written": written,
        "signals_by_strategy": dict(sorted(counts.items())),
        "required_strategies": sorted(REQUIRED_STRATEGIES),
        "missing_strategies": missing,
        "malformed_signal_ids": malformed,
        "note": (
            "Synthetic off-market smoke only. It proves the Phase 9 engines and "
            "recorder can emit first-class shadow events; it does not prove edge."
        ),
    }
    (out_dir / "phase9_preopen_readiness_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    report = build_readiness_report(out_dir=args.out_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
