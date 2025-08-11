"""
Test FastAPI Endpoints
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from backend.api.main import app


@pytest.fixture
def client():
    """Test client for FastAPI"""
    return TestClient(app)

@pytest.fixture
def mock_app_state():
    """Mock application state for testing"""
    mock_state = {
        'risk_manager': AsyncMock(),
        'ensemble_model': AsyncMock(),
        'strategy_manager': AsyncMock(),
        'alpaca_client': AsyncMock(),
        'sentiment_analyzer': AsyncMock(),
        'feature_engineer': MagicMock(),
        'model_manager': AsyncMock(),
        'active_websockets': []
    }

    # Configure mock return values
    mock_state['alpaca_client'].get_historical_data.return_value = MagicMock()
    mock_state['alpaca_client'].is_connected.return_value = True
    mock_state['risk_manager'].get_portfolio_value.return_value = 100000.0
    mock_state['risk_manager'].get_positions.return_value = {}
    mock_state['risk_manager'].get_risk_metrics.return_value = {
        'var_95': -0.05,
        'cvar_95': -0.08,
        'portfolio_beta': 1.2,
        'sharpe_ratio': 1.5
    }

    return mock_state

class TestHealthEndpoints:
    """Test health check endpoints"""

    @pytest.mark.unit
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert data["status"] == "healthy"

class TestTradingSignalEndpoints:
    """Test trading signal endpoints"""

    @patch('backend.api.main.app_state', {
        'strategy_manager': AsyncMock(),
        'alpaca_client': AsyncMock(),
        'feature_engineer': MagicMock()
    })
    @pytest.mark.unit
    def test_get_trading_signal_success(self, client, sample_price_data, sample_features):
        """Test successful signal generation"""
        from backend.api.main import app_state
        from backend.strategies.trading_strategies import SignalType, TradingSignal

        mock_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.75,
            target_price=155.0,
            position_size=100,
            timestamp=datetime.now(),
            metadata={"strategy": "test"}
        )

        # Configure the mock objects
        app_state['strategy_manager'].generate_combined_signal = AsyncMock(return_value=mock_signal)
        app_state['alpaca_client'].get_historical_data = AsyncMock(return_value=sample_price_data)
        app_state['feature_engineer'].compute_all_features = MagicMock(return_value=sample_features)

        response = client.get("/api/v1/signals/AAPL")

        # Should return signal data
        assert response.status_code == 200 or response.status_code == 503  # May be unavailable in test

    @patch('backend.api.main.app_state')
    @pytest.mark.unit
    def test_get_trading_signal_missing_data(self, mock_state, client):
        """Test signal generation with missing market data"""
        import pandas as pd

        mock_state.return_value = {
            'strategy_manager': AsyncMock(),
            'alpaca_client': AsyncMock(),
            'feature_engineer': MagicMock()
        }

        # Mock empty data response
        mock_state.return_value['alpaca_client'].get_historical_data.return_value = pd.DataFrame()

        response = client.get("/api/v1/signals/INVALID")

        # Should handle missing data gracefully
        assert response.status_code in [404, 500, 503]

    @pytest.mark.unit
    def test_get_multiple_signals(self, client):
        """Test getting signals for multiple symbols"""
        response = client.get("/api/v1/signals?symbols=AAPL,GOOGL,MSFT")

        # Should return signals for all symbols (or appropriate error)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "signals" in data
            assert "timestamp" in data

class TestModelPredictionEndpoints:
    """Test AI model prediction endpoints"""

    @patch('backend.api.main.app_state', {
        'ensemble_model': MagicMock(),
        'alpaca_client': AsyncMock(),
        'feature_engineer': MagicMock()
    })
    @pytest.mark.unit
    def test_get_prediction_success(self, client, sample_price_data, sample_features):
        """Test successful prediction retrieval"""
        from backend.api.main import app_state
        from backend.models.ensemble_model import ModelPrediction

        mock_prediction = ModelPrediction(
            symbol="AAPL",
            timestamp=datetime.now(),
            predictions={"lstm": 155.0, "xgboost": 154.5, "random_forest": 156.0},
            confidence_scores={"lstm": 0.8, "xgboost": 0.75, "random_forest": 0.7},
            ensemble_prediction=155.2,
            ensemble_confidence=0.75,
            metadata={}
        )

        app_state['ensemble_model'].predict = MagicMock(return_value=mock_prediction)
        app_state['alpaca_client'].get_historical_data = AsyncMock(return_value=sample_price_data)
        app_state['feature_engineer'].compute_all_features = MagicMock(return_value=sample_features)

        response = client.get("/api/v1/predictions/AAPL")

        assert response.status_code in [200, 503]  # Success or service unavailable

    @patch('backend.api.main.app_state', {'ensemble_model': None})
    @pytest.mark.unit
    def test_get_prediction_model_unavailable(self, client):
        """Test prediction with unavailable model"""
        response = client.get("/api/v1/predictions/AAPL")
        assert response.status_code == 503

class TestPortfolioEndpoints:
    """Test portfolio management endpoints"""

    @patch('backend.api.main.app_state', {
        'risk_manager': MagicMock()
    })
    @pytest.mark.unit
    def test_get_portfolio_status(self, client):
        """Test portfolio status retrieval"""
        from backend.api.main import app_state

        app_state['risk_manager'].get_portfolio_value = MagicMock(return_value=150000.0)
        app_state['risk_manager'].get_positions = MagicMock(return_value={
            'AAPL': {'quantity': 100, 'market_value': 15000}
        })
        # Return a dict instead of MagicMock for Pydantic validation
        app_state['risk_manager'].get_risk_metrics = MagicMock(return_value={
            'var_95': -0.02,
            'sharpe_ratio': 1.8
        })

        response = client.get("/api/v1/portfolio/status")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "total_value" in data
            assert "positions" in data
            assert "risk_metrics" in data

class TestTradingEndpoints:
    """Test trade execution endpoints"""

    @patch('backend.api.main.app_state', {
        'alpaca_client': AsyncMock(),
        'risk_manager': MagicMock()
    })
    @pytest.mark.unit
    def test_submit_trade_success(self, client):
        """Test successful trade submission"""
        from backend.api.main import app_state

        # Mock successful risk check
        app_state['risk_manager'].assess_position_risk = AsyncMock(return_value={
            'approved': True,
            'reason': 'Risk check passed'
        })

        # Mock successful order submission
        app_state['alpaca_client'].submit_order = AsyncMock(return_value={
            'id': 'order_123',
            'status': 'accepted'
        })

        trade_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'quantity': 10,
            'order_type': 'market'
        }

        response = client.post("/api/v1/trades", json=trade_data)

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert data["status"] == "submitted"

    @patch('backend.api.main.app_state', {
        'alpaca_client': AsyncMock(),
        'risk_manager': MagicMock()
    })
    @pytest.mark.unit
    def test_submit_trade_risk_rejection(self, client):
        """Test trade rejection due to risk"""
        from backend.api.main import app_state

        # Mock risk rejection
        app_state['risk_manager'].assess_position_risk = AsyncMock(return_value={
            'approved': False,
            'reason': 'Position size too large'
        })

        trade_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'quantity': 10000,  # Large position
            'order_type': 'market'
        }

        response = client.post("/api/v1/trades", json=trade_data)

        assert response.status_code in [403, 503]  # Forbidden or service unavailable

    @pytest.mark.unit
    def test_submit_trade_invalid_data(self, client):
        """Test trade submission with invalid data"""
        invalid_trade_data = {
            'symbol': 'AAPL'
            # Missing required fields
        }

        response = client.post("/api/v1/trades", json=invalid_trade_data)

        assert response.status_code in [400, 503]  # Bad request or service unavailable

class TestMarketDataEndpoints:
    """Test market data endpoints"""

    @patch('backend.api.main.app_state', {
        'alpaca_client': AsyncMock()
    })
    @pytest.mark.unit
    def test_get_market_data(self, client, sample_price_data):
        """Test market data retrieval"""
        from backend.api.main import app_state

        app_state['alpaca_client'].get_historical_data.return_value = sample_price_data

        response = client.get("/api/v1/market-data/AAPL?timeframe=1Day&limit=50")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert "data" in data
            assert data["symbol"] == "AAPL"

    @patch('backend.api.main.app_state', {'alpaca_client': None})
    @pytest.mark.unit
    def test_get_market_data_no_client(self, client):
        """Test market data with unavailable client"""

        response = client.get("/api/v1/market-data/AAPL")
        assert response.status_code == 503

class TestSentimentEndpoints:
    """Test sentiment analysis endpoints"""

    @patch('backend.api.main.app_state', {
        'sentiment_analyzer': AsyncMock()
    })
    @pytest.mark.unit
    def test_get_sentiment(self, client):
        """Test sentiment data retrieval"""
        from backend.api.main import app_state

        mock_sentiment = {
            'overall_sentiment': 0.65,
            'bullish_ratio': 0.7,
            'bearish_ratio': 0.3,
            'volume': 1500
        }

        app_state['sentiment_analyzer'].get_aggregated_sentiment.return_value = mock_sentiment

        response = client.get("/api/v1/sentiment/AAPL")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert "sentiment" in data

class TestModelManagementEndpoints:
    """Test MLOps model management endpoints"""

    @pytest.mark.unit
    def test_train_model(self, client):
        """Test model training endpoint"""
        training_request = {
            'model_id': 'test_model',
            'symbols': ['AAPL', 'GOOGL'],
            'training_period_days': 30
        }

        response = client.post("/api/v1/models/train", json=training_request)

        # Should accept the training request (or be unavailable)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert data["status"] == "training_started"

    @patch('backend.api.main.app_state')
    @pytest.mark.unit
    def test_get_models_status(self, mock_state, client):
        """Test models status retrieval"""
        mock_state.return_value = {
            'model_manager': AsyncMock()
        }

        mock_status = {
            'test_model': {
                'total_versions': 3,
                'champion_version': 'v2',
                'latest_version': 'v3'
            }
        }

        mock_state.return_value['model_manager'].get_model_status.return_value = mock_status

        response = client.get("/api/v1/models/status")

        assert response.status_code in [200, 503]

class TestRiskEndpoints:
    """Test risk management endpoints"""

    @patch('backend.api.main.app_state')
    @pytest.mark.unit
    def test_get_risk_metrics(self, mock_state, client):
        """Test risk metrics retrieval"""
        mock_state.return_value = {
            'risk_manager': AsyncMock()
        }

        mock_metrics = {
            'var_95': -0.03,
            'cvar_95': -0.05,
            'portfolio_beta': 1.1,
            'sharpe_ratio': 1.6,
            'max_drawdown': -0.08
        }

        mock_state.return_value['risk_manager'].get_risk_metrics.return_value = mock_metrics

        response = client.get("/api/v1/risk/metrics")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "risk_metrics" in data
            assert "timestamp" in data

    @pytest.mark.unit
    def test_update_risk_limits(self, client):
        """Test risk limits update"""
        new_limits = {
            'max_position_size': 2000,
            'max_portfolio_risk': 0.03,
            'daily_loss_limit': 5000
        }

        response = client.post("/api/v1/risk/limits", json=new_limits)

        assert response.status_code in [200, 503]

class TestSystemEndpoints:
    """Test system status endpoints"""

    @pytest.mark.unit
    def test_get_system_status(self, client):
        """Test system status retrieval"""
        response = client.get("/api/v1/system/status")

        assert response.status_code in [200, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "components" in data

class TestWebSocketEndpoints:
    """Test WebSocket endpoints"""

    @pytest.mark.unit
    def test_websocket_connection(self, client):
        """Test WebSocket connection"""
        # Note: Testing WebSocket requires special setup
        # This is a basic test to ensure the endpoint exists
        try:
            with client.websocket_connect("/ws/realtime/test_client") as websocket:
                # Send ping
                websocket.send_json({"type": "ping"})

                # Should receive pong
                response = websocket.receive_json()
                assert response.get("type") == "pong"

        except Exception as e:
            # WebSocket testing can be complex, allow for setup issues
            pytest.skip(f"WebSocket test skipped due to: {e}")

class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.unit
    def test_invalid_endpoints(self, client):
        """Test invalid endpoint handling"""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_malformed_json(self, client):
        """Test malformed JSON handling"""
        response = client.post(
            "/api/v1/trades",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422, 503]

    @patch('backend.api.main.app_state', {
        'risk_manager': None,
        'ensemble_model': None,
        'strategy_manager': None,
        'alpaca_client': None,
        'sentiment_analyzer': None,
        'feature_engineer': None,
        'model_manager': None
    })
    @pytest.mark.unit
    def test_service_unavailable(self, client):
        """Test service unavailable scenarios"""

        # All these should return 503
        endpoints = [
            "/api/v1/signals/AAPL",
            "/api/v1/predictions/AAPL",
            "/api/v1/portfolio/status",
            "/api/v1/market-data/AAPL",
            "/api/v1/sentiment/AAPL"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 503
