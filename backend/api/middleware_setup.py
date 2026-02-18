"""
Middleware configuration for the FastAPI application.

Extracted from factory.py for maintainability.
"""
import time

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


def register_middleware(app, settings) -> None:
    """Install all middleware on the app."""

    _setup_cors(app, settings)
    _setup_gzip(app)
    _setup_deduplication(app)
    _setup_rate_limiting(app)
    _setup_metrics_middleware(app)


def _setup_cors(app, settings) -> None:
    from fastapi.middleware.cors import CORSMiddleware

    cors_origins: list[str] | None = None

    if hasattr(settings, "api") and hasattr(settings.api, "cors_origins"):
        candidate = getattr(settings.api, "cors_origins", None)
        if isinstance(candidate, list) and candidate:
            cors_origins = candidate
    elif hasattr(settings, "app") and hasattr(settings.app, "cors_origins"):
        candidate = getattr(settings.app, "cors_origins", None)
        if isinstance(candidate, list) and candidate:
            cors_origins = candidate

    if not cors_origins:
        cors_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://localhost:3000",
            "https://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://localhost:5173",
            "https://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "https://localhost:5174",
            "https://127.0.0.1:5174",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Authorization", "Content-Type", "Accept", "Accept-Language",
            "Accept-Encoding", "Origin", "DNT", "User-Agent",
            "X-Requested-With", "If-Modified-Since", "Cache-Control", "Range",
        ],
        expose_headers=[
            "Content-Length", "Content-Range", "X-Total-Count",
            "X-Rate-Limit-Remaining", "X-Rate-Limit-Reset", "X-Idempotency-Status",
        ],
    )


def _setup_gzip(app) -> None:
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=500)


def _setup_deduplication(app) -> None:
    try:
        from backend.api.middleware.deduplication import RequestDeduplicationMiddleware

        app.add_middleware(
            RequestDeduplicationMiddleware,
            ttl_seconds=300,
            max_cache_size=10000,
            enabled=True,
        )
    except ImportError as e:
        logger.warning(f"Deduplication middleware not available: {e}")


def _setup_rate_limiting(app) -> None:
    try:
        from backend.api.middleware.rate_limit import RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            enabled=True,
            exempt_paths={
                "/health", "/healthz", "/readyz", "/livez",
                "/metrics", "/docs", "/openapi.json", "/api/v1/health",
            },
        )
    except ImportError as e:
        logger.warning(f"Rate limiting middleware not available: {e}")


def _setup_metrics_middleware(app) -> None:

    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        if not hasattr(request.app.state, "metrics"):
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        status = "success" if 200 <= response.status_code < 300 else "error"
        metrics = getattr(request.app.state, "metrics", None)
        if metrics:
            try:
                metrics.counter(
                    "http_requests_total",
                    {"method": request.method, "route": request.url.path, "status": status},
                ).inc()
                metrics.histogram(
                    "http_request_duration_seconds",
                    {"method": request.method, "route": request.url.path},
                ).observe(duration)
            except Exception:
                pass

        return response
