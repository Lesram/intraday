# Test Metrics Registry Injection Guide

## Overview

This guide explains how to properly inject test metrics registries to avoid global counter issues and maintain test isolation. This pattern prevents metric pollution between tests and enables proper testing of metrics-dependent code.

## ⚠️ The Problem: Global Metrics

**DON'T DO THIS:**

```python
# ❌ WRONG: Global metrics registry
from prometheus_client import Counter, Histogram, REGISTRY

# Global counters - shared across all tests!
RISK_BLOCKS = Counter("risk_blocks_total", "Risk manager blocks", ["reason"])
ORDER_SUBMISSIONS = Counter("orders_submitted_total", "Orders submitted")

class RiskManager:
    def before_order(self, order):
        # This affects ALL tests!
        RISK_BLOCKS.labels(reason="position_limit").inc()
```

**Problems:**
- ✅ Metrics persist between test runs
- ✅ Tests affect each other's metric values  
- ✅ Parallel tests can interfere
- ✅ Hard to assert on specific metric changes
- ✅ Cleanup is complex and error-prone

## ✅ The Solution: Dependency Injection

### Pattern 1: Constructor Injection (Recommended)

```python
# ✅ CORRECT: Inject metrics registry
from prometheus_client import CollectorRegistry, Counter, Histogram

class RiskManager:
    def __init__(self, metrics_registry=None):
        # Use provided registry or create isolated one
        self.registry = metrics_registry or CollectorRegistry()
        
        # Create metrics bound to THIS registry
        self.risk_blocks = Counter(
            "risk_blocks_total", 
            "Risk manager blocks", 
            ["reason"],
            registry=self.registry
        )
        
        self.decision_latency = Histogram(
            "risk_decision_latency_seconds",
            "Risk decision latency", 
            registry=self.registry
        )
    
    def before_order(self, order):
        # Metrics only affect THIS instance's registry
        self.risk_blocks.labels(reason="position_limit").inc()
```

### Pattern 2: Registry Interface (Advanced)

```python
# ✅ CORRECT: Registry interface for flexibility
from abc import ABC, abstractmethod
from typing import Protocol

class MetricsRegistry(Protocol):
    def counter(self, name: str, labels: dict = None) -> None: ...
    def histogram(self, name: str) -> None: ...
    def gauge(self, name: str) -> None: ...

class PrometheusMetrics:
    def __init__(self, registry=None):
        self.registry = registry or CollectorRegistry()
        self._counters = {}
        self._histograms = {}
    
    def counter(self, name: str, labels: dict = None):
        if name not in self._counters:
            self._counters[name] = Counter(name, "", registry=self.registry)
        
        if labels:
            return self._counters[name].labels(**labels)
        return self._counters[name]

class RiskManager:
    def __init__(self, metrics: MetricsRegistry):
        self.metrics = metrics
    
    def before_order(self, order):
        # Clean interface - no prometheus details
        self.metrics.counter("risk_blocks_total", {"reason": "position_limit"}).inc()
```

## Test Implementation

### Unit Tests with Isolated Registries

```python
import pytest
from prometheus_client import CollectorRegistry

class TestRiskManager:
    
    @pytest.fixture
    def isolated_registry(self):
        """Provide isolated metrics registry per test."""
        return CollectorRegistry()
    
    @pytest.fixture  
    def risk_manager(self, isolated_registry):
        """Risk manager with isolated metrics."""
        return RiskManager(metrics_registry=isolated_registry)
    
    @pytest.mark.unit
    def test_risk_block_increments_counter(self, risk_manager, isolated_registry):
        """Test that risk blocks increment the counter correctly."""
        # Get initial metric value (should be 0)
        initial_blocks = get_metric_value(isolated_registry, "risk_blocks_total")
        assert initial_blocks == 0
        
        # Trigger risk block
        order = OrderSpec(symbol="AAPL", qty=Decimal("10000"))  # Over limit
        decision = risk_manager.before_order(order)
        
        # Assert business logic
        assert not decision.allowed
        assert decision.reason == "position_limit"
        
        # Assert metrics change
        final_blocks = get_metric_value(isolated_registry, "risk_blocks_total")
        assert final_blocks == 1
        
        # Each test gets fresh registry - no pollution!

def get_metric_value(registry, metric_name):
    """Helper to extract metric values from registry."""
    for metric_family in registry.collect():
        if metric_family.name == metric_name:
            return sum(sample.value for sample in metric_family.samples)
    return 0
```

### Mock Metrics for Fast Tests

```python
class MockMetrics:
    """Lightweight mock for tests that don't need real metrics."""
    
    def __init__(self):
        self.calls = []
    
    def counter(self, name: str, labels: dict = None):
        self.calls.append(("counter", name, labels))
        return self  # Chainable
    
    def inc(self, value=1):
        self.calls.append(("inc", value))
        return self
    
    def histogram(self, name: str):
        self.calls.append(("histogram", name))
        return self
        
    def observe(self, value):
        self.calls.append(("observe", value))
        return self

@pytest.fixture
def mock_metrics():
    return MockMetrics()

@pytest.mark.unit
def test_risk_manager_calls_metrics(mock_metrics):
    """Fast test using mock metrics."""
    risk_manager = RiskManager(metrics=mock_metrics)
    
    order = OrderSpec(symbol="AAPL", qty=Decimal("100"))
    risk_manager.before_order(order)
    
    # Assert metrics were called correctly
    assert ("counter", "risk_blocks_total", {"reason": "approved"}) in mock_metrics.calls
    assert ("inc", 1) in mock_metrics.calls
```

## Integration Tests

```python
@pytest.mark.integration
def test_metrics_endpoint_reflects_risk_decisions():
    """Integration test that metrics endpoint works with real registry."""
    # Use shared registry for integration test
    from prometheus_client import REGISTRY
    
    risk_manager = RiskManager(metrics_registry=REGISTRY)
    
    # Perform operations
    order = OrderSpec(symbol="AAPL", qty=Decimal("100"))
    risk_manager.before_order(order)
    
    # Check metrics endpoint
    response = client.get("/metrics")
    assert "risk_blocks_total" in response.text
    assert 'reason="approved"' in response.text
```

## Factory Pattern Integration

```python
# In backend/api/factory.py
def create_app(config=None, metrics_registry=None):
    """Factory with optional metrics injection."""
    
    # Use provided registry or default global one
    registry = metrics_registry or REGISTRY
    
    # Create metrics-aware services
    metrics = PrometheusMetrics(registry=registry)
    risk_manager = RiskManager(metrics=metrics)
    order_service = OrderService(metrics=metrics)
    
    # Wire up dependencies
    app = FastAPI()
    app.state.risk_manager = risk_manager
    app.state.order_service = order_service
    
    return app

# In tests
def test_app_with_isolated_metrics():
    test_registry = CollectorRegistry()
    app = create_app(metrics_registry=test_registry)
    
    # App uses isolated metrics - no cross-contamination
```

## Best Practices

### ✅ DO
- Always inject metrics registries via constructor
- Use isolated registries for unit tests
- Provide factory methods that accept registry parameters
- Use mock metrics for tests that don't need real metrics
- Clean up registries in test teardown (if needed)
- Use registry interfaces to decouple from Prometheus

### ❌ DON'T  
- Use global metrics registries in business logic
- Share registries between unrelated tests
- Create metrics in static/module scope
- Hardcode prometheus_client imports in business logic
- Forget to reset metrics between integration tests
- Mix real and mock metrics in the same test

## Migration from Global Metrics

If you have existing global metrics:

1. **Add registry parameter** to constructors
2. **Update metric creation** to use provided registry
3. **Update tests** to use isolated registries
4. **Update factories** to accept registry parameter
5. **Deprecate global metrics** with warnings
6. **Remove global metrics** after migration

```python
# Migration example
import warnings

# Old global way (deprecated)
GLOBAL_COUNTER = Counter("old_metric", "Deprecated")

class ServiceOld:
    def operation(self):
        warnings.warn("Global metrics deprecated", DeprecationWarning)
        GLOBAL_COUNTER.inc()

# New injection way  
class ServiceNew:
    def __init__(self, metrics_registry=None):
        registry = metrics_registry or CollectorRegistry() 
        self.counter = Counter("new_metric", "", registry=registry)
    
    def operation(self):
        self.counter.inc()
```

## Summary

This pattern ensures:
- 🔒 **Test Isolation**: Each test gets fresh metrics
- 🚀 **Performance**: Mock metrics for fast unit tests  
- 🧪 **Testability**: Easy to assert on metric changes
- 🔧 **Flexibility**: Support both real and test scenarios
- 🏗️ **Architecture**: Clean separation of concerns

Always inject your metrics registries - your future self (and your teammates) will thank you!
