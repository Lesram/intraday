"""
FastAPI Gateway - Main API Server
Provides REST and WebSocket endpoints for the algorithmic trading platform
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import logging
import time
from typing import Any

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
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    PROMETHEUS_AVAILABLE = True

    # Prometheus metrics
    REQUEST_COUNT = Counter(
        "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
    )
    REQUEST_DURATION = Histogram(
        "http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"]
    )
    WS_CONNECTIONS = Counter(
        "websocket_connections_total", "Total WebSocket connections", ["client_type"]
    )
    WS_MESSAGES = Counter(
        "websocket_messages_total",
        "WebSocket messages sent/received",
        ["direction", "message_type"],
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
from ..models.ensemble_model import EnsembleModel
from ..risk.risk_manager import RiskManager
from ..strategies.trading_strategies import StrategyManager
from ..utils.logger import audit_logger


# WebSocket client manager
class WebSocketClientManager:
    """Manages WebSocket clients with backpressure and heartbeat"""

    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.clients: dict[str, dict[str, Any]] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    async def add_client(self, client_id: str, websocket: WebSocket) -> None:
        """Add a new WebSocket client with bounded queue"""
        message_queue = asyncio.Queue(maxsize=self.max_queue_size)

        self.clients[client_id] = {
            "websocket": websocket,
            "queue": message_queue,
            "last_ping": time.time(),
            "subscriptions": set(),
            "send_task": None,
        }

        # Start message sender task for this client
        send_task = asyncio.create_task(self._message_sender(client_id))
        self.clients[client_id]["send_task"] = send_task

        if PROMETHEUS_AVAILABLE:
            WS_CONNECTIONS.labels(client_type="trading").inc()

        audit_logger.info("websocket_client_added", client_id=client_id)

    async def remove_client(self, client_id: str) -> None:
        """Remove WebSocket client and cleanup resources"""
        if client_id in self.clients:
            client_info = self.clients[client_id]

            # Cancel send task
            if client_info["send_task"]:
                client_info["send_task"].cancel()
                try:
                    await client_info["send_task"]
                except asyncio.CancelledError:
                    pass

            # Close websocket
            try:
                await client_info["websocket"].close()
            except Exception:
                pass

            del self.clients[client_id]
            audit_logger.info("websocket_client_removed", client_id=client_id)

    async def broadcast_message(
        self, message: dict[str, Any], subscription_filter: str | None = None
    ) -> None:
        """Broadcast message to subscribed clients with backpressure handling"""
        for client_id, client_info in self.clients.items():
            if subscription_filter and subscription_filter not in client_info["subscriptions"]:
                continue

            try:
                # Non-blocking put with backpressure policy
                client_info["queue"].put_nowait(message)
            except asyncio.QueueFull:
                # Drop oldest message to make room (backpressure policy)
                try:
                    client_info["queue"].get_nowait()
                    client_info["queue"].put_nowait(message)
                    logging.warning(f"Queue full for client {client_id}, dropped old message")
                except asyncio.QueueEmpty:
                    pass

    async def _message_sender(self, client_id: str) -> None:
        """Send messages from queue to WebSocket client"""
        client_info = self.clients.get(client_id)
        if not client_info:
            return

        websocket = client_info["websocket"]
        queue = client_info["queue"]

        try:
            while True:
                message = await queue.get()
                await websocket.send_text(json.dumps(message))

                if PROMETHEUS_AVAILABLE:
                    WS_MESSAGES.labels(
                        direction="sent", message_type=message.get("type", "unknown")
                    ).inc()

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
                    if current_time - client_info["last_ping"] > 60:
                        stale_clients.append(client_id)
                        continue

                    try:
                        client_info["queue"].put_nowait(ping_message)
                    except asyncio.QueueFull:
                        # Client can't keep up, mark as stale
                        stale_clients.append(client_id)

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
        metadata: dict[str, Any] = {}

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
        app.state.alpaca_client = AlpacaClient()

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
            app.state.risk_manager, app.state.ensemble_model
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

        audit_logger.info(
            "trading_platform_started",
            timestamp=datetime.now(),
            components={
                "alpaca_client": True,
                "sentiment_analyzer": True,
                "feature_engineer": True,
                "model_manager": True,
                "ensemble_model": True,
                "risk_manager": True,
                "strategy_manager": True,
            },
        )

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
        if hasattr(app.state, "ws_manager"):
            shutdown_tasks.append(asyncio.create_task(app.state.ws_manager.stop_heartbeat()))

            # Disconnect all WebSocket clients
            for client_id in list(app.state.ws_manager.clients.keys()):
                shutdown_tasks.append(
                    asyncio.create_task(app.state.ws_manager.remove_client(client_id))
                )

        # Stop market data stream
        if hasattr(app.state, "alpaca_client") and app.state.alpaca_client:
            shutdown_tasks.append(
                asyncio.create_task(cleanup_alpaca_client(app.state.alpaca_client))
            )

        # Flush audit logs
        shutdown_tasks.append(asyncio.create_task(flush_audit_logs()))

        # Wait for shutdown tasks with timeout
        if shutdown_tasks:
            await asyncio.wait_for(
                asyncio.gather(*shutdown_tasks, return_exceptions=True), timeout=10.0
            )

        audit_logger.info("trading_platform_shutdown", timestamp=datetime.now())
        logging.info("Trading platform shutdown completed")

    except TimeoutError:
        logging.warning("Shutdown tasks did not complete within timeout")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}", exc_info=True)


async def start_market_data_stream(app: FastAPI):
    """Start real-time market data streaming"""
    if hasattr(app.state, "alpaca_client") and app.state.alpaca_client:
        try:
            await app.state.alpaca_client.connect_data_stream()
            logging.info("Market data stream started successfully")
        except Exception as e:
            logging.error(f"Error starting market data stream: {e}")


async def cleanup_alpaca_client(alpaca_client: AlpacaClient):
    """Cleanup Alpaca client connections"""
    try:
        await alpaca_client.disconnect()
        logging.info("Alpaca client disconnected successfully")
    except Exception as e:
        logging.error(f"Error stopping market data stream: {e}")


async def flush_audit_logs():
    """Flush any pending audit log entries"""
    try:
        # Force flush audit logger
        for handler in audit_logger.handlers:
            if hasattr(handler, "flush"):
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
            raise HTTPException(status_code=503, detail="Strategy manager not available")

        # Get market data
        if not alpaca_client:
            raise HTTPException(status_code=503, detail="Market data client not available")

        price_data = await alpaca_client.get_historical_data(symbol, timeframe="1Day", limit=100)
        if price_data.empty:
            raise HTTPException(status_code=404, detail="No market data found")

        # Generate features
        features = feature_engineer.compute_all_features(price_data)

        # Generate signal
        signal = await strategy_manager.generate_combined_signal(symbol, price_data, features)

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
async def get_all_signals(symbols: str = "AAPL,GOOGL,MSFT,TSLA,NVDA"):
    """Get trading signals for multiple symbols"""
    try:
        symbol_list = [s.strip() for s in symbols.split(",")]
        signals = {}

        for symbol in symbol_list:
            try:
                # This would ideally be done in parallel
                signal_response = await get_trading_signal(symbol)
                if PYDANTIC_AVAILABLE:
                    signals[symbol] = signal_response.dict()
                else:
                    signals[symbol] = signal_response
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


# Model Prediction Endpoints
@app.get("/api/v1/predictions/{symbol}")
async def get_prediction(
    symbol: str,
    ensemble_model: EnsembleModel = Depends(get_ensemble_model),
    alpaca_client: AlpacaClient = Depends(get_alpaca_client),
    feature_engineer: FeatureEngineer = Depends(get_feature_engineer),
):
    """Get AI model prediction for a symbol"""
    try:
        if not ensemble_model:
            raise HTTPException(status_code=503, detail="Ensemble model not available")

        # Get data
        price_data = await alpaca_client.get_historical_data(symbol, timeframe="1Day", limit=100)
        features = feature_engineer.compute_all_features(price_data)

        # Get prediction
        prediction = ensemble_model.predict(price_data, features, symbol)

        if PYDANTIC_AVAILABLE:
            return ModelPredictionResponse(
                symbol=prediction.symbol,
                ensemble_prediction=prediction.ensemble_prediction,
                ensemble_confidence=prediction.ensemble_confidence,
                individual_predictions=prediction.predictions,
                timestamp=prediction.timestamp.isoformat(),
            )
        else:
            return {
                "symbol": prediction.symbol,
                "ensemble_prediction": prediction.ensemble_prediction,
                "ensemble_confidence": prediction.ensemble_confidence,
                "individual_predictions": prediction.predictions,
                "timestamp": prediction.timestamp.isoformat(),
            }

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error getting prediction for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Portfolio Management Endpoints
@app.get("/api/v1/portfolio/status")
async def get_portfolio_status(
    risk_manager: RiskManager = Depends(get_risk_manager),
):
    """Get current portfolio status"""
    try:
        if not risk_manager:
            raise HTTPException(status_code=503, detail="Risk manager not available")

        portfolio_value = risk_manager.get_portfolio_value()
        positions = risk_manager.get_positions()
        risk_metrics = risk_manager.get_risk_metrics()

        # Calculate P&L (simplified)
        daily_pnl = 0.0
        total_pnl = 0.0

        if PYDANTIC_AVAILABLE:
            return PortfolioStatus(
                total_value=portfolio_value,
                cash=portfolio_value * 0.1,  # Placeholder
                positions=positions,
                daily_pnl=daily_pnl,
                total_pnl=total_pnl,
                risk_metrics=risk_metrics,
            )
        else:
            return {
                "total_value": portfolio_value,
                "cash": portfolio_value * 0.1,
                "positions": positions,
                "daily_pnl": daily_pnl,
                "total_pnl": total_pnl,
                "risk_metrics": risk_metrics,
            }

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error getting portfolio status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Trading Endpoints
@app.post("/api/v1/trades")
async def submit_trade(trade_request: dict):
    """Submit a trade order"""
    try:
        if not app_state["alpaca_client"]:
            raise HTTPException(status_code=503, detail="Trading client not available")

        symbol = trade_request.get("symbol")
        side = trade_request.get("side")
        quantity = trade_request.get("quantity")
        order_type = trade_request.get("order_type", "market")

        if not all([symbol, side, quantity]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Risk check
        if app_state["risk_manager"]:
            risk_check = await app_state["risk_manager"].assess_position_risk(
                symbol, quantity, side
            )
            if not risk_check["approved"]:
                raise HTTPException(
                    status_code=403, detail=f"Trade rejected: {risk_check['reason']}"
                )

        # Submit order
        order = await app_state["alpaca_client"].submit_order(
            symbol=symbol, qty=quantity, side=side, type=order_type, time_in_force="day"
        )

        audit_logger.info(
            "trade_submitted",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_id=order.get("id", "unknown"),
        )

        return {"status": "submitted", "order": order}

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error submitting trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Market Data Endpoints
@app.get("/api/v1/market-data/{symbol}")
async def get_market_data(symbol: str, timeframe: str = "1Day", limit: int = 100):
    """Get historical market data"""
    try:
        if not app_state["alpaca_client"]:
            raise HTTPException(status_code=503, detail="Market data client not available")

        data = await app_state["alpaca_client"].get_historical_data(symbol, timeframe, limit)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": data.to_dict("records") if not data.empty else [],
            "count": len(data),
        }

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error getting market data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Sentiment Analysis Endpoint
@app.get("/api/v1/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    """Get social sentiment for a symbol"""
    try:
        if not app_state["sentiment_analyzer"]:
            raise HTTPException(status_code=503, detail="Sentiment analyzer not available")

        sentiment_data = await app_state["sentiment_analyzer"].get_aggregated_sentiment(symbol)

        return {
            "symbol": symbol,
            "sentiment": sentiment_data,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error getting sentiment for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Model Management Endpoints
@app.post("/api/v1/models/train")
async def train_model(training_request: dict, background_tasks: BackgroundTasks):
    """Train a new model"""
    try:
        model_id = training_request.get("model_id", "default")
        symbols = training_request.get("symbols", ["AAPL"])
        training_days = training_request.get("training_period_days", 30)

        # Start training in background
        background_tasks.add_task(train_model_background, model_id, symbols, training_days)

        return {
            "status": "training_started",
            "model_id": model_id,
            "message": "Model training started in background",
        }

    except Exception as e:
        logging.error(f"Error starting model training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def train_model_background(model_id: str, symbols: list[str], training_days: int):
    """Background task for model training"""
    try:
        # Get training data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=training_days)

        training_data = None
        for symbol in symbols:
            data = await app_state["alpaca_client"].get_historical_data(
                symbol, timeframe="1Day", limit=training_days
            )
            if training_data is None:
                training_data = data
            else:
                training_data = training_data.append(data)

        # Generate features
        features = app_state["feature_engineer"].compute_all_features(training_data)

        # Train model
        await app_state["model_manager"].train_and_register_model(model_id, training_data, features)

        audit_logger.info(
            "model_training_completed",
            model_id=model_id,
            symbols=symbols,
            training_days=training_days,
        )

    except Exception as e:
        logging.error(f"Error in background model training: {e}")
        audit_logger.error("model_training_failed", model_id=model_id, error=str(e))


@app.get("/api/v1/models/status")
async def get_models_status():
    """Get status of all models"""
    try:
        if not app_state["model_manager"]:
            raise HTTPException(status_code=503, detail="Model manager not available")

        return app_state["model_manager"].get_model_status()

    except Exception as e:
        logging.error(f"Error getting models status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Risk Management Endpoints
@app.get("/api/v1/risk/metrics")
async def get_risk_metrics():
    """Get current risk metrics"""
    try:
        if not app_state["risk_manager"]:
            raise HTTPException(status_code=503, detail="Risk manager not available")

        metrics = app_state["risk_manager"].get_risk_metrics()
        return {"risk_metrics": metrics, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logging.error(f"Error getting risk metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/risk/limits")
async def update_risk_limits(limits: dict):
    """Update risk limits"""
    try:
        if not app_state["risk_manager"]:
            raise HTTPException(status_code=503, detail="Risk manager not available")

        # Update limits (implementation depends on RiskManager interface)
        audit_logger.info("risk_limits_updated", limits=limits)

        return {"status": "updated", "limits": limits}

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    except Exception as e:
        logging.error(f"Error updating risk limits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System Status Endpoints
@app.get("/api/v1/system/status")
async def get_system_status():
    """Get comprehensive system status"""
    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "uptime": "N/A",  # Would calculate actual uptime
            "components": {
                "risk_manager": {
                    "status": "active" if app_state["risk_manager"] else "inactive",
                    "metrics": (
                        app_state["risk_manager"].get_risk_metrics()
                        if app_state["risk_manager"]
                        else {}
                    ),
                },
                "ensemble_model": {
                    "status": "active" if app_state["ensemble_model"] else "inactive",
                    "model_info": (
                        app_state["ensemble_model"].get_model_status()
                        if app_state["ensemble_model"]
                        else {}
                    ),
                },
                "strategy_manager": {
                    "status": "active" if app_state["strategy_manager"] else "inactive",
                    "strategies": (
                        app_state["strategy_manager"].get_strategy_status()
                        if app_state["strategy_manager"]
                        else {}
                    ),
                },
                "alpaca_client": {
                    "status": "active" if app_state["alpaca_client"] else "inactive",
                    "connected": (
                        app_state["alpaca_client"].is_connected()
                        if app_state["alpaca_client"]
                        else False
                    ),
                },
            },
            "active_websockets": len(app_state["active_websockets"]),
        }

        return status

    except Exception as e:
        logging.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time data
@app.websocket("/ws/realtime/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time trading data"""
    await websocket.accept()
    app_state["active_websockets"].append(websocket)

    audit_logger.info("websocket_connected", client_id=client_id)

    try:
        while True:
            # Wait for client message
            data = await websocket.receive_text()
            message = json.loads(data)

            message_type = message.get("type")

            if message_type == "subscribe_signals":
                symbols = message.get("symbols", [])
                # Start sending signals for these symbols
                await send_realtime_signals(websocket, symbols)

            elif message_type == "subscribe_portfolio":
                # Send portfolio updates
                await send_portfolio_updates(websocket)

            elif message_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        app_state["active_websockets"].remove(websocket)
        audit_logger.info("websocket_disconnected", client_id=client_id)
    except Exception as e:
        logging.error(f"WebSocket error for client {client_id}: {e}")
        try:
            await websocket.close()
        except:
            pass
        if websocket in app_state["active_websockets"]:
            app_state["active_websockets"].remove(websocket)


async def send_realtime_signals(websocket: WebSocket, symbols: list[str]):
    """Send real-time trading signals"""
    try:
        # In a real implementation, this would be triggered by market data events
        # For now, we'll send periodic updates
        while True:
            for symbol in symbols:
                try:
                    signal_response = await get_trading_signal(symbol)
                    if PYDANTIC_AVAILABLE:
                        signal_data = signal_response.dict()
                    else:
                        signal_data = signal_response

                    await websocket.send_text(
                        json.dumps({"type": "signal_update", "data": signal_data})
                    )
                except Exception as e:
                    logging.warning(f"Error sending signal for {symbol}: {e}")

            await asyncio.sleep(60)  # Send updates every minute

    except Exception as e:
        logging.error(f"Error in realtime signals: {e}")


async def send_portfolio_updates(websocket: WebSocket):
    """Send real-time portfolio updates"""
    try:
        while True:
            portfolio_status = await get_portfolio_status()
            if PYDANTIC_AVAILABLE:
                portfolio_data = portfolio_status.dict()
            else:
                portfolio_data = portfolio_status

            await websocket.send_text(
                json.dumps({"type": "portfolio_update", "data": portfolio_data})
            )

            await asyncio.sleep(30)  # Send updates every 30 seconds

    except Exception as e:
        logging.error(f"Error in portfolio updates: {e}")


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
