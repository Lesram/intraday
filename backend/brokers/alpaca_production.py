#!/usr/bin/env python3
"""
Production Alpaca Broker Client
Hedge Fund Grade Integration with SLO Monitoring
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import time
from typing import Any
import uuid

try:
    import alpaca_trade_api as tradeapi
    from alpaca_trade_api.rest import APIError
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    # Mock classes for when Alpaca SDK is not available
    class APIError(Exception):
        def __init__(self, message, response=None):
            self.message = message
            self.response = response
            super().__init__(message)

    class MockAlpacaAPI:
        def __init__(self, *args, **kwargs):
            pass

        def submit_order(self, *args, **kwargs):
            return MockOrder()

        def get_order(self, order_id):
            return MockOrder()

        def list_orders(self, *args, **kwargs):
            return []

    class MockOrder:
        def __init__(self):
            self.id = str(uuid.uuid4())
            self.status = 'filled'
            self.filled_qty = 100
            self.filled_avg_price = 150.0

class OrderStatus(Enum):
    """Order status enumeration"""
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"

class OrderSide(Enum):
    """Order side enumeration"""
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    """Order type enumeration"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

@dataclass
class OrderRequest:
    """Order request data structure"""
    symbol: str
    qty: int | float
    side: OrderSide
    type: OrderType
    time_in_force: str = "day"
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None
    order_class: str | None = None
    take_profit: dict[str, float] | None = None
    stop_loss: dict[str, float] | None = None

@dataclass
class OrderResponse:
    """Order response data structure"""
    order_id: str
    broker_order_id: str
    status: OrderStatus
    symbol: str
    qty: int | float
    filled_qty: int | float
    side: OrderSide
    order_type: OrderType
    submitted_at: datetime
    filled_at: datetime | None = None
    canceled_at: datetime | None = None
    failed_at: datetime | None = None
    filled_avg_price: float | None = None
    error_message: str | None = None
    broker_fees: float | None = None

@dataclass
class BrokerError:
    """Broker error information"""
    error_code: str
    error_message: str
    error_category: str  # network, authentication, validation, rate_limit, server_error
    timestamp: datetime
    retry_after: int | None = None
    is_retryable: bool = False

class ProductionAlpacaClient:
    """
    Production-grade Alpaca broker client
    Includes rate limiting, circuit breakers, and comprehensive error handling
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper_trading: bool = True,
        rate_limit_requests_per_minute: int = 200,
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_timeout_seconds: int = 60
    ):
        """Initialize production Alpaca client"""

        self.logger = logging.getLogger(__name__)

        # API Configuration
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_trading = paper_trading

        # Rate limiting
        self.rate_limit_requests_per_minute = rate_limit_requests_per_minute
        self.request_timestamps = []

        # Circuit breaker
        self.circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self.circuit_breaker_timeout_seconds = circuit_breaker_timeout_seconds
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = None
        self.circuit_breaker_open = False

        # Initialize Alpaca API
        if ALPACA_AVAILABLE:
            base_url = 'https://paper-api.alpaca.markets' if paper_trading else 'https://api.alpaca.markets'
            self.alpaca_api = tradeapi.REST(
                key_id=api_key,
                secret_key=api_secret,
                base_url=base_url,
                api_version='v2'
            )
        else:
            import os as _os
            if _os.getenv("ENVIRONMENT", "development") == "production":
                raise RuntimeError(
                    "Alpaca SDK (alpaca-trade-api) is not installed. "
                    "Cannot start broker in production without real SDK."
                )
            self.alpaca_api = MockAlpacaAPI()
            self.logger.warning("Alpaca SDK not available, using mock client (non-production only)")

        # SLO Integration
        try:
            from backend.monitoring.slo_metrics import get_slo_collector
            self.slo_collector = get_slo_collector()
        except ImportError:
            self.slo_collector = None
            self.logger.warning("SLO collector not available")

        # Order tracking
        self.pending_orders: dict[str, OrderResponse] = {}
        self.order_history: list[OrderResponse] = []

        # Statistics
        self.stats = {
            'orders_submitted': 0,
            'orders_filled': 0,
            'orders_failed': 0,
            'api_errors': 0,
            'rate_limit_delays': 0
        }

    async def _check_rate_limit(self) -> bool:
        """Check and enforce rate limiting"""

        now = time.time()

        # Clean old timestamps (older than 1 minute)
        cutoff = now - 60
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > cutoff]

        # Check if we're at the rate limit
        if len(self.request_timestamps) >= self.rate_limit_requests_per_minute:
            self.stats['rate_limit_delays'] += 1

            # Calculate delay needed
            oldest_timestamp = min(self.request_timestamps)
            delay_needed = 60 - (now - oldest_timestamp)

            if delay_needed > 0:
                self.logger.warning(f"Rate limit hit, delaying {delay_needed:.2f}s")
                await asyncio.sleep(delay_needed)
                return False

        # Add current timestamp
        self.request_timestamps.append(now)
        return True

    def _check_circuit_breaker(self) -> bool:
        """Check circuit breaker status"""

        if not self.circuit_breaker_open:
            return True

        # Check if timeout period has passed
        if self.circuit_breaker_last_failure:
            elapsed = time.time() - self.circuit_breaker_last_failure
            if elapsed > self.circuit_breaker_timeout_seconds:
                self.logger.info("Circuit breaker timeout elapsed, attempting to close")
                self.circuit_breaker_open = False
                self.circuit_breaker_failures = 0
                return True

        self.logger.warning("Circuit breaker is OPEN - rejecting request")
        return False

    def _handle_api_error(self, error: Exception) -> BrokerError:
        """Handle and classify API errors"""

        self.stats['api_errors'] += 1

        error_message = str(error)
        error_code = "unknown"
        error_category = "server_error"
        is_retryable = False
        retry_after = None

        if isinstance(error, APIError):
            error_code = getattr(error, 'code', 'api_error')

            # Classify error types
            if "401" in error_message or "unauthorized" in error_message.lower():
                error_category = "authentication"
                is_retryable = False
            elif "429" in error_message or "rate limit" in error_message.lower():
                error_category = "rate_limit"
                is_retryable = True
                retry_after = 60  # Default retry after 1 minute
            elif "400" in error_message or "invalid" in error_message.lower():
                error_category = "validation"
                is_retryable = False
            elif "500" in error_message or "503" in error_message:
                error_category = "server_error"
                is_retryable = True
                retry_after = 30
            elif "timeout" in error_message.lower() or "connection" in error_message.lower():
                error_category = "network"
                is_retryable = True
                retry_after = 10

        # Update circuit breaker
        if not is_retryable or error_category in ["server_error", "network"]:
            self.circuit_breaker_failures += 1
            self.circuit_breaker_last_failure = time.time()

            if self.circuit_breaker_failures >= self.circuit_breaker_failure_threshold:
                self.circuit_breaker_open = True
                self.logger.error(f"Circuit breaker OPENED after {self.circuit_breaker_failures} failures")

        return BrokerError(
            error_code=error_code,
            error_message=error_message,
            error_category=error_category,
            timestamp=datetime.now(),
            retry_after=retry_after,
            is_retryable=is_retryable
        )

    async def submit_order_async(self, order_request: OrderRequest) -> OrderResponse:
        """Submit order to Alpaca with comprehensive error handling (async version)"""

        start_time = time.time()

        # Generate internal order ID
        internal_order_id = str(uuid.uuid4())

        try:
            # Check circuit breaker
            if not self._check_circuit_breaker():
                raise Exception("Circuit breaker is open")

            # Check rate limit
            await self._check_rate_limit()

            # Prepare order parameters
            order_params = {
                'symbol': order_request.symbol,
                'qty': order_request.qty,
                'side': order_request.side.value,
                'type': order_request.type.value,
                'time_in_force': order_request.time_in_force
            }

            # Add optional parameters
            if order_request.limit_price:
                order_params['limit_price'] = order_request.limit_price

            if order_request.stop_price:
                order_params['stop_price'] = order_request.stop_price

            if order_request.client_order_id:
                order_params['client_order_id'] = order_request.client_order_id
            else:
                order_params['client_order_id'] = internal_order_id

            # Submit order to Alpaca
            self.logger.info(f"Submitting order: {order_request.symbol} {order_request.qty} {order_request.side.value}")

            alpaca_order = self.alpaca_api.submit_order(**order_params)

            # Create response
            order_response = OrderResponse(
                order_id=internal_order_id,
                broker_order_id=alpaca_order.id,
                status=OrderStatus(alpaca_order.status),
                symbol=order_request.symbol,
                qty=order_request.qty,
                filled_qty=float(alpaca_order.filled_qty or 0),
                side=order_request.side,
                order_type=order_request.type,
                submitted_at=datetime.now(),
                filled_avg_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None
            )

            # Track order
            self.pending_orders[internal_order_id] = order_response
            self.order_history.append(order_response)
            self.stats['orders_submitted'] += 1

            # Record SLO metrics
            latency_ms = (time.time() - start_time) * 1000
            if self.slo_collector:
                self.slo_collector.record_order_latency(
                    latency_ms=latency_ms,
                    order_type=order_request.type.value,
                    symbol=order_request.symbol,
                    account="production"
                )

                self.slo_collector.record_order_outcome(
                    status="submitted" if order_response.status == OrderStatus.NEW else "filled",
                    order_type=order_request.type.value,
                    symbol=order_request.symbol
                )

            self.logger.info(f"Order submitted successfully: {alpaca_order.id} (latency: {latency_ms:.1f}ms)")

            return order_response

        except Exception as e:
            # Handle error
            broker_error = self._handle_api_error(e)

            # Create failed order response
            order_response = OrderResponse(
                order_id=internal_order_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                symbol=order_request.symbol,
                qty=order_request.qty,
                filled_qty=0,
                side=order_request.side,
                order_type=order_request.type,
                submitted_at=datetime.now(),
                failed_at=datetime.now(),
                error_message=broker_error.error_message
            )

            self.order_history.append(order_response)
            self.stats['orders_failed'] += 1

            # Record SLO metrics
            latency_ms = (time.time() - start_time) * 1000
            if self.slo_collector:
                self.slo_collector.record_order_latency(
                    latency_ms=latency_ms,
                    order_type=order_request.type.value,
                    symbol=order_request.symbol,
                    account="production"
                )

                self.slo_collector.record_order_outcome(
                    status="rejected",
                    order_type=order_request.type.value,
                    symbol=order_request.symbol
                )

            self.logger.error(f"Order submission failed: {broker_error.error_message} (latency: {latency_ms:.1f}ms)")

            # Re-raise for caller to handle
            raise Exception(f"Order submission failed: {broker_error.error_message}")

    async def get_order_status(self, order_id: str) -> OrderResponse | None:
        """Get current order status from Alpaca"""

        start_time = time.time()

        try:
            # Check circuit breaker
            if not self._check_circuit_breaker():
                raise Exception("Circuit breaker is open")

            # Check rate limit
            await self._check_rate_limit()

            # Get order from local tracking first
            if order_id in self.pending_orders:
                order_response = self.pending_orders[order_id]
                broker_order_id = order_response.broker_order_id

                # Get updated status from Alpaca
                alpaca_order = self.alpaca_api.get_order(broker_order_id)

                # Update order response
                order_response.status = OrderStatus(alpaca_order.status)
                order_response.filled_qty = float(alpaca_order.filled_qty or 0)
                order_response.filled_avg_price = float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None

                if alpaca_order.status in ['filled', 'partially_filled']:
                    order_response.filled_at = datetime.now()
                    if alpaca_order.status == 'filled':
                        self.stats['orders_filled'] += 1

                        # Record fill event
                        if self.slo_collector:
                            fill_ratio = order_response.filled_qty / order_response.qty
                            self.slo_collector.record_fill_event(
                                fill_type="full" if fill_ratio >= 0.99 else "partial",
                                symbol=order_response.symbol,
                                account="production",
                                filled_qty=order_response.filled_qty
                            )

                elif alpaca_order.status in ['canceled', 'rejected', 'expired']:
                    order_response.canceled_at = datetime.now()
                    if order_id in self.pending_orders:
                        del self.pending_orders[order_id]

                latency_ms = (time.time() - start_time) * 1000
                self.logger.debug(f"Order status retrieved: {order_id} -> {order_response.status.value} (latency: {latency_ms:.1f}ms)")

                return order_response

        except Exception as e:
            broker_error = self._handle_api_error(e)
            self.logger.error(f"Failed to get order status: {broker_error.error_message}")

        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""

        try:
            # Check circuit breaker
            if not self._check_circuit_breaker():
                raise Exception("Circuit breaker is open")

            # Check rate limit
            await self._check_rate_limit()

            if order_id in self.pending_orders:
                order_response = self.pending_orders[order_id]
                broker_order_id = order_response.broker_order_id

                # Cancel order via Alpaca
                self.alpaca_api.cancel_order(broker_order_id)

                # Update local tracking
                order_response.status = OrderStatus.CANCELED
                order_response.canceled_at = datetime.now()
                del self.pending_orders[order_id]

                self.logger.info(f"Order canceled successfully: {order_id}")
                return True

        except Exception as e:
            broker_error = self._handle_api_error(e)
            self.logger.error(f"Failed to cancel order: {broker_error.error_message}")

        return False

    def get_account(self):
        """Get account information from Alpaca"""
        try:
            if ALPACA_AVAILABLE and hasattr(self.alpaca_api, 'get_account'):
                return self.alpaca_api.get_account()
            else:
                import os as _os
                if _os.getenv("ENVIRONMENT", "development") == "production":
                    raise RuntimeError("Alpaca SDK not available — cannot get account in production")
                self.logger.warning("Returning mock account (non-production)")
                class MockAccount:
                    def __init__(self):
                        self.status = "ACTIVE"
                        self.buying_power = "100000.00"
                        self.paper_trading = True

                return MockAccount()
        except RuntimeError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            return None

    def get_latest_quote(self, symbol: str):
        """Get latest quote for symbol"""
        try:
            if ALPACA_AVAILABLE and hasattr(self.alpaca_api, 'get_latest_quote'):
                return self.alpaca_api.get_latest_quote(symbol)
            else:
                import os as _os
                if _os.getenv("ENVIRONMENT", "development") == "production":
                    raise RuntimeError(f"Alpaca SDK not available — cannot get quote for {symbol} in production")
                self.logger.warning(f"Returning mock quote for {symbol} (non-production)")
                class MockQuote:
                    def __init__(self, symbol):
                        self.symbol = symbol
                        self.bid_price = 150.0
                        self.ask_price = 150.1
                        self.timestamp = datetime.now()

                return MockQuote(symbol)
        except RuntimeError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to get quote for {symbol}: {e}")
            return None

    def list_positions(self):
        """List all current positions"""
        try:
            if ALPACA_AVAILABLE and hasattr(self.alpaca_api, 'list_positions'):
                return self.alpaca_api.list_positions()
            else:
                # Return empty list for testing
                return []
        except Exception as e:
            self.logger.error(f"Failed to list positions: {e}")
            return []

    def submit_order(self, *args, **kwargs):
        """Submit order - handles both OrderRequest objects and keyword arguments"""
        try:
            # Handle OrderRequest object
            if args and isinstance(args[0], OrderRequest):
                order_request = args[0]
            else:
                # Handle keyword arguments
                symbol = kwargs.get('symbol')
                qty = kwargs.get('qty')
                side = kwargs.get('side')
                order_type = kwargs.get('type', 'market')
                time_in_force = kwargs.get('time_in_force', 'day')

                if not all([symbol, qty, side]):
                    raise ValueError("Missing required parameters: symbol, qty, side")

                # Create OrderRequest object
                order_request = OrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide(side),
                    type=OrderType(order_type),
                    time_in_force=time_in_force,
                    limit_price=kwargs.get('limit_price'),
                    stop_price=kwargs.get('stop_price'),
                    client_order_id=kwargs.get('client_order_id')
                )

            # Use existing async method
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self.submit_order_async(order_request))
            except RuntimeError:
                # If no event loop, create one
                return asyncio.run(self.submit_order_async(order_request))

        except Exception as e:
            self.logger.error(f"Failed to submit order: {e}")
            self.stats['orders_failed'] = self.stats.get('orders_failed', 0) + 1
            raise  # Propagate error — caller must know the order was NOT submitted

    def get_client_statistics(self) -> dict[str, Any]:
        """Get client performance statistics"""

        total_orders = self.stats['orders_submitted']
        fill_rate = (self.stats['orders_filled'] / total_orders * 100) if total_orders > 0 else 0
        error_rate = (self.stats['orders_failed'] / total_orders * 100) if total_orders > 0 else 0

        return {
            'orders_submitted': self.stats['orders_submitted'],
            'orders_filled': self.stats['orders_filled'],
            'orders_failed': self.stats['orders_failed'],
            'fill_rate_percent': round(fill_rate, 2),
            'error_rate_percent': round(error_rate, 2),
            'api_errors': self.stats['api_errors'],
            'rate_limit_delays': self.stats['rate_limit_delays'],
            'pending_orders_count': len(self.pending_orders),
            'circuit_breaker_open': self.circuit_breaker_open,
            'circuit_breaker_failures': self.circuit_breaker_failures
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check of Alpaca connection"""

        start_time = time.time()

        try:
            # Simple API call to check connectivity
            account = self.alpaca_api.get_account()

            health_status = {
                'status': 'healthy',
                'latency_ms': round((time.time() - start_time) * 1000, 1),
                'account_status': account.status if hasattr(account, 'status') else 'active',
                'trading_blocked': getattr(account, 'trading_blocked', False),
                'paper_trading': self.paper_trading,
                'circuit_breaker_open': self.circuit_breaker_open,
                'timestamp': datetime.now().isoformat()
            }

            # Update system health in SLO collector
            if self.slo_collector:
                health_score = 100.0 if not self.circuit_breaker_open else 25.0
                self.slo_collector.update_system_health(
                    component="alpaca_client",
                    health_score=health_score
                )

            return health_status

        except Exception as e:
            broker_error = self._handle_api_error(e)

            health_status = {
                'status': 'unhealthy',
                'latency_ms': round((time.time() - start_time) * 1000, 1),
                'error_message': broker_error.error_message,
                'error_category': broker_error.error_category,
                'circuit_breaker_open': self.circuit_breaker_open,
                'timestamp': datetime.now().isoformat()
            }

            # Update system health in SLO collector
            if self.slo_collector:
                self.slo_collector.update_system_health(
                    component="alpaca_client",
                    health_score=0.0
                )

            return health_status

# Global client instance
_alpaca_client = None

def get_production_alpaca_client(
    api_key: str | None = None,
    api_secret: str | None = None,
    paper_trading: bool = True
) -> ProductionAlpacaClient:
    """Get global production Alpaca client instance"""

    global _alpaca_client

    if _alpaca_client is None:
        # Use provided credentials or environment variables
        if not api_key or not api_secret:
            import os
            api_key = api_key or os.getenv('ALPACA_API_KEY_ID')
            api_secret = api_secret or os.getenv('ALPACA_API_SECRET_KEY')

        if not api_key or not api_secret:
            raise ValueError(
                "Alpaca API credentials not provided. Set ALPACA_API_KEY_ID "
                "and ALPACA_API_SECRET_KEY environment variables."
            )

        _alpaca_client = ProductionAlpacaClient(
            api_key=api_key,
            api_secret=api_secret,
            paper_trading=paper_trading
        )

    return _alpaca_client
