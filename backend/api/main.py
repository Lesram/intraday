"""
FastAPI Gateway - Main API Server with Lifespan and Dependency Injection
Provides REST and WebSocket endpoints for the algorithmic trading platform
"""

import asyncio
import json
import logging
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ValidationError

# Prometheus imports
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
    
    # Prometheus metrics
    REQUEST_COUNT = Counter(
        'http_requests_total', 
        'Total HTTP requests', 
        ['method', 'endpoint', 'status']
    )
    REQUEST_DURATION = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration',
        ['method', 'endpoint']
    )
    WS_CONNECTIONS = Counter(
        'websocket_connections_total',
        'Total WebSocket connections',
        ['client_type']
    )
    WS_MESSAGES = Counter(
        'websocket_messages_total',
        'WebSocket messages sent/received',
        ['direction', 'message_type']
    )
    WS_QUEUE_SIZE = Gauge(
        'websocket_queue_size',
        'Current WebSocket queue size',
        ['client_id']
    )
    WS_MESSAGES_DROPPED = Counter(
        'websocket_messages_dropped_total',
        'WebSocket messages dropped due to backpressure',
        ['client_id', 'reason']
    )
    WS_SUBSCRIBER_TIMEOUTS = Counter(
        'websocket_subscriber_timeouts_total',
        'WebSocket subscriber timeouts',
        ['client_id']
    )
    
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
from ..config import get_settings
from ..data.alpaca_client import AlpacaClient
from ..data.social_sentiment import SocialSentimentAnalyzer
from ..features.feature_engineering import FeatureEngineer
from ..mlops.model_manager import ModelManager
from ..models.ensemble_model import EnsembleModel, ModelPrediction
from ..risk.risk_manager import RiskManager
from ..strategies.trading_strategies import SignalType, StrategyManager, TradingSignal
from backend.utils.logger import get_logger, audit_logger

# Authentication imports
from backend.infra.security import (
    AuthenticatedUser,
    create_access_token,
    get_authenticated_user,
    get_current_user,
    require_admin,
    require_trader,
    require_roles
)
from backend.infra.users import get_user_repository

# Structured error models for API responses
class ErrorDetail(BaseModel):
    """Detailed error information"""
    code: str
    message: str
    context: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    """Standardized error response structure"""
    error: ErrorDetail
    timestamp: str
    request_id: Optional[str] = None
    
class ValidationErrorResponse(BaseModel):
    """Validation error response with field details"""
    error: ErrorDetail
    validation_errors: List[Dict[str, Any]]
    timestamp: str
    request_id: Optional[str] = None

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
    price: Optional[float] = None
    timestamp: str
    features: Optional[Dict[str, Any]] = None

class SystemStatusResponse(BaseModel):
    """System status API response"""
    status: str
    timestamp: str
    uptime_seconds: int
    version: str
    environment: str
    components: Dict[str, Any]
    background_tasks: Dict[str, Any]
    warnings: List[str]
    metrics: Dict[str, Any]

class HealthCheckResponse(BaseModel):
    """Health check API response"""
    status: str
    timestamp: str
    components: Dict[str, bool]


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
    user: Dict[str, Any]


class TokenValidationResponse(BaseModel):
    """Token validation response"""
    valid: bool
    user: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None


# WebSocket client manager
class WebSocketClientManager:
    """Manages WebSocket clients with backpressure and heartbeat"""
    
    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.clients: Dict[str, Dict[str, Any]] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def add_client(self, client_id: str, websocket: WebSocket) -> None:
        """Add a new WebSocket client with bounded queue"""
        message_queue = asyncio.Queue(maxsize=self.max_queue_size)
        
        self.clients[client_id] = {
            'websocket': websocket,
            'queue': message_queue,
            'last_ping': time.time(),
            'subscriptions': set(),
            'send_task': None
        }
        
        # Start message sender task for this client
        send_task = asyncio.create_task(
            self._message_sender(client_id)
        )
        self.clients[client_id]['send_task'] = send_task
        
        if PROMETHEUS_AVAILABLE:
            WS_CONNECTIONS.labels(client_type='trading').inc()
        
        audit_logger.info("websocket_client_added", client_id=client_id)
        
    async def remove_client(self, client_id: str) -> None:
        """Remove WebSocket client and cleanup resources"""
        if client_id in self.clients:
            client_info = self.clients[client_id]
            
            # Cancel send task
            if client_info['send_task']:
                client_info['send_task'].cancel()
                try:
                    await client_info['send_task']
                except asyncio.CancelledError:
                    pass
            
            # Close websocket
            try:
                await client_info['websocket'].close()
            except Exception:
                pass
                
            del self.clients[client_id]
            audit_logger.info("websocket_client_removed", client_id=client_id)
    
    async def broadcast_message(self, message: Dict[str, Any], subscription_filter: Optional[str] = None) -> None:
        """Broadcast message to subscribed clients with backpressure handling"""
        for client_id, client_info in self.clients.items():
            if subscription_filter and subscription_filter not in client_info['subscriptions']:
                continue
                
            try:
                # Update queue size metric
                if PROMETHEUS_AVAILABLE:
                    WS_QUEUE_SIZE.labels(client_id=client_id).set(client_info['queue'].qsize())
                
                # Non-blocking put with backpressure policy
                client_info['queue'].put_nowait(message)
            except asyncio.QueueFull:
                # Drop oldest message to make room (backpressure policy)
                try:
                    client_info['queue'].get_nowait()
                    client_info['queue'].put_nowait(message)
                    logging.warning(f"Queue full for client {client_id}, dropped old message")
                    
                    # Update metrics
                    if PROMETHEUS_AVAILABLE:
                        WS_MESSAGES_DROPPED.labels(client_id=client_id, reason='queue_full').inc()
                        
                except asyncio.QueueEmpty:
                    # Queue became empty between checks, just put the message
                    client_info['queue'].put_nowait(message)
                    pass
                    
    async def _message_sender(self, client_id: str) -> None:
        """Send messages from queue to WebSocket client"""
        client_info = self.clients.get(client_id)
        if not client_info:
            return
            
        websocket = client_info['websocket']
        queue = client_info['queue']
        
        try:
            while True:
                message = await queue.get()
                await websocket.send_text(json.dumps(message))
                
                if PROMETHEUS_AVAILABLE:
                    WS_MESSAGES.labels(direction='sent', message_type=message.get('type', 'unknown')).inc()
                    
                queue.task_done()
                
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logging.error(f"Error sending message to client {client_id}: {e}")
            await self.remove_client(client_id)
    
    async def start_heartbeat(self) -> None:
        """Start heartbeat task"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
    async def stop_heartbeat(self) -> None:
        """Stop heartbeat task"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
                
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to all clients"""
        while True:
            try:
                current_time = time.time()
                ping_message = {"type": "ping", "timestamp": current_time}
                
                # Send heartbeat and check for stale connections
                stale_clients = []
                for client_id, client_info in self.clients.items():
                    # Check if client is stale (no pong for 60 seconds)
                    if current_time - client_info['last_ping'] > 60:
                        stale_clients.append(client_id)
                        
                        # Track timeout in metrics
                        if PROMETHEUS_AVAILABLE:
                            WS_SUBSCRIBER_TIMEOUTS.labels(client_id=client_id).inc()
                        continue
                        
                    try:
                        client_info['queue'].put_nowait(ping_message)
                    except asyncio.QueueFull:
                        # Client can't keep up, mark as stale
                        stale_clients.append(client_id)
                        
                        # Track queue full timeout
                        if PROMETHEUS_AVAILABLE:
                            WS_SUBSCRIBER_TIMEOUTS.labels(client_id=client_id).inc()
                
                # Remove stale clients
                for client_id in stale_clients:
                    await self.remove_client(client_id)
                    
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(30)

# Global WebSocket manager
ws_manager = WebSocketClientManager()

if PYDANTIC_AVAILABLE:
    # Pydantic models for API
    class TradingSignalResponse(BaseModel):
        symbol: str
        signal_type: str
        confidence: float
        target_price: float
        position_size: float
        timestamp: str
        metadata: Dict[str, Any] = {}

    class TechnicalFeatures(BaseModel):
        rsi: Optional[float] = None
        macd: Optional[float] = None
        bb_position: Optional[float] = None
        volume_ratio: Optional[float] = None

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
        metadata: Dict[str, Any] = {}
        authenticated: bool
        technical_features: Optional[TechnicalFeatures] = None
        risk_assessment: Optional[RiskAssessment] = None
        
    class AdvancedSignalsMetadata(BaseModel):
        timestamp: str
        authenticated: bool
        symbols_requested: int
        symbols_processed: int
        features_included: bool
        risk_metrics_included: bool
        
    class AdvancedSignalsResponse(BaseModel):
        signals: Dict[str, AdvancedSignalResponse]
        metadata: AdvancedSignalsMetadata

    class ModelPredictionResponse(BaseModel):
        symbol: str
        ensemble_prediction: float
        ensemble_confidence: float
        individual_predictions: Dict[str, float]
        timestamp: str

    class PortfolioStatus(BaseModel):
        total_value: float
        cash: float
        positions: Dict[str, Any]
        daily_pnl: float
        total_pnl: float
        risk_metrics: Dict[str, float]

    class MarketDataRequest(BaseModel):
        symbols: List[str]
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
        symbols: List[str]
        training_period_days: int = 30
        retrain_existing: bool = False

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
        
        # Initialize core components and store in app.state
        logging.info("Initializing AlpacaClient...")
        # Initialize AlpacaClient with test mode for dummy credentials
        api_key = settings.alpaca_api_key or "dummy_key_for_testing"
        secret_key = settings.alpaca_secret_key or "dummy_secret_for_testing"
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
        
        # Initialize WebSocket manager
        app.state.ws_manager = ws_manager
        
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

    # Shutdown
    logging.info("Shutting down algorithmic trading platform...")
    
    shutdown_tasks = []
    
    try:
        # Cancel all tracked background tasks first
        if hasattr(app.state, 'background_tasks'):
            for task_name, task in app.state.background_tasks.items():
                if not task.done():
                    logging.info(f"Cancelling background task: {task_name}")
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        logging.warning(f"Task {task_name} cancellation completed")
                    except Exception as e:
                        logging.error(f"Error cancelling task {task_name}: {e}")
        
        # Stop WebSocket manager
        if hasattr(app.state, 'ws_manager'):
            shutdown_tasks.append(asyncio.create_task(app.state.ws_manager.stop_heartbeat()))
            
            # Disconnect all WebSocket clients
            for client_id in list(app.state.ws_manager.clients.keys()):
                shutdown_tasks.append(asyncio.create_task(app.state.ws_manager.remove_client(client_id)))
        
        # Stop market data stream
        if hasattr(app.state, 'alpaca_client') and app.state.alpaca_client:
            shutdown_tasks.append(asyncio.create_task(cleanup_alpaca_client(app.state.alpaca_client)))
        
        # Flush audit logs
        shutdown_tasks.append(asyncio.create_task(flush_audit_logs()))
        
        # Wait for shutdown tasks with timeout
        if shutdown_tasks:
            await asyncio.wait_for(
                asyncio.gather(*shutdown_tasks, return_exceptions=True),
                timeout=10.0
            )
        
        audit_logger.info("trading_platform_shutdown", 
                         timestamp=datetime.now(),
                         background_tasks_cancelled=len(background_tasks))
        logging.info("Trading platform shutdown completed")
        
    except asyncio.TimeoutError:
        logging.warning("Shutdown tasks did not complete within timeout")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}", exc_info=True)


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


# Create FastAPI app
app = FastAPI(
    title="Algorithmic Trading Platform API",
    description="Institutional-grade algorithmic trading platform with AI/ML capabilities",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing and logging middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """Add request timing and logging for observability"""
    start_time = time.time()
    request_id = generate_request_id()
    
    # Add request ID to headers for tracing
    request.state.request_id = request_id
    
    # Log request start
    logger.info(f"Request started: {request.method} {request.url.path}", 
               extra={
                   "request_id": request_id,
                   "method": request.method,
                   "path": request.url.path,
                   "client_ip": request.client.host if request.client else None
               })
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate timing
        process_time = time.time() - start_time
        
        # Add timing headers
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        
        # Log response
        logger.info(f"Request completed: {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)",
                   extra={
                       "request_id": request_id,
                       "method": request.method,
                       "path": request.url.path,
                       "status_code": response.status_code,
                       "process_time": process_time
                   })
        
        # Update Prometheus metrics if available
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(process_time)
        
        return response
        
    except Exception as e:
        # Log error
        process_time = time.time() - start_time
        logger.error(f"Request failed: {request.method} {request.url.path} - {str(e)} ({process_time:.3f}s)",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(e),
                        "process_time": process_time
                    })
        
        # Re-raise to let error handlers process
        raise

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


# Middleware for Prometheus metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics"""
    if not PROMETHEUS_AVAILABLE:
        return await call_next(request)
    
    start_time = time.time()
    method = request.method
    endpoint = request.url.path
    
    response = await call_next(request)
    
    # Record metrics
    duration = time.time() - start_time
    status = str(response.status_code)
    
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    
    return response


# Prometheus metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Prometheus not available")
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
        expires_in = settings.jwt_access_token_expire_minutes * 60  # Convert to seconds
        
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
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user)
):
    """Validate the provided JWT token"""
    if not current_user:
        return TokenValidationResponse(valid=False)
    
    # Calculate token expiration (approximate, since we don't store it)
    settings = get_settings()
    expires_at = (
        datetime.now() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
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


@app.get("/auth/me", response_model=Dict[str, Any], tags=["Authentication"])
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
    import time
    
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


@app.get("/api/v1/signals", response_model=Dict[str, SignalResponse], tags=["Trading Signals"])
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
@app.get("/api/v1/signals/advanced", response_model=AdvancedSignalsResponse if PYDANTIC_AVAILABLE else Dict[str, Any], tags=["Trading Signals", "Protected"])
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

            if PROMETHEUS_AVAILABLE:
                WS_MESSAGES.labels(direction='received', message_type=message.get('type', 'unknown')).inc()

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


async def send_realtime_signals(ws_manager: WebSocketClientManager, client_id: str, symbols: List[str]):
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


# Protected Trading Endpoints
@app.post("/api/v1/trades/execute", tags=["Trading", "Protected"])
async def execute_trade(
    symbol: str,
    action: str,  # "BUY" or "SELL"
    quantity: int,
    order_type: str = "market",  # "market", "limit"
    limit_price: Optional[float] = None,
    current_user: AuthenticatedUser = Depends(require_trader),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """Execute a trade order (requires trader or admin role)"""
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
            "Trade execution requested",
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
            "executed_by": current_user.username
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
    max_position_size: Optional[float] = None,
    max_daily_loss: Optional[float] = None,
    max_portfolio_risk: Optional[float] = None,
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
