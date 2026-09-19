import asyncio
import os

from backend.api.routes.signals import get_market_data_client, get_order_service
from backend.services.auto_breakout_scanner import scan_breakouts
from backend.services.multi_strategy_live_runner import MultiStrategyLiveRunner
from backend.utils.logger import get_logger


logger = get_logger(__name__)

_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def _loop(app) -> None:
    # Audit-J finding J-4 (2026-05-02): _stop_event is now initialized
    # in start_*_scheduler before create_task — see that function below.
    global _stop_event

    interval_seconds = int(os.getenv("AUTO_BREAKOUT_SCAN_INTERVAL_SECONDS", "300"))
    limit = int(os.getenv("AUTO_BREAKOUT_SCAN_LIMIT", "25"))
    timeframe = os.getenv("AUTO_BREAKOUT_SCAN_TIMEFRAME", "1Day")

    auto_trade = os.getenv("AUTO_BREAKOUT_AUTO_TRADE", "0").lower() in ("1", "true", "yes")
    trade_top_n = int(os.getenv("AUTO_BREAKOUT_TRADE_TOP_N", "5"))

    runner = MultiStrategyLiveRunner()

    logger.info(
        "Auto breakout scanner scheduler started",
        extra={
            "interval_seconds": interval_seconds,
            "limit": limit,
            "timeframe": timeframe,
            "auto_trade": auto_trade,
            "trade_top_n": trade_top_n,
        },
    )

    while not _stop_event.is_set():
        try:
            data_client = get_market_data_client()
            scan = await scan_breakouts(data_client=data_client, timeframe=timeframe, limit=limit)

            if auto_trade and scan.candidates:
                symbols = [c.symbol for c in scan.candidates[: max(1, trade_top_n)]]

                class _Req:
                    def __init__(self, app):
                        self.app = app

                order_service = await get_order_service(_Req(app))
                await runner.run_once(
                    symbols=symbols,
                    data_client=data_client,
                    order_service=order_service,
                    timeframe=timeframe,
                )

        except Exception as e:
            logger.error("Auto breakout scanner tick failed", extra={"error": str(e)})

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass

    logger.info("Auto breakout scanner scheduler stopped")


async def start_auto_breakout_scanner_scheduler(app) -> bool:
    global _task

    enabled = os.getenv("AUTO_BREAKOUT_SCAN_ENABLED", "0").lower() in ("1", "true", "yes")
    if not enabled:
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if _task is not None and not _task.done():
        return False

    # Audit-J finding J-4 (2026-05-02): init _stop_event BEFORE create_task
    global _stop_event
    _stop_event = asyncio.Event()

    _task = asyncio.create_task(_loop(app), name="auto_breakout_scanner_scheduler")
    return True


async def stop_auto_breakout_scanner_scheduler() -> None:
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
