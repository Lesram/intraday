from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.infra.schemas import ModelLifecycleEvent
from backend.utils.logger import get_logger


logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


@dataclass
class PolicySnapshot:
    ts: str
    mode: str
    regime: dict[str, Any]
    weights: dict[str, float]
    scores: dict[str, float]
    notes: dict[str, Any]


class LivingPolicyEngine:
    """Minimal 'living' policy loop (soft mixing) with bounded adaptation.

    What it does today:
    - Maintains per-strategy weights (used by StrategyEngine netting)
    - Updates weights slowly based on recent realized returns vs prior signal direction
    - Computes a lightweight regime summary from per-signal metadata
    - Persists periodic snapshots to ModelLifecycleEvent for auditability

    What it intentionally does NOT do yet:
    - Parameter optimization / walk-forward tuning
    - Hard gating/rotation
    - Full PnL attribution from fills
    """

    DEFAULT_SOURCES = (
        "momentum",
        "mean_reversion",
        "stat_arb",
        "regime_momentum",
        "breakout",
        "ensemble",
    )

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        policy_name: str = "living_policy",
    ) -> None:
        self._sessionmaker = sessionmaker
        self._policy_name = policy_name

        self._mode = os.getenv("LIVING_STRATEGY_MODE", "active").lower()  # active|shadow
        self._alpha = float(os.getenv("LIVING_STRATEGY_SCORE_EMA_ALPHA", "0.2"))
        self._max_delta = float(os.getenv("LIVING_STRATEGY_WEIGHT_MAX_DELTA", "0.05"))
        self._w_min = float(os.getenv("LIVING_STRATEGY_WEIGHT_MIN", "0.10"))
        self._w_max = float(os.getenv("LIVING_STRATEGY_WEIGHT_MAX", "2.50"))
        self._score_mult = float(os.getenv("LIVING_STRATEGY_SCORE_MULT", "5.0"))
        self._persist_every_s = int(os.getenv("LIVING_STRATEGY_PERSIST_EVERY_SECONDS", "300"))
        self._last_persist_at: datetime | None = None

        # State
        self.weights: dict[str, float] = {s: 1.0 for s in self.DEFAULT_SOURCES}
        self.scores: dict[str, float] = {s: 0.0 for s in self.DEFAULT_SOURCES}
        # Last observation per (source,symbol) used for realized-return scoring
        self._last_obs: dict[str, dict[str, Any]] = {}

        # P&L-002: Stale-weight detection fields
        self._last_weight_change_at: datetime | None = None
        self._stale_threshold_s: float = 86_400.0  # 24 hours

        # P&L-030: Fill-based P&L buffer (source → list[float])
        self._fill_pnl_buffer: dict[str, list[float]] = {}

    async def maybe_restore_from_db(self) -> None:
        if not self._sessionmaker:
            return
        try:
            async with self._sessionmaker() as session:
                row = await self._load_latest_snapshot(session)
                if not row:
                    return
                payload = row.payload or {}
                weights = payload.get("weights") or {}
                scores = payload.get("scores") or {}
                last_obs = payload.get("last_obs") or {}

                if isinstance(weights, dict):
                    for k, v in weights.items():
                        try:
                            self.weights[str(k)] = float(v)
                        except Exception:
                            continue
                if isinstance(scores, dict):
                    for k, v in scores.items():
                        try:
                            self.scores[str(k)] = float(v)
                        except Exception:
                            continue
                if isinstance(last_obs, dict):
                    self._last_obs = last_obs

                logger.info(
                    "Living policy restored from DB",
                    extra={"policy": self._policy_name, "sources": len(self.weights)},
                )
        except Exception as e:
            logger.warning("Living policy restore failed", extra={"error": str(e)})

    def get_weights(self) -> dict[str, float]:
        # Always include all known keys so StrategyEngine has stable label values.
        for s in self.DEFAULT_SOURCES:
            self.weights.setdefault(s, 1.0)
            self.scores.setdefault(s, 0.0)
        return dict(self.weights)

    def observe_signals(
        self,
        *,
        engine_signals: list[Any],
        breakout_candidates: list[str] | None = None,
    ) -> PolicySnapshot:
        """Update scores/weights from the latest signals.

        This uses a simple realized-return proxy:
        when we see a new signal for (source,symbol), we compare the current close
        to the last close observed for that (source,symbol) and score the prior direction.
        """
        breakout_candidates = breakout_candidates or []
        now = _utcnow()

        # Lightweight regime aggregation from metadata
        trending = 0
        volatile = 0
        n = 0

        per_source_deltas: dict[str, float] = {}

        for sig in engine_signals:
            source = str(getattr(sig, "source", "other"))
            symbol = str(getattr(sig, "symbol", ""))
            target_exposure = float(getattr(sig, "target_exposure", 0.0) or 0.0)
            meta = getattr(sig, "metadata", {}) or {}
            close = meta.get("price_close")

            if close is None:
                continue
            try:
                close_f = float(close)
            except Exception:
                continue

            sma50 = meta.get("sma_50")
            atr_ratio = meta.get("atr_ratio")
            try:
                sma50_f = float(sma50) if sma50 is not None else None
            except Exception:
                sma50_f = None
            try:
                atr_f = float(atr_ratio) if atr_ratio is not None else None
            except Exception:
                atr_f = None

            if sma50_f and close_f:
                trending += 1 if close_f >= sma50_f else 0
                n += 1
            if atr_f is not None:
                volatile += 1 if atr_f >= 0.03 else 0
                n += 1

            key = f"{source}:{symbol}"
            prev = self._last_obs.get(key)
            if prev and prev.get("close"):
                prev_close = float(prev["close"])
                if prev_close > 0:
                    realized = (close_f / prev_close) - 1.0
                    direction = int(prev.get("direction", 0))
                    pnl = float(direction) * realized
                    pnl = _clamp(pnl, -0.05, 0.05)
                    per_source_deltas[source] = per_source_deltas.get(source, 0.0) + pnl

            self._last_obs[key] = {
                "close": close_f,
                "direction": _sign(target_exposure),
                "ts": meta.get("bar_timestamp") or getattr(sig, "ts", None) or now.isoformat(),
            }

        # Update per-source scores (EMA)
        # P&L-030: Prefer fill-based P&L over close-to-close proxy when available.
        fill_deltas = self._drain_fill_pnl()
        for source, delta_sum in per_source_deltas.items():
            # Use fill-based delta if available, otherwise close-to-close proxy.
            actual_delta = fill_deltas.pop(source, delta_sum)
            delta = _clamp(actual_delta, -0.10, 0.10)
            prev = float(self.scores.get(source, 0.0))
            self.scores[source] = (1.0 - self._alpha) * prev + self._alpha * delta
        # Process any remaining fill-only sources (no close-to-close signal)
        for source, fill_delta in fill_deltas.items():
            delta = _clamp(fill_delta, -0.10, 0.10)
            prev = float(self.scores.get(source, 0.0))
            self.scores[source] = (1.0 - self._alpha) * prev + self._alpha * delta

        # Compute regime multipliers
        trend_ratio = (trending / max(1, n)) if n else 0.0
        vol_ratio = (volatile / max(1, n)) if n else 0.0

        regime = {
            "trend_ratio": float(trend_ratio),
            "vol_ratio": float(vol_ratio),
            "label": "trending" if trend_ratio >= 0.55 else "chop",
            "vol": "volatile" if vol_ratio >= 0.55 else "normal",
            "breakout_candidates": len(breakout_candidates),
        }

        # Update bounded weights (soft mixing)
        new_weights: dict[str, float] = {}
        for source in set(list(self.weights.keys()) + list(self.scores.keys()) + list(self.DEFAULT_SOURCES)):
            base = float(self.weights.get(source, 1.0))
            score = float(self.scores.get(source, 0.0))
            raw = base * (1.0 + self._score_mult * score)

            # P&L-029: Regime tilts increased from 5% to 15-20% to be 
            # material in the weight vector.  Previous 5% was noise-level.
            if regime["label"] == "trending" and source in ("momentum", "regime_momentum", "breakout"):
                raw *= 1.20
            if regime["label"] == "chop" and source in ("mean_reversion", "stat_arb"):
                raw *= 1.15
            if regime["vol"] == "volatile" and source in ("breakout",):
                raw *= 0.80
            if regime["vol"] == "volatile" and source in ("mean_reversion",):
                raw *= 0.90

            # Breakout tie-in: if scanner has candidates, give breakout a small boost.
            if breakout_candidates and source == "breakout":
                raw *= 1.15

            raw = _clamp(raw, self._w_min, self._w_max)
            prev = float(self.weights.get(source, 1.0))
            step = _clamp(raw - prev, -self._max_delta, self._max_delta)
            new_weights[source] = _clamp(prev + step, self._w_min, self._w_max)

        # P&L-002: Detect if weights actually changed
        weights_changed = any(
            abs(new_weights.get(s, 1.0) - self.weights.get(s, 1.0)) > 1e-6
            for s in set(list(new_weights) + list(self.weights))
        )
        self.weights = new_weights
        if weights_changed:
            self._last_weight_change_at = now
        elif self._last_weight_change_at is not None:
            stale_s = (now - self._last_weight_change_at).total_seconds()
            if stale_s > self._stale_threshold_s:
                logger.warning(
                    "Living policy weights unchanged for >24h -- may indicate stale signals",
                    extra={"seconds_since_change": stale_s},
                )

        snapshot = PolicySnapshot(
            ts=now.isoformat(),
            mode=self._mode,
            regime=regime,
            weights=dict(self.weights),
            scores=dict(self.scores),
            notes={
                "updated_sources": len(per_source_deltas),
            },
        )
        return snapshot

    async def maybe_persist_snapshot(self, snapshot: PolicySnapshot) -> None:
        if not self._sessionmaker:
            return

        now = _utcnow()
        if self._last_persist_at and (now - self._last_persist_at).total_seconds() < self._persist_every_s:
            return

        payload = {
            "policy": self._policy_name,
            "ts": snapshot.ts,
            "mode": snapshot.mode,
            "regime": snapshot.regime,
            "weights": snapshot.weights,
            "scores": snapshot.scores,
            "notes": snapshot.notes,
            "last_obs": self._last_obs,
        }

        try:
            async with self._sessionmaker() as session:
                session.add(
                    ModelLifecycleEvent(
                        model_id=None,
                        model_name=self._policy_name,
                        model_version=None,
                        event_type="living_policy_snapshot",
                        payload=payload,
                        created_at=_utcnow(),
                    )
                )
                await session.commit()
            self._last_persist_at = now
        except Exception as e:
            logger.warning("Living policy persist failed", extra={"error": str(e)})

    async def _load_latest_snapshot(self, session: AsyncSession) -> ModelLifecycleEvent | None:
        res = await session.execute(
            select(ModelLifecycleEvent)
            .where(
                ModelLifecycleEvent.model_name == self._policy_name,
                ModelLifecycleEvent.event_type == "living_policy_snapshot",
            )
            .order_by(desc(ModelLifecycleEvent.created_at))
            .limit(1)
        )
        return res.scalars().first()

    # ------------------------------------------------------------------
    # P&L-030: Fill-based P&L attribution
    # ------------------------------------------------------------------
    def record_fill_pnl(self, source: str, realized_pnl: float) -> None:
        """Record realized (fill-based) P&L for a strategy source.

        Call this from OrderService after a fill is confirmed, passing the
        originating strategy ``source`` and the fill P&L. The next call to
        ``observe_signals()`` will incorporate these into score updates
        instead of relying solely on the close-to-close proxy.
        """
        buf = self._fill_pnl_buffer.setdefault(source, [])
        buf.append(_clamp(realized_pnl, -0.05, 0.05))

    def _drain_fill_pnl(self) -> dict[str, float]:
        """Drain buffered fill P&L into per-source deltas and clear buffer."""
        deltas: dict[str, float] = {}
        for source, pnls in self._fill_pnl_buffer.items():
            if pnls:
                deltas[source] = sum(pnls)
        self._fill_pnl_buffer.clear()
        return deltas
