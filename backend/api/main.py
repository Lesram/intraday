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
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from ..utils.logger import audit_logger, performance_logger

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
    startup_tasks = []
    
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
        
        # Start background tasks
        logging.info("Starting market data stream...")
        startup_tasks.append(asyncio.create_task(start_market_data_stream(app)))
        
        logging.info("Starting WebSocket heartbeat...")
        startup_tasks.append(asyncio.create_task(app.state.ws_manager.start_heartbeat()))
        
        # Wait for critical services to be ready
        await asyncio.sleep(1)  # Give services time to initialize
        
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
                         })
        
        logging.info("Trading platform startup completed successfully")
        
        yield

    except Exception as e:
        logging.error(f"Error during startup: {e}", exc_info=True)
        # Cancel any running startup tasks
        for task in startup_tasks:
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
        
        audit_logger.info("trading_platform_shutdown", timestamp=datetime.now())
        logging.info("Trading platform shutdown completed")
        
    except asyncio.TimeoutError:
        logging.warning("Shutdown tasks did not complete within timeout")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}", exc_info=True)


async def start_market_data_stream(app: FastAPI):
    """Start real-time market data streaming"""
    if hasattr(app.state, 'alpaca_client') and app.state.alpaca_client:
        try:
            # Get default symbols from settings
            settings = get_settings()
            symbols = settings.default_symbols
            await app.state.alpaca_client.connect_data_stream(symbols=symbols)
            logging.info(f"Market data stream started successfully for symbols: {symbols}")
        except Exception as e:
            logging.error(f"Error starting market data stream: {e}")


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


# Health check endpoint
@app.get("/health")
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


# Trading Signals Endpoints
@app.get("/api/v1/signals/{symbol}")
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
            )
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


@app.get("/api/v1/signals")
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
                        ).dict()
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
    """WebSocket endpoint for real-time trading data with backpressure handling"""
    await websocket.accept()
    await ws_manager.add_client(client_id, websocket)
    
    # Track background tasks for this client
    background_tasks = {}

    try:
        while True:
            # Wait for client message
            data = await websocket.receive_text()
            message = json.loads(data)

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
