"""
Application lifespan management — startup and shutdown sequences.

Extracted from factory.py for maintainability.
"""
import asyncio
import os
from datetime import UTC

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


async def startup(app) -> dict:
    """
    Run all startup sequences. Returns a dict of resources to clean up on shutdown.

    The returned dict may contain:
      - outbox_worker
      - organism_scheduler
      - ml_scheduler
      - stream_task
    """
    ctx: dict = {
        "outbox_worker": None,
        "organism_scheduler": None,
        "ml_scheduler": None,
        "stream_task": None,
        "reconciliation_scheduler": False,
    }

    # ── Observability ────────────────────────────────────────────────
    try:
        from backend.infra.observability import (
            ObservabilityConfig as InfraObsConfig,
            initialize_observability,
        )
        from backend.config.settings import get_settings

        _settings = get_settings()
        _obs = getattr(_settings, "observability", None)

        obs_config = InfraObsConfig(
            service_name=getattr(_obs, "otel_service_name", "intraday-backend"),
            otel_enabled=getattr(_obs, "otel_enabled", True),
            otel_exporter_otlp_endpoint=getattr(_obs, "otel_exporter_otlp_endpoint", None),
            otel_exporter_protocol=getattr(_obs, "otel_exporter_protocol", "grpc"),
            otel_sampler=getattr(_obs, "otel_sampler", "traceidratio"),
            otel_sampler_arg=getattr(_obs, "otel_sampler_arg", 0.5),
            prometheus_enabled=getattr(_obs, "prometheus_enabled", True),
            prometheus_path=getattr(_obs, "prometheus_path", "/metrics"),
            metric_namespace=getattr(_obs, "metric_namespace", "intraday"),
            latency_buckets_ms=getattr(
                _obs, "latency_buckets_ms", "5,10,25,50,100,250,500,1000,2500,5000"
            ),
        )
        initialize_observability(obs_config)
        logger.info("Observability initialized")
    except Exception as obs_e:
        logger.warning("Observability initialization failed (non-critical)", error=str(obs_e))

    # ── SLO Monitoring ───────────────────────────────────────────────
    try:
        from backend.monitoring.slo_metrics import SLOMetricsCollector

        app.state.slo_collector = SLOMetricsCollector()
        logger.info("SLO metrics collector initialized")
    except Exception as slo_e:
        logger.warning("SLO metrics collector failed (non-critical)", error=str(slo_e))

    # ── Database ─────────────────────────────────────────────────────
    if hasattr(app.state, "database_url") and app.state.database_url:
        try:
            from backend.infra.db import init_db

            engine, sessionmaker = init_db(app.state.database_url)
            app.state.sessionmaker = sessionmaker
            app.state.db_sessionmaker = sessionmaker
            logger.info("Database initialized successfully")

            # Pre-warm connection pool
            try:
                pool_size = min(int(os.getenv("DB_POOL_PREWARM_SIZE", "5")), 20)
                if pool_size > 0:

                    async def prewarm():
                        async with sessionmaker() as session:
                            from sqlalchemy import text

                            await session.execute(text("SELECT 1"))

                    await asyncio.gather(*[prewarm() for _ in range(pool_size)])
                    logger.info(f"Pre-warmed {pool_size} database connections")
            except Exception as warm_e:
                logger.warning(f"Pool pre-warming failed (non-critical): {warm_e}")

        except Exception as e:
            env = os.getenv("APP_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")).lower()
            if env in ("production", "prod", "staging"):
                raise RuntimeError(f"Database init failed in {env}: {e}") from e
            logger.warning("Database init failed, continuing (dev only)", error=str(e))
            app.state.sessionmaker = None
            app.state.db_sessionmaker = None
    else:
        logger.info("No database configured")
        app.state.sessionmaker = None
        app.state.db_sessionmaker = None

    _reload_active = os.getenv("UVICORN_RELOAD_ACTIVE") == "1"
    _skip_bg = _reload_active and os.getenv("PYTEST_CURRENT_TEST") is None
    _has_db = hasattr(app.state, "sessionmaker") and app.state.sessionmaker

    # ── Outbox Worker ────────────────────────────────────────────────
    if _has_db and not _skip_bg:
        try:
            from backend.infra.outbox_worker import start_outbox_worker

            ctx["outbox_worker"] = await start_outbox_worker(app.state.sessionmaker)
            app.state.outbox_worker = ctx["outbox_worker"]
            logger.info("Outbox worker started")
        except Exception as e:
            logger.warning("Outbox worker failed", error=str(e))
            app.state.outbox_worker = None
    else:
        app.state.outbox_worker = None

    # ── Living Strategy Policy (OPT-OUT) ─────────────────────────────
    if (
        os.getenv("LIVING_STRATEGY_ENABLED", "true").lower() in ("1", "true", "yes")
        and _has_db
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            from backend.strategies.living_policy import LivingPolicyEngine

            policy = LivingPolicyEngine(sessionmaker=app.state.sessionmaker)
            await policy.maybe_restore_from_db()
            app.state.living_policy = policy
            logger.info("Living strategy policy enabled")
        except Exception as e:
            logger.warning("Living strategy policy failed", error=str(e))
            app.state.living_policy = None

    # ── Full Living Organism (OPT-IN) ────────────────────────────────
    if (
        os.getenv("ORGANISM_ENABLED", "0").lower() in ("1", "true", "yes")
        and _has_db
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            from backend.organism.governance import GovernanceController
            from backend.organism.runner import OrganismRunner
            from backend.organism.promotion import PromotionController
            from backend.organism.nightly_scheduler import start_organism_nightly_scheduler

            governance = GovernanceController()
            app.state.organism_governance = governance

            runner = OrganismRunner(governance=governance)
            app.state.organism_runner = runner

            promotion = PromotionController(
                sessionmaker=app.state.sessionmaker, governance=governance
            )
            await promotion.restore_state()
            app.state.organism_promotion = promotion

            await start_organism_nightly_scheduler(app)
            logger.info("Living organism initialized")
        except Exception as e:
            logger.warning("Living organism failed", error=str(e))
            app.state.organism_governance = None
            app.state.organism_runner = None
            app.state.organism_promotion = None

    # ── Multi-Strategy Live Runner (OPT-IN) ──────────────────────────
    if (
        os.getenv("MULTI_STRATEGY_LIVE_ENABLED", "0") in ("1", "true", "True", "yes")
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            from backend.services.multi_strategy_live_scheduler import (
                start_multi_strategy_live_scheduler,
            )

            started = await start_multi_strategy_live_scheduler(app)
            app.state.multi_strategy_live_scheduler_started = started
            if started:
                logger.info("Multi-strategy live scheduler enabled")
        except Exception as e:
            logger.warning("Multi-strategy live scheduler failed", error=str(e))
            app.state.multi_strategy_live_scheduler_started = False

    # ── Auto Breakout Scanner (OPT-IN) ───────────────────────────────
    if (
        os.getenv("AUTO_BREAKOUT_SCAN_ENABLED", "0").lower() in ("1", "true", "yes")
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            from backend.services.auto_breakout_scanner_scheduler import (
                start_auto_breakout_scanner_scheduler,
            )

            started = await start_auto_breakout_scanner_scheduler(app)
            app.state.auto_breakout_scanner_started = started
            if started:
                logger.info("Auto breakout scanner scheduler enabled")
        except Exception as e:
            logger.warning("Auto breakout scanner scheduler failed", error=str(e))
            app.state.auto_breakout_scanner_started = False

    # ── ML Lifecycle Scheduler (OPT-IN) ──────────────────────────────
    if (
        os.getenv("ENABLE_ML_LIFECYCLE_SCHEDULER", "0") == "1"
        and _has_db
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            from backend.ml.lifecycle_scheduler import LifecycleScheduler

            ml_scheduler = LifecycleScheduler(app.state.sessionmaker)
            ml_scheduler.start()
            ctx["ml_scheduler"] = ml_scheduler
            app.state.ml_lifecycle_scheduler = ml_scheduler
            logger.info("ML lifecycle scheduler enabled")
        except Exception as e:
            logger.warning("ML lifecycle scheduler failed", error=str(e))
            app.state.ml_lifecycle_scheduler = None

    # ── Organism Live Engine Scheduler (OPT-IN) ──────────────────────
    if (
        os.getenv("ENABLE_ORGANISM_SCHEDULER", "0").lower() in ("1", "true", "yes")
        and not os.getenv("PYTEST_CURRENT_TEST")
    ):
        try:
            ctx["organism_scheduler"] = await _start_organism_scheduler(app)
        except Exception as e:
            logger.warning("Organism scheduler failed", error=str(e))
            app.state.organism_scheduler = None

    # ── Alpaca Stream ────────────────────────────────────────────────
    use_mock = os.getenv("USE_MOCK_BROKER", "false").lower() in ("true", "1", "yes")
    if not use_mock and _has_db:
        try:
            from backend.integrations.alpaca_stream import get_stream_client

            stream_client = get_stream_client()
            ctx["stream_task"] = asyncio.create_task(stream_client.start_with_reconnect())
            app.state.alpaca_stream_task = ctx["stream_task"]
            app.state.alpaca_stream_client = stream_client
            logger.info("Alpaca WebSocket stream started")
        except Exception as e:
            logger.warning("Alpaca stream failed", error=str(e))
            app.state.alpaca_stream_task = None
            app.state.alpaca_stream_client = None
    else:
        app.state.alpaca_stream_task = None
        app.state.alpaca_stream_client = None

    # ── Reconciliation Scheduler ────────────────────────────────────
    if _has_db and not _skip_bg and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from backend.services.scheduled_reconciliation import start_reconciliation_scheduler

            started = await start_reconciliation_scheduler()
            ctx["reconciliation_scheduler"] = started
            if started:
                logger.info("Reconciliation scheduler started")
        except Exception as e:
            logger.warning("Reconciliation scheduler failed (non-critical)", error=str(e))
            ctx["reconciliation_scheduler"] = False

    # ── Portfolio Sync ───────────────────────────────────────────────
    if not use_mock and _has_db:
        try:
            from backend.services.portfolio_sync_service import get_portfolio_sync_service

            sync_service = get_portfolio_sync_service()
            default_user_id = os.getenv("DEFAULT_USER_ID", "demo")
            sync_result = await sync_service.sync_full_portfolio(default_user_id)
            if sync_result.get("success"):
                logger.info("Portfolio sync completed", user_id=default_user_id)
            else:
                logger.warning("Portfolio sync failed", error=sync_result.get("error"))
        except Exception as e:
            logger.warning("Portfolio sync failed", error=str(e))

    # ── Order Sync ───────────────────────────────────────────────────
    if ctx["stream_task"] is not None:
        await asyncio.sleep(0.5)

    if not use_mock and _has_db:
        await _sync_orders(app)

    return ctx


async def shutdown(app, ctx: dict, baseline: set) -> None:
    """Graceful shutdown of all services."""
    # ML scheduler
    if ctx.get("ml_scheduler"):
        try:
            await ctx["ml_scheduler"].stop()
            logger.info("ML lifecycle scheduler stopped")
        except Exception as e:
            logger.warning(f"Error stopping ML scheduler: {e}")

    # Organism scheduler
    if ctx.get("organism_scheduler"):
        try:
            await ctx["organism_scheduler"].stop()
            logger.info("Organism scheduler stopped")
        except Exception as e:
            logger.warning(f"Error stopping organism scheduler: {e}")

    # Alpaca stream client
    if hasattr(app.state, "alpaca_stream_client") and app.state.alpaca_stream_client:
        try:
            await app.state.alpaca_stream_client.stop()
            logger.info("Alpaca stream stopped")
        except Exception as e:
            logger.warning(f"Error stopping Alpaca stream: {e}")

    # Close broker/data httpx clients
    for attr in ("alpaca_broker_client", "alpaca_data_client"):
        client = getattr(app.state, attr, None)
        if client and hasattr(client, "aclose"):
            try:
                await client.aclose()
            except Exception:
                pass

    # Cancel stream task
    stream_task = ctx.get("stream_task")
    if stream_task and not stream_task.done():
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

    # Outbox worker
    if ctx.get("outbox_worker"):
        try:
            await ctx["outbox_worker"].stop()
            logger.info("Outbox worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping outbox worker: {e}")

    # Multi-strategy / breakout scheduler
    try:
        from backend.services.multi_strategy_live_scheduler import stop_multi_strategy_live_scheduler

        await stop_multi_strategy_live_scheduler()
    except Exception:
        pass
    try:
        from backend.services.auto_breakout_scanner_scheduler import (
            stop_auto_breakout_scanner_scheduler,
        )

        await stop_auto_breakout_scanner_scheduler()
    except Exception:
        pass

    # Reconciliation scheduler
    if ctx.get("reconciliation_scheduler"):
        try:
            from backend.services.scheduled_reconciliation import stop_reconciliation_scheduler

            await stop_reconciliation_scheduler()
            logger.info("Reconciliation scheduler stopped")
        except Exception as e:
            logger.warning(f"Error stopping reconciliation scheduler: {e}")

    # Database engine
    if hasattr(app.state, "sessionmaker") and app.state.sessionmaker:
        try:
            from backend.infra.db import dispose_engine

            await dispose_engine()
            logger.info("Database engine disposed")
        except Exception as e:
            logger.warning(f"Error disposing database: {e}")

    # Cleanup background tasks
    reg = list(app.state.task_registry.tasks())
    new = [t for t in asyncio.all_tasks() if t not in baseline]
    to_cancel = [t for t in set(reg + new) if not t.done() and not t.cancelled()]
    for t in to_cancel:
        try:
            t.cancel()
        except (RuntimeError, asyncio.InvalidStateError):
            pass
    if to_cancel:
        try:
            await asyncio.wait_for(asyncio.gather(*to_cancel, return_exceptions=True), timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass


# ── Helpers ──────────────────────────────────────────────────────────


async def _start_organism_scheduler(app):
    """Create and start the organism live engine scheduler."""
    from backend.organism.scheduler import OrganismScheduler

    _data_client = getattr(app.state, "alpaca_data_client", None)
    _order_service = getattr(app.state, "order_service", None)
    _positions_svc = getattr(app.state, "positions_service", None)
    _sessionmaker = getattr(app.state, "sessionmaker", None)

    if _data_client is None:
        try:
            from backend.integrations.alpaca_data import get_alpaca_data_client

            _data_client = get_alpaca_data_client()
            app.state.alpaca_data_client = _data_client
        except Exception:
            pass

    if _order_service is None and _sessionmaker:
        try:
            from backend.services.order_service import OrderService

            _order_service = OrderService(sessionmaker=_sessionmaker)
            app.state.order_service = _order_service
        except Exception:
            pass

    if _positions_svc is None:
        try:
            from backend.services.positions_service import PositionsService

            _trading_client = None
            try:
                from alpaca.trading.client import TradingClient

                _ak = os.getenv("ALPACA_API_KEY_ID", "") or os.getenv("ALPACA_API_KEY", "")
                _sk = os.getenv("ALPACA_API_SECRET_KEY", "") or os.getenv("ALPACA_SECRET_KEY", "")
                _paper = os.getenv("ALPACA_PAPER", "true").lower() in ("1", "true")
                if _ak and _sk:
                    _trading_client = TradingClient(api_key=_ak, secret_key=_sk, paper=_paper)
                    logger.info("PositionsService TradingClient created (paper=%s)", _paper)
                else:
                    logger.warning(
                        "PositionsService TradingClient skipped — missing API keys "
                        "(ALPACA_API_KEY_ID=%s, ALPACA_API_SECRET_KEY=%s)",
                        "set" if _ak else "EMPTY",
                        "set" if _sk else "EMPTY",
                    )
            except Exception as exc:
                logger.error("Failed to create TradingClient for PositionsService: %s", exc)
            _positions_svc = PositionsService(trading_client=_trading_client)
            app.state.positions_service = _positions_svc
        except Exception as exc:
            logger.error("Failed to create PositionsService: %s", exc)

    if _data_client and _order_service and _positions_svc:
        # Streaming configuration
        _use_streaming = os.getenv("ORGANISM_USE_STREAMING", "0").lower() in ("1", "true", "yes")
        _alpaca_key = os.getenv("ALPACA_API_KEY_ID", "") or os.getenv("ALPACA_API_KEY", "")
        _alpaca_secret = os.getenv("ALPACA_API_SECRET_KEY", "") or os.getenv("ALPACA_SECRET_KEY", "")
        _alpaca_feed = os.getenv("ALPACA_DATA_FEED", "sip")

        # Cancel stale open orders before starting the engine to prevent
        # wash-trade rejections from orders left over after a restart.
        try:
            from backend.integrations.alpaca_broker import get_alpaca_broker_client
            _broker = get_alpaca_broker_client()
            canceled = await _broker.cancel_all_open_orders()
            if canceled:
                logger.info("Canceled %d stale open orders before engine start", canceled)
        except Exception as e:
            logger.debug("Stale order cleanup skipped: %s", e)

        scheduler = OrganismScheduler(
            data_client=_data_client,
            order_service=_order_service,
            positions_service=_positions_svc,
            sessionmaker=_sessionmaker,
            use_streaming=_use_streaming,
            alpaca_api_key=_alpaca_key if _use_streaming else None,
            alpaca_api_secret=_alpaca_secret if _use_streaming else None,
            alpaca_feed=_alpaca_feed,
        )
        await scheduler.start()
        app.state.organism_scheduler = scheduler
        logger.info(
            "Organism live engine scheduler enabled (streaming=%s)",
            _use_streaming,
        )
        return scheduler

    logger.info("Organism scheduler skipped — missing dependencies")
    app.state.organism_scheduler = None
    return None


async def _sync_orders(app):
    """Sync orders from Alpaca on startup."""
    try:
        from datetime import datetime
        from decimal import Decimal

        from backend.infra.repositories.orders import OrdersRepo
        from backend.integrations.alpaca_broker import get_alpaca_broker_client

        logger.info("Starting initial order sync from Alpaca...")
        broker_client = get_alpaca_broker_client()

        url = f"{broker_client.base_url}/v2/orders"
        headers = broker_client._get_auth_headers()
        params = {"status": "all", "limit": 500, "direction": "desc"}

        response = await asyncio.wait_for(
            broker_client.client.get(url, headers=headers, params=params),
            timeout=10.0,
        )

        if response.status_code != 200:
            logger.warning(f"Order sync: HTTP {response.status_code}")
            return

        alpaca_orders = response.json()
        logger.info(f"Fetched {len(alpaca_orders)} orders for sync")

        synced, updated = 0, 0
        status_mapping = {
            "new": "submitted",
            "accepted": "accepted",
            "pending_new": "submitting",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "canceled": "cancelled",
            "rejected": "rejected",
            "expired": "expired",
        }

        async with app.state.sessionmaker() as session:
            repo = OrdersRepo(session)
            for ao in alpaca_orders:
                broker_id = ao.get("id")
                db_order = await repo.get_by_broker_order_id(broker_id)
                if not db_order:
                    continue

                alpaca_status = status_mapping.get(ao.get("status", ""), ao.get("status", ""))
                alpaca_filled = float(ao.get("filled_qty", 0))
                alpaca_price = ao.get("filled_avg_price")

                needs_update = (
                    float(db_order.filled_qty or 0) != alpaca_filled
                    or db_order.status != alpaca_status
                )
                if needs_update:
                    await repo.attach_broker_result(
                        db_order.id,
                        status=alpaca_status,
                        filled_qty=Decimal(str(alpaca_filled)),
                        avg_fill_price=Decimal(str(alpaca_price)) if alpaca_price else None,
                    )
                    updated += 1

                    try:
                        from backend.api.socketio_server import broadcast_order_update

                        user_id = getattr(db_order, "user_id", None) or os.getenv(
                            "DEFAULT_USER_ID", "demo"
                        )
                        await broadcast_order_update(
                            user_id,
                            {
                                "order_id": str(db_order.id),
                                "broker_order_id": broker_id,
                                "symbol": db_order.symbol,
                                "side": db_order.side,
                                "qty": float(db_order.qty),
                                "filled_qty": alpaca_filled,
                                "avg_fill_price": float(alpaca_price) if alpaca_price else None,
                                "status": alpaca_status,
                                "order_type": db_order.order_type,
                                "submitted_at": (
                                    db_order.submitted_at.isoformat()
                                    if db_order.submitted_at
                                    else None
                                ),
                                "updated_at": datetime.now(UTC).isoformat(),
                            },
                        )
                    except Exception:
                        pass

                synced += 1
            await session.commit()

        logger.info(f"Order sync completed: {synced} synced, {updated} updated")
    except Exception as e:
        logger.warning("Order sync failed", error=str(e))
