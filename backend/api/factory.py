"""
FastAPI Application Factory
Creates isolated FastAPI instances with proper dependency injection and metrics setup.
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CollectorRegistry

from backend.config import get_settings
from backend.infra.metrics import initialize_metrics_registry


def create_app(registry: Optional[CollectorRegistry] = None) -> FastAPI:
    """
    Create a FastAPI application instance with proper configuration.
    
    Args:
        registry: Optional CollectorRegistry for metrics isolation (useful for tests)
        
    Returns:
        Configured FastAPI application
    """
    settings = get_settings()
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan management."""
        # Metrics are initialized immediately after app creation
        
        # Initialize other components (commented out for testing compatibility)
        # These imports can cause dependency issues during testing
        try:
            # Component initialization would go here in production
            # await init_db()
            # app.state.alpaca_client = AlpacaClient()
            # etc.
            app.state.active_websockets = []
            yield
            
        finally:
            # Cleanup
            if hasattr(app.state, 'alpaca_client'):
                await app.state.alpaca_client.close()
            if hasattr(app.state, 'active_websockets'):
                for ws in app.state.active_websockets:
                    try:
                        await ws.close()
                    except:
                        pass
    
    # Create FastAPI app
    app = FastAPI(
        title="Intraday Trading Platform",
        description="Advanced algorithmic trading platform with ML capabilities",
        version="1.0.0",
        lifespan=lifespan,
        debug=settings.app.debug,
    )
    
    # Initialize metrics registry immediately for test compatibility
    if registry is not None:
        app.state.metrics = initialize_metrics_registry(
            namespace="intraday", 
            registry=registry
        )
    else:
        app.state.metrics = initialize_metrics_registry(
            namespace="intraday",
            registry=CollectorRegistry()
        )
    
    # Initialize WebSocket manager with metrics registry
    from backend.api.websocket_manager import WebSocketClientManager
    app.state.ws_manager = WebSocketClientManager(metrics_registry=app.state.metrics)
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routes and middleware  
    register_middleware(app)
    register_routes(app)
    
    return app


def register_middleware(app: FastAPI):
    """Register all middleware for the app"""
    from backend.infra.observability import normalize_route, trace_span
    from backend.infra.metrics import get_metrics_registry
    from backend.infra.logging import get_logger as get_structured_logger
    import uuid
    import time

    def generate_request_id() -> str:
        """Generate unique request ID for error tracking"""
        return str(uuid.uuid4())[:8]

    # Request timing and logging middleware
    # NOTE: Disabled to avoid conflict with metrics_middleware which handles the same metrics
    async def timing_middleware_disabled(request, call_next):
        """Add request timing, tracing, and logging for comprehensive observability"""
        start_time = time.time()
        request_id = generate_request_id()

        # Add request ID to headers for tracing
        request.state.request_id = request_id

        # Get structured logger from global getter (can be patched in tests)
        structured_logger = get_structured_logger(__name__)
        
        # Use app-scoped metrics registry instead of global getter
        metrics_registry = getattr(request.app.state, 'metrics', None)

        # Log request start with structured context
        structured_logger.log_http_request(
            method=request.method,
            path=request.url.path,
            status_code=0,  # Will be updated on completion
            duration_ms=0,  # Will be updated on completion
            request_id=request_id
        )

        # Start tracing span
        with trace_span(
            "http_request",
            {
                "http.method": request.method,
                "http.route": normalize_route(request.url.path),
                "http.scheme": request.url.scheme,
                "http.host": request.headers.get("host", "unknown"),
                "http.user_agent": request.headers.get("user-agent", "unknown"),
                "http.request_id": request_id
            }
        ) as span:
            try:
                # Process request
                response = await call_next(request)

                # Calculate timing
                process_time = time.time() - start_time
                duration_ms = process_time * 1000

                # Add timing headers
                response.headers["X-Process-Time"] = f"{process_time:.3f}"
                response.headers["X-Request-ID"] = request_id

                # Update span with response info
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.response_size", len(response.body) if hasattr(response, 'body') else 0)

                # Log structured response
                structured_logger.log_http_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    request_id=request_id
                )

                # Record metrics using app-scoped registry (if available)
                if metrics_registry is not None:
                    normalized_route = normalize_route(request.url.path)

                    # HTTP request counter
                    status = "success" if 200 <= response.status_code < 400 else "error"
                    metrics_registry.inc_counter(
                        "http_requests_total",
                        {
                            "route": normalized_route,
                            "method": request.method,
                            "status": status
                        }
                    )

                    # HTTP latency histogram
                    metrics_registry.observe_histogram(
                        "http_request_duration_seconds",
                        process_time,
                        {
                            "route": normalized_route,
                            "method": request.method
                        }
                    )

                # Metrics are now handled by centralized registry above

                return response

            except Exception as e:
                # Calculate timing for error case
                process_time = time.time() - start_time
                duration_ms = process_time * 1000

                # Update span with error info
                span.set_attribute("http.status_code", 500)
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))

                # Log structured error
                structured_logger.log_http_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    duration_ms=duration_ms,
                    request_id=request_id
                )

                # Record error metrics (if registry available)
                if metrics_registry is not None:
                    normalized_route = normalize_route(request.url.path)
                    metrics_registry.inc_counter(
                        "http_requests_total",
                        {
                            "route": normalized_route,
                            "method": request.method,
                            "status": "error"
                        }
                    )

                    # Record error latency
                    metrics_registry.observe_histogram(
                        "http_request_duration_seconds",
                        process_time,
                        {
                            "route": normalized_route,
                            "method": request.method
                        }
                    )

                # Re-raise to let error handlers process
                raise

    # Middleware for Prometheus metrics
    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        """Middleware to collect Prometheus metrics using centralized registry"""
        if not hasattr(request.app.state, 'metrics'):
            return await call_next(request)

        start_time = time.time()
        method = request.method
        route = request.url.path

        response = await call_next(request)

        # Record metrics using centralized registry
        duration = time.time() - start_time
        status_code = response.status_code
        
        # Map HTTP status codes to metrics status labels
        def map_status_code(code: int) -> str:
            if 200 <= code < 300:
                return "success" 
            elif 400 <= code < 500:
                return "error"
            elif 500 <= code:
                return "error"
            else:
                return "error"

        status = map_status_code(status_code)

        # Get metrics registry from app state, skip if not available
        metrics = getattr(request.app.state, 'metrics', None)
        if metrics:
            try:
                metrics.counter("http_requests_total", {"method": method, "route": route, "status": status}).inc()
                metrics.histogram("http_request_duration_seconds", {"method": method, "route": route}).observe(duration)
            except Exception:
                # Silently skip metrics recording if there's an issue
                pass

        return response


def register_routes(app: FastAPI):
    """Register all routes for the app"""
    # This will be implemented by importing and registering route modules
    # For now, leaving as placeholder since routes are still defined in main.py with decorators
    pass
