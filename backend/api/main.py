"""
FastAPI Gateway - Main API Server with Lifespan and Dependency Injection
Provides REST and WebSocket endpoints for the algorithmic trading platform
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import logging
import time
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

# Prometheus imports - using centralized metrics registry
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("Prometheus client not available")

# Pydantic imports
try:
    from pydantic import BaseModel, Field

    PYDANTIC_AVAILABLE = True
except ImportError:
    logging.warning("Pydantic not available, using basic data classes")
    PYDANTIC_AVAILABLE = False

# Internal imports
from backend.utils.logger import audit_logger, get_logger
from backend.api.websocket_manager import WebSocketClientManager

from ..config import get_settings
from ..data.alpaca_client import AlpacaClient
from ..data.social_sentiment import SocialSentimentAnalyzer
from ..features.feature_engineering import FeatureEngineer
from ..mlops.model_manager import ModelManager
from ..models.ensemble_model import EnsembleModel
from ..risk.risk_manager import RiskManager
from ..strategies.trading_strategies import StrategyManager

# Branch 2.9: Feature validation imports
try:
    from ..features.types import LookaheadLeakError, SchemaValidationError
    FEATURE_VALIDATION_AVAILABLE = True
except ImportError:
    FEATURE_VALIDATION_AVAILABLE = False
    # Create dummy classes for consistent exception handling
    class SchemaValidationError(Exception):
        def __init__(self, message, missing_columns=None, extra_columns=None):
            super().__init__(message)
            self.missing_columns = missing_columns or []
            self.extra_columns = extra_columns or []

    class LookaheadLeakError(Exception):
        def __init__(self, message, columns=None):
            super().__init__(message)
            self.columns = columns or []

# B2.5 - Observability imports
from sqlalchemy.ext.asyncio import AsyncSession

# B2.4 - Outbox pattern imports
from backend.infra.db import get_sessionmaker, init_db
from backend.infra.logging import configure_structured_logging
from backend.infra.logging import get_logger as get_structured_logger
from backend.infra.metrics import get_metrics_registry, initialize_metrics_registry
from backend.infra.observability import ObservabilityConfig, initialize_observability
from backend.infra.outbox import OutboxDispatcher

# Authentication imports
from backend.infra.security import (
    AuthenticatedUser,
    create_access_token,
    get_authenticated_user,
    get_current_user,
    require_admin,
    require_roles,
    require_trader,
)
from backend.infra.users import get_user_repository
from backend.services.order_service import OrderService

# B2.7 - Strategy engine imports
from backend.strategies.engine import StrategyEngine
from backend.strategies.types import TradingSignal as StrategySignal


# Structured error models for API responses
class ErrorDetail(BaseModel):
    """Detailed error information"""
    code: str
    message: str
    context: dict[str, Any] | None = None

class ErrorResponse(BaseModel):
    """Standardized error response structure"""
    error: ErrorDetail
    timestamp: str
    request_id: str | None = None

class ValidationErrorResponse(BaseModel):
    """Validation error response with field details"""
    error: ErrorDetail
    validation_errors: list[dict[str, Any]]
    timestamp: str
    request_id: str | None = None

# Initialize logging and utilities
logger = get_logger(__name__)
# audit_logger is already initialized in the logger module

# Request ID generation for error tracking
import uuid


def generate_request_id() -> str:
    """Generate unique request ID for error tracking"""
    return str(uuid.uuid4())[:8]

# API Response Models for OpenAPI documentation
class SignalResponse(BaseModel):
    """Trading signal API response"""
    symbol: str
    signal_type: str
    strength: float
    confidence: float
    price: float | None = None
    timestamp: str
    features: dict[str, Any] | None = None

class SystemStatusResponse(BaseModel):
    """System status API response"""
    status: str
    timestamp: str
    uptime_seconds: int
    version: str
    environment: str
    components: dict[str, Any]
    background_tasks: dict[str, Any]
    warnings: list[str]
    metrics: dict[str, Any]

class HealthCheckResponse(BaseModel):
    """Health check API response"""
    status: str
    timestamp: str
    components: dict[str, bool]


# Authentication models
class LoginRequest(BaseModel):
    """Login request payload"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with JWT token"""
    access_token: str
    token_type: str
    expires_in: int
    user: dict[str, Any]


class TokenValidationResponse(BaseModel):
    """Token validation response"""
    valid: bool
    user: dict[str, Any] | None = None
    expires_at: str | None = None


# WebSocket manager is now initialized in factory.py

if PYDANTIC_AVAILABLE:
    # Pydantic models for API
    class TradingSignalResponse(BaseModel):
        symbol: str
        signal_type: str
        confidence: float
        target_price: float
        position_size: float
        timestamp: str
        metadata: dict[str, Any] = {}

    class TechnicalFeatures(BaseModel):
        rsi: float | None = None
        macd: float | None = None
        bb_position: float | None = None
        volume_ratio: float | None = None

    class RiskAssessment(BaseModel):
        risk_score: float
        var_1d: float
        position_risk: str
        max_position_size: float

    class AdvancedSignalResponse(BaseModel):
        symbol: str
        signal_type: str
        confidence: float
        target_price: float
        position_size: float
        timestamp: str
        metadata: dict[str, Any] = {}
        authenticated: bool
        technical_features: TechnicalFeatures | None = None
        risk_assessment: RiskAssessment | None = None

    class AdvancedSignalsMetadata(BaseModel):
        timestamp: str
        authenticated: bool
        symbols_requested: int
        symbols_processed: int
        features_included: bool
        risk_metrics_included: bool

    class AdvancedSignalsResponse(BaseModel):
        signals: dict[str, AdvancedSignalResponse]
        metadata: AdvancedSignalsMetadata

    class ModelPredictionResponse(BaseModel):
        symbol: str
        ensemble_prediction: float
        ensemble_confidence: float
        individual_predictions: dict[str, float]
        timestamp: str

    class PortfolioStatus(BaseModel):
        total_value: float
        cash: float
        positions: dict[str, Any]
        daily_pnl: float
        total_pnl: float
        risk_metrics: dict[str, float]

    class MarketDataRequest(BaseModel):
        symbols: list[str]
        timeframe: str = "1Min"
        limit: int = 100

    class TradeRequest(BaseModel):
        symbol: str
        side: str  # buy/sell
        quantity: float
        order_type: str = "market"
        time_in_force: str = "day"

    class ModelTrainingRequest(BaseModel):
        model_id: str
        symbols: list[str]
        training_period_days: int = 30
        retrain_existing: bool = False

    # B2.4 - Order submission models with outbox pattern
    class OrderSubmissionRequest(BaseModel):
        symbol: str
        side: str  # 'buy' or 'sell'
        qty: float
        order_type: str = "market"  # 'market', 'limit', 'stop', 'stop_limit'
        time_in_force: str = "gtc"  # 'gtc', 'day', 'ioc', 'fok'
        limit_price: float | None = None
        stop_price: float | None = None
        client_order_id: str | None = None
        idempotency_key: str | None = None

    class OrderSubmissionResponse(BaseModel):
        order_id: str
        client_order_id: str
        client_idempotency_key: str
        status: str
        symbol: str
        side: str
        qty: float
        order_type: str
        time_in_force: str
        limit_price: float | None
        stop_price: float | None
        created_at: str
        outbox_event_id: str | None = None
        submission_mode: str

    class OrderStatusResponse(BaseModel):
        order_id: str
        client_order_id: str
        broker_order_id: str | None
        status: str
        symbol: str
        side: str
        qty: float
        filled_qty: float | None
        order_type: str
        time_in_force: str
        limit_price: float | None
        stop_price: float | None
        created_at: str | None
        updated_at: str | None
        submitted_at: str | None
        filled_at: str | None

else:
    # Fallback classes if Pydantic not available
    class BaseModel:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Creates and manages all long-lived resources with proper cleanup
    """
    # Startup
    logging.info("Starting algorithmic trading platform...")
    background_tasks = {}  # Track all background tasks
    startup_success = False

    try:
        settings = get_settings()

        # B2.5 - Initialize observability first
        logging.info("Initializing observability infrastructure...")

        # Configure structured logging
        configure_structured_logging(
            level=settings.app.log_level,
            service_name=settings.observability.otel_service_name,
            service_version=settings.app.version,
            enable_trace_correlation=settings.observability.log_trace_correlation,
            json_format=True,
            extra_fields={"environment": settings.app.environment}
        )

        # Initialize OpenTelemetry observability
        observability_config = ObservabilityConfig(
            service_name=settings.observability.otel_service_name,
            service_version=settings.app.version,
            otel_enabled=settings.observability.otel_enabled,
            otel_exporter_otlp_endpoint=settings.observability.otel_exporter_otlp_endpoint,
            otel_exporter_protocol=settings.observability.otel_exporter_protocol,
            otel_sampler=settings.observability.otel_sampler,
            otel_sampler_arg=settings.observability.otel_sampler_arg,
            prometheus_enabled=settings.observability.prometheus_enabled,
            prometheus_path=settings.observability.prometheus_path,
            metric_namespace=settings.observability.metric_namespace,
            latency_buckets_ms=settings.observability.latency_buckets_ms
        )

        initialize_observability(observability_config)

        # Initialize metrics registry
        app.state.metrics_registry = initialize_metrics_registry(
            namespace=settings.observability.metric_namespace
        )

        # Get structured logger for this module
        structured_logger = get_structured_logger(__name__)
        structured_logger.info("Observability initialized successfully", {
            "otel_enabled": settings.observability.otel_enabled,
            "prometheus_enabled": settings.observability.prometheus_enabled,
            "trace_correlation": settings.observability.log_trace_correlation
        })

        # Initialize core components and store in app.state
        logging.info("Initializing AlpacaClient...")
        # Initialize AlpacaClient with test mode for dummy credentials
        api_key = settings.alpaca.api_key or "dummy_key_for_testing"
        secret_key = settings.alpaca.secret_key or "dummy_secret_for_testing"
        test_mode = api_key == "dummy_key_for_testing" or secret_key == "dummy_secret_for_testing"

        app.state.alpaca_client = AlpacaClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=True,
            test_mode=test_mode
        )

        logging.info("Initializing SocialSentimentAnalyzer...")
        app.state.sentiment_analyzer = SocialSentimentAnalyzer()

        logging.info("Initializing FeatureEngineer...")
        app.state.feature_engineer = FeatureEngineer()

        logging.info("Initializing ModelManager...")
        app.state.model_manager = ModelManager()

        logging.info("Initializing EnsembleModel...")
        app.state.ensemble_model = EnsembleModel()

        logging.info("Initializing RiskManager...")
        app.state.risk_manager = RiskManager()

        logging.info("Initializing StrategyManager...")
        app.state.strategy_manager = StrategyManager(
            app.state.risk_manager,
            app.state.ensemble_model
        )

        # B2.7 - Initialize StrategyEngine with required dependencies
        logging.info("Initializing StrategyEngine...")
        from backend.services.positions_service import PositionsService
        app.state.strategy_engine = StrategyEngine(
            risk_manager=app.state.risk_manager,
            positions_service=PositionsService()
        )

        # WebSocket manager is now initialized in factory.py

        # B2.4 - Initialize database and outbox infrastructure
        if settings.outbox.enabled:
            logging.info("Initializing database sessionmaker...")
            engine, sessionmaker = init_db()
            app.state.db_engine = engine
            app.state.db_sessionmaker = sessionmaker
            logging.info("Initializing outbox dispatcher...")
            app.state.outbox_dispatcher = OutboxDispatcher(
                app.state.db_sessionmaker,
                app.state.alpaca_client,
                settings
            )

            # Create shutdown event for outbox dispatcher
            app.state.outbox_stop_event = asyncio.Event()

        # Start and track background tasks
        logging.info("Starting market data stream...")
        background_tasks['market_data'] = asyncio.create_task(
            start_market_data_stream(app), name="market_data_stream"
        )

        logging.info("Starting WebSocket heartbeat...")
        background_tasks['websocket_heartbeat'] = asyncio.create_task(
            app.state.ws_manager.start_heartbeat(), name="websocket_heartbeat"
        )

        # Start model auto-retraining task
        logging.info("Starting model auto-retraining...")
        background_tasks['model_retraining'] = asyncio.create_task(
            start_model_retraining_loop(app), name="model_retraining"
        )

        # B2.4 - Start outbox dispatcher if enabled
        if settings.outbox.enabled and hasattr(app.state, 'outbox_dispatcher'):
            logging.info("Starting outbox dispatcher...")
            background_tasks['outbox_dispatcher'] = asyncio.create_task(
                app.state.outbox_dispatcher.run_forever(app.state.outbox_stop_event),
                name="outbox_dispatcher"
            )

        # Store background tasks in app state for shutdown access
        app.state.background_tasks = background_tasks

        # Wait for critical services to be ready
        await asyncio.sleep(1)  # Give services time to initialize
        startup_success = True

        audit_logger.info("trading_platform_started",
                         timestamp=datetime.now(),
                         components={
                             'alpaca_client': True,
                             'sentiment_analyzer': True,
                             'feature_engineer': True,
                             'model_manager': True,
                             'ensemble_model': True,
                             'risk_manager': True,
                             'strategy_manager': True
                         },
                         background_tasks=list(background_tasks.keys()))

        logging.info("Trading platform startup completed successfully")

        yield

    except Exception as e:
        logging.error(f"Error during startup: {e}", exc_info=True)
        # Cancel any running background tasks on startup failure
        if not startup_success:
            for task_name, task in background_tasks.items():
                if not task.done():
                    logging.warning(f"Cancelling background task: {task_name}")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        raise

    # Shutdown - Enhanced for Production Deployment (BRANCH 2.12)
    logging.info("Initiating graceful shutdown of algorithmic trading platform...")

    shutdown_tasks = []
    shutdown_timeout = 30.0  # Total shutdown timeout

    try:
        # Step 1: Signal all background tasks to stop gracefully
        logging.info("Step 1: Signaling background tasks to stop...")

        # B2.4 - Signal outbox dispatcher to stop first (highest priority)
        if hasattr(app.state, 'outbox_stop_event'):
            logging.info("Signaling outbox dispatcher to stop gracefully...")
            app.state.outbox_stop_event.set()

            # Wait briefly for outbox to flush pending messages
            outbox_task = app.state.background_tasks.get('outbox_dispatcher')
            if outbox_task and not outbox_task.done():
                try:
                    await asyncio.wait_for(outbox_task, timeout=10.0)
                    logging.info("Outbox dispatcher completed gracefully")
                except TimeoutError:
                    logging.warning("Outbox dispatcher did not complete within timeout, forcing cancellation")
                    outbox_task.cancel()
                except Exception as e:
                    logging.error(f"Error waiting for outbox dispatcher: {e}")

        # Step 2: Stop WebSocket manager and disconnect all clients
        logging.info("Step 2: Stopping WebSocket manager...")
        if hasattr(app.state, 'ws_manager') and app.state.ws_manager:
            try:
                # Stop heartbeat first
                shutdown_tasks.append(
                    asyncio.create_task(
                        app.state.ws_manager.stop_heartbeat(),
                        name="stop_ws_heartbeat"
                    )
                )

                # Disconnect all WebSocket clients gracefully
                client_disconnect_tasks = []
                for client_id in list(app.state.ws_manager.clients.keys()):
                    client_disconnect_tasks.append(
                        asyncio.create_task(
                            app.state.ws_manager.remove_client(client_id),
                            name=f"disconnect_client_{client_id}"
                        )
                    )

                # Wait for all WebSocket clients to disconnect
                if client_disconnect_tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*client_disconnect_tasks, return_exceptions=True),
                            timeout=5.0
                        )
                        logging.info(f"Disconnected {len(client_disconnect_tasks)} WebSocket clients")
                    except TimeoutError:
                        logging.warning("WebSocket client disconnection timed out")

            except Exception as e:
                logging.error(f"Error stopping WebSocket manager: {e}")

        # Step 3: Cancel remaining background tasks
        logging.info("Step 3: Cancelling remaining background tasks...")
        if hasattr(app.state, 'background_tasks'):
            for task_name, task in app.state.background_tasks.items():
                if not task.done() and task_name != 'outbox_dispatcher':  # Already handled
                    logging.info(f"Cancelling background task: {task_name}")
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                        logging.info(f"Task {task_name} cancelled successfully")
                    except (TimeoutError, asyncio.CancelledError):
                        logging.warning(f"Task {task_name} cancellation completed with timeout/cancellation")
                    except Exception as e:
                        logging.error(f"Error cancelling task {task_name}: {e}")

        # Step 4: Stop market data stream and disconnect broker
        logging.info("Step 4: Disconnecting market data stream...")
        if hasattr(app.state, 'alpaca_client') and app.state.alpaca_client:
            shutdown_tasks.append(
                asyncio.create_task(
                    cleanup_alpaca_client(app.state.alpaca_client),
                    name="cleanup_alpaca_client"
                )
            )

        # Step 5: Dispose database engine
        logging.info("Step 5: Disposing database engine...")
        if hasattr(app.state, 'db_sessionmaker'):
            try:
                # Get the underlying engine from sessionmaker
                sessionmaker = app.state.db_sessionmaker
                if hasattr(sessionmaker, 'bind') and sessionmaker.bind:
                    await sessionmaker.bind.dispose()
                    logging.info("Database engine disposed successfully")
            except Exception as e:
                logging.error(f"Error disposing database engine: {e}")

        # Step 6: Flush all audit logs
        logging.info("Step 6: Flushing audit logs...")
        shutdown_tasks.append(
            asyncio.create_task(
                flush_audit_logs(),
                name="flush_audit_logs"
            )
        )

        # Step 7: Wait for all shutdown tasks with timeout
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=shutdown_timeout - 5.0  # Reserve 5s for final cleanup
                )
                logging.info("All shutdown tasks completed")
            except TimeoutError:
                logging.warning(f"Shutdown tasks did not complete within {shutdown_timeout-5}s timeout")

        # Final audit log
        audit_logger.info("trading_platform_shutdown_complete",
                         timestamp=datetime.now(),
                         background_tasks_cancelled=len(background_tasks),
                         shutdown_reason="graceful")

        logging.info("Graceful shutdown completed successfully")

    except TimeoutError:
        logging.warning(f"Graceful shutdown exceeded {shutdown_timeout}s timeout")
        audit_logger.warning("trading_platform_shutdown_timeout",
                            timestamp=datetime.now(),
                            timeout_seconds=shutdown_timeout)
    except Exception as e:
        logging.error(f"Error during graceful shutdown: {e}", exc_info=True)
        audit_logger.error("trading_platform_shutdown_error",
                          timestamp=datetime.now(),
                          error=str(e))


async def start_market_data_stream(app: FastAPI):
    """Start real-time market data streaming"""
    if hasattr(app.state, 'alpaca_client') and app.state.alpaca_client:
        try:
            # Connect to Alpaca data streams
            await app.state.alpaca_client.connect_data_stream()
            logging.info("Market data stream started successfully")
        except Exception as e:
            logging.error(f"Error starting market data stream: {e}")


async def start_model_retraining_loop(app: FastAPI):
    """Start background model retraining loop"""
    if hasattr(app.state, 'model_manager') and app.state.model_manager:
        try:
            logging.info("Starting model auto-retraining loop...")
            while True:
                try:
                    # Check for models that need retraining every hour
                    await asyncio.sleep(3600)  # 1 hour

                    if hasattr(app.state.model_manager, 'auto_retrain_models'):
                        retrained_models = await app.state.model_manager.auto_retrain_models()
                        if retrained_models:
                            logging.info(f"Auto-retrained models: {list(retrained_models.keys())}")
                            audit_logger.info("models_auto_retrained",
                                            models=list(retrained_models.keys()),
                                            timestamp=datetime.now())

                except asyncio.CancelledError:
                    logging.info("Model retraining loop cancelled")
                    raise
                except Exception as e:
                    logging.error(f"Error in model retraining loop: {e}")
                    # Continue loop despite errors
                    await asyncio.sleep(300)  # Wait 5 minutes before retry

        except asyncio.CancelledError:
            logging.info("Model retraining loop stopped")
            raise
        except Exception as e:
            logging.error(f"Fatal error in model retraining loop: {e}")


async def cleanup_alpaca_client(alpaca_client: AlpacaClient):
    """Cleanup Alpaca client connections"""
    try:
        # disconnect() is synchronous, not async
        alpaca_client.disconnect()
        logging.info("Alpaca client disconnected successfully")
    except Exception as e:
        logging.error(f"Error stopping market data stream: {e}")


async def flush_audit_logs():
    """Flush any pending audit log entries"""
    try:
        # Get the underlying standard logger and flush its handlers
        underlying_logger = logging.getLogger("audit")
        for handler in underlying_logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
        logging.info("Audit logs flushed successfully")
    except Exception as e:
        logging.error(f"Error flushing audit logs: {e}")


# Create FastAPI app using factory pattern
from .factory import create_app
app = create_app()

# Middleware is now registered in factory.py

# Structured error handlers for consistent API responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with structured error response"""
    request_id = generate_request_id()

    error_detail = ErrorDetail(
        code=f"HTTP_{exc.status_code}",
        message=exc.detail,
        context={
            "status_code": exc.status_code,
            "path": str(request.url),
            "method": request.method
        }
    )

    error_response = ErrorResponse(
        error=error_detail,
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )

    # Log error for monitoring
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}",
                extra={"request_id": request_id, "path": str(request.url)})

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors with field details"""
    request_id = generate_request_id()

    error_detail = ErrorDetail(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        context={
            "path": str(request.url),
            "method": request.method
        }
    )

    validation_response = ValidationErrorResponse(
        error=error_detail,
        validation_errors=[
            {
                "field": ".".join(str(loc) for loc in error.get("loc", [])),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
                "input": error.get("input")
            }
            for error in exc.errors()
        ],
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )

    logger.warning(f"Validation error: {len(exc.errors())} fields failed validation",
                  extra={"request_id": request_id, "path": str(request.url)})

    return JSONResponse(
        status_code=422,
        content=validation_response.model_dump()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors with structured response and logging"""
    request_id = generate_request_id()

    error_detail = ErrorDetail(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        context={
            "path": str(request.url),
            "method": request.method,
            "error_type": exc.__class__.__name__
        }
    )

    error_response = ErrorResponse(
        error=error_detail,
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )

    # Log full exception for debugging
    logger.exception(f"Unhandled exception: {exc.__class__.__name__}: {str(exc)}",
                    extra={"request_id": request_id, "path": str(request.url)})

    return JSONResponse(
        status_code=500,
        content=error_response.model_dump()
    )

# Branch 2.9: Feature validation exception handlers
@app.exception_handler(SchemaValidationError)
async def schema_validation_exception_handler(request: Request, exc: SchemaValidationError):
    """Handle feature schema validation errors with helpful messages"""
    request_id = generate_request_id()

    error_detail = ErrorDetail(
        code="SCHEMA_VALIDATION_ERROR",
        message="Feature schema validation failed",
        context={
            "path": str(request.url),
            "method": request.method,
            "missing_columns": exc.missing_columns,
            "extra_columns": exc.extra_columns
        }
    )

    error_response = ErrorResponse(
        error=error_detail,
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )

    logger.warning("Feature schema validation failed",
                  extra={"request_id": request_id, "missing": exc.missing_columns,
                        "extra": exc.extra_columns})

    return JSONResponse(
        status_code=400,
        content=error_response.model_dump()
    )

@app.exception_handler(LookaheadLeakError)
async def lookahead_leak_exception_handler(request: Request, exc: LookaheadLeakError):
    """Handle lookahead bias detection with helpful messages"""
    request_id = generate_request_id()

    error_detail = ErrorDetail(
        code="LOOKAHEAD_BIAS_DETECTED",
        message="Lookahead bias detected in features",
        context={
            "path": str(request.url),
            "method": request.method,
            "suspicious_columns": getattr(exc, 'columns', [])
        }
    )

    error_response = ErrorResponse(
        error=error_detail,
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )

    logger.error("Lookahead bias detected in feature pipeline",
                extra={"request_id": request_id, "columns": getattr(exc, 'columns', [])})

    return JSONResponse(
        status_code=400,
        content=error_response.model_dump()
    )


# Dependency providers for lightweight injection
def get_risk_manager(request: Request) -> RiskManager:
    """Get RiskManager instance from app state"""
    return request.app.state.risk_manager


def get_ensemble_model(request: Request) -> EnsembleModel:
    """Get EnsembleModel instance from app state"""
    return request.app.state.ensemble_model


def get_strategy_manager(request: Request) -> StrategyManager:
    """Get StrategyManager instance from app state"""
    return request.app.state.strategy_manager


def get_alpaca_client(request: Request) -> AlpacaClient:
    """Get AlpacaClient instance from app state"""
    return request.app.state.alpaca_client


def get_sentiment_analyzer(request: Request) -> SocialSentimentAnalyzer:
    """Get SocialSentimentAnalyzer instance from app state"""
    return request.app.state.sentiment_analyzer


def get_feature_engineer(request: Request) -> FeatureEngineer:
    """Get FeatureEngineer instance from app state"""
    return request.app.state.feature_engineer


def get_model_manager(request: Request) -> ModelManager:
    """Get ModelManager instance from app state"""
    return request.app.state.model_manager


def get_ws_manager(request: Request) -> WebSocketClientManager:
    """Get WebSocketClientManager instance from app state"""
    return request.app.state.ws_manager


def get_strategy_engine(request: Request) -> StrategyEngine:
    """Get StrategyEngine instance from app state"""
    return request.app.state.strategy_engine


# B2.4 - Database and outbox dependencies
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state sessionmaker"""
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_order_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> OrderService:
    """Get OrderService instance with database session"""
    return OrderService(db_session)


# Middleware is now registered in factory.py

# Prometheus metrics endpoint
@app.get("/metrics")
async def get_metrics(request: Request):
    """Prometheus metrics endpoint with comprehensive observability metrics"""
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Metrics not available")

    try:
        # Generate metrics from the app's centralized registry
        if hasattr(request.app.state, 'metrics'):
            return Response(
                generate_latest(request.app.state.metrics.registry),
                media_type=CONTENT_TYPE_LATEST
            )
        else:
            raise HTTPException(status_code=501, detail="Metrics registry not initialized")

    except Exception as e:
        # Fallback to basic prometheus metrics if available
        if PROMETHEUS_AVAILABLE:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
        else:
            raise HTTPException(status_code=501, detail=f"Metrics unavailable: {str(e)}")


# Authentication endpoints
@app.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
async def login(
    username: str = Form(...),
    password: str = Form(...),
):
    """Authenticate user and return JWT access token"""
    user_repo = get_user_repository()
    user = user_repo.authenticate_user(username, password)

    if not user:
        # Audit failed login attempt
        audit_logger.warning(
            "Failed login attempt",
            extra={
                "username": username,
                "ip": "unknown",  # Would need request object for real IP
                "timestamp": datetime.now().isoformat()
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Create access token
    try:
        access_token = create_access_token(
            subject=user.username,
            roles=user.roles
        )

        settings = get_settings()
        expires_in = settings.security.jwt_expire_minutes * 60  # Convert to seconds

        # Audit successful login
        audit_logger.info(
            "Successful login",
            extra={
                "username": username,
                "roles": user.roles,
                "timestamp": datetime.now().isoformat()
            }
        )

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user={
                "username": user.username,
                "roles": user.roles,
                "is_active": user.is_active
            }
        )

    except Exception as e:
        logger.error(f"Token creation failed for user {username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create access token"
        )


@app.post("/auth/token/validate", response_model=TokenValidationResponse, tags=["Authentication"])
async def validate_token(
    current_user: AuthenticatedUser | None = Depends(get_current_user)
):
    """Validate the provided JWT token"""
    if not current_user:
        return TokenValidationResponse(valid=False)

    # Calculate token expiration (approximate, since we don't store it)
    settings = get_settings()
    expires_at = (
        datetime.now() + timedelta(minutes=settings.security.jwt_expire_minutes)
    ).isoformat()

    return TokenValidationResponse(
        valid=True,
        user={
            "username": current_user.username,
            "roles": current_user.roles,
            "token_id": current_user.token_id
        },
        expires_at=expires_at
    )


@app.get("/auth/me", response_model=dict[str, Any], tags=["Authentication"])
async def get_current_user_info(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
):
    """Get current authenticated user information"""
    return {
        "username": current_user.username,
        "roles": current_user.roles,
        "authenticated": True,
        "token_id": current_user.token_id
    }


# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse, tags=["System Health"])
async def health_check(
    risk_manager: RiskManager = Depends(get_risk_manager),
    ensemble_model: EnsembleModel = Depends(get_ensemble_model),
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    sentiment_analyzer: SocialSentimentAnalyzer = Depends(get_sentiment_analyzer),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
    model_manager: ModelManager = Depends(get_model_manager),
):
    """Health check endpoint with dependency injection"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "risk_manager": risk_manager is not None,
            "ensemble_model": ensemble_model is not None,
            "strategy_manager": strategy_manager is not None,
            "alpaca_client": alpaca_client is not None,
            "sentiment_analyzer": sentiment_analyzer is not None,
            "feature_engineer": feature_engineer is not None,
            "model_manager": model_manager is not None,
        },
    }


# Production Health Probes - BRANCH 2.12
@app.get("/healthz", tags=["System Health"])
async def liveness_probe():
    """
    Kubernetes liveness probe - checks if process is alive and responsive.

    This endpoint does NOT check dependencies (DB, broker) - only process health.
    Returns 200 if the process is alive and the event loop is responsive.
    Used by Kubernetes to determine if pod should be restarted.
    """
    try:
        # Quick async operation to verify event loop is responsive
        await asyncio.sleep(0.001)

        return {
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
            "process_id": "unknown",  # Could add os.getpid() if needed
            "check": "liveness"
        }
    except Exception as e:
        # If we can't even complete a simple async operation, we're in trouble
        raise HTTPException(
            status_code=503,
            detail=f"Process not responsive: {str(e)}"
        )


@app.get("/readyz", tags=["System Health"])
async def readiness_probe(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Kubernetes readiness probe - checks if service is ready to handle traffic.

    Verifies:
    - Database connectivity and health
    - Broker/Alpaca client connectivity
    - Critical components are operational
    - Outbox dispatcher is running (if enabled)

    Returns 200 only when service is fully ready to serve requests.
    Used by Kubernetes to determine if pod should receive traffic.
    """
    health_checks = {}
    overall_ready = True

    try:
        # 1. Database Health Check
        try:
            from backend.infra.db import db_health_check
            db_status = await db_health_check()
            health_checks["database"] = {
                "status": "healthy" if db_status else "unhealthy",
                "ready": bool(db_status)
            }
            if not db_status:
                overall_ready = False
        except Exception as e:
            health_checks["database"] = {
                "status": "error",
                "ready": False,
                "error": str(e)
            }
            overall_ready = False

        # 2. Broker/Alpaca Client Health Check
        try:
            alpaca_client = getattr(request.app.state, 'alpaca_client', None)
            if alpaca_client and not getattr(alpaca_client, 'test_mode', True):
                # Only check real broker connections, not test mode
                broker_ready = getattr(alpaca_client, 'connected', False)
                health_checks["broker"] = {
                    "status": "connected" if broker_ready else "disconnected",
                    "ready": broker_ready,
                    "test_mode": False
                }
                if not broker_ready:
                    overall_ready = False
            else:
                # Test mode - consider ready
                health_checks["broker"] = {
                    "status": "test_mode",
                    "ready": True,
                    "test_mode": True
                }
        except Exception as e:
            health_checks["broker"] = {
                "status": "error",
                "ready": False,
                "error": str(e)
            }
            overall_ready = False

        # 3. Outbox Dispatcher Health (if enabled)
        try:
            if hasattr(request.app.state, 'background_tasks'):
                outbox_task = request.app.state.background_tasks.get('outbox_dispatcher')
                if outbox_task:
                    outbox_ready = not outbox_task.done() and not outbox_task.cancelled()
                    health_checks["outbox_dispatcher"] = {
                        "status": "running" if outbox_ready else "stopped",
                        "ready": outbox_ready
                    }
                    if not outbox_ready:
                        overall_ready = False
                else:
                    health_checks["outbox_dispatcher"] = {
                        "status": "not_configured",
                        "ready": True  # If not configured, don't fail readiness
                    }
            else:
                health_checks["outbox_dispatcher"] = {
                    "status": "not_configured",
                    "ready": True
                }
        except Exception as e:
            health_checks["outbox_dispatcher"] = {
                "status": "error",
                "ready": False,
                "error": str(e)
            }

        # 4. WebSocket Manager Health
        try:
            ws_manager = getattr(request.app.state, 'ws_manager', None)
            if ws_manager:
                ws_ready = not getattr(ws_manager, '_stop_heartbeat', False)
                health_checks["websocket_manager"] = {
                    "status": "running" if ws_ready else "stopped",
                    "ready": ws_ready
                }
                if not ws_ready:
                    overall_ready = False
            else:
                health_checks["websocket_manager"] = {
                    "status": "not_configured",
                    "ready": True
                }
        except Exception as e:
            health_checks["websocket_manager"] = {
                "status": "error",
                "ready": False,
                "error": str(e)
            }

        # Return readiness status
        status_code = 200 if overall_ready else 503
        response_data = {
            "status": "ready" if overall_ready else "not_ready",
            "timestamp": datetime.now().isoformat(),
            "checks": health_checks,
            "overall_ready": overall_ready,
            "check": "readiness"
        }

        if overall_ready:
            return response_data
        else:
            raise HTTPException(status_code=503, detail=response_data)

    except HTTPException:
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "check": "readiness"
            }
        )


# Enhanced system status endpoint
@app.get("/api/v1/system/status", response_model=SystemStatusResponse, tags=["System Health"])
async def system_status(
    risk_manager: RiskManager = Depends(get_risk_manager),
    ensemble_model: EnsembleModel = Depends(get_ensemble_model),
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    sentiment_analyzer: SocialSentimentAnalyzer = Depends(get_sentiment_analyzer),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
    model_manager: ModelManager = Depends(get_model_manager),
    ws_manager: WebSocketClientManager = Depends(get_ws_manager),
):
    """Comprehensive system status endpoint with normalized response structure"""

    current_time = datetime.now()
    app_state = getattr(app, 'state', None)

    # Calculate uptime (approximate from last risk check if available)
    uptime_seconds = 0
    if risk_manager and hasattr(risk_manager, 'last_risk_check'):
        uptime_seconds = (current_time - risk_manager.last_risk_check.replace(tzinfo=None)).total_seconds()

    # Component status with detailed info
    components = {}

    # Risk Manager Status
    components["risk_manager"] = {
        "available": risk_manager is not None,
        "status": "operational" if risk_manager else "unavailable",
        "mock_fallbacks_used": list(getattr(risk_manager, 'mock_data_used', [])) if risk_manager else [],
        "circuit_breaker_active": getattr(risk_manager, 'circuit_breaker_active', False) if risk_manager else False,
        "daily_trades": getattr(risk_manager, 'daily_trades', 0) if risk_manager else 0
    }

    # Model Status
    model_status = {}
    if ensemble_model:
        model_status = ensemble_model.get_model_status()

    components["ensemble_model"] = {
        "available": ensemble_model is not None,
        "status": "operational" if ensemble_model else "unavailable",
        "models": model_status
    }

    # WebSocket Manager Status
    active_connections = len(ws_manager.clients) if ws_manager else 0
    components["websocket_manager"] = {
        "available": ws_manager is not None,
        "status": "operational" if ws_manager else "unavailable",
        "active_connections": active_connections,
        "heartbeat_active": hasattr(ws_manager, '_heartbeat_task') and ws_manager._heartbeat_task is not None if ws_manager else False
    }

    # Alpaca Client Status
    components["alpaca_client"] = {
        "available": alpaca_client is not None,
        "status": "operational" if alpaca_client else "unavailable",
        "connected": getattr(alpaca_client, 'connected', False) if alpaca_client else False,
        "test_mode": getattr(alpaca_client, 'test_mode', True) if alpaca_client else True
    }

    # Other Components
    for name, component in [
        ("strategy_manager", strategy_manager),
        ("sentiment_analyzer", sentiment_analyzer),
        ("feature_engineer", feature_engineer),
        ("model_manager", model_manager)
    ]:
        components[name] = {
            "available": component is not None,
            "status": "operational" if component else "unavailable"
        }

    # Background Tasks Status
    background_tasks_info = {}
    if app_state and hasattr(app_state, 'background_tasks'):
        for task_name, task in app_state.background_tasks.items():
            background_tasks_info[task_name] = {
                "running": not task.done(),
                "cancelled": task.cancelled(),
                "exception": str(task.exception()) if task.done() and task.exception() else None
            }

    # Overall system health
    all_critical_components_up = all([
        components["risk_manager"]["available"],
        components["ensemble_model"]["available"],
        components["alpaca_client"]["available"],
        components["websocket_manager"]["available"]
    ])

    system_health = "healthy" if all_critical_components_up else "degraded"

    # Mock fallbacks warning
    mock_warnings = []
    if components["risk_manager"]["mock_fallbacks_used"]:
        mock_warnings.append("Risk calculations using mock data fallbacks")

    return {
        "status": system_health,
        "timestamp": current_time.isoformat(),
        "uptime_seconds": int(uptime_seconds),
        "version": "1.0.0-branch1",
        "environment": "development",  # Could be loaded from settings
        "components": components,
        "background_tasks": background_tasks_info,
        "warnings": mock_warnings,
        "metrics": {
            "total_components": len(components),
            "operational_components": sum(1 for c in components.values() if c["status"] == "operational"),
            "websocket_connections": active_connections,
            "mock_fallbacks_active": len(components["risk_manager"]["mock_fallbacks_used"]) > 0
        }
    }


# Trading Signals Endpoints
@app.get("/api/v1/signals/{symbol}", response_model=SignalResponse, tags=["Trading Signals"])
async def get_trading_signal(
    symbol: str,
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
):
    """Get trading signal for a specific symbol"""
    start_time = time.time() if PROMETHEUS_AVAILABLE else 0

    try:
        if not strategy_manager:
            raise HTTPException(
                status_code=503, detail="Strategy manager not available"
            )

        # Get market data
        if not alpaca_client:
            raise HTTPException(
                status_code=503, detail="Market data client not available"
            )

        price_data = await alpaca_client.get_historical_data(
            symbol, timeframe="1Day", limit=100
        )
        if price_data.empty:
            raise HTTPException(status_code=404, detail="No market data found")

        # Generate features
        features = feature_engineer.compute_all_features(price_data)

        # Generate signal
        signal = await strategy_manager.generate_combined_signal(
            symbol, price_data, features
        )

        if PYDANTIC_AVAILABLE:
            return TradingSignalResponse(
                symbol=signal.symbol,
                signal_type=signal.signal_type.value,
                confidence=signal.confidence,
                target_price=signal.target_price,
                position_size=signal.position_size,
                timestamp=signal.timestamp.isoformat(),
                metadata=signal.metadata,
            ).model_dump()
        else:
            return {
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "target_price": signal.target_price,
                "position_size": signal.position_size,
                "timestamp": signal.timestamp.isoformat(),
                "metadata": signal.metadata,
            }

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error generating signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/signals", response_model=dict[str, SignalResponse], tags=["Trading Signals"])
async def get_all_signals(
    symbols: str = "AAPL,GOOGL,MSFT,TSLA,NVDA",
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
):
    """Get trading signals for multiple symbols"""
    try:
        symbol_list = [s.strip() for s in symbols.split(",")]
        signals = {}

        for symbol in symbol_list:
            try:
                # Generate signal for each symbol
                price_data = await alpaca_client.get_historical_data(
                    symbol, timeframe="1Day", limit=100
                )
                if not price_data.empty:
                    features = feature_engineer.compute_all_features(price_data)
                    signal = await strategy_manager.generate_combined_signal(
                        symbol, price_data, features
                    )

                    if PYDANTIC_AVAILABLE:
                        signals[symbol] = TradingSignalResponse(
                            symbol=signal.symbol,
                            signal_type=signal.signal_type.value,
                            confidence=signal.confidence,
                            target_price=signal.target_price,
                            position_size=signal.position_size,
                            timestamp=signal.timestamp.isoformat(),
                            metadata=signal.metadata,
                        ).model_dump()
                    else:
                        signals[symbol] = {
                            "symbol": signal.symbol,
                            "signal_type": signal.signal_type.value,
                            "confidence": signal.confidence,
                            "target_price": signal.target_price,
                            "position_size": signal.position_size,
                            "timestamp": signal.timestamp.isoformat(),
                            "metadata": signal.metadata,
                        }
                else:
                    signals[symbol] = {"error": "No market data available"}
            except Exception as e:
                logging.warning(f"Error getting signal for {symbol}: {e}")
                signals[symbol] = {"error": str(e)}

        return {"signals": signals, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logging.exception(f"Error in get_all_signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Advanced Signals Endpoint with Optional Authentication
@app.get("/api/v1/signals/advanced", response_model=AdvancedSignalsResponse if PYDANTIC_AVAILABLE else dict[str, Any], tags=["Trading Signals", "Protected"])
async def get_advanced_signals(
    symbols: str = "AAPL,GOOGL,MSFT,TSLA,NVDA",
    include_features: bool = False,
    include_risk_metrics: bool = False,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),  # Authentication required
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """
    Advanced trading signals with optional authentication and enhanced data
    Authentication is required for access to full features and risk metrics
    """
    try:
        symbol_list = [s.strip() for s in symbols.split(",")]
        enhanced_signals = {}

        # Enhanced features available only to authenticated users
        is_authenticated = current_user is not None

        for symbol in symbol_list:
            try:
                # Get market data
                price_data = await alpaca_client.get_historical_data(
                    symbol, timeframe="1Day", limit=100
                )

                if not price_data.empty:
                    # Compute features
                    features = feature_engineer.compute_all_features(price_data)

                    # Generate enhanced signal
                    signal = await strategy_manager.generate_combined_signal(
                        symbol, price_data, features
                    )

                    # Base signal data
                    signal_data = {
                        "symbol": signal.symbol,
                        "signal_type": signal.signal_type.value,
                        "confidence": signal.confidence,
                        "target_price": signal.target_price,
                        "position_size": signal.position_size,
                        "timestamp": signal.timestamp.isoformat(),
                        "metadata": signal.metadata or {},
                        "authenticated": is_authenticated
                    }

                    # Add enhanced data for authenticated users
                    if is_authenticated and include_features and features is not None:
                        # Include latest technical indicators
                        signal_data["technical_features"] = {
                            "rsi": float(features.get("RSI", 0)) if "RSI" in features else None,
                            "macd": float(features.get("MACD", 0)) if "MACD" in features else None,
                            "bb_position": float(features.get("bb_position", 0)) if "bb_position" in features else None,
                            "volume_ratio": float(features.get("volume_ratio", 1)) if "volume_ratio" in features else None
                        }

                    # Add risk metrics for authenticated users
                    if is_authenticated and include_risk_metrics and risk_manager:
                        try:
                            risk_metrics = await risk_manager.evaluate_trade_risk(
                                symbol, signal.position_size, signal.target_price
                            )
                            signal_data["risk_assessment"] = {
                                "risk_score": risk_metrics.get("risk_score", 0),
                                "var_1d": risk_metrics.get("var_1d", 0),
                                "position_risk": risk_metrics.get("position_risk", "unknown"),
                                "max_position_size": risk_metrics.get("max_position_size", 0)
                            }
                        except Exception as risk_error:
                            signal_data["risk_assessment"] = {"error": str(risk_error)}

                    enhanced_signals[symbol] = signal_data

                else:
                    enhanced_signals[symbol] = {"error": "No market data available"}

            except Exception as symbol_error:
                logger.warning(f"Error processing symbol {symbol}: {symbol_error}")
                enhanced_signals[symbol] = {"error": str(symbol_error)}

        # Response metadata
        response = {
            "signals": enhanced_signals,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "authenticated": is_authenticated,
                "symbols_requested": len(symbol_list),
                "symbols_processed": len(enhanced_signals),
                "features_included": include_features and is_authenticated,
                "risk_metrics_included": include_risk_metrics and is_authenticated
            }
        }

        # Add audit log for authenticated requests
        if is_authenticated:
            audit_logger.info("advanced_signals_requested",
                            user=current_user,
                            symbols=symbol_list,
                            include_features=include_features,
                            include_risk_metrics=include_risk_metrics)

        return response

    except Exception as e:
        logger.exception(f"Error in get_advanced_signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error getting signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time data with improved backpressure handling
@app.websocket("/ws/realtime/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    ws_manager: WebSocketClientManager = Depends(get_ws_manager),
):
    """WebSocket endpoint for real-time trading data with backpressure handling and rate limiting"""
    await websocket.accept()
    await ws_manager.add_client(client_id, websocket)

    # Track background tasks and rate limiting for this client
    background_tasks = {}
    message_count = 0
    last_reset_time = time.time()
    MAX_MESSAGES_PER_MINUTE = settings.websocket_rate_limit_per_minute  # Configurable rate limit

    try:
        while True:
            # Wait for client message
            data = await websocket.receive_text()
            message = json.loads(data)

            # Rate limiting check
            current_time = time.time()
            if current_time - last_reset_time >= 60:  # Reset counter every minute
                message_count = 0
                last_reset_time = current_time

            message_count += 1
            if message_count > MAX_MESSAGES_PER_MINUTE:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Rate limit exceeded. Maximum 60 messages per minute."
                }))
                continue

            if PROMETHEUS_AVAILABLE and ws_manager.metrics_registry:
                ws_manager.metrics_registry.counter(
                    'websocket_messages_total',
                    {'direction': 'received', 'message_type': message.get('type', 'unknown')}
                ).inc()

            message_type = message.get("type")
            client_info = ws_manager.clients.get(client_id)

            if not client_info:
                break

            if message_type == "subscribe_signals":
                symbols = message.get("symbols", [])
                client_info['subscriptions'].add('signals')

                # Cancel previous signals task if exists
                if "signals" in background_tasks:
                    background_tasks["signals"].cancel()

                # Start new background task for signals
                background_tasks["signals"] = asyncio.create_task(
                    send_realtime_signals(ws_manager, client_id, symbols)
                )

            elif message_type == "subscribe_portfolio":
                client_info['subscriptions'].add('portfolio')

                # Cancel previous portfolio task if exists
                if "portfolio" in background_tasks:
                    background_tasks["portfolio"].cancel()

                # Start new background task for portfolio
                background_tasks["portfolio"] = asyncio.create_task(
                    send_portfolio_updates(ws_manager, client_id)
                )

            elif message_type == "unsubscribe_signals":
                client_info['subscriptions'].discard('signals')
                if "signals" in background_tasks:
                    background_tasks["signals"].cancel()
                    del background_tasks["signals"]

            elif message_type == "unsubscribe_portfolio":
                client_info['subscriptions'].discard('portfolio')
                if "portfolio" in background_tasks:
                    background_tasks["portfolio"].cancel()
                    del background_tasks["portfolio"]

            elif message_type == "pong":
                client_info['last_ping'] = time.time()

            elif message_type == "ping":
                await ws_manager.broadcast_message(
                    {"type": "pong", "timestamp": time.time()},
                    subscription_filter=None
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        # Cancel all background tasks for this client
        for task_name, task in background_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logging.warning(f"Error cancelling {task_name} task for client {client_id}: {e}")

        # Remove client from manager
        await ws_manager.remove_client(client_id)


async def send_realtime_signals(ws_manager: WebSocketClientManager, client_id: str, symbols: list[str]):
    """Send real-time trading signals to specific client - runs as background task"""
    try:
        while client_id in ws_manager.clients:
            try:
                client_info = ws_manager.clients.get(client_id)
                if not client_info or 'signals' not in client_info.get('subscriptions', set()):
                    break

                for symbol in symbols:
                    # Mock signal generation - in production this would be event-driven
                    signal_data = {
                        "type": "signal_update",
                        "data": {
                            "symbol": symbol,
                            "signal_type": "hold",
                            "confidence": 0.5,
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    await ws_manager.broadcast_message(signal_data, subscription_filter='signals')

                await asyncio.sleep(60)  # Send updates every minute

            except Exception as e:
                logging.error(f"Error in periodic signal updates: {e}")
                break
    except asyncio.CancelledError:
        logging.info(f"Signal updates cancelled for client {client_id}")
        raise
    except Exception as e:
        logging.error(f"Error setting up realtime signals: {e}")


async def send_portfolio_updates(ws_manager: WebSocketClientManager, client_id: str):
    """Send real-time portfolio updates to specific client - runs as background task"""
    try:
        while client_id in ws_manager.clients:
            try:
                client_info = ws_manager.clients.get(client_id)
                if not client_info or 'portfolio' not in client_info.get('subscriptions', set()):
                    break

                portfolio_data = {
                    "type": "portfolio_update",
                    "data": {
                        "total_value": 100000.0,  # Mock data
                        "timestamp": datetime.now().isoformat()
                    }
                }

                await ws_manager.broadcast_message(portfolio_data, subscription_filter='portfolio')
                await asyncio.sleep(30)  # Send updates every 30 seconds

            except Exception as e:
                logging.error(f"Error in periodic portfolio updates: {e}")
                break
    except asyncio.CancelledError:
        logging.info(f"Portfolio updates cancelled for client {client_id}")
        raise
    except Exception as e:
        logging.error(f"Error setting up portfolio updates: {e}")


# Protected Trading Endpoints with Outbox Pattern
@app.post("/api/v1/orders/submit",
         response_model=OrderSubmissionResponse if PYDANTIC_AVAILABLE else dict[str, Any],
         tags=["Trading", "Protected", "Outbox"])
async def submit_order(
    request: OrderSubmissionRequest,
    current_user: AuthenticatedUser = Depends(require_trader),
    order_service: OrderService = Depends(get_order_service),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """
    Submit an order with exactly-once guarantees using transactional outbox pattern.

    Features:
    - Atomic order creation and outbox enqueuing
    - Idempotency protection via client_order_id
    - Background side-effect processing
    - Complete audit trail
    - Risk management validation
    """
    try:
        # Validate trade parameters
        if request.side.lower() not in ["buy", "sell"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Side must be 'buy' or 'sell'"
            )

        if request.qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be positive"
            )

        # Risk management check
        risk_check = risk_manager.check_trade_risk(
            request.symbol,
            request.side.upper(),
            request.qty
        )
        if not risk_check.get("allowed", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Order rejected by risk management: {risk_check.get('reason')}"
            )

        # Audit order request
        audit_logger.info(
            "Order submission requested via outbox",
            extra={
                "user": current_user.username,
                "symbol": request.symbol,
                "side": request.side,
                "qty": request.qty,
                "order_type": request.order_type,
                "time_in_force": request.time_in_force,
                "limit_price": request.limit_price,
                "stop_price": request.stop_price,
                "client_order_id": request.client_order_id,
                "idempotency_key": request.idempotency_key,
                "timestamp": datetime.now().isoformat()
            }
        )

        # Submit order transactionally via service layer
        result = await order_service.submit_order_transactionally(
            symbol=request.symbol,
            side=request.side,
            qty=request.qty,
            order_type=request.order_type,
            tif=request.time_in_force,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            client_order_id=request.client_order_id,
            idempotency_key=request.idempotency_key
        )

        # Audit successful submission
        audit_logger.info(
            "Order submitted successfully via outbox",
            extra={
                "user": current_user.username,
                "order_id": result["order_id"],
                "client_order_id": result["client_order_id"],
                "outbox_event_id": result.get("outbox_event_id"),
                "submission_mode": result["submission_mode"],
                "timestamp": datetime.now().isoformat()
            }
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order submission failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order submission failed"
        )


@app.get("/api/v1/orders/{order_id}",
         response_model=OrderStatusResponse if PYDANTIC_AVAILABLE else dict[str, Any],
         tags=["Trading", "Protected", "Outbox"])
async def get_order_status(
    order_id: str,
    current_user: AuthenticatedUser = Depends(require_trader),
    order_service: OrderService = Depends(get_order_service)
):
    """Get current order status and details."""
    try:
        order_status = await order_service.get_order_status(order_id)

        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order not found: {order_id}"
            )

        return order_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order status"
        )


@app.post("/api/v1/orders/{order_id}/cancel",
          tags=["Trading", "Protected", "Outbox"])
async def cancel_order(
    order_id: str,
    idempotency_key: str | None = None,
    current_user: AuthenticatedUser = Depends(require_trader),
    order_service: OrderService = Depends(get_order_service)
):
    """Cancel an order with outbox pattern for exactly-once cancellation."""
    try:
        # Audit cancellation request
        audit_logger.info(
            "Order cancellation requested",
            extra={
                "user": current_user.username,
                "order_id": order_id,
                "idempotency_key": idempotency_key,
                "timestamp": datetime.now().isoformat()
            }
        )

        result = await order_service.cancel_order(
            order_id,
            idempotency_key=idempotency_key
        )

        # Audit cancellation result
        audit_logger.info(
            "Order cancellation processed",
            extra={
                "user": current_user.username,
                "order_id": order_id,
                "cancellation_mode": result.get("cancellation_mode"),
                "status": result.get("status"),
                "timestamp": datetime.now().isoformat()
            }
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order cancellation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order cancellation failed"
        )


# Legacy Trading Endpoint (deprecated - kept for backward compatibility)
@app.post("/api/v1/trades/execute", tags=["Trading", "Protected", "Deprecated"])
async def execute_trade_legacy(
    symbol: str,
    action: str,  # "BUY" or "SELL"
    quantity: int,
    order_type: str = "market",  # "market", "limit"
    limit_price: float | None = None,
    current_user: AuthenticatedUser = Depends(require_trader),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """Execute a trade order (DEPRECATED - use /api/v1/orders/submit instead)"""
    try:
        # Validate trade parameters
        if action not in ["BUY", "SELL"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'BUY' or 'SELL'"
            )

        if quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be positive"
            )

        # Risk management check
        risk_check = risk_manager.check_trade_risk(symbol, action, quantity)
        if not risk_check.get("allowed", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Trade rejected by risk management: {risk_check.get('reason')}"
            )

        # Audit trade request
        audit_logger.info(
            "Legacy trade execution requested",
            extra={
                "user": current_user.username,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "timestamp": datetime.now().isoformat()
            }
        )

        # Mock trade execution (replace with real Alpaca integration)
        trade_result = {
            "trade_id": f"trade_{int(time.time())}",
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "order_type": order_type,
            "status": "submitted",
            "timestamp": datetime.now().isoformat(),
            "executed_by": current_user.username,
            "note": "DEPRECATED: Please use /api/v1/orders/submit for new integrations"
        }

        return trade_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trade execution failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trade execution failed"
        )


@app.get("/api/v1/trades/history", tags=["Trading", "Protected"])
async def get_trade_history(
    limit: int = 50,
    offset: int = 0,
    current_user: AuthenticatedUser = Depends(require_trader),
):
    """Get trade history (requires trader or admin role)"""
    # Mock trade history - replace with real data access
    trades = [
        {
            "trade_id": f"trade_{i}",
            "symbol": ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"][i % 5],
            "action": ["BUY", "SELL"][i % 2],
            "quantity": (i + 1) * 10,
            "price": 100.0 + i,
            "timestamp": (datetime.now() - timedelta(days=i)).isoformat(),
            "status": "executed"
        }
        for i in range(limit)
    ]

    return {
        "trades": trades[offset:offset + limit],
        "total": len(trades),
        "limit": limit,
        "offset": offset
    }


# Protected Model Management Endpoints
@app.post("/api/v1/models/train", tags=["ML Models", "Protected"])
async def trigger_model_training(
    model_type: str = "ensemble",
    retrain_all: bool = False,
    current_user: AuthenticatedUser = Depends(require_admin),
    model_manager: ModelManager = Depends(get_model_manager),
):
    """Trigger model training (requires admin role)"""
    try:
        # Audit model training request
        audit_logger.info(
            "Model training triggered",
            extra={
                "user": current_user.username,
                "model_type": model_type,
                "retrain_all": retrain_all,
                "timestamp": datetime.now().isoformat()
            }
        )

        # Trigger training (mock implementation)
        training_job = {
            "job_id": f"training_{int(time.time())}",
            "model_type": model_type,
            "status": "started",
            "started_by": current_user.username,
            "timestamp": datetime.now().isoformat()
        }

        return training_job

    except Exception as e:
        logger.error(f"Model training trigger failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger model training"
        )


@app.get("/api/v1/models/status", tags=["ML Models", "Protected"])
async def get_model_status(
    current_user: AuthenticatedUser = Depends(require_trader),
    model_manager: ModelManager = Depends(get_model_manager),
):
    """Get model training and deployment status (requires trader or admin role)"""
    # Mock model status - replace with real model manager integration
    return {
        "models": [
            {
                "name": "ensemble_model",
                "version": "1.0.0",
                "status": "deployed",
                "accuracy": 0.85,
                "last_trained": datetime.now().isoformat(),
                "predictions_today": 1250
            },
            {
                "name": "sentiment_model",
                "version": "1.2.0",
                "status": "training",
                "progress": 0.65,
                "eta_minutes": 15
            }
        ],
        "timestamp": datetime.now().isoformat()
    }


# Protected Risk Management Endpoints
@app.put("/api/v1/risk/limits", tags=["Risk Management", "Protected"])
async def update_risk_limits(
    max_position_size: float | None = None,
    max_daily_loss: float | None = None,
    max_portfolio_risk: float | None = None,
    current_user: AuthenticatedUser = Depends(require_admin),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """Update risk management limits (requires admin role)"""
    try:
        updates = {}
        if max_position_size is not None:
            updates["max_position_size"] = max_position_size
        if max_daily_loss is not None:
            updates["max_daily_loss"] = max_daily_loss
        if max_portfolio_risk is not None:
            updates["max_portfolio_risk"] = max_portfolio_risk

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No updates provided"
            )

        # Audit risk limits update
        audit_logger.warning(
            "Risk limits updated",
            extra={
                "user": current_user.username,
                "updates": updates,
                "timestamp": datetime.now().isoformat()
            }
        )

        # Apply updates (mock implementation)
        result = {
            "updated_limits": updates,
            "updated_by": current_user.username,
            "timestamp": datetime.now().isoformat(),
            "status": "applied"
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Risk limits update failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update risk limits"
        )


@app.get("/api/v1/risk/metrics", tags=["Risk Management", "Protected"])
async def get_risk_metrics(
    current_user: AuthenticatedUser = Depends(require_trader),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """Get current risk metrics (requires trader or admin role)"""
    # Mock risk metrics - replace with real risk manager integration
    return {
        "portfolio_risk": {
            "current_exposure": 0.65,
            "max_allowed_exposure": 0.8,
            "var_1d": -2500.0,
            "var_5d": -8500.0
        },
        "position_limits": {
            "max_position_size": 10000.0,
            "current_max_position": 7500.0,
            "utilization": 0.75
        },
        "daily_pnl": {
            "current": 1250.0,
            "max_allowed_loss": -5000.0,
            "remaining_risk_budget": 6250.0
        },
        "timestamp": datetime.now().isoformat()
    }


# B2.7 - Strategy Engine API Endpoints

# Request/Response models for strategy endpoints
class StrategySignalRequest(BaseModel):
    """Request model for submitting strategy signals"""
    symbol: str = Field(..., description="Trading symbol", example="AAPL")
    source: str = Field(..., description="Strategy source", example="momentum")
    target_exposure: float = Field(..., ge=-1.0, le=1.0, description="Target exposure [-1,1]", example=0.5)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence [0,1]", example=0.8)


class StrategySignalResponse(BaseModel):
    """Response model for strategy signal submission"""
    signal_id: str = Field(..., description="Unique signal identifier")
    accepted: bool = Field(..., description="Whether signal was accepted")
    execution_plan: dict[str, Any] | None = Field(None, description="Generated execution plan if accepted")
    reason: str | None = Field(None, description="Reason if rejected")


class ExecutionPlanResponse(BaseModel):
    """Response model for execution plan requests"""
    plans: list[dict[str, Any]] = Field(..., description="List of execution plans")
    netted_signals: dict[str, Any] = Field(..., description="Netted signal data")
    timestamp: str = Field(..., description="Generation timestamp")


@app.post("/api/v1/strategy/signals/submit",
          response_model=StrategySignalResponse,
          tags=["Strategy Engine", "Protected"])
async def submit_strategy_signal(
    request: StrategySignalRequest,
    strategy_engine: StrategyEngine = Depends(get_strategy_engine),
    current_user: dict[str, Any] = Depends(require_roles(["trader", "admin"]))
) -> StrategySignalResponse:
    """
    Submit a trading signal to the strategy engine.
    Requires trader or admin role.
    """
    try:
        # Create strategy signal
        signal = StrategySignal(
            symbol=request.symbol,
            source=request.source,
            ts=datetime.now(),
            target_exposure=request.target_exposure,
            confidence=request.confidence
        )

        # Submit to strategy engine
        execution_plans = await strategy_engine.generate_and_gate([signal])

        if execution_plans:
            plan = execution_plans[0]
            return StrategySignalResponse(
                signal_id=f"{request.symbol}_{request.source}_{int(signal.ts.timestamp())}",
                accepted=True,
                execution_plan={
                    "symbol": plan.symbol,
                    "side": plan.side.value,
                    "qty": plan.qty,
                    "notional": plan.notional,
                    "reason": plan.reason,
                    "risk_allowed": plan.risk_allowed
                }
            )
        else:
            return StrategySignalResponse(
                signal_id=f"{request.symbol}_{request.source}_{int(signal.ts.timestamp())}",
                accepted=False,
                reason="Signal rejected by strategy engine (throttled or risk blocked)"
            )

    except Exception as e:
        logger.error(f"Error submitting strategy signal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit strategy signal: {str(e)}"
        )


@app.post("/api/v1/strategy/signals/batch",
          response_model=ExecutionPlanResponse,
          tags=["Strategy Engine", "Protected"])
async def submit_strategy_signals_batch(
    signals: list[StrategySignalRequest],
    strategy_engine: StrategyEngine = Depends(get_strategy_engine),
    current_user: dict[str, Any] = Depends(require_roles(["trader", "admin"]))
) -> ExecutionPlanResponse:
    """
    Submit multiple trading signals for netting and execution planning.
    Requires trader or admin role.
    """
    try:
        # Convert requests to strategy signals
        strategy_signals = []
        for req in signals:
            signal = StrategySignal(
                symbol=req.symbol,
                source=req.source,
                ts=datetime.now(),
                target_exposure=req.target_exposure,
                confidence=req.confidence
            )
            strategy_signals.append(signal)

        # Generate execution plans
        execution_plans = await strategy_engine.generate_and_gate(strategy_signals)

        # Convert execution plans to response format
        plan_dicts = []
        for plan in execution_plans:
            plan_dicts.append({
                "symbol": plan.symbol,
                "side": plan.side.value,
                "qty": plan.qty,
                "notional": plan.notional,
                "from_exposure": plan.from_exposure,
                "to_exposure": plan.to_exposure,
                "reason": plan.reason,
                "risk_allowed": plan.risk_allowed,
                "risk_reason": plan.risk_reason
            })

        # Get netted signals for debugging
        netted_signals = {}
        symbols_processed = list(set(s.symbol for s in strategy_signals))
        for symbol in symbols_processed:
            symbol_signals = [s for s in strategy_signals if s.symbol == symbol]
            if symbol_signals:
                # Calculate weighted average for display
                total_weight = sum(s.confidence for s in symbol_signals)
                if total_weight > 0:
                    weighted_exposure = sum(s.target_exposure * s.confidence for s in symbol_signals) / total_weight
                    netted_signals[symbol] = {
                        "target_exposure": max(-1.0, min(1.0, weighted_exposure)),
                        "signal_count": len(symbol_signals),
                        "total_confidence": total_weight
                    }

        return ExecutionPlanResponse(
            plans=plan_dicts,
            netted_signals=netted_signals,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error processing strategy signals batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process strategy signals: {str(e)}"
        )


@app.get("/api/v1/strategy/status",
         response_model=dict[str, Any],
         tags=["Strategy Engine", "Protected"])
async def get_strategy_engine_status(
    strategy_engine: StrategyEngine = Depends(get_strategy_engine),
    current_user: dict[str, Any] = Depends(require_admin)
) -> dict[str, Any]:
    """
    Get strategy engine status and configuration.
    Requires admin role.
    """
    try:
        return {
            "status": "active",
            "config": {
                "strategy_weights": strategy_engine.strategy_weights,
                "min_flip_interval_s": strategy_engine.min_flip_interval_s,
                "max_new_risk_per_bar": strategy_engine.max_new_risk_per_bar,
                "min_notional": strategy_engine.min_notional
            },
            "throttle_state": {
                "tracked_positions": len(strategy_engine._position_flip_times),
                "note": "Detailed throttle state available in metrics"
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting strategy engine status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get strategy engine status: {str(e)}"
        )


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logging.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
