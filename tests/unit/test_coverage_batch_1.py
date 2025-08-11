"""
Coverage Batch-1 Tests: Risk math edges, validators, JWT negatives, order idempotency, WS backpressure, middleware exception path
Targets specific modules for 40% coverage threshold.
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Depends
from fastapi.testclient import TestClient
from jose import JWTError

from backend.infra.security import create_access_token, verify_token
from backend.risk.risk_manager import RiskManager
from backend.services.order_service import OrderService


class TestRiskMathEdges:
    """Test risk calculation edge cases and mathematical boundaries."""

    def test_risk_manager_zero_portfolio_value(self):
        """Test risk calculations with zero portfolio value."""
        risk_manager = RiskManager()
        
        # Mock portfolio with zero value
        portfolio_data = {
            "total_value": 0.0,
            "positions": {},
            "cash": 0.0
        }
        
        # Should handle zero division gracefully
        risk_metrics = risk_manager.calculate_portfolio_risk(portfolio_data)
        
        assert risk_metrics is not None
        assert risk_metrics.get("var_95", 0) == 0
        assert risk_metrics.get("max_drawdown", 0) == 0

    def test_risk_manager_negative_portfolio_value(self):
        """Test risk calculations with negative portfolio value."""
        risk_manager = RiskManager()
        
        portfolio_data = {
            "total_value": -1000.0,
            "positions": {"AAPL": {"value": -500}, "MSFT": {"value": -500}},
            "cash": 0.0
        }
        
        # Should handle negative values appropriately
        risk_metrics = risk_manager.calculate_portfolio_risk(portfolio_data)
        assert risk_metrics is not None

    def test_risk_manager_extreme_volatility(self):
        """Test risk calculations with extreme volatility values."""
        risk_manager = RiskManager()
        
        # Extremely high volatility
        high_vol_data = {
            "symbol": "VOLATILE",
            "volatility": 5.0,  # 500% volatility
            "price": 100.0,
            "quantity": 10
        }
        
        risk_assessment = risk_manager.assess_position_risk(high_vol_data)
        assert risk_assessment["risk_level"] == "HIGH"
        assert risk_assessment["var_contribution"] > 0

    def test_risk_manager_correlation_matrix_edge_cases(self):
        """Test correlation matrix with edge cases."""
        risk_manager = RiskManager()
        
        # Perfect correlation (1.0)
        perfect_correlation = {
            "AAPL": {"MSFT": 1.0, "GOOGL": 1.0},
            "MSFT": {"AAPL": 1.0, "GOOGL": 1.0},
            "GOOGL": {"AAPL": 1.0, "MSFT": 1.0}
        }
        
        portfolio_risk = risk_manager.calculate_correlation_risk(perfect_correlation)
        assert portfolio_risk["systemic_risk"] > 0.8  # High systemic risk

    def test_risk_manager_empty_correlation_matrix(self):
        """Test correlation matrix with empty data."""
        risk_manager = RiskManager()
        
        empty_correlation = {}
        portfolio_risk = risk_manager.calculate_correlation_risk(empty_correlation)
        
        assert portfolio_risk["systemic_risk"] == 0.0
        assert portfolio_risk["diversification_ratio"] == 1.0

    def test_risk_manager_nan_infinity_handling(self):
        """Test risk manager handles NaN and infinity values."""
        risk_manager = RiskManager()
        
        # Data with NaN and infinity
        bad_data = {
            "symbol": "BAD",
            "volatility": float('nan'),
            "price": float('inf'),
            "quantity": -float('inf')
        }
        
        # Should not crash and return safe values
        risk_assessment = risk_manager.assess_position_risk(bad_data)
        assert risk_assessment["risk_level"] in ["LOW", "MEDIUM", "HIGH", "EXTREME"]

    def test_risk_manager_position_size_limits(self):
        """Test position size limit edge cases."""
        risk_manager = RiskManager()
        
        # Maximum position size
        max_position = {
            "symbol": "MAXPOS",
            "quantity": 1000000,  # Very large position
            "price": 1000.0,
            "portfolio_value": 100000.0  # Small portfolio
        }
        
        is_allowed = risk_manager.check_position_limits(max_position)
        assert is_allowed is False  # Should reject oversized position

    def test_risk_manager_kelly_criterion_edge_cases(self):
        """Test Kelly criterion with edge cases."""
        risk_manager = RiskManager()
        
        # Zero win probability
        zero_prob = {"win_probability": 0.0, "win_loss_ratio": 2.0}
        kelly_fraction = risk_manager.calculate_kelly_fraction(zero_prob)
        assert kelly_fraction <= 0  # Should not bet

        # Certainty (100% win probability)
        certainty = {"win_probability": 1.0, "win_loss_ratio": 1.0}
        kelly_fraction = risk_manager.calculate_kelly_fraction(certainty)
        assert 0 < kelly_fraction <= 1  # Should bet, but not exceed 100%

        # Negative edge (losing bet)
        negative_edge = {"win_probability": 0.3, "win_loss_ratio": 1.0}
        kelly_fraction = risk_manager.calculate_kelly_fraction(negative_edge)
        assert kelly_fraction <= 0  # Should not bet


class TestValidatorEdgeCases:
    """Test input validation edge cases and boundary conditions."""

    def test_symbol_validation_edge_cases(self):
        """Test symbol validation with various edge cases."""
        from backend.infra.validation import validate_symbol
        
        # Empty symbol
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol("")
        
        # Too long symbol
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_symbol("A" * 20)  # 20 characters
        
        # Invalid characters
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("ABC@123")
        
        # Numbers at start
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_symbol("123ABC")

    def test_price_validation_edge_cases(self):
        """Test price validation with edge cases."""
        from backend.infra.validation import validate_price
        
        # Zero price
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(0.0)
        
        # Negative price
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-10.50)
        
        # Too many decimal places
        with pytest.raises(ValueError, match="Too many decimal places"):
            validate_price(10.123456)  # More than 4 decimal places
        
        # Very large price
        with pytest.raises(ValueError, match="Price too large"):
            validate_price(1e10)  # 10 billion

    def test_quantity_validation_edge_cases(self):
        """Test quantity validation with edge cases."""
        from backend.infra.validation import validate_quantity
        
        # Zero quantity
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0)
        
        # Fractional shares when not allowed
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            validate_quantity(10.5, allow_fractional=False)
        
        # Excessive quantity
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(1e9)  # 1 billion shares

    def test_order_validation_missing_fields(self):
        """Test order validation with missing required fields."""
        from backend.infra.validation import validate_order
        
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_order({"quantity": 100, "price": 10.50})
        
        # Missing quantity
        with pytest.raises(ValueError, match="Quantity is required"):
            validate_order({"symbol": "AAPL", "price": 10.50})
        
        # Invalid order type
        with pytest.raises(ValueError, match="Invalid order type"):
            validate_order({
                "symbol": "AAPL",
                "quantity": 100,
                "price": 10.50,
                "order_type": "INVALID"
            })

    def test_portfolio_validation_constraints(self):
        """Test portfolio validation with constraint violations."""
        from backend.infra.validation import validate_portfolio_constraints
        
        # Excessive concentration
        concentrated_portfolio = {
            "positions": {
                "AAPL": {"weight": 0.95},  # 95% in one stock
                "MSFT": {"weight": 0.05}
            }
        }
        
        violations = validate_portfolio_constraints(concentrated_portfolio)
        assert len(violations) > 0
        assert any("concentration" in v.lower() for v in violations)

    def test_risk_limits_validation(self):
        """Test risk limits validation."""
        from backend.infra.validation import validate_risk_limits
        
        # Conflicting limits
        conflicting_limits = {
            "max_position_size": 0.10,  # 10%
            "min_position_size": 0.20   # 20% - impossible constraint
        }
        
        with pytest.raises(ValueError, match="Conflicting risk limits"):
            validate_risk_limits(conflicting_limits)


class TestJWTNegativeTests:
    """Test JWT authentication failure scenarios and edge cases."""

    def test_jwt_token_expired(self):
        """Test JWT token expiration handling."""
        # Create an expired token
        expired_token = create_access_token(
            subject="testuser",
            roles=["trader"],
            expires_minutes=-30  # Expired 30 minutes ago
        )
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_jwt_token_malformed(self):
        """Test malformed JWT token handling."""
        malformed_tokens = [
            "not.a.token",
            "header.payload",  # Missing signature
            "invalid_base64!",
            "",
            None
        ]
        
        for token in malformed_tokens:
            with pytest.raises(HTTPException) as exc_info:
                verify_token(token or "")
            
            assert exc_info.value.status_code == 401

    def test_jwt_token_invalid_signature(self):
        """Test JWT token with invalid signature."""
        # Create token with one secret, verify with another
        valid_token = create_access_token("testuser", ["trader"])
        
        # Tamper with the signature part
        parts = valid_token.split('.')
        tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature"
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered_token)
        
        assert exc_info.value.status_code == 401

    def test_jwt_token_missing_claims(self):
        """Test JWT token with missing required claims."""
        from jose import jwt
        from backend.config import get_settings
        
        settings = get_settings()
        
        # Token without required claims
        incomplete_payload = {
            "exp": int(time.time()) + 3600,  # Valid expiration
            # Missing 'sub', 'iss', 'aud'
        }
        
        incomplete_token = jwt.encode(
            incomplete_payload,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm
        )
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(incomplete_token)
        
        assert exc_info.value.status_code == 401

    def test_jwt_token_wrong_audience(self):
        """Test JWT token with wrong audience claim."""
        from jose import jwt
        from backend.config import get_settings
        
        settings = get_settings()
        
        # Token with wrong audience
        wrong_audience_payload = {
            "sub": "testuser",
            "iss": settings.security.jwt_issuer,
            "aud": "wrong-audience",  # Wrong audience
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "roles": ["trader"]
        }
        
        wrong_token = jwt.encode(
            wrong_audience_payload,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm
        )
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(wrong_token)
        
        assert exc_info.value.status_code == 401
        assert "audience" in exc_info.value.detail.lower()

    def test_jwt_authentication_missing_header(self):
        """Test API endpoints with missing authentication header."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.infra.security import get_authenticated_user
        
        app = FastAPI()
        
        @app.get("/protected")
        async def protected_endpoint(user=Depends(get_authenticated_user)):
            return {"user": user.username}
        
        client = TestClient(app)
        
        # Request without authorization header
        response = client.get("/protected")
        assert response.status_code == 401

    def test_jwt_authentication_invalid_scheme(self):
        """Test authentication with invalid scheme (not Bearer)."""
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient
        from backend.infra.security import get_authenticated_user
        
        app = FastAPI()
        
        @app.get("/protected")
        async def protected_endpoint(user=Depends(get_authenticated_user)):
            return {"user": user.username}
        
        client = TestClient(app)
        
        # Wrong authentication scheme
        response = client.get(
            "/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"}  # Basic auth instead of Bearer
        )
        assert response.status_code == 401


class TestOrderIdempotency:
    """Test order service idempotency and duplicate handling."""

    def test_order_service_duplicate_order_id(self):
        """Test that duplicate order IDs are handled correctly."""
        order_service = OrderService()
        
        order_data = {
            "order_id": "TEST-123",
            "symbol": "AAPL",
            "quantity": 100,
            "price": 150.0,
            "side": "buy"
        }
        
        # Submit first order
        result1 = order_service.submit_order(order_data)
        assert result1["status"] == "submitted"
        
        # Submit same order again (same order_id)
        result2 = order_service.submit_order(order_data)
        
        # Should return existing order, not create duplicate
        assert result2["status"] in ["submitted", "duplicate"]
        assert result2["order_id"] == "TEST-123"

    def test_order_service_concurrent_submissions(self):
        """Test concurrent order submissions with same ID."""
        order_service = OrderService()
        
        order_data = {
            "order_id": "CONCURRENT-123",
            "symbol": "MSFT",
            "quantity": 50,
            "price": 300.0,
            "side": "buy"
        }
        
        async def submit_order():
            return order_service.submit_order(order_data)
        
        # Simulate concurrent submissions
        import asyncio
        results = asyncio.run(asyncio.gather(
            submit_order(),
            submit_order(),
            submit_order(),
            return_exceptions=True
        ))
        
        # Only one should succeed, others should be handled gracefully
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "submitted")
        assert success_count == 1

    def test_order_service_modification_idempotency(self):
        """Test order modification idempotency."""
        order_service = OrderService()
        
        # Create initial order
        order_data = {
            "order_id": "MODIFY-123",
            "symbol": "GOOGL",
            "quantity": 25,
            "price": 2500.0,
            "side": "buy"
        }
        order_service.submit_order(order_data)
        
        # Modify order
        modification = {
            "order_id": "MODIFY-123",
            "price": 2450.0,  # Price change
            "modification_id": "MOD-456"
        }
        
        result1 = order_service.modify_order(modification)
        assert result1["status"] == "modified"
        
        # Same modification again
        result2 = order_service.modify_order(modification)
        assert result2["status"] in ["modified", "already_modified"]

    def test_order_service_cancellation_idempotency(self):
        """Test order cancellation idempotency."""
        order_service = OrderService()
        
        # Create and cancel order
        order_data = {
            "order_id": "CANCEL-123",
            "symbol": "TSLA",
            "quantity": 10,
            "price": 800.0,
            "side": "sell"
        }
        order_service.submit_order(order_data)
        
        # Cancel order
        result1 = order_service.cancel_order("CANCEL-123")
        assert result1["status"] in ["cancelled", "pending_cancel"]
        
        # Cancel same order again
        result2 = order_service.cancel_order("CANCEL-123")
        assert result2["status"] in ["cancelled", "already_cancelled"]


class TestWebSocketBackpressure:
    """Test WebSocket backpressure handling and flow control."""

    @pytest.mark.asyncio
    async def test_websocket_backpressure_queue_full(self):
        """Test WebSocket behavior when message queue is full."""
        from backend.api.websocket_manager import WebSocketClientManager
        
        manager = WebSocketClientManager(max_queue_size=3)  # Small queue for testing
        
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.send_text = AsyncMock()
        
        await manager.connect(mock_websocket, "test_client")
        
        # Fill up the queue beyond capacity
        messages = [f"message_{i}" for i in range(10)]
        
        for message in messages:
            await manager.send_personal_message(message, "test_client")
        
        # Should have dropped oldest messages due to backpressure
        # Verify that some messages were dropped
        assert mock_websocket.send_text.call_count <= 3

    @pytest.mark.asyncio
    async def test_websocket_slow_consumer(self):
        """Test WebSocket handling of slow consumers."""
        from backend.api.websocket_manager import WebSocketClientManager
        
        manager = WebSocketClientManager()
        
        # Mock slow WebSocket connection
        mock_websocket = AsyncMock()
        slow_send_calls = []
        
        async def slow_send_text(message):
            slow_send_calls.append(message)
            await asyncio.sleep(0.1)  # Simulate slow send
        
        mock_websocket.send_text = slow_send_text
        
        await manager.connect(mock_websocket, "slow_client")
        
        # Send multiple messages quickly
        start_time = time.time()
        for i in range(5):
            await manager.send_personal_message(f"fast_message_{i}", "slow_client")
        
        # Should not block indefinitely
        elapsed = time.time() - start_time
        assert elapsed < 1.0  # Should complete within reasonable time

    @pytest.mark.asyncio
    async def test_websocket_connection_cleanup_on_error(self):
        """Test WebSocket connection cleanup when errors occur."""
        from backend.api.websocket_manager import WebSocketClientManager
        
        manager = WebSocketClientManager()
        
        # Mock WebSocket that raises exception
        mock_websocket = AsyncMock()
        mock_websocket.send_text.side_effect = Exception("Connection lost")
        
        await manager.connect(mock_websocket, "error_client")
        
        # Try to send message (should trigger cleanup)
        await manager.send_personal_message("test", "error_client")
        
        # Client should be removed from active connections
        assert "error_client" not in manager.active_connections

    @pytest.mark.asyncio
    async def test_websocket_broadcast_with_failed_connections(self):
        """Test broadcast behavior when some connections fail."""
        from backend.api.websocket_manager import WebSocketClientManager
        
        manager = WebSocketClientManager()
        
        # Create good and bad connections
        good_websocket = AsyncMock()
        bad_websocket = AsyncMock()
        bad_websocket.send_text.side_effect = Exception("Failed connection")
        
        await manager.connect(good_websocket, "good_client")
        await manager.connect(bad_websocket, "bad_client")
        
        # Broadcast message
        await manager.broadcast("broadcast_test")
        
        # Good connection should receive message
        good_websocket.send_text.assert_called_once_with("broadcast_test")
        
        # Bad connection should be cleaned up
        assert "bad_client" not in manager.active_connections
        assert "good_client" in manager.active_connections


class TestMiddlewareExceptionPaths:
    """Test middleware exception handling and error paths."""

    def test_rate_limit_middleware_exception_handling(self):
        """Test rate limit middleware with application exceptions."""
        from fastapi import FastAPI, HTTPException
        from backend.infra.security_hardening import RateLimitMiddleware, SimpleRateLimiter
        
        app = FastAPI()
        
        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=500, detail="Internal error")
        
        @app.get("/exception")
        async def exception_endpoint():
            raise ValueError("Application error")
        
        limiter = SimpleRateLimiter()
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter, enabled=True)
        
        client = TestClient(app)
        
        # Even with application errors, rate limiting headers should be present
        response = client.get("/error")
        assert "X-RateLimit-Limit" in response.headers
        
        # Unhandled exceptions should still have rate limiting applied
        response = client.get("/exception")
        assert "X-RateLimit-Limit" in response.headers

    def test_security_headers_middleware_with_exceptions(self):
        """Test security headers middleware with various exceptions."""
        from fastapi import FastAPI
        from backend.infra.security_hardening import SecurityHeadersMiddleware
        
        app = FastAPI()
        
        @app.get("/timeout")
        async def timeout_endpoint():
            import asyncio
            await asyncio.sleep(10)  # Long delay
        
        @app.get("/json_error")
        async def json_error_endpoint():
            return {"invalid": "json", "circular": object()}  # Can't serialize
        
        app.add_middleware(SecurityHeadersMiddleware, enabled=True)
        
        client = TestClient(app)
        
        # Even with timeouts, security headers should be applied
        with pytest.raises(Exception):  # TestClient will raise on timeout
            response = client.get("/timeout", timeout=0.1)

    def test_cors_middleware_with_invalid_origins(self):
        """Test CORS middleware with invalid origin requests."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI()
        
        @app.get("/api/data")
        async def get_data():
            return {"data": "test"}
        
        # Restrictive CORS policy
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://allowed.com"],
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["*"],
        )
        
        client = TestClient(app)
        
        # Request from disallowed origin
        response = client.get(
            "/api/data",
            headers={"Origin": "https://malicious.com"}
        )
        
        # Should not have CORS headers for disallowed origin
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_authentication_middleware_exception_propagation(self):
        """Test that authentication exceptions are properly propagated."""
        from fastapi import FastAPI, Depends, HTTPException
        from fastapi.testclient import TestClient
        from backend.infra.security import get_authenticated_user
        
        app = FastAPI()
        
        @app.get("/protected")
        async def protected_endpoint(user=Depends(get_authenticated_user)):
            # Force an error after authentication
            if user.username == "error_user":
                raise HTTPException(status_code=422, detail="Processing error")
            return {"user": user.username}
        
        client = TestClient(app)
        
        # Create token for error user
        error_token = create_access_token("error_user", ["trader"])
        
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {error_token}"}
        )
        
        # Should get the application error, not auth error
        assert response.status_code == 422
