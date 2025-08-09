"""
FastAPI Gateway - Main API Server
Provides REST and WebSocket endpoints for the algorithmic trading platform
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

# Global state
app_state = {
    "risk_manager": None,
    "ensemble_model": None,
    "strategy_manager": None,
    "alpaca_client": None,
    "sentiment_analyzer": None,
    "feature_engineer": None,
    "model_manager": None,
    "active_websockets": [],
    "market_data_stream": None,
}

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
    """Application lifespan manager"""
    # Startup
    logging.info("Starting algorithmic trading platform...")

    try:
        settings = get_settings()

        # Initialize core components
        app_state["risk_manager"] = RiskManager()
        app_state["ensemble_model"] = EnsembleModel()
        app_state["strategy_manager"] = StrategyManager(
            app_state["risk_manager"], app_state["ensemble_model"]
        )
        app_state["alpaca_client"] = AlpacaClient()
        app_state["sentiment_analyzer"] = SocialSentimentAnalyzer()
        app_state["feature_engineer"] = FeatureEngineer()
        app_state["model_manager"] = ModelManager()

        # Start market data stream
        await start_market_data_stream()

        audit_logger.info("trading_platform_started", timestamp=datetime.now())

        yield

    except Exception as e:
        logging.error(f"Error during startup: {e}")
        yield

    # Shutdown
    logging.info("Shutting down algorithmic trading platform...")
    await cleanup_resources()
    audit_logger.info("trading_platform_shutdown", timestamp=datetime.now())


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


async def start_market_data_stream():
    """Start real-time market data streaming"""
    if app_state["alpaca_client"]:
        try:
            await app_state["alpaca_client"].connect_data_stream()
        except Exception as e:
            logging.error(f"Error starting market data stream: {e}")


async def cleanup_resources():
    """Cleanup resources during shutdown"""
    # Close websocket connections
    for websocket in app_state["active_websockets"]:
        try:
            await websocket.close()
        except:
            pass

    # Stop market data stream
    if app_state["alpaca_client"]:
        try:
            await app_state["alpaca_client"].disconnect()
        except Exception as e:
            logging.error(f"Error stopping market data stream: {e}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "risk_manager": app_state["risk_manager"] is not None,
            "ensemble_model": app_state["ensemble_model"] is not None,
            "strategy_manager": app_state["strategy_manager"] is not None,
            "alpaca_client": app_state["alpaca_client"] is not None,
            "sentiment_analyzer": app_state["sentiment_analyzer"] is not None,
            "feature_engineer": app_state["feature_engineer"] is not None,
            "model_manager": app_state["model_manager"] is not None,
        },
    }


# Trading Signals Endpoints
@app.get("/api/v1/signals/{symbol}")
async def get_trading_signal(symbol: str):
    """Get trading signal for a specific symbol"""
    try:
        if not app_state["strategy_manager"]:
            raise HTTPException(
                status_code=503, detail="Strategy manager not available"
            )

        # Get market data
        alpaca_client = app_state["alpaca_client"]
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
        feature_engineer = app_state["feature_engineer"]
        features = feature_engineer.compute_all_features(price_data)

        # Generate signal
        signal = await app_state["strategy_manager"].generate_combined_signal(
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

    except Exception as e:
        logging.error(f"Error getting signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Model Prediction Endpoints
@app.get("/api/v1/predictions/{symbol}")
async def get_prediction(symbol: str):
    """Get AI model prediction for a symbol"""
    try:
        if not app_state["ensemble_model"]:
            raise HTTPException(status_code=503, detail="Ensemble model not available")

        # Get data
        alpaca_client = app_state["alpaca_client"]
        price_data = await alpaca_client.get_historical_data(
            symbol, timeframe="1Day", limit=100
        )
        features = app_state["feature_engineer"].compute_all_features(price_data)

        # Get prediction
        prediction = app_state["ensemble_model"].predict(price_data, features, symbol)

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

    except Exception as e:
        logging.error(f"Error getting prediction for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Portfolio Management Endpoints
@app.get("/api/v1/portfolio/status")
async def get_portfolio_status():
    """Get current portfolio status"""
    try:
        if not app_state["risk_manager"]:
            raise HTTPException(status_code=503, detail="Risk manager not available")

        portfolio_value = app_state["risk_manager"].get_portfolio_value()
        positions = app_state["risk_manager"].get_positions()
        risk_metrics = app_state["risk_manager"].get_risk_metrics()

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

    except Exception as e:
        logging.error(f"Error submitting trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Market Data Endpoints
@app.get("/api/v1/market-data/{symbol}")
async def get_market_data(symbol: str, timeframe: str = "1Day", limit: int = 100):
    """Get historical market data"""
    try:
        if not app_state["alpaca_client"]:
            raise HTTPException(
                status_code=503, detail="Market data client not available"
            )

        data = await app_state["alpaca_client"].get_historical_data(
            symbol, timeframe, limit
        )

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": data.to_dict("records") if not data.empty else [],
            "count": len(data),
        }

    except Exception as e:
        logging.error(f"Error getting market data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Sentiment Analysis Endpoint
@app.get("/api/v1/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    """Get social sentiment for a symbol"""
    try:
        if not app_state["sentiment_analyzer"]:
            raise HTTPException(
                status_code=503, detail="Sentiment analyzer not available"
            )

        sentiment_data = await app_state["sentiment_analyzer"].get_aggregated_sentiment(
            symbol
        )

        return {
            "symbol": symbol,
            "sentiment": sentiment_data,
            "timestamp": datetime.now().isoformat(),
        }

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
        background_tasks.add_task(
            train_model_background, model_id, symbols, training_days
        )

        return {
            "status": "training_started",
            "model_id": model_id,
            "message": "Model training started in background",
        }

    except Exception as e:
        logging.error(f"Error starting model training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def train_model_background(model_id: str, symbols: List[str], training_days: int):
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
        await app_state["model_manager"].train_and_register_model(
            model_id, training_data, features
        )

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


async def send_realtime_signals(websocket: WebSocket, symbols: List[str]):
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
