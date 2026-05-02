import asyncio
import os
from typing import Any

from backend.api.routes.signals import get_market_data_client
from backend.services.multi_strategy_live_runner import MultiStrategyLiveRunner
from backend.services.auto_breakout_scanner import get_latest_breakout_scan
from backend.strategies.engine import StrategyEngine
from backend.utils.logger import get_logger


logger = get_logger(__name__)

_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def _parse_symbols(value: str) -> list[str]:
    parts = [p.strip().upper() for p in value.split(",")]
    return [p for p in parts if p]


async def _loop(app, interval_seconds: int, symbols: list[str], lookback: int, timeframe: str) -> None:
    # Audit-J finding J-4 (2026-05-02): _stop_event now initialized
    # in start_multi_strategy_live_scheduler before create_task.
    global _stop_event

    runner = MultiStrategyLiveRunner()
    engine = StrategyEngine.create_default()

    policy = getattr(app.state, "living_policy", None)

    logger.info(
        "Multi-strategy live scheduler started",
        extra={
            "interval_seconds": interval_seconds,
            "symbols": symbols,
            "lookback": lookback,
            "timeframe": timeframe,
        },
    )

    while not _stop_event.is_set():
        try:
            # Create an OrderService with a real DB session.
            sessionmaker = getattr(app.state, "sessionmaker", None)
            if not sessionmaker:
                raise RuntimeError("DB sessionmaker not configured; cannot run multi-strategy scheduler")

            from backend.services.order_service import OrderService
            from backend.infra.repositories.orders import OrdersRepo
            from backend.infra.outbox import OutboxRepo

            data_client = get_market_data_client()

            # Tie-in breakout scanner: extend the universe with latest candidates
            dynamic_symbols = list(symbols)
            scan = get_latest_breakout_scan()
            breakout_syms: list[str] = []
            if scan and getattr(scan, "candidates", None):
                breakout_syms = [c.symbol.strip().upper() for c in scan.candidates]
                include_scan = os.getenv("LIVING_STRATEGY_INCLUDE_BREAKOUT_CANDIDATES", "1").lower() in (
                    "1",
                    "true",
                    "yes",
                )
                if include_scan:
                    limit = int(os.getenv("LIVING_STRATEGY_BREAKOUT_CANDIDATES_LIMIT", "20"))
                    # P&L-011: Gate breakout candidates by minimum score and total
                    # position count to prevent portfolio over-expansion.
                    min_score = float(os.getenv("LIVING_STRATEGY_BREAKOUT_MIN_SCORE", "55.0"))
                    max_total_positions = int(os.getenv("LIVING_STRATEGY_MAX_TOTAL_POSITIONS", "40"))
                    added = 0
                    for cand in scan.candidates[:max(0, limit)]:
                        sym = cand.symbol.strip().upper()
                        if not sym or sym in dynamic_symbols:
                            continue
                        # P&L-011: Skip low-quality breakouts
                        if cand.score < min_score:
                            continue
                        # P&L-011: Respect maximum total position count
                        if len(dynamic_symbols) >= max_total_positions:
                            logger.info(
                                "Max total positions reached, skipping remaining breakouts",
                                extra={"max": max_total_positions, "skipped": sym},
                            )
                            break
                        dynamic_symbols.append(sym)
                        added += 1
                    if added > 0:
                        logger.info("Added %d breakout candidates (score >= %.0f)", added, min_score)

            # Apply current living policy weights
            if policy is not None:
                engine.strategy_weights.update(policy.get_weights())

            # ── Organism pre-execution hook ──────────────────────────
            organism_runner = getattr(app.state, "organism_runner", None)
            skip_execution = False
            if organism_runner is not None:
                base_w = dict(engine.strategy_weights)
                organism_pre = organism_runner.pre_execution_hook(base_weights=base_w)
                engine.strategy_weights.update(organism_pre["final_weights"])
                if not organism_pre["trading_allowed"]:
                    logger.warning("Organism governance blocked execution this tick")
                    skip_execution = True
            # ─────────────────────────────────────────────────────────

            if not skip_execution:
                async with sessionmaker() as session:
                    order_service = OrderService(
                        db_session=session,
                        sessionmaker=sessionmaker,
                        orders_repo=OrdersRepo(session),
                        outbox_repo=OutboxRepo(session),
                    )

                    result = await runner.run_once(
                        symbols=dynamic_symbols,
                        lookback=lookback,
                        timeframe=timeframe,
                        data_client=data_client,
                        order_service=order_service,
                        strategy_engine=engine,
                    )

                    await session.commit()

                # ── Organism post-execution hook ─────────────────────
                if organism_runner is not None:
                    # Compute live drawdown metrics for the kill switch
                    live_metrics = {}
                    try:
                        portfolio_value = getattr(result, "portfolio_value", None)
                        if portfolio_value is not None:
                            live_metrics["portfolio_value"] = float(portfolio_value)
                        # Attempt to get drawdown from runner's risk manager
                        rm = getattr(runner, "_risk_manager", None)
                        if rm is not None and hasattr(rm, "get_portfolio_value"):
                            import inspect
                            pv = rm.get_portfolio_value()
                            if inspect.isawaitable(pv):
                                pv = await pv
                            pv = float(pv or 0)
                            if pv > 0:
                                live_metrics["portfolio_value"] = pv
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Kill-switch portfolio value fetch failed: %s", e
                        )
                    organism_runner.post_execution_hook(live_metrics=live_metrics)
                # ─────────────────────────────────────────────────────

                # Update + persist policy snapshot after each tick
                if policy is not None:
                    snap = policy.observe_signals(engine_signals=result.engine_signals, breakout_candidates=breakout_syms)
                    await policy.maybe_persist_snapshot(snap)
        except Exception as e:
            logger.error(
                "Multi-strategy live scheduler tick failed",
                extra={"error": str(e)},
            )

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass

    logger.info("Multi-strategy live scheduler stopped")


async def start_multi_strategy_live_scheduler(app) -> bool:
    """Start background multi-strategy loop (disabled unless env enabled)."""
    global _task

    enabled = os.getenv("MULTI_STRATEGY_LIVE_ENABLED", "0").lower() in ("1", "true", "yes")
    if not enabled:
        return False

    if os.getenv("PYTEST_CURRENT_TEST"):
        return False

    symbols_raw = os.getenv("MULTI_STRATEGY_LIVE_SYMBOLS", "").strip()
    symbols = _parse_symbols(symbols_raw) if symbols_raw else []
    if not symbols:
        logger.warning("MULTI_STRATEGY_LIVE_ENABLED=1 but no MULTI_STRATEGY_LIVE_SYMBOLS set")
        return False

    interval_seconds = int(os.getenv("MULTI_STRATEGY_LIVE_INTERVAL_SECONDS", "300"))
    lookback = int(os.getenv("MULTI_STRATEGY_LIVE_LOOKBACK", "200"))
    timeframe = os.getenv("MULTI_STRATEGY_LIVE_TIMEFRAME", "1Day")

    if _task is not None and not _task.done():
        return False

    # Audit-J finding J-4 (2026-05-02): init _stop_event BEFORE create_task
    global _stop_event
    _stop_event = asyncio.Event()

    _task = asyncio.create_task(
        _loop(app, interval_seconds=interval_seconds, symbols=symbols, lookback=lookback, timeframe=timeframe),
        name="multi_strategy_live_scheduler",
    )
    return True


async def stop_multi_strategy_live_scheduler() -> None:
    global _task, _stop_event

    if _stop_event is not None:
        _stop_event.set()

    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except asyncio.TimeoutError:
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
        finally:
            _task = None
            _stop_event = None


def get_multi_strategy_live_scheduler_status() -> dict[str, Any]:
    if _task is None:
        return {"status": "not_started", "running": False}
    if _task.done():
        exception = _task.exception() if not _task.cancelled() else None
        return {"status": "stopped", "running": False, "error": str(exception) if exception else None}
    return {"status": "running", "running": True}
