"""
FastAPI Application Factory
Creates isolated FastAPI instances with proper dependency injection and metrics setup.
"""
import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request, Response

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class TaskRegistry:
    """Registry for tracking background tasks for guaranteed shutdown cleanup."""

    def __init__(self):
        self._tasks = set()

    def add(self, t: asyncio.Task):
        self._tasks.add(t)
        return t

    def tasks(self):
        return list(self._tasks)


def get_settings():
    """Get settings instance from canonical source."""
    from backend.config import get_settings as _canonical_get_settings
    return _canonical_get_settings()


try:
    settings_instance = get_settings()
except ImportError as e:
    import logging
    logging.error(f"Failed to load settings: {e}")
    raise RuntimeError(
        "Settings module not available. Ensure backend.config is properly installed."
    ) from e

from backend.infra.metrics import initialize_metrics_registry


class CompatSessionmaker:
    """Compatibility wrapper for sessionmaker with engine unpacking support."""
    def __init__(self, sm, engine=None):
        self._sm, self._engine = sm, engine

    def __call__(self, *a, **k):
        return self._sm(*a, **k)

    def __iter__(self):
        yield self._sm
        yield self._engine


def get_db_sessionmaker():
    """Get database sessionmaker with compatibility wrapper."""
    try:
        sm = get_sessionmaker()
        return CompatSessionmaker(sm, None)
    except Exception as e:
        raise RuntimeError(f"Database sessionmaker unavailable: {e}") from e


def get_sessionmaker():
    """Get the database sessionmaker from infra module."""
    from backend.infra.db import get_sessionmaker as infra_get_sessionmaker
    return infra_get_sessionmaker()


def create_app(settings=None, *, registry=None, ws_queue_max: int | None = None, **kwargs):

    if settings is None:
        from backend.config import get_settings
        settings = get_settings()

    # Resolve database URL — REQUIRED for production
    database_url = None
    if hasattr(settings, 'database') and hasattr(settings.database, 'url'):
        database_url = settings.database.url
    elif hasattr(settings, 'data') and hasattr(settings.data, 'database_url'):
        database_url = settings.data.database_url
    else:
        database_url = os.getenv('DATABASE_URL')

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required but not set.\n\n"
            "For local development, start PostgreSQL with Docker:\n"
            "  docker-compose up -d db\n\n"
            "Then set DATABASE_URL (see .env.example for connection string format).\n"
        )

    # ── Lifespan ─────────────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(app):
        from backend.api.lifespan import startup, shutdown

        baseline = set(asyncio.all_tasks())
        ctx = {}
        try:
            ctx = await startup(app)
            yield
        finally:
            await shutdown(app, ctx, baseline)

    # ── Create App ───────────────────────────────────────────────────
    app = FastAPI(
        title="Intraday Trading Platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.task_registry = TaskRegistry()
    app.state.settings = settings
    app.state.is_platform_app = True
    app.state.database_url = database_url

    def register_task(task: asyncio.Task) -> asyncio.Task:
        return app.state.task_registry.add(task)
    app.state.register_task = register_task

    # ── Metrics Registry ─────────────────────────────────────────────
    if registry is not None:
        app.state.metrics_registry = registry
        app.state.metrics = registry
    else:
        app.state.metrics = initialize_metrics_registry()
        app.state.metrics_registry = app.state.metrics

    # ── Risk Manager ─────────────────────────────────────────────────
    try:
        from backend.risk.risk_manager import RiskManager
        app.state.risk_manager = RiskManager()
    except ImportError:
        app.state.risk_manager = None

    # ── Model Manager ────────────────────────────────────────────────
    if os.environ.get("DISABLE_ML", "0") == "1":
        from backend.ml.model_manager import _NoOpModelManager
        app.state.model_manager = _NoOpModelManager()
    else:
        from backend.ml.model_manager import get_model_manager
        app.state.model_manager = get_model_manager()

    # ── Health Endpoints ─────────────────────────────────────────────
    _register_health_endpoints(app)

    # ── Routes ───────────────────────────────────────────────────────
    from backend.api.routes_setup import register_routes
    register_routes(app)

    # ── WebSocket Manager ────────────────────────────────────────────
    from backend.api.websocket_manager import WebSocketClientManager
    qmax = ws_queue_max if ws_queue_max is not None else 1000
    ws_kwargs = {}
    for key, value in kwargs.items():
        if key == 'ws_heartbeat':
            ws_kwargs['heartbeat_interval'] = value
        elif key != 'ws_queue_max':
            ws_kwargs[key] = value
    app.state.ws_manager = WebSocketClientManager(
        queue_max=qmax, metrics_registry=app.state.metrics_registry, **ws_kwargs
    )

    # ── Middleware ────────────────────────────────────────────────────
    from backend.api.middleware_setup import register_middleware
    register_middleware(app, settings)

    # ── OpenAPI ──────────────────────────────────────────────────────
    _configure_openapi(app)

    return app


# ── Helpers ──────────────────────────────────────────────────────────


def _register_health_endpoints(app) -> None:
    """Register health, readiness, liveness, and metrics endpoints."""
    from backend.api.routes.health import create_health_endpoints
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    health_fn, liveness_fn, readiness_fn = create_health_endpoints()

    @app.get("/")
    async def root():
        return {
            "service": "Algorithmic Trading Platform API",
            "version": "1.0.0",
            "status": "operational",
            "api_version": "v1",
            "endpoints": {
                "health": "/health", "readiness": "/readyz",
                "liveness": "/livez", "metrics": "/metrics",
                "docs": "/docs", "api": "/api/v1",
            },
        }

    @app.get("/health")
    async def health_check():
        return await health_fn()

    @app.get("/readyz")
    async def readiness_check(request: Request = None):
        return await readiness_fn(request)

    @app.get("/livez")
    async def liveness_check():
        return await liveness_fn()

    @app.get("/healthz")
    async def healthz_check():
        return await liveness_fn()

    @app.get("/metrics")
    async def metrics():
        try:
            reg = getattr(app.state, "metrics_registry", None)
            if reg and hasattr(reg, "registry"):
                content = generate_latest(reg.registry)
            elif reg:
                content = generate_latest(reg)
            else:
                content = generate_latest()
            return Response(content=content, media_type=CONTENT_TYPE_LATEST)
        except Exception as e:
            return Response(content=f"# Metrics error: {e}\n", media_type="text/plain")


def _configure_openapi(app) -> None:
    """Set up custom OpenAPI schema with JWT Bearer auth."""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title="Intraday Trading Platform",
            version="1.0.0",
            description="Advanced algorithmic trading platform with ML-powered signals",
            routes=app.routes,
        )
        schema["components"]["securitySchemes"] = {
            "HTTPBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
        schema["security"] = [{"HTTPBearer": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi


# ── Legacy compatibility ─────────────────────────────────────────────

async def get_session(request):
    """Get AsyncSession from app state — FastAPI dependency."""
    from backend.infra.db import get_session_from
    async with get_session_from(request.app.state) as session:
        yield session
