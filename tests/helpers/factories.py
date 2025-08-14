"""
Test data factories for creating consistent test fixtures.
Provides builders for OrderSpec, signals, features, positions, and other test objects.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import random
from typing import Any
import uuid

import numpy as np
import pandas as pd

from backend.features.types import FeatureFrame, FeatureSchema

# Import our domain types
from backend.risk.types import OrderSpec
from backend.strategies.trading_strategies import OrderType
from backend.strategies.types import Side


# Factory configuration
@dataclass
class FactoryConfig:
    """Configuration for test factories."""

    seed: int = 42
    default_symbol: str = "AAPL"
    default_account_id: str = "test-account-123"
    base_price: float = 100.0
    price_variance: float = 0.1


# Initialize default config
factory_config = FactoryConfig()


def seed_random(seed: int | None = None) -> None:
    """Seed all random number generators for deterministic tests."""
    seed = seed or factory_config.seed
    random.seed(seed)
    np.random.seed(seed)


# Order factories


def create_order_spec(
    symbol: str = None,
    side: Side = None,
    order_type: OrderType = None,
    quantity: Decimal = None,
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    time_in_force: str = None,
    client_order_id: str = None,
    **kwargs,
) -> OrderSpec:
    """Create an OrderSpec for testing."""

    return OrderSpec(
        symbol=symbol or factory_config.default_symbol,
        side=side if isinstance(side, str) else (side.value if side else "buy"),
        qty=quantity or Decimal("100"),
        notional=(quantity or Decimal("100"))
        * Decimal(str(limit_price or factory_config.base_price)),
        price=limit_price,
        tif=time_in_force or "day",
        attributes={
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "order_type": (
                order_type.value
                if order_type
                else (
                    OrderType.MARKET.value if hasattr(OrderType, "MARKET") else "market"
                )
            ),
            **kwargs,
        },
    )


def create_market_buy_order(symbol: str = None, quantity: Decimal = None) -> OrderSpec:
    """Create a market buy order."""
    return create_order_spec(
        symbol=symbol,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity or Decimal("100"),
    )


def create_market_sell_order(symbol: str = None, quantity: Decimal = None) -> OrderSpec:
    """Create a market sell order."""
    return create_order_spec(
        symbol=symbol,
        side=Side.SELL,
        order_type=OrderType.MARKET,
        quantity=quantity or Decimal("100"),
    )


def create_limit_order(
    symbol: str = None,
    side: Side = None,
    quantity: Decimal = None,
    limit_price: Decimal = None,
) -> OrderSpec:
    """Create a limit order."""
    base_price = factory_config.base_price

    return create_order_spec(
        symbol=symbol,
        side=side or Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity or Decimal("100"),
        limit_price=limit_price
        or Decimal(str(base_price * 0.99)),  # Slightly below market
    )


def create_stop_loss_order(
    symbol: str = None, quantity: Decimal = None, stop_price: Decimal = None
) -> OrderSpec:
    """Create a stop-loss order."""
    base_price = factory_config.base_price

    return create_order_spec(
        symbol=symbol,
        side=Side.SELL,
        order_type=OrderType.STOP,
        quantity=quantity or Decimal("100"),
        stop_price=stop_price or Decimal(str(base_price * 0.95)),  # 5% below market
    )


# Signal factories


def create_signal_payload(
    symbol: str = None,
    signal_strength: float = None,
    timestamp: datetime = None,
    features: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Create a trading signal payload."""

    return {
        "symbol": symbol or factory_config.default_symbol,
        "signal_strength": signal_strength or 0.7,
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        "features": features or create_sample_features(),
        "metadata": {
            "model_version": "v1.0.0",
            "confidence": signal_strength or 0.7,
            "source": "test_factory",
        },
    }


def create_batch_signals(
    symbols: list[str] = None,
    count: int = 10,
    time_range: tuple[datetime, datetime] = None,
) -> list[dict[str, Any]]:
    """Create a batch of trading signals."""
    symbols = symbols or ["AAPL", "GOOGL", "MSFT", "TSLA"]

    if time_range:
        start_time, end_time = time_range
        time_delta = (end_time - start_time) / count
    else:
        start_time = datetime.now(UTC) - timedelta(hours=1)
        time_delta = timedelta(minutes=6)

    signals = []
    for i in range(count):
        signal_time = start_time + (time_delta * i)
        symbol = random.choice(symbols)

        signals.append(
            create_signal_payload(
                symbol=symbol,
                signal_strength=random.uniform(0.3, 0.9),
                timestamp=signal_time,
            )
        )

    return signals


# Feature factories


def create_sample_features(n_features: int = 20) -> dict[str, float]:
    """Create sample feature values."""
    features = {}

    # Price-based features
    features.update(
        {
            "returns_1": random.gauss(0.0, 0.02),
            "returns_5": random.gauss(0.0, 0.05),
            "sma_20": random.uniform(95.0, 105.0),
            "ema_12": random.uniform(95.0, 105.0),
            "bollinger_upper": random.uniform(102.0, 108.0),
            "bollinger_lower": random.uniform(92.0, 98.0),
        }
    )

    # Technical indicators
    features.update(
        {
            "rsi_14": random.uniform(20.0, 80.0),
            "macd": random.gauss(0.0, 0.5),
            "macd_signal": random.gauss(0.0, 0.3),
            "stochastic_k": random.uniform(0.0, 100.0),
            "williams_r": random.uniform(-100.0, 0.0),
        }
    )

    # Volume features
    features.update(
        {
            "volume_sma_10": random.uniform(800000, 1200000),
            "volume_ratio": random.uniform(0.5, 2.0),
            "vwap": random.uniform(98.0, 102.0),
            "obv": random.uniform(-1000000, 1000000),
        }
    )

    # Volatility features
    features.update(
        {
            "atr_14": random.uniform(1.0, 5.0),
            "volatility_20": random.uniform(0.15, 0.45),
            "volatility_ratio": random.uniform(0.8, 1.5),
        }
    )

    # Add more features if requested
    while len(features) < n_features:
        feature_name = f"feature_{len(features) + 1}"
        features[feature_name] = random.gauss(0.0, 1.0)

    return dict(list(features.items())[:n_features])


def create_feature_dataframe(
    n_periods: int = 100,
    n_features: int = 20,
    start_date: datetime = None,
    freq: str = "1min",
) -> pd.DataFrame:
    """Create a DataFrame of feature data for testing."""

    if start_date is None:
        start_date = datetime(2023, 1, 1, 9, 30, tzinfo=UTC)

    # Create datetime index
    dates = pd.date_range(start=start_date, periods=n_periods, freq=freq)

    # Generate feature data
    data = {}
    feature_names = list(create_sample_features(n_features).keys())

    for feature_name in feature_names[:n_features]:
        if "return" in feature_name:
            # Returns should be mean-reverting
            data[feature_name] = np.random.normal(0, 0.02, n_periods)
        elif "sma" in feature_name or "ema" in feature_name:
            # Moving averages should trend
            base = factory_config.base_price
            trend = np.cumsum(np.random.normal(0, 0.1, n_periods))
            data[feature_name] = base + trend
        elif "rsi" in feature_name:
            # RSI bounded 0-100
            data[feature_name] = 50 + 30 * np.random.beta(2, 2, n_periods) - 15
        elif "volume" in feature_name:
            # Volume always positive
            data[feature_name] = np.random.exponential(1000000, n_periods)
        else:
            # Generic feature
            data[feature_name] = np.random.normal(0, 1, n_periods)

    return pd.DataFrame(data, index=dates)


def create_feature_frame(
    n_periods: int = 100, n_features: int = 20, target_name: str = "target_return"
) -> FeatureFrame:
    """Create a FeatureFrame for testing."""

    # Create feature DataFrame
    features_df = create_feature_dataframe(n_periods, n_features)

    # Create schema
    schema = FeatureSchema(
        features=[
            {"name": col, "dtype": str(features_df[col].dtype), "nullable": True}
            for col in features_df.columns
        ],
        target_name=target_name,
        created_at=datetime.now(UTC).isoformat(),
    )

    return FeatureFrame(data=features_df, schema=schema)


# OHLCV factories


def create_ohlcv_data(
    symbol: str = None,
    n_periods: int = 100,
    start_date: datetime = None,
    freq: str = "1min",
    base_price: float = None,
) -> pd.DataFrame:
    """Create OHLCV data for testing."""

    symbol = symbol or factory_config.default_symbol
    base_price = base_price or factory_config.base_price

    if start_date is None:
        start_date = datetime(2023, 1, 1, 9, 30, tzinfo=UTC)

    # Create datetime index
    dates = pd.date_range(start=start_date, periods=n_periods, freq=freq)

    # Generate price data (random walk with small drift)
    returns = np.random.normal(0.0001, 0.02, n_periods)  # Small positive drift
    close_prices = base_price * np.exp(np.cumsum(returns))

    # Generate OHLC from close prices
    ohlcv_data = []
    for i, close in enumerate(close_prices):
        # Create realistic OHLC relationships
        high = close * (1 + abs(np.random.normal(0, 0.005)))
        low = close * (1 - abs(np.random.normal(0, 0.005)))
        open_price = close + np.random.normal(0, 0.001 * close)

        # Ensure OHLC constraints
        high = max(high, close, open_price)
        low = min(low, close, open_price)

        # Generate volume
        volume = np.random.exponential(1000)

        ohlcv_data.append(
            {
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    return pd.DataFrame(ohlcv_data, index=dates)


# Position factories


def create_position_data(
    symbol: str = None,
    quantity: Decimal = None,
    avg_price: Decimal = None,
    current_price: Decimal = None,
) -> dict[str, Any]:
    """Create position data for testing."""

    symbol = symbol or factory_config.default_symbol
    quantity = quantity or Decimal("100")
    avg_price = avg_price or Decimal(str(factory_config.base_price))
    current_price = current_price or avg_price * Decimal("1.01")  # 1% gain

    market_value = quantity * current_price
    cost_basis = quantity * avg_price
    unrealized_pl = market_value - cost_basis

    return {
        "symbol": symbol,
        "qty": str(quantity),
        "avg_entry_price": str(avg_price),
        "current_price": str(current_price),
        "market_value": str(market_value),
        "cost_basis": str(cost_basis),
        "unrealized_pl": str(unrealized_pl),
        "unrealized_plpc": (
            str((unrealized_pl / cost_basis) * 100) if cost_basis else "0.0"
        ),
        "side": "long" if quantity > 0 else "short",
        "created_at": datetime.now(UTC).isoformat(),
    }


def create_portfolio_snapshot(
    symbols: list[str] = None, total_value: Decimal = None
) -> dict[str, Any]:
    """Create a portfolio snapshot for testing."""

    symbols = symbols or ["AAPL", "GOOGL", "MSFT"]
    total_value = total_value or Decimal("100000")

    positions = []
    remaining_value = total_value

    for i, symbol in enumerate(symbols):
        if i == len(symbols) - 1:
            # Last position gets remaining value
            position_value = remaining_value
        else:
            # Random allocation
            max_allocation = remaining_value * Decimal("0.4")  # Max 40% per position
            position_value = Decimal(
                str(random.uniform(float(max_allocation * 0.1), float(max_allocation)))
            )
            remaining_value -= position_value

        # Calculate quantity and price
        price = Decimal(str(random.uniform(50, 200)))
        quantity = position_value / price

        positions.append(
            create_position_data(
                symbol=symbol,
                quantity=quantity,
                avg_price=price,
                current_price=price
                * Decimal(str(random.uniform(0.95, 1.05))),  # +/- 5%
            )
        )

    return {
        "positions": positions,
        "total_value": str(total_value),
        "cash": str(total_value * Decimal("0.1")),  # 10% cash
        "buying_power": str(total_value * Decimal("0.25")),  # 25% buying power
        "created_at": datetime.now(UTC).isoformat(),
    }


# Database record factories


def create_order_record(
    order_spec: OrderSpec = None, status: str = "submitted", broker_order_id: str = None
) -> dict[str, Any]:
    """Create an order database record."""

    if order_spec is None:
        order_spec = create_order_spec()

    return {
        "id": str(uuid.uuid4()),
        "client_order_id": order_spec.client_order_id,
        "broker_order_id": broker_order_id or str(uuid.uuid4()),
        "account_id": factory_config.default_account_id,
        "symbol": order_spec.symbol,
        "side": order_spec.side.value,
        "order_type": order_spec.order_type.value,
        "quantity": str(order_spec.quantity),
        "limit_price": str(order_spec.limit_price) if order_spec.limit_price else None,
        "stop_price": str(order_spec.stop_price) if order_spec.stop_price else None,
        "time_in_force": order_spec.time_in_force.value,
        "status": status,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "submitted_at": datetime.now(UTC) if status != "pending" else None,
    }


def create_execution_record(
    order_id: str, fill_quantity: Decimal = None, fill_price: Decimal = None
) -> dict[str, Any]:
    """Create an execution database record."""

    return {
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "fill_quantity": str(fill_quantity or Decimal("100")),
        "fill_price": str(fill_price or Decimal(str(factory_config.base_price))),
        "commission": "1.00",
        "execution_time": datetime.now(UTC),
        "created_at": datetime.now(UTC),
    }


# Bulk factories for performance testing


def create_bulk_orders(count: int = 1000) -> list[OrderSpec]:
    """Create many orders for performance testing."""
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "META", "AMZN", "NFLX"]
    sides = [Side.BUY, Side.SELL]
    order_types = [OrderType.MARKET, OrderType.LIMIT]

    orders = []
    for _ in range(count):
        orders.append(
            create_order_spec(
                symbol=random.choice(symbols),
                side=random.choice(sides),
                order_type=random.choice(order_types),
                quantity=Decimal(str(random.randint(1, 1000))),
                limit_price=(
                    Decimal(str(random.uniform(50, 200)))
                    if random.choice(order_types) == OrderType.LIMIT
                    else None
                ),
            )
        )

    return orders


def create_bulk_signals(count: int = 1000) -> list[dict[str, Any]]:
    """Create many signals for performance testing."""
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "META", "AMZN", "NFLX"] * (
        count // 8 + 1
    )

    signals = []
    base_time = datetime.now(UTC) - timedelta(hours=1)

    for i in range(count):
        signal_time = base_time + timedelta(
            seconds=i * 3.6
        )  # One signal per 3.6 seconds

        signals.append(
            create_signal_payload(
                symbol=symbols[i],
                signal_strength=random.uniform(0.1, 0.9),
                timestamp=signal_time,
            )
        )

    return signals


# Utility functions


def reset_factory_config(config: FactoryConfig = None) -> None:
    """Reset factory configuration."""
    global factory_config
    factory_config = config or FactoryConfig()


def with_deterministic_seed(seed: int = 42):
    """Decorator to run a test with deterministic randomization."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            original_random_state = random.getstate()
            original_numpy_state = np.random.get_state()

            try:
                seed_random(seed)
                return func(*args, **kwargs)
            finally:
                random.setstate(original_random_state)
                np.random.set_state(original_numpy_state)

        return wrapper

    return decorator
