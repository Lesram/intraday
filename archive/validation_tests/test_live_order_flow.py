#!/usr/bin/env python3
"""
Live Order Flow Testing System
Real Alpaca Integration with Production SLO Monitoring
"""

import asyncio
import json
import time
import uuid
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from backend.brokers.alpaca_production import (
        ProductionAlpacaClient, OrderRequest, OrderResponse, OrderSide, OrderType, get_production_alpaca_client
    )
    from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
    PRODUCTION_IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Production imports not available: {e}")
    PRODUCTION_IMPORTS_AVAILABLE = False

class TestScenario(Enum):
    """Order flow test scenarios"""
    BASIC_MARKET_ORDER = "basic_market_order"
    BASIC_LIMIT_ORDER = "basic_limit_order"
    RAPID_ORDER_BURST = "rapid_order_burst"
    STRESS_TEST = "stress_test"
    ERROR_RECOVERY = "error_recovery"
    SLO_COMPLIANCE = "slo_compliance"

@dataclass
class TestConfig:
    """Test configuration parameters"""
    scenario: TestScenario
    duration_seconds: int = 60
    orders_per_minute: int = 10
    symbols: List[str] = None
    order_types: List[OrderType] = None
    max_position_size: float = 1000.0
    price_deviation_percent: float = 0.5
    
    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        if self.order_types is None:
            self.order_types = [OrderType.MARKET, OrderType.LIMIT]

@dataclass
class TestResult:
    """Test execution result"""
    scenario: TestScenario
    start_time: datetime
    end_time: datetime
    orders_submitted: int
    orders_filled: int
    orders_failed: int
    average_latency_ms: float
    p99_latency_ms: float
    slo_violations: List[Dict[str, Any]]
    error_summary: Dict[str, int]
    success_rate: float

class LiveOrderFlowTester:
    """
    Live order flow testing with real Alpaca paper trading
    Comprehensive SLO monitoring and validation
    """
    
    def __init__(
        self, 
        alpaca_api_key: Optional[str] = None,
        alpaca_secret_key: Optional[str] = None,
        paper_trading: bool = True
    ):
        """Initialize live order flow tester"""
        
        self.logger = logging.getLogger(__name__)
        self.paper_trading = paper_trading
        
        # Initialize clients
        if PRODUCTION_IMPORTS_AVAILABLE:
            self.alpaca_client = get_production_alpaca_client(
                api_key=alpaca_api_key,
                api_secret=alpaca_secret_key,
                paper_trading=paper_trading
            )
            self.security_middleware = SecurityMiddleware()
        else:
            self.alpaca_client = None
            self.security_middleware = None
            self.logger.warning("Production components not available - running in simulation mode")
        
        # SLO Integration
        try:
            from backend.monitoring.slo_metrics import get_slo_collector
            self.slo_collector = get_slo_collector()
        except ImportError:
            self.slo_collector = None
            self.logger.warning("SLO collector not available")
        
        # Test state
        self.test_orders: Dict[str, OrderResponse] = {}
        self.latency_measurements: List[float] = []
        self.error_counts = {}
        self.slo_violations = []
        
        # Market data simulation (for realistic pricing)
        self.simulated_prices = {
            "AAPL": 150.0,
            "GOOGL": 2800.0,
            "MSFT": 350.0,
            "AMZN": 3400.0,
            "TSLA": 800.0
        }

    def _get_current_price(self, symbol: str) -> float:
        """Get current market price (simulated for testing)"""
        
        base_price = self.simulated_prices.get(symbol, 100.0)
        
        # Add random price movement (±2%)
        price_change = random.uniform(-0.02, 0.02)
        current_price = base_price * (1 + price_change)
        
        # Update simulated price
        self.simulated_prices[symbol] = current_price
        
        return round(current_price, 2)

    def _create_test_order(self, config: TestConfig) -> OrderRequest:
        """Create a test order based on configuration"""
        
        # Random symbol
        symbol = random.choice(config.symbols)
        
        # Random side
        side = random.choice([OrderSide.BUY, OrderSide.SELL])
        
        # Random order type
        order_type = random.choice(config.order_types)
        
        # Random quantity (small for testing)
        qty = random.randint(1, 10)  # Small quantities for paper trading
        
        # Create order request
        order_request = OrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            type=order_type,
            time_in_force="day"
        )
        
        # Add limit price for limit orders
        if order_type == OrderType.LIMIT:
            current_price = self._get_current_price(symbol)
            
            # Set limit price slightly away from current price
            if side == OrderSide.BUY:
                # Buy limit below market
                order_request.limit_price = current_price * (1 - config.price_deviation_percent / 100)
            else:
                # Sell limit above market
                order_request.limit_price = current_price * (1 + config.price_deviation_percent / 100)
            
            order_request.limit_price = round(order_request.limit_price, 2)
        
        return order_request

    async def _submit_test_order(self, order_request: OrderRequest) -> Optional[OrderResponse]:
        """Submit test order and measure performance"""
        
        if not self.alpaca_client:
            # Simulate order in mock mode
            return self._simulate_order_response(order_request)
        
        start_time = time.time()
        
        try:
            # Submit order through production client
            order_response = await self.alpaca_client.submit_order(order_request)
            
            # Measure latency
            latency_ms = (time.time() - start_time) * 1000
            self.latency_measurements.append(latency_ms)
            
            # Track order
            self.test_orders[order_response.order_id] = order_response
            
            self.logger.info(
                f"Order submitted: {order_request.symbol} {order_request.qty} {order_request.side.value} "
                f"(latency: {latency_ms:.1f}ms)"
            )
            
            # Check SLO compliance
            if latency_ms > 100:  # P99 SLO target
                self.slo_violations.append({
                    'type': 'latency_violation',
                    'order_id': order_response.order_id,
                    'latency_ms': latency_ms,
                    'timestamp': datetime.now()
                })
            
            return order_response
            
        except Exception as e:
            error_type = type(e).__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
            
            latency_ms = (time.time() - start_time) * 1000
            self.latency_measurements.append(latency_ms)
            
            self.logger.error(f"Order submission failed: {str(e)} (latency: {latency_ms:.1f}ms)")
            
            return None

    def _simulate_order_response(self, order_request: OrderRequest) -> OrderResponse:
        """Simulate order response for testing without real broker"""
        
        # Simulate latency
        simulated_latency = random.uniform(20, 80)  # 20-80ms
        time.sleep(simulated_latency / 1000)
        self.latency_measurements.append(simulated_latency)
        
        # Create mock response
        order_response = OrderResponse(
            order_id=str(uuid.uuid4()),
            broker_order_id=f"sim_{uuid.uuid4().hex[:8]}",
            status=random.choice(["new", "filled"]) if random.random() < 0.95 else "rejected",
            symbol=order_request.symbol,
            qty=order_request.qty,
            filled_qty=order_request.qty if random.random() < 0.9 else 0,
            side=order_request.side,
            order_type=order_request.type,
            submitted_at=datetime.now(),
            filled_avg_price=self._get_current_price(order_request.symbol) if random.random() < 0.9 else None
        )
        
        self.test_orders[order_response.order_id] = order_response
        
        return order_response

    async def run_test_scenario(self, config: TestConfig) -> TestResult:
        """Run a specific test scenario"""
        
        self.logger.info(f"Starting test scenario: {config.scenario.value}")
        self.logger.info(f"Duration: {config.duration_seconds}s, Rate: {config.orders_per_minute} orders/min")
        
        start_time = datetime.now()
        
        # Reset test state
        self.test_orders.clear()
        self.latency_measurements.clear()
        self.error_counts.clear()
        self.slo_violations.clear()
        
        orders_submitted = 0
        orders_filled = 0
        orders_failed = 0
        
        # Calculate order interval
        order_interval = 60.0 / config.orders_per_minute
        
        try:
            if config.scenario == TestScenario.BASIC_MARKET_ORDER:
                # Simple market order test
                await self._run_basic_order_test(config, order_interval)
            
            elif config.scenario == TestScenario.RAPID_ORDER_BURST:
                # Burst of rapid orders
                await self._run_burst_test(config)
            
            elif config.scenario == TestScenario.STRESS_TEST:
                # High-frequency stress test
                await self._run_stress_test(config)
            
            elif config.scenario == TestScenario.SLO_COMPLIANCE:
                # SLO compliance focused test
                await self._run_slo_compliance_test(config, order_interval)
            
            else:
                # Default basic test
                await self._run_basic_order_test(config, order_interval)
        
        except Exception as e:
            self.logger.error(f"Test scenario failed: {str(e)}")
        
        end_time = datetime.now()
        
        # Calculate statistics
        orders_submitted = len(self.test_orders)
        orders_filled = len([o for o in self.test_orders.values() if o.filled_qty > 0])
        orders_failed = len([o for o in self.test_orders.values() if o.error_message])
        
        avg_latency = sum(self.latency_measurements) / len(self.latency_measurements) if self.latency_measurements else 0
        p99_latency = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.99)] if self.latency_measurements else 0
        success_rate = (orders_filled / orders_submitted * 100) if orders_submitted > 0 else 0
        
        # Create result
        result = TestResult(
            scenario=config.scenario,
            start_time=start_time,
            end_time=end_time,
            orders_submitted=orders_submitted,
            orders_filled=orders_filled,
            orders_failed=orders_failed,
            average_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            slo_violations=self.slo_violations.copy(),
            error_summary=self.error_counts.copy(),
            success_rate=success_rate
        )
        
        self._log_test_results(result)
        
        return result

    async def _run_basic_order_test(self, config: TestConfig, order_interval: float):
        """Run basic order test scenario"""
        
        test_end_time = time.time() + config.duration_seconds
        
        while time.time() < test_end_time:
            # Create and submit order
            order_request = self._create_test_order(config)
            await self._submit_test_order(order_request)
            
            # Wait for next order
            await asyncio.sleep(order_interval)

    async def _run_burst_test(self, config: TestConfig):
        """Run burst test scenario (rapid orders)"""
        
        burst_size = 10
        burst_interval = config.duration_seconds / 6  # 6 bursts
        
        for burst in range(6):
            self.logger.info(f"Starting burst {burst + 1}/6 ({burst_size} orders)")
            
            # Submit burst of orders rapidly
            tasks = []
            for _ in range(burst_size):
                order_request = self._create_test_order(config)
                task = asyncio.create_task(self._submit_test_order(order_request))
                tasks.append(task)
            
            # Wait for all orders in burst to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait before next burst
            if burst < 5:  # Don't wait after last burst
                await asyncio.sleep(burst_interval)

    async def _run_stress_test(self, config: TestConfig):
        """Run stress test scenario (high frequency)"""
        
        # Override to very high frequency
        high_frequency_interval = 0.5  # 2 orders per second
        test_end_time = time.time() + config.duration_seconds
        
        while time.time() < test_end_time:
            order_request = self._create_test_order(config)
            
            # Fire and forget to maintain high frequency
            asyncio.create_task(self._submit_test_order(order_request))
            
            await asyncio.sleep(high_frequency_interval)

    async def _run_slo_compliance_test(self, config: TestConfig, order_interval: float):
        """Run SLO compliance focused test"""
        
        test_end_time = time.time() + config.duration_seconds
        slo_check_interval = 10  # Check SLO every 10 seconds
        last_slo_check = time.time()
        
        while time.time() < test_end_time:
            # Submit order
            order_request = self._create_test_order(config)
            await self._submit_test_order(order_request)
            
            # Periodic SLO compliance check
            if time.time() - last_slo_check > slo_check_interval:
                await self._check_slo_compliance()
                last_slo_check = time.time()
            
            await asyncio.sleep(order_interval)

    async def _check_slo_compliance(self):
        """Check real-time SLO compliance"""
        
        if not self.slo_collector:
            return
        
        try:
            # Get current SLO compliance
            compliance_data = self.slo_collector.calculate_slo_compliance("order_submission_latency_p99")
            
            if compliance_data:
                burn_rate = compliance_data.get('burn_rate', 0.0)
                
                if burn_rate > 1.0:  # Exceeding error budget
                    self.slo_violations.append({
                        'type': 'slo_burn_rate_violation',
                        'burn_rate': burn_rate,
                        'timestamp': datetime.now()
                    })
                    
                    self.logger.warning(f"SLO burn rate violation detected: {burn_rate:.2f}x")
        
        except Exception as e:
            self.logger.error(f"SLO compliance check failed: {str(e)}")

    def _log_test_results(self, result: TestResult):
        """Log comprehensive test results"""
        
        self.logger.info("=" * 60)
        self.logger.info(f"TEST RESULTS: {result.scenario.value}")
        self.logger.info("=" * 60)
        
        duration = (result.end_time - result.start_time).total_seconds()
        
        self.logger.info(f"Duration: {duration:.1f}s")
        self.logger.info(f"Orders Submitted: {result.orders_submitted}")
        self.logger.info(f"Orders Filled: {result.orders_filled}")
        self.logger.info(f"Orders Failed: {result.orders_failed}")
        self.logger.info(f"Success Rate: {result.success_rate:.1f}%")
        self.logger.info(f"Average Latency: {result.average_latency_ms:.1f}ms")
        self.logger.info(f"P99 Latency: {result.p99_latency_ms:.1f}ms")
        
        # SLO compliance
        slo_compliant = result.p99_latency_ms <= 100.0
        self.logger.info(f"SLO Compliance (P99 <100ms): {'✅ PASS' if slo_compliant else '❌ FAIL'}")
        
        if result.slo_violations:
            self.logger.warning(f"SLO Violations: {len(result.slo_violations)}")
            for violation in result.slo_violations:
                self.logger.warning(f"  - {violation}")
        
        if result.error_summary:
            self.logger.info(f"Error Summary: {result.error_summary}")

    def save_test_report(self, results: List[TestResult], output_file: str = "live_order_flow_report.json"):
        """Save comprehensive test report"""
        
        report_data = {
            'test_execution': {
                'timestamp': datetime.now().isoformat(),
                'total_scenarios': len(results),
                'paper_trading_mode': self.paper_trading,
                'alpaca_client_available': self.alpaca_client is not None,
                'slo_monitoring_available': self.slo_collector is not None
            },
            'scenarios': []
        }
        
        overall_stats = {
            'total_orders': 0,
            'total_filled': 0,
            'total_failed': 0,
            'total_slo_violations': 0,
            'average_latency': 0,
            'p99_latency': 0
        }
        
        for result in results:
            scenario_data = asdict(result)
            scenario_data['start_time'] = result.start_time.isoformat()
            scenario_data['end_time'] = result.end_time.isoformat()
            scenario_data['scenario'] = result.scenario.value
            
            report_data['scenarios'].append(scenario_data)
            
            # Accumulate stats
            overall_stats['total_orders'] += result.orders_submitted
            overall_stats['total_filled'] += result.orders_filled
            overall_stats['total_failed'] += result.orders_failed
            overall_stats['total_slo_violations'] += len(result.slo_violations)
        
        # Calculate overall averages
        if results:
            overall_stats['average_latency'] = sum(r.average_latency_ms for r in results) / len(results)
            overall_stats['p99_latency'] = max(r.p99_latency_ms for r in results)
            overall_stats['success_rate'] = (overall_stats['total_filled'] / overall_stats['total_orders'] * 100) if overall_stats['total_orders'] > 0 else 0
        
        report_data['overall_statistics'] = overall_stats
        
        # Save report
        try:
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            self.logger.info(f"Test report saved: {output_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save test report: {str(e)}")

async def run_live_order_flow_tests():
    """Run comprehensive live order flow tests"""
    
    print("🚀 Live Order Flow Testing with Real Alpaca Integration")
    print("=" * 60)
    
    # Initialize tester (will use mock if Alpaca not available)
    tester = LiveOrderFlowTester(paper_trading=True)
    
    # Test scenarios
    test_scenarios = [
        TestConfig(
            scenario=TestScenario.BASIC_MARKET_ORDER,
            duration_seconds=30,
            orders_per_minute=20,
            order_types=[OrderType.MARKET]
        ),
        TestConfig(
            scenario=TestScenario.BASIC_LIMIT_ORDER,
            duration_seconds=30,
            orders_per_minute=15,
            order_types=[OrderType.LIMIT]
        ),
        TestConfig(
            scenario=TestScenario.RAPID_ORDER_BURST,
            duration_seconds=60,
            orders_per_minute=60  # High frequency
        ),
        TestConfig(
            scenario=TestScenario.SLO_COMPLIANCE,
            duration_seconds=90,
            orders_per_minute=30
        )
    ]
    
    results = []
    
    # Run each test scenario
    for i, config in enumerate(test_scenarios):
        print(f"\n🧪 Running Test {i+1}/{len(test_scenarios)}: {config.scenario.value}")
        
        try:
            result = await tester.run_test_scenario(config)
            results.append(result)
            
            # Brief pause between tests
            if i < len(test_scenarios) - 1:
                print("   ⏸️  Pausing 10s before next test...")
                await asyncio.sleep(10)
        
        except Exception as e:
            print(f"   ❌ Test failed: {str(e)}")
    
    # Generate comprehensive report
    print(f"\n📊 COMPREHENSIVE TEST SUMMARY")
    print("=" * 60)
    
    if results:
        total_orders = sum(r.orders_submitted for r in results)
        total_filled = sum(r.orders_filled for r in results)
        total_violations = sum(len(r.slo_violations) for r in results)
        
        avg_latency = sum(r.average_latency_ms for r in results) / len(results)
        max_p99_latency = max(r.p99_latency_ms for r in results)
        overall_success_rate = (total_filled / total_orders * 100) if total_orders > 0 else 0
        
        print(f"Total Orders: {total_orders}")
        print(f"Total Filled: {total_filled}")
        print(f"Success Rate: {overall_success_rate:.1f}%")
        print(f"Average Latency: {avg_latency:.1f}ms")
        print(f"Max P99 Latency: {max_p99_latency:.1f}ms")
        print(f"SLO Violations: {total_violations}")
        
        # SLO compliance assessment
        slo_compliant = max_p99_latency <= 100.0 and total_violations == 0
        print(f"\n🎯 SLO Compliance: {'✅ PASS' if slo_compliant else '❌ FAIL'}")
        
        if slo_compliant:
            print("   ✓ P99 latency under 100ms")
            print("   ✓ No SLO violations detected")
            print("   ✓ System ready for production load")
        else:
            print("   ⚠️  Performance optimization needed")
        
        # Save detailed report
        tester.save_test_report(results)
        
        return slo_compliant
    
    else:
        print("❌ No test results available")
        return False

def main():
    """Main test execution"""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    success = asyncio.run(run_live_order_flow_tests())
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)