"""
Phase 2.3 — Organism Live Scheduler.

Drives the ``OrganismLiveEngine.live_tick()`` on a configurable interval.
Follows the same ``start / stop / _run_loop`` pattern used by
``LifecycleScheduler`` so it can be wired into the FastAPI lifespan
in ``factory.py``.

Environment variables:

    ENABLE_ORGANISM_SCHEDULER=1          # opt-in
    ORGANISM_TICK_INTERVAL_SECONDS=60    # seconds between ticks
    ORGANISM_BRAIN_DIR=organism_brain    # brain persistence directory
    ORGANISM_LIVE_SYMBOLS=AAPL,MSFT,... # comma-separated universe

Usage in factory.py lifespan::

    from backend.organism.scheduler import OrganismScheduler

    scheduler = OrganismScheduler(
        data_client=alpaca_client,
        order_service=order_service,
        positions_service=positions_service,
    )
    await scheduler.start()
    ...
    await scheduler.stop()
"""

from __future__ import annotations

import asyncio
from collections import deque
import os
import random
from datetime import UTC, datetime, time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── US equity market hours (Eastern Time) ─────────────────────────
_ET = ZoneInfo("America/New_York")
_MARKET_OPEN = dt_time(9, 30)   # 9:30 AM ET
_MARKET_CLOSE = dt_time(16, 0)  # 4:00 PM ET
# Buffer: start ticking 2 min before open, stop 1 min after close
# so the engine is warm when market opens and can catch late fills.
_TICK_START = dt_time(9, 28)
_TICK_STOP = dt_time(16, 1)


def _is_market_tick_window() -> bool:
    """Return True if current time is within the tick window for US equities.

    Checks weekday + time-of-day in Eastern Time.
    """
    now_et = datetime.now(_ET)
    if now_et.weekday() >= 5:  # Saturday / Sunday
        return False
    t = now_et.time()
    return _TICK_START <= t <= _TICK_STOP


TICK_INTERVAL = int(
    os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "60")
)

# ── Backoff configuration (HFT-tuned) ────────────────────────────
_BASE_BACKOFF_S = 2             # first retry wait (was 5)
_MAX_BACKOFF_S = 30             # cap at 30s (was 300s / 5min)
_JITTER_FRACTION = 0.10         # ±10 % randomness (was 0.25)


class OrganismScheduler:
    """Background scheduler for the Organism Live Engine.

    The scheduler owns the engine instance, initialises it once,
    then calls ``live_tick()`` every ``tick_interval`` seconds.
    """

    def __init__(
        self,
        *,
        data_client: Any,
        order_service: Any,
        positions_service: Any,
        sessionmaker: Any | None = None,
        tick_interval: int = TICK_INTERVAL,
        brain_dir: str | None = None,
        universe: list[str] | None = None,
        history_limit: int = 200,
        use_streaming: bool = False,
        alpaca_api_key: str | None = None,
        alpaca_api_secret: str | None = None,
        alpaca_feed: str = "sip",
    ) -> None:
        self._data_client = data_client
        self._order_service = order_service
        self._positions_service = positions_service
        self._sessionmaker = sessionmaker
        self._tick_interval = tick_interval
        self._brain_dir = brain_dir
        self._universe = universe
        self._history_limit = max(10, int(history_limit))

        # Streaming config
        self._use_streaming = use_streaming
        self._alpaca_api_key = alpaca_api_key
        self._alpaca_api_secret = alpaca_api_secret
        self._alpaca_feed = alpaca_feed
        self._streaming_provider: Any = None

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._engine: Any = None  # lazily created
        self._last_tick_result: dict[str, Any] | None = None
        self._tick_history: deque[dict[str, Any]] = deque(maxlen=self._history_limit)

    # ── public API ───────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the organism scheduler background task."""
        if self.is_running:
            return

        # Late import to avoid circular dependencies at module level
        from backend.organism.live_engine import OrganismLiveEngine

        # ── Start streaming provider if configured ────────────────
        if self._use_streaming and self._alpaca_api_key and self._alpaca_api_secret:
            try:
                from backend.organism.streaming_data_provider import StreamingDataProvider

                self._streaming_provider = StreamingDataProvider()
                universe = self._universe or [
                    s.strip().upper()
                    for s in os.getenv(
                        "ORGANISM_LIVE_SYMBOLS",
                        "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,AVGO,CRM,"
                        "COST,WMT,LLY,XOM,CAT,SPY,QQQ,IWM,XLK,XLE",
                    ).split(",")
                    if s.strip()
                ]
                await self._streaming_provider.start(
                    symbols=universe,
                    api_key=self._alpaca_api_key,
                    api_secret=self._alpaca_api_secret,
                    feed=self._alpaca_feed,
                )
                logger.info("Streaming data provider started for scheduler")
            except Exception as e:
                logger.warning("Streaming provider failed, continuing without: %s", e)
                self._streaming_provider = None

        kwargs: dict[str, Any] = {
            "data_client": self._data_client,
            "order_service": self._order_service,
            "positions_service": self._positions_service,
        }
        if self._sessionmaker is not None:
            kwargs["sessionmaker"] = self._sessionmaker
        if self._brain_dir:
            kwargs["brain_dir"] = self._brain_dir
        if self._universe:
            kwargs["universe"] = self._universe
        if self._streaming_provider is not None:
            kwargs["streaming_provider"] = self._streaming_provider

        self._engine = OrganismLiveEngine(**kwargs)
        brain_loaded = await self._engine.initialize()

        logger.info(
            "Organism scheduler starting: tick_interval=%ds, "
            "brain_loaded=%s, streaming=%s",
            self._tick_interval,
            brain_loaded,
            self._streaming_provider is not None,
        )

        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the scheduler and persist final brain state."""
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (TimeoutError, asyncio.TimeoutError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except Exception:
                pass
        self._task = None

        # Shut down streaming provider before engine
        if self._streaming_provider is not None:
            try:
                await self._streaming_provider.stop()
            except Exception as e:
                logger.warning("Error stopping streaming provider: %s", e)
            self._streaming_provider = None

        if self._engine:
            await self._engine.shutdown()

        logger.info("Organism scheduler stopped")

    def state(self) -> dict[str, Any]:
        """Return scheduler + engine status for monitoring."""
        base = {
            "running": self.is_running,
            "tick_interval_s": self._tick_interval,
            "last_tick": self._last_tick_result,
            "tick_history": list(self._tick_history),
        }
        if self._engine:
            base["engine"] = self._engine.status()
        return base

    async def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Hot-reload configuration from settings API.

        Updates tick interval, engine params, and streaming subscriptions.
        Returns a dict of parameters that were actually changed.
        """
        changed: dict[str, Any] = {}

        if "tick_interval_seconds" in config:
            self._tick_interval = int(config["tick_interval_seconds"])
            changed["tick_interval_seconds"] = self._tick_interval

        # Forward remaining config to the engine
        if self._engine:
            engine_changed = self._engine.update_config(config)
            changed.update(engine_changed)

        # Update streaming subscriptions if universe changed
        if "universe" in config and self._streaming_provider is not None:
            try:
                await self._streaming_provider.update_subscriptions(config["universe"])
            except Exception as e:
                logger.warning("Streaming subscription update failed: %s", e)

        if changed:
            logger.info("Scheduler config updated: %s", changed)
        return changed

    # ── internal loop ────────────────────────────────────────────

    async def _broadcast_tick(self, tick_data: dict[str, Any]) -> None:
        """Push tick result to WebSocket topic 'organism'."""
        try:
            from backend.websocket import get_websocket_manager

            manager = get_websocket_manager()
            await manager.broadcast_to_topic(
                "organism",
                {
                    "type": "organism_tick",
                    "data": tick_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            pass  # WebSocket not available — acceptable

        try:
            from backend.api.socketio_server import broadcast_to_topic as sio_broadcast_to_topic

            await sio_broadcast_to_topic(
                "organism",
                "organism_tick",
                {
                    "type": "organism_tick",
                    "data": tick_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            pass

    async def _run_loop(self) -> None:
        logger.info("Organism scheduler loop started")
        consecutive_errors = 0
        _last_outside_hours_log: float = 0  # throttle "outside hours" logs

        while not self._stop.is_set():
            try:
                if not _is_market_tick_window():
                    # Log once per 5 minutes to avoid spam
                    now_ts = datetime.now(UTC).timestamp()
                    if now_ts - _last_outside_hours_log > 300:
                        now_et = datetime.now(_ET)
                        logger.debug(
                            "Outside market hours (%s ET %s) — skipping tick",
                            now_et.strftime("%H:%M"),
                            now_et.strftime("%A"),
                        )
                        _last_outside_hours_log = now_ts
                else:
                    result = await asyncio.wait_for(
                        self._engine.live_tick(),
                        timeout=60,  # HFT: 60s hard timeout (was 300s)
                    )
                    self._last_tick_result = result.to_dict()
                    self._tick_history.append(self._last_tick_result)
                    consecutive_errors = 0  # success → reset

                    if result.errors:
                        logger.warning(
                            "Organism tick completed with errors: %s",
                            result.errors,
                        )
                    else:
                        logger.info(
                            "Organism tick: regime=%s signals=%d "
                            "orders=%d exits=%d %.1fs",
                            result.regime,
                            result.signals_generated,
                            result.orders_submitted,
                            result.trades_closed,
                            result.duration_s,
                        )

                    # Broadcast to WebSocket subscribers
                    await self._broadcast_tick(self._last_tick_result)

            except Exception as e:
                consecutive_errors += 1
                logger.exception(
                    "Organism scheduler tick failed (streak=%d): %s",
                    consecutive_errors,
                    e,
                )

            # Compute wait time — exponential backoff on errors
            if consecutive_errors > 0:
                raw = min(
                    _BASE_BACKOFF_S * (2 ** (consecutive_errors - 1)),
                    _MAX_BACKOFF_S,
                )
                jitter = raw * _JITTER_FRACTION * (random.random() * 2 - 1)
                wait = max(raw + jitter, _BASE_BACKOFF_S)
                logger.info(
                    "Organism scheduler backing off for %.0fs "
                    "(consecutive_errors=%d)",
                    wait,
                    consecutive_errors,
                )
            else:
                wait = self._tick_interval

            # Wait for next interval (or stop signal)
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=wait,
                )
            except (TimeoutError, asyncio.TimeoutError):
                pass

        logger.info("Organism scheduler loop exiting")
