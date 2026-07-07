"""Shadow/evidence telemetry-recording helpers for the live engine.

Extracted from ``live_engine.py`` (2026-06-08 decomposition) as a mixin to
shrink the ``OrganismLiveEngine`` god-object. These methods write shadow
strategy signals and tick telemetry to the evidence feed / DB and have no
intra-class method calls. ``OrganismLiveEngine`` inherits
``_TelemetryRecordingMixin`` so ``inspect.getsource`` on these methods still
resolves via the MRO and all behavioural call sites are unchanged.

NOTE: ``_record_candidate_evidence`` is deliberately NOT moved — a file-text
guard (test_phase3_candidate_shadow_telemetry) pins its ``def`` location in
live_engine.py relative to ``_live_tick_inner``.

backend.organism dependencies (``_market_return_bps``, ``CandidateSignal``) are
imported lazily inside the methods to avoid any import cycle with
``live_engine``. Behaviour is otherwise byte-for-byte identical to the prior
inline methods.

Requires the host class to provide: ``_phase9_shadow_engines``,
``_strategy_evidence_recorder``, ``_now_fn``, ``_phase9_last_shadow_bar``,
``_phase9_last_engine_counts``, ``_tick_count``, ``_strategy_evidence_events``,
``_phase9_shadow_signal_events``, ``_legacy_orb_last_signal_keys``,
``_sessionmaker``, ``_telemetry``, ``_telemetry_write_errors``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class _TelemetryRecordingMixin:
    """Write shadow strategy signals and tick telemetry to evidence feed / DB."""

    def _record_phase9_shadow_signals(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        *,
        regime: str,
        now_iso: str,
    ) -> None:
        """Record Phase 9 strategy-engine shadow signals once per bar."""
        from backend.organism.live_engine import _market_return_bps

        if not self._phase9_shadow_engines or self._strategy_evidence_recorder is None:
            return
        shadow_now = self._now_fn()
        current_bar = shadow_now.strftime("%Y-%m-%d %H:%M")
        if current_bar == self._phase9_last_shadow_bar:
            return
        self._phase9_last_shadow_bar = current_bar
        context = {
            "features_by_symbol": features_by_symbol,
            "now": shadow_now,
            "regime": str(regime),
            "market_return_bps": _market_return_bps(
                features_by_symbol.get("SPY"),
                shadow_now,
            ),
        }
        signals = []
        engine_counts: dict[str, int] = {}
        for engine in self._phase9_shadow_engines:
            strategy_id = str(
                getattr(engine, "strategy_id", engine.__class__.__name__),
            )
            try:
                generated = list(engine.generate_signals(context))
                engine_counts[strategy_id] = len(generated)
                signals.extend(generated)
            except Exception as exc:
                engine_counts[strategy_id] = -1
                logger.debug("Phase 9 shadow engine %s failed: %s", engine, exc)
        self._phase9_last_engine_counts = engine_counts
        if signals or self._tick_count % 30 == 0:
            logger.info("Phase 9 shadow engine counts: %s", engine_counts)
        if not signals:
            return
        try:
            written = self._strategy_evidence_recorder.record_signals(
                signals,
                tick=self._tick_count,
                timestamp=now_iso,
            )
            self._strategy_evidence_events += written
            self._phase9_shadow_signal_events += written
            logger.info("Phase 9 shadow recorded %d strategy signals", written)
        except Exception as exc:
            logger.warning("Phase 9 shadow signal telemetry write failed: %s", exc)

    def _record_legacy_orb_shadow_signals(
        self,
        triggered: list[Any],
        *,
        regime: str,
        now_iso: str,
    ) -> None:
        """Mirror legacy ORB shadow breakouts into the strategy evidence feed."""
        from backend.organism.schema.candidate_signal import CandidateSignal

        if not triggered or self._strategy_evidence_recorder is None:
            return
        shadow_now = self._now_fn()
        current_bar = shadow_now.strftime("%Y-%m-%d %H:%M")
        if len(self._legacy_orb_last_signal_keys) > 5000:
            self._legacy_orb_last_signal_keys.clear()

        signals: list[CandidateSignal] = []
        for candidate in triggered:
            symbol = str(getattr(candidate, "symbol", "") or "").upper()
            direction = float(getattr(candidate, "direction", 1.0) or 1.0)
            side = "long" if direction >= 0 else "short"
            key = f"{current_bar}:{symbol}:{side}"
            if not symbol or key in self._legacy_orb_last_signal_keys:
                continue
            self._legacy_orb_last_signal_keys.add(key)
            variant = f"legacy_orb_breakout_{side}"
            signals.append(
                CandidateSignal(
                    signal_id=(
                        f"orb-legacy-{symbol.lower()}-{self._tick_count}-"
                        f"{current_bar.replace(' ', 'T').replace(':', '')}"
                    ),
                    strategy_id="orb_legacy_shadow",
                    engine_version="legacy_orb_scanner.v1",
                    symbol=symbol,
                    side=side,
                    timeframe="1Min",
                    created_at=now_iso,
                    intended_horizon_bars=60,
                    regime=str(regime),
                    evidence_tier=0,
                    shadow_only=True,
                    expected_edge_bps=None,
                    confidence=min(
                        0.8,
                        max(
                            0.35,
                            0.45
                            + 0.05
                            * float(getattr(candidate, "rv_ratio", 0.0) or 0.0),
                        ),
                    ),
                    stop_price=(
                        float(getattr(candidate, "suggested_stop", 0.0) or 0.0)
                        or None
                    ),
                    target_price=None,
                    risk_budget_bps=0.0,
                    features={
                        "variant": variant,
                        "orb_high": float(
                            getattr(candidate, "orb_high", 0.0) or 0.0,
                        ),
                        "orb_low": float(
                            getattr(candidate, "orb_low", 0.0) or 0.0,
                        ),
                        "orb_open": float(
                            getattr(candidate, "orb_open", 0.0) or 0.0,
                        ),
                        "orb_close": float(
                            getattr(candidate, "orb_close", 0.0) or 0.0,
                        ),
                        "current_price": float(
                            getattr(candidate, "current_price", 0.0) or 0.0,
                        ),
                        "rv_ratio": float(getattr(candidate, "rv_ratio", 0.0) or 0.0),
                        "atr_at_entry": float(
                            getattr(candidate, "atr_at_entry", 0.0) or 0.0,
                        ),
                        "breakout_triggered": bool(
                            getattr(candidate, "breakout_triggered", False),
                        ),
                        "live_enabled": False,
                    },
                )
            )

        if not signals:
            return
        try:
            written = self._strategy_evidence_recorder.record_signals(
                signals,
                tick=self._tick_count,
                timestamp=now_iso,
            )
            self._strategy_evidence_events += written
            self._phase9_shadow_signal_events += written
            logger.info("Legacy ORB shadow recorded %d strategy evidence signals", written)
        except Exception as exc:
            logger.warning("Legacy ORB shadow telemetry write failed: %s", exc)

    def _record_framework_shadow_candidates(
        self,
        scan_res: dict,
        *,
        regime: str,
        now_iso: str,
    ) -> None:
        """Phase 3 Task 4: stream UN-ROUTED framework candidates into the
        strategy evidence feed as shadow signals — measured, never sized
        (Rule A: a strategy influences live capital only after its forward
        verdict; until then it accumulates comparison data here). Dedup is
        per bar+strategy+symbol+side, same discipline as the legacy ORB
        mirror. strategy_id = "fw_<name>_shadow" keys the per-strategy
        per-regime attribution report."""
        from backend.organism.schema.candidate_signal import CandidateSignal

        if not scan_res or self._strategy_evidence_recorder is None:
            return
        shadow_now = self._now_fn()
        current_bar = shadow_now.strftime("%Y-%m-%d %H:%M")
        if len(self._fw_shadow_last_signal_keys) > 5000:
            self._fw_shadow_last_signal_keys.clear()

        signals: list[CandidateSignal] = []
        for name, entry in scan_res.items():
            if entry.get("routed"):
                continue                    # capital path records itself
            for cand in entry.get("candidates", []):
                symbol = str(cand.symbol or "").upper()
                side = "long" if cand.direction >= 0 else "short"
                key = f"{current_bar}:{name}:{symbol}:{side}"
                if not symbol or key in self._fw_shadow_last_signal_keys:
                    continue
                self._fw_shadow_last_signal_keys.add(key)
                extra = cand.extra if isinstance(cand.extra, dict) else {}
                signals.append(
                    CandidateSignal(
                        signal_id=(
                            f"fw-{name}-{symbol.lower()}-{self._tick_count}-"
                            f"{current_bar.replace(' ', 'T').replace(':', '')}"
                        ),
                        strategy_id=f"fw_{name}_shadow",
                        engine_version="framework_selector.v2",
                        symbol=symbol,
                        side=side,
                        timeframe="1Min",
                        created_at=now_iso,
                        intended_horizon_bars=60,
                        regime=str(regime),
                        evidence_tier=0,
                        shadow_only=True,
                        expected_edge_bps=None,
                        confidence=float(cand.confidence),
                        stop_price=(
                            float(extra.get("stop_price")
                                  or extra.get("suggested_stop") or 0.0) or None
                        ),
                        target_price=(
                            float(extra.get("target_price") or 0.0) or None
                        ),
                        risk_budget_bps=0.0,
                        features={
                            "framework_strategy": name,
                            "routed": False,
                            "atr_at_entry": float(extra.get("atr_at_entry", 0.0) or 0.0),
                        },
                    )
                )
        if not signals:
            return
        try:
            written = self._strategy_evidence_recorder.record_signals(
                signals, tick=self._tick_count, timestamp=now_iso,
            )
            self._strategy_evidence_events += written
            self._phase9_shadow_signal_events += written
            logger.info(
                "Framework shadow recorded %d un-routed strategy signals", written,
            )
        except Exception as exc:
            logger.warning("Framework shadow telemetry write failed: %s", exc)

    async def _persist_telemetry_to_db(self) -> None:
        """Write latest telemetry snapshot to DB (every 6th tick ≈ 1/min)."""
        if self._sessionmaker is None:
            return
        snap = self._telemetry.latest
        if snap is None:
            return
        try:
            from backend.infra.schemas import TickTelemetry
            # V4 N-C-2 (2026-05-02): canonical module is `backend.infra.db`;
            # `backend.infra.database` does not exist — the ImportError was
            # silently swallowed by `except Exception`, dropping every
            # tick_telemetry write since this code path was added.
            from backend.infra.db import get_session_context

            # Top candidates summary (compact)
            top_cands = [
                {"sym": ad.symbol, "score": round(ad.composite_score, 4), "dir": ad.direction}
                for ad in snap.alpha_details[:5]
            ]
            # Exit decisions summary
            exit_decs = [
                {"sym": ed.symbol, "bars": ed.bars_held, "pnl": round(ed.pnl_pct, 4),
                 "nearest": ed.nearest_exit}
                for ed in snap.exit_details
            ]

            async with get_session_context() as session:
                row = TickTelemetry(
                    tick_number=snap.tick_number,
                    regime=snap.regime,
                    equity=snap.equity,
                    drawdown_pct=snap.drawdown_pct,
                    open_positions=snap.open_positions,
                    entries_blocked_reason=snap.filtering.entries_blocked_reason,
                    orders_submitted=snap.filtering.orders_submitted,
                    gate_rejections=snap.filtering.to_dict().get("rejections", {}),
                    top_candidates=top_cands,
                    exit_decisions=exit_decs,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            # V8 NN-HIGH-1 / Wave-34 (2026-05-03): surface telemetry-write
            # failures at WARNING (was DEBUG, which silently masked the
            # zero-rows-in-DB issue audited in V8 BB2 / NN tracks).  The
            # write is best-effort — we never raise — but the operator
            # should see persistent failures.
            try:
                self._telemetry_write_errors = (
                    getattr(self, "_telemetry_write_errors", 0) + 1
                )
            except Exception:
                logger.debug("telemetry error-counter bump failed", exc_info=True)
            logger.warning(
                "Telemetry DB write FAILED (count=%d): %s",
                getattr(self, "_telemetry_write_errors", 1), e,
            )
