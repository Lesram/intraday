"""
Centralized route registration for the FastAPI application.

Extracted from factory.py for maintainability.
"""
from fastapi import APIRouter, Depends, Request

from backend.infra.security import get_authenticated_user
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


def register_routes(app) -> None:
    """Import and mount all API routers onto the app."""

    api_router = APIRouter(prefix="/api/v1", tags=["API v1"])
    protected = APIRouter(dependencies=[Depends(get_authenticated_user)])

    # ── Imports ──────────────────────────────────────────────────────
    from backend.api.errors import router as errors_router
    from backend.api.portfolio import router as portfolio_router
    from backend.api.routes.admin_trading import router as admin_trading_router
    from backend.api.routes.audit import router as audit_router
    from backend.api.routes.auth import router as auth_router
    from backend.api.routes.auto_breakout_scanner import router as auto_breakout_scanner_router
    from backend.api.routes.backtest import router as backtest_router
    from backend.api.routes.chart_templates import public_router as chart_templates_public_router
    from backend.api.routes.chart_templates import router as chart_templates_router
    from backend.api.routes.drawings import router as drawings_router
    from backend.api.routes.indicators import router as indicators_router
    from backend.api.routes.lots import router as lots_router
    from backend.api.routes.market_data import router as market_data_router
    from backend.api.routes.models import router as models_router
    from backend.api.routes.monitoring import router as monitoring_router
    from backend.api.routes.multi_strategy_live import router as multi_strategy_live_router
    from backend.api.routes.observability import router as observability_router
    from backend.api.routes.optimizations import router as optimizations_router
    from backend.api.routes.orders import router as orders_router
    from backend.api.routes.positions import router as positions_router
    from backend.api.routes.risk import router as risk_router
    from backend.api.routes.scanner import router as scanner_router
    from backend.api.routes.settings import router as settings_router
    from backend.api.routes.signals import router as signals_router
    from backend.api.routes.strategy import router as strategy_router
    from backend.api.routes.strategy_health import router as strategy_health_router
    from backend.api.routes.system import router as system_router
    from backend.api.routes.trades import router as trades_router
    from backend.api.routes.watchlists import router as watchlists_router

    # ── Public routes (no auth) ──────────────────────────────────────
    api_router.include_router(system_router, tags=["System - Public"])
    api_router.include_router(monitoring_router, tags=["Monitoring - Public"])
    api_router.include_router(observability_router, tags=["Observability - Public"])
    api_router.include_router(auth_router, tags=["Authentication - Public"])
    api_router.include_router(chart_templates_public_router, tags=["Chart Templates - Public"])

    # ── Protected routes (JWT required) ──────────────────────────────
    protected.include_router(portfolio_router, tags=["Portfolio"])
    protected.include_router(positions_router, tags=["Positions"])
    protected.include_router(risk_router, tags=["Risk Management"])
    protected.include_router(orders_router, tags=["Orders"])
    protected.include_router(trades_router, tags=["Trades"])
    protected.include_router(signals_router, tags=["Signals"])
    protected.include_router(multi_strategy_live_router, tags=["Multi-Strategy Live"])
    protected.include_router(auto_breakout_scanner_router, tags=["Auto Breakout"])
    protected.include_router(models_router, tags=["Models"])
    protected.include_router(strategy_router, tags=["Strategy"])
    # V12 W71 (EXT-1): /api/v1/health/strategy — expectancy gate.
    # External auditor's #1 finding: 11 audits validated correctness
    # without ever exposing realized PnL/Sharpe/win-rate.  Protected
    # because PnL leak to public is an info-disclosure risk.
    protected.include_router(strategy_health_router, tags=["Health"])
    protected.include_router(backtest_router, tags=["Backtesting"])
    protected.include_router(optimizations_router, tags=["Optimizations"])
    protected.include_router(indicators_router, tags=["Indicators"])
    protected.include_router(drawings_router, tags=["Drawings"])
    protected.include_router(watchlists_router, tags=["Watchlists"])
    protected.include_router(chart_templates_router, tags=["Chart Templates"])
    protected.include_router(admin_trading_router, tags=["Admin Trading"])
    protected.include_router(audit_router, tags=["Audit"])
    protected.include_router(lots_router, tags=["Lots"])
    protected.include_router(settings_router, tags=["Settings"])

    # Organism routes (optional module)
    try:
        from backend.organism.routes import router as organism_router

        protected.include_router(organism_router, tags=["Living Organism"])
    except ImportError:
        logger.info("Organism module not available — skipping organism routes")
    except Exception as e:
        logger.warning(f"Failed to load organism routes: {e}")

    # ── Mount ────────────────────────────────────────────────────────
    api_router.include_router(protected)
    # WebSocket routes handle their own auth
    api_router.include_router(market_data_router, tags=["Market Data"])
    api_router.include_router(scanner_router, tags=["Scanner"])

    # Positions alias
    @api_router.get("/positions")
    async def get_positions_alias(
        request: Request, current_user=Depends(get_authenticated_user)
    ):
        from backend.api.portfolio import get_positions as portfolio_get_positions

        return await portfolio_get_positions(request, current_user)

    # Mount onto app
    app.include_router(api_router)
    app.include_router(errors_router)
    # Legacy auth at /auth/* for backward compat
    app.include_router(auth_router, tags=["Authentication"])

    # Error handlers
    from backend.api.errors import install_error_handlers

    install_error_handlers(app)
