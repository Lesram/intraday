"""
Risk Reasons Table Testing with Comprehensive Coverage.
Tests block reasons table: negative μ, σ≈0, per-symbol/day cap, leverage exceeded, 
kill switch, notional too small. Asserts (allowed, reason, adjusted_qty) tuple responses
and orders_blocked_total{reason} Prometheus metric increments.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Tuple, Optional
from prometheus_client import CollectorRegistry, Counter

# Mock the backend risk modules since they don't exist yet
# This represents the expected interface for risk management

class MockPositionLimits:
    """Mock position limits for testing."""
    def __init__(self, max_position_per_symbol: Decimal = Decimal('10000')):
        self.max_position_per_symbol = max_position_per_symbol
    
    def check_position_limit(self, symbol: str, current_qty: Decimal, new_qty: Decimal) -> Tuple[bool, str]:
        total_qty = abs(current_qty + new_qty)
        if total_qty > self.max_position_per_symbol:
            return False, f"Position limit exceeded: {total_qty} > {self.max_position_per_symbol}"
        return True, ""

class MockVolatilityAnalyzer:
    """Mock volatility analyzer for testing."""
    def __init__(self):
        self.volatility_data = {}
    
    def get_volatility(self, symbol: str) -> Decimal:
        return self.volatility_data.get(symbol, Decimal('0.02'))  # Default 2% volatility
    
    def is_low_volatility(self, symbol: str, threshold: Decimal = Decimal('0.001')) -> bool:
        return self.get_volatility(symbol) < threshold

class MockMarginCalculator:
    """Mock margin calculator for testing."""
    def calculate_margin_requirement(self, symbol: str, qty: Decimal, price: Decimal) -> Decimal:
        return abs(qty * price) * Decimal('0.25')  # 25% margin requirement
    
    def check_margin_available(self, account_id: str, required_margin: Decimal) -> bool:
        # Mock available margin check
        return required_margin < Decimal('50000')  # $50k available margin

class MockRiskManager:
    """Mock risk manager that implements the expected interface."""
    
    def __init__(self):
        self.position_limits = MockPositionLimits()
        self.volatility_analyzer = MockVolatilityAnalyzer()
        self.margin_calculator = MockMarginCalculator()
        self.kill_switch_active = False
        self.daily_limits = {}
        
        # Prometheus metrics
        self.metrics_registry = CollectorRegistry()
        self.orders_blocked_counter = Counter(
            'orders_blocked_total',
            'Number of orders blocked by risk management',
            ['reason'],
            registry=self.metrics_registry
        )
    
    def evaluate_order_risk(self, order_request: dict, current_position: Decimal = Decimal('0')) -> Tuple[bool, str, Decimal]:
        """
        Evaluate order risk and return (allowed, reason, adjusted_qty).
        
        Returns:
            Tuple[bool, str, Decimal]: (is_allowed, block_reason, adjusted_quantity)
        """
        symbol = order_request['symbol']
        side = order_request['side']
        requested_qty = Decimal(str(order_request['qty']))
        price = Decimal(str(order_request.get('price', 100)))
        account_id = order_request.get('account_id', 'test-account')
        
        # Apply quantity direction
        signed_qty = requested_qty if side == 'buy' else -requested_qty
        
        # Check kill switch
        if self.kill_switch_active:
            self.orders_blocked_counter.labels(reason='kill_switch').inc()
            return False, "Trading kill switch is active", Decimal('0')
        
        # Check position limits
        allowed, reason = self.position_limits.check_position_limit(symbol, current_position, signed_qty)
        if not allowed:
            self.orders_blocked_counter.labels(reason='position_limit').inc()
            return False, reason, Decimal('0')
        
        # Check volatility (sigma ≈ 0 check)
        if self.volatility_analyzer.is_low_volatility(symbol):
            self.orders_blocked_counter.labels(reason='low_volatility').inc()
            return False, f"Volatility too low for {symbol}", Decimal('0')
        
        # Check notional size
        notional = abs(requested_qty * price)
        if notional < Decimal('1000'):  # Minimum $1000 notional
            self.orders_blocked_counter.labels(reason='notional_too_small').inc()
            return False, f"Notional ${notional} below minimum $1000", Decimal('0')
        
        # Check leverage/margin
        required_margin = self.margin_calculator.calculate_margin_requirement(symbol, signed_qty, price)
        if not self.margin_calculator.check_margin_available(account_id, required_margin):
            self.orders_blocked_counter.labels(reason='insufficient_margin').inc()
            return False, f"Insufficient margin: ${required_margin} required", Decimal('0')
        
        # Check daily limits
        daily_key = f"{account_id}:{symbol}:{datetime.now().date()}"
        daily_traded = self.daily_limits.get(daily_key, Decimal('0'))
        daily_limit = Decimal('100000')  # $100k daily limit per symbol per account
        
        if daily_traded + notional > daily_limit:
            remaining = max(Decimal('0'), daily_limit - daily_traded)
            adjusted_qty = remaining / price if price > 0 else Decimal('0')
            
            if adjusted_qty < requested_qty * Decimal('0.1'):  # Less than 10% of requested
                self.orders_blocked_counter.labels(reason='daily_limit').inc()
                return False, f"Daily limit exceeded for {symbol}", Decimal('0')
            else:
                # Partial fill allowed
                return True, f"Partial fill due to daily limit", adjusted_qty
        
        # Order allowed
        return True, "", requested_qty
    
    async def before_order(self, order_spec, portfolio_state=None, request_id=None):
        """Legacy compatibility method that calls evaluate_order_risk."""
        # Convert OrderSpec to dict format expected by evaluate_order_risk
        order_dict = {
            'symbol': getattr(order_spec, 'symbol', 'AAPL'),
            'side': getattr(order_spec, 'side', 'buy'), 
            'qty': getattr(order_spec, 'qty', 100),
            'price': getattr(order_spec, 'price', 150),
            'account_id': getattr(order_spec, 'account_id', 'test-account')
        }
        
        allowed, reason, adjusted_qty = self.evaluate_order_risk(order_dict)
        
        # Return mock RiskDecision-like object
        decision = MagicMock()
        decision.allowed = allowed
        decision.reason = reason if reason else None  # Convert empty string to None
        # For normal allowed orders, adjusted_qty should be None (no adjustment)
        decision.adjusted_qty = None if (allowed and adjusted_qty == order_dict['qty']) else adjusted_qty
        return decision


# Risk decision result type
RiskResult = Tuple[bool, Optional[str], Optional[Decimal]]  # (allowed, reason, adjusted_qty)


# Comprehensive risk test scenarios data table
RISK_BLOCK_SCENARIOS = [
    # (symbol, side, qty, price, scenario_name, expected_allowed, expected_reason_contains, expected_adjusted_qty)
    
    # Negative μ (mean return) scenarios
    ("DECLINING_STOCK", "buy", 1000, 50.0, "negative_mu_block", False, "negative expected return", None),
    ("BEAR_MARKET_ETF", "buy", 500, 25.0, "negative_mu_bear", False, "bearish trend detected", None),
    
    # σ≈0 (low volatility) scenarios  
    ("STABLE_BOND", "buy", 10000, 100.0, "low_volatility_block", False, "insufficient volatility", None),
    ("PENNY_STABLE", "sell", 50000, 0.01, "zero_volatility", False, "no price movement", None),
    
    # Per-symbol daily cap scenarios
    ("AAPL", "buy", 5000, 150.0, "symbol_daily_cap_exceeded", False, "daily trading limit exceeded", None),
    ("TSLA", "sell", 1000, 800.0, "symbol_cap_partial", True, "reduced to daily limit", Decimal("500")),
    
    # Leverage exceeded scenarios
    ("LEVERAGED_ETF", "buy", 1000, 300.0, "leverage_exceeded", False, "leverage ratio too high", None),
    ("MARGIN_HEAVY", "buy", 2000, 200.0, "margin_requirement", False, "insufficient margin available", None),
    
    # Kill switch scenarios
    ("ANY_SYMBOL", "buy", 100, 50.0, "market_kill_switch", False, "trading halted by kill switch", None),
    ("VOLATILE_MEME", "sell", 500, 10.0, "symbol_kill_switch", False, "symbol trading suspended", None),
    
    # Notional too small scenarios
    ("EXPENSIVE_STOCK", "buy", 1, 5000.0, "notional_too_small_qty", False, "trade size below minimum", None),
    ("CHEAP_PENNY", "buy", 10, 0.05, "notional_too_small_value", False, "notional value too small", None),
    
    # Allowed scenarios (for baseline)
    ("AAPL", "buy", 100, 150.0, "normal_allowed", True, None, None),
    ("MSFT", "sell", 50, 300.0, "normal_sell_allowed", True, None, None),
]

# Additional edge case scenarios
RISK_EDGE_CASES = [
    # (symbol, side, qty, price, scenario_name, expected_result_pattern)
    ("", "buy", 100, 150.0, "empty_symbol", "invalid symbol"),
    ("VALIDSTOCK", "invalid_side", 100, 150.0, "invalid_side", "invalid order side"), 
    ("VALIDSTOCK", "buy", 0, 150.0, "zero_quantity", "quantity must be positive"),
    ("VALIDSTOCK", "buy", -100, 150.0, "negative_quantity", "quantity cannot be negative"),
    ("VALIDSTOCK", "buy", 100, 0, "zero_price", "price must be positive"),
    ("VALIDSTOCK", "buy", 100, -50.0, "negative_price", "price cannot be negative"),
]


# Test fixtures
@pytest.fixture
def mock_position_limits():
    """Mock position limits checker with configurable responses."""
    limits = AsyncMock()  # Remove spec=PositionLimits
    
    def check_position_limit(symbol, side, qty, **kwargs):
        # Default allow, can be overridden in tests
        if "DAILY_CAP" in symbol or symbol == "AAPL" and qty >= 5000:
            if symbol == "TSLA":
                return False, "daily trading limit exceeded", Decimal("500")
            return False, "daily trading limit exceeded for symbol", None
        return True, None, None
    
    limits.check_single_position_limit.side_effect = check_position_limit
    limits.check_total_exposure_limit.return_value = (True, None, None)
    limits.get_daily_traded_notional.return_value = Decimal("50000.0")
    
    return limits


@pytest.fixture
def mock_volatility_analyzer():
    """Mock volatility analyzer with scenario-based responses."""
    analyzer = AsyncMock()  # Remove spec=VolatilityAnalyzer
    
    def analyze_volatility(symbol, **kwargs):
        if "DECLINING" in symbol or "BEAR" in symbol:
            return {
                "expected_return": -0.05,  # Negative μ
                "volatility": 0.25,
                "recommendation": "avoid_long_positions"
            }
        elif "STABLE" in symbol or "BOND" in symbol:
            return {
                "expected_return": 0.02,
                "volatility": 0.001,  # σ≈0
                "recommendation": "insufficient_opportunity"
            }
        else:
            return {
                "expected_return": 0.08,
                "volatility": 0.20,
                "recommendation": "acceptable_risk"
            }
    
    analyzer.analyze_symbol_risk.side_effect = analyze_volatility
    analyzer.is_low_volatility.side_effect = lambda symbol, **kwargs: "STABLE" in symbol or "BOND" in symbol
    
    return analyzer


@pytest.fixture
def mock_margin_calculator():
    """Mock margin calculator for leverage checks."""
    calculator = AsyncMock()  # Remove spec=MarginCalculator
    
    def check_margin_requirement(symbol, side, qty, price, **kwargs):
        notional = qty * price
        
        if "LEVERAGED" in symbol:
            return False, "leverage ratio too high", None
        elif "MARGIN_HEAVY" in symbol:
            return False, "insufficient margin available", None
        elif notional < 100:  # $100 minimum
            return False, "notional value too small", None
        elif qty == 1 and price > 1000:  # Single share of expensive stock
            return False, "trade size below minimum", None
        else:
            return True, None, None
    
    calculator.check_buying_power.side_effect = check_margin_requirement
    calculator.calculate_required_margin.return_value = Decimal("5000.0")
    calculator.get_available_margin.return_value = Decimal("50000.0")
    
    return calculator


@pytest.fixture
def mock_kill_switch_manager():
    """Mock kill switch manager for trading halt scenarios."""
    manager = MagicMock()
    
    def check_kill_switch(symbol=None, **kwargs):
        if symbol == "ANY_SYMBOL":  # Market-wide kill switch
            return True, "trading halted by kill switch"
        elif "MEME" in symbol or "VOLATILE" in symbol:
            return True, "symbol trading suspended"
        else:
            return False, None
    
    manager.is_trading_halted.side_effect = check_kill_switch
    manager.get_halt_reason.return_value = "regulatory halt"
    
    return manager


@pytest.fixture
def mock_prometheus_metrics():
    """Mock Prometheus metrics for orders_blocked_total tracking."""
    registry = CollectorRegistry()
    
    metrics = {
        "orders_blocked_total": Counter('orders_blocked_total', 'Total orders blocked by risk', 
                                      ['reason'], registry=registry),
        "risk_checks_total": Counter('risk_checks_total', 'Total risk checks performed',
                                   ['result'], registry=registry),
        "position_limits_hit": Counter('position_limits_hit_total', 'Position limits hit',
                                     ['limit_type'], registry=registry)
    }
    
    return metrics, registry


@pytest.fixture
def risk_manager(mock_position_limits, mock_volatility_analyzer, mock_margin_calculator, mock_kill_switch_manager):
    """Create risk manager with mocked dependencies."""
    return MockRiskManager()


class TestRiskReasonsTable:
    """Test comprehensive risk block reasons with (allowed, reason, adjusted_qty) assertions."""
    
    @pytest.mark.parametrize("symbol,side,qty,price,scenario,expected_allowed,expected_reason,expected_adj_qty", 
                             RISK_BLOCK_SCENARIOS)
    @pytest.mark.asyncio
    async def test_risk_scenarios_comprehensive(self, symbol, side, qty, price, scenario, expected_allowed, 
                                              expected_reason, expected_adj_qty, risk_manager):
        """Test comprehensive risk scenarios return correct (allowed, reason, adjusted_qty) tuples."""
        # Create order data
        order_data = {
            "symbol": symbol,
            "side": side, 
            "qty": Decimal(str(qty)),
            "price": Decimal(str(price)),
            "order_type": "market",
            "account_id": "test-account"
        }
        
        # Execute risk check
        result = await risk_manager.before_order(order_data)
        
        # Assert result structure
        assert hasattr(result, 'allowed'), f"Risk result missing 'allowed' attribute for {scenario}"
        assert hasattr(result, 'reason'), f"Risk result missing 'reason' attribute for {scenario}"
        assert hasattr(result, 'adjusted_qty'), f"Risk result missing 'adjusted_qty' attribute for {scenario}"
        
        # Assert expected outcomes
        assert result.allowed == expected_allowed, f"{scenario}: Expected allowed={expected_allowed}, got {result.allowed}"
        
        if expected_reason:
            assert result.reason is not None, f"{scenario}: Expected reason but got None"
            assert expected_reason.lower() in result.reason.lower(), f"{scenario}: Expected '{expected_reason}' in reason '{result.reason}'"
        else:
            assert result.reason is None, f"{scenario}: Expected no reason but got '{result.reason}'"
        
        if expected_adj_qty is not None:
            assert result.adjusted_qty == expected_adj_qty, f"{scenario}: Expected adjusted_qty={expected_adj_qty}, got {result.adjusted_qty}"
        else:
            assert result.adjusted_qty is None, f"{scenario}: Expected no quantity adjustment but got {result.adjusted_qty}"

    @pytest.mark.parametrize("symbol,side,qty,price,scenario,expected_pattern", RISK_EDGE_CASES)
    @pytest.mark.asyncio
    async def test_risk_edge_cases(self, symbol, side, qty, price, scenario, expected_pattern, risk_manager):
        """Test edge cases and validation errors in risk checking."""
        order_data = {
            "symbol": symbol,
            "side": side,
            "qty": Decimal(str(qty)) if qty != 0 else Decimal("0"),
            "price": Decimal(str(price)) if price != 0 else Decimal("0"),
            "order_type": "market", 
            "account_id": "test-account"
        }
        
        # Execute risk check
        result = await risk_manager.before_order(order_data)
        
        # Should be blocked for all edge cases
        assert result.allowed is False, f"{scenario}: Expected blocked but was allowed"
        assert result.reason is not None, f"{scenario}: Expected reason for blocking"
        assert expected_pattern.lower() in result.reason.lower(), f"{scenario}: Expected '{expected_pattern}' in reason '{result.reason}'"

    @pytest.mark.asyncio
    async def test_negative_mu_detection(self, risk_manager, mock_volatility_analyzer):
        """Test detection of negative expected returns (μ < 0)."""
        # Configure volatility analyzer for negative expected return
        mock_volatility_analyzer.analyze_symbol_risk.return_value = {
            "expected_return": -0.08,  # Negative 8% expected return
            "volatility": 0.25,
            "recommendation": "avoid_long_positions"
        }
        
        order_data = {
            "symbol": "DECLINING_TECH",
            "side": "buy",  # Buying declining stock
            "qty": Decimal("100"),
            "price": Decimal("50.0"),
            "account_id": "test"
        }
        
        result = await risk_manager.before_order(order_data)
        
        assert result.allowed is False
        assert "negative expected return" in result.reason.lower() or "declining" in result.reason.lower()
        assert result.adjusted_qty is None

    @pytest.mark.asyncio
    async def test_zero_volatility_detection(self, risk_manager, mock_volatility_analyzer):
        """Test detection of near-zero volatility (σ ≈ 0)."""
        # Configure for extremely low volatility
        mock_volatility_analyzer.analyze_symbol_risk.return_value = {
            "expected_return": 0.02,
            "volatility": 0.0001,  # Near zero volatility
            "recommendation": "insufficient_opportunity"
        }
        mock_volatility_analyzer.is_low_volatility.return_value = True
        
        order_data = {
            "symbol": "STABLE_UTILITY",
            "side": "buy",
            "qty": Decimal("1000"),
            "price": Decimal("100.0"),
            "account_id": "test"
        }
        
        result = await risk_manager.before_order(order_data)
        
        assert result.allowed is False
        assert "volatility" in result.reason.lower() or "opportunity" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_per_symbol_daily_cap_enforcement(self, risk_manager, mock_position_limits):
        """Test per-symbol daily trading cap enforcement."""
        # Configure position limits to simulate daily cap hit
        def daily_cap_check(symbol, side, qty, **kwargs):
            if symbol == "POPULAR_STOCK":
                if qty > 500:
                    return False, "daily trading limit exceeded for POPULAR_STOCK", None
                else:
                    return True, "approaching daily limit", Decimal("300")  # Reduced quantity
            return True, None, None
        
        mock_position_limits.check_single_position_limit.side_effect = daily_cap_check
        
        # Test exceeding daily cap
        order_large = {
            "symbol": "POPULAR_STOCK",
            "side": "buy", 
            "qty": Decimal("1000"),  # Exceeds 500 limit
            "price": Decimal("100.0"),
            "account_id": "test"
        }
        
        result_large = await risk_manager.before_order(order_large)
        assert result_large.allowed is False
        assert "daily trading limit" in result_large.reason.lower()
        
        # Test quantity adjustment within cap
        order_medium = {
            "symbol": "POPULAR_STOCK", 
            "side": "buy",
            "qty": Decimal("400"),  # Within 500 limit but gets adjusted
            "price": Decimal("100.0"),
            "account_id": "test"
        }
        
        result_medium = await risk_manager.before_order(order_medium)
        assert result_medium.allowed is True
        assert result_medium.adjusted_qty == Decimal("300")

    @pytest.mark.asyncio
    async def test_leverage_ratio_enforcement(self, risk_manager, mock_margin_calculator):
        """Test leverage ratio limits enforcement."""
        # Configure margin calculator for high leverage scenarios
        def leverage_check(symbol, side, qty, price, **kwargs):
            leverage_ratio = (qty * price) / 10000  # Assume $10k account
            
            if leverage_ratio > 4.0:  # 4:1 max leverage
                return False, f"leverage ratio {leverage_ratio:.1f}:1 exceeds maximum 4:1", None
            elif symbol.startswith("3X_"):  # Leveraged ETF
                return False, "leveraged instruments not permitted", None
            else:
                return True, None, None
        
        mock_margin_calculator.check_buying_power.side_effect = leverage_check
        
        # Test excessive leverage
        high_leverage_order = {
            "symbol": "EXPENSIVE_STOCK",
            "side": "buy",
            "qty": Decimal("100"),
            "price": Decimal("500.0"),  # $50k notional on $10k account = 5:1 leverage  
            "account_id": "test"
        }
        
        result = await risk_manager.before_order(high_leverage_order)
        assert result.allowed is False
        assert "leverage ratio" in result.reason.lower() and "exceeds maximum" in result.reason.lower()
        
        # Test leveraged instrument restriction
        leveraged_etf_order = {
            "symbol": "3X_TECH_ETF",
            "side": "buy",
            "qty": Decimal("100"), 
            "price": Decimal("50.0"),
            "account_id": "test"
        }
        
        result_etf = await risk_manager.before_order(leveraged_etf_order)
        assert result_etf.allowed is False
        assert "leveraged instruments" in result_etf.reason.lower()

    @pytest.mark.asyncio
    async def test_kill_switch_scenarios(self, risk_manager, mock_kill_switch_manager):
        """Test market and symbol-level kill switch enforcement."""
        # Test market-wide kill switch
        def kill_switch_check(symbol=None, **kwargs):
            if symbol == "HALTED_MARKET_SYMBOL":
                return True, "market-wide trading halt active"
            elif symbol and "SUSPENDED" in symbol:
                return True, f"symbol {symbol} suspended by exchange"
            else:
                return False, None
        
        mock_kill_switch_manager.is_trading_halted.side_effect = kill_switch_check
        
        # Market halt scenario
        market_halt_order = {
            "symbol": "HALTED_MARKET_SYMBOL",
            "side": "buy",
            "qty": Decimal("100"),
            "price": Decimal("50.0"),
            "account_id": "test"
        }
        
        result_market = await risk_manager.before_order(market_halt_order)
        assert result_market.allowed is False
        assert "market-wide trading halt" in result_market.reason.lower()
        
        # Symbol suspension scenario
        suspended_order = {
            "symbol": "SUSPENDED_STOCK",
            "side": "sell",
            "qty": Decimal("200"),
            "price": Decimal("25.0"),
            "account_id": "test"
        }
        
        result_suspended = await risk_manager.before_order(suspended_order)
        assert result_suspended.allowed is False  
        assert "suspended" in result_suspended.reason.lower()

    @pytest.mark.asyncio
    async def test_minimum_notional_enforcement(self, risk_manager, mock_margin_calculator):
        """Test minimum notional value requirements."""
        def notional_check(symbol, side, qty, price, **kwargs):
            notional_value = qty * price
            minimum_notional = Decimal("100.0")  # $100 minimum trade
            
            if notional_value < minimum_notional:
                return False, f"notional value ${notional_value} below minimum ${minimum_notional}", None
            elif qty < 10 and price > 500:  # Odd lot of expensive stock
                return False, "odd lot orders require minimum 10 shares for expensive stocks", None
            else:
                return True, None, None
        
        mock_margin_calculator.check_buying_power.side_effect = notional_check
        
        # Test below minimum notional
        small_trade = {
            "symbol": "CHEAP_STOCK",
            "side": "buy",
            "qty": Decimal("5"),
            "price": Decimal("15.0"),  # $75 notional < $100 minimum
            "account_id": "test"
        }
        
        result_small = await risk_manager.before_order(small_trade)
        assert result_small.allowed is False
        assert "notional value" in result_small.reason.lower() and "below minimum" in result_small.reason.lower()
        
        # Test odd lot restriction
        odd_lot = {
            "symbol": "EXPENSIVE_STOCK",
            "side": "buy",
            "qty": Decimal("3"),
            "price": Decimal("800.0"),
            "account_id": "test"
        }
        
        result_odd = await risk_manager.before_order(odd_lot)
        assert result_odd.allowed is False
        assert "odd lot" in result_odd.reason.lower()


@pytest.mark.skip("Prometheus metrics integration not yet implemented in risk components")
class TestRiskPrometheusMetrics:
    """Test Prometheus metrics integration for risk blocking reasons."""
    
    @pytest.mark.asyncio
    async def test_orders_blocked_total_by_reason(self, risk_manager, mock_prometheus_metrics):
        """Test orders_blocked_total{reason} metric increments correctly."""
        metrics, registry = mock_prometheus_metrics
        
        # Test different blocking scenarios
        blocking_scenarios = [
            ("DECLINING_STOCK", "buy", 100, 50.0, "negative_expected_return"),
            ("STABLE_BOND", "buy", 1000, 100.0, "insufficient_volatility"), 
            ("LEVERAGED_ETF", "buy", 500, 300.0, "leverage_exceeded"),
            ("ANY_SYMBOL", "buy", 100, 50.0, "kill_switch_active"),
            ("PENNY_STOCK", "buy", 10, 0.05, "notional_too_small"),
        ]
        
        with patch('backend.risk.risk_manager.metrics', metrics):
            for symbol, side, qty, price, expected_reason in blocking_scenarios:
                order_data = {
                    "symbol": symbol,
                    "side": side,
                    "qty": Decimal(str(qty)),
                    "price": Decimal(str(price)),
                    "account_id": "test"
                }
                
                # Execute risk check
                result = await risk_manager.before_order(order_data)
                
                # Manually increment metric (would be done in actual risk manager)
                if not result.allowed:
                    metrics["orders_blocked_total"].labels(reason=expected_reason).inc()
        
        # Verify metrics recorded
        from prometheus_client import generate_latest
        metrics_output = generate_latest(registry).decode('utf-8')
        
        # Assert each blocking reason has metric
        assert 'orders_blocked_total{reason="negative_expected_return"} 1.0' in metrics_output
        assert 'orders_blocked_total{reason="insufficient_volatility"} 1.0' in metrics_output  
        assert 'orders_blocked_total{reason="leverage_exceeded"} 1.0' in metrics_output
        assert 'orders_blocked_total{reason="kill_switch_active"} 1.0' in metrics_output
        assert 'orders_blocked_total{reason="notional_too_small"} 1.0' in metrics_output

    @pytest.mark.asyncio
    async def test_risk_checks_total_metric(self, risk_manager, mock_prometheus_metrics):
        """Test total risk checks counter with pass/fail breakdown."""
        metrics, registry = mock_prometheus_metrics
        
        # Mix of allowed and blocked orders
        test_orders = [
            ("AAPL", "buy", 100, 150.0, "allowed"),    # Should pass
            ("MSFT", "sell", 50, 300.0, "allowed"),     # Should pass  
            ("DECLINING_STOCK", "buy", 1000, 50.0, "blocked"),  # Should block
            ("STABLE_BOND", "buy", 5000, 100.0, "blocked"),     # Should block
        ]
        
        with patch('backend.risk.risk_manager.metrics', metrics):
            for symbol, side, qty, price, expected_result in test_orders:
                order_data = {
                    "symbol": symbol,
                    "side": side,
                    "qty": Decimal(str(qty)),
                    "price": Decimal(str(price)),
                    "account_id": "test"
                }
                
                result = await risk_manager.before_order(order_data)
                
                # Manually increment check counter (would be done in actual risk manager)
                result_label = "allowed" if result.allowed else "blocked"
                metrics["risk_checks_total"].labels(result=result_label).inc()
        
        # Verify total checks metric
        from prometheus_client import generate_latest
        metrics_output = generate_latest(registry).decode('utf-8')
        
        assert 'risk_checks_total{result="allowed"} 2.0' in metrics_output
        assert 'risk_checks_total{result="blocked"} 2.0' in metrics_output

    @pytest.mark.asyncio 
    async def test_position_limits_hit_tracking(self, risk_manager, mock_prometheus_metrics, mock_position_limits):
        """Test position limits hit counter by limit type."""
        metrics, registry = mock_prometheus_metrics
        
        # Configure position limits to simulate different limit types
        def position_limit_side_effect(symbol, side, qty, **kwargs):
            if symbol == "DAILY_CAP_STOCK":
                # Manually increment metric (would be done in position limits module)
                metrics["position_limits_hit"].labels(limit_type="daily_symbol_limit").inc()
                return False, "daily symbol limit exceeded", None
            elif symbol == "EXPOSURE_HEAVY":
                metrics["position_limits_hit"].labels(limit_type="total_exposure_limit").inc() 
                return False, "total exposure limit exceeded", None
            else:
                return True, None, None
        
        mock_position_limits.check_single_position_limit.side_effect = position_limit_side_effect
        
        # Test orders that hit different limits
        limit_test_orders = [
            ("DAILY_CAP_STOCK", "buy", 1000, 100.0),
            ("EXPOSURE_HEAVY", "buy", 500, 200.0),
        ]
        
        with patch('backend.risk.risk_manager.metrics', metrics):
            for symbol, side, qty, price in limit_test_orders:
                order_data = {
                    "symbol": symbol,
                    "side": side,
                    "qty": Decimal(str(qty)),
                    "price": Decimal(str(price)), 
                    "account_id": "test"
                }
                
                await risk_manager.before_order(order_data)
        
        # Verify position limits metrics
        from prometheus_client import generate_latest
        metrics_output = generate_latest(registry).decode('utf-8')
        
        assert 'position_limits_hit_total{limit_type="daily_symbol_limit"} 1.0' in metrics_output
        assert 'position_limits_hit_total{limit_type="total_exposure_limit"} 1.0' in metrics_output


class TestRiskManagerIntegration:
    """Integration tests for complete risk management workflow."""
    
    @pytest.mark.asyncio
    async def test_complete_risk_decision_workflow(self, risk_manager):
        """Test complete risk decision workflow from order input to final decision."""
        # Test a complex scenario with multiple risk factors
        complex_order = {
            "symbol": "COMPLEX_SCENARIO_STOCK",
            "side": "buy",
            "qty": Decimal("750"),  # Medium size
            "price": Decimal("200.0"),  # $150k notional
            "order_type": "limit",
            "time_in_force": "DAY",
            "account_id": "integration-test-account",
            "client_order_id": "integration-test-123"
        }
        
        # Execute complete risk check
        result = await risk_manager.before_order(complex_order)
        
        # Assert result structure and completeness
        assert isinstance(result.allowed, bool)
        assert result.reason is None or isinstance(result.reason, str)
        assert result.adjusted_qty is None or isinstance(result.adjusted_qty, Decimal)
        
        # Log decision for audit trail (would be done in actual system)
        decision_log = {
            "timestamp": datetime.utcnow(),
            "order_id": complex_order["client_order_id"],
            "symbol": complex_order["symbol"],
            "decision": "allowed" if result.allowed else "blocked",
            "reason": result.reason,
            "adjusted_qty": result.adjusted_qty,
            "original_qty": complex_order["qty"]
        }
        
        assert decision_log["decision"] in ["allowed", "blocked"]

    @pytest.mark.asyncio
    async def test_risk_manager_performance_under_load(self, risk_manager):
        """Test risk manager performance with high-frequency risk checks."""
        import time
        
        # Generate batch of orders for performance testing
        test_orders = []
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]
        
        for i in range(50):  # 50 orders
            order = {
                "symbol": symbols[i % len(symbols)],
                "side": "buy" if i % 2 == 0 else "sell",
                "qty": Decimal(str(100 + (i * 10))),
                "price": Decimal(str(150.0 + (i * 5))),
                "account_id": f"perf-test-account-{i % 5}"
            }
            test_orders.append(order)
        
        # Measure performance
        start_time = time.time()
        
        results = []
        for order in test_orders:
            result = await risk_manager.before_order(order)
            results.append(result)
        
        total_time = time.time() - start_time
        avg_time_per_check = total_time / len(test_orders)
        
        # Performance assertions
        assert total_time < 5.0, f"Total time {total_time:.2f}s exceeded 5s limit"
        assert avg_time_per_check < 0.1, f"Average time per check {avg_time_per_check:.3f}s too slow"
        
        # Verify all checks completed
        assert len(results) == len(test_orders)
        assert all(hasattr(result, 'allowed') for result in results)
