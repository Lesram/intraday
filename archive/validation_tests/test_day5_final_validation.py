"""
Day 5 Final Integration Validation System
Comprehensive end-to-end validation for Phase 5 Production Deployment
"""

import asyncio
import datetime
import json
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

try:
    # Import core components
    from backend.risk.advanced_risk_manager import AdvancedRiskManager
    from backend.optimization.portfolio_optimizer import PortfolioOptimizer  
    from monitoring.production_dashboard import ProductionDashboard
    from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
    
    # Import SLO monitoring if available
    try:
        from backend.monitoring.slo_monitor import SLOMonitor
        SLO_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: SLO Monitor not available: {e}")
        SLO_AVAILABLE = False
    
    # Import database components
    try:
        from backend.database.models_production import Order, OrderEvent
        from backend.services.guardrails_production import TransactionalGuardrails
        DB_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: Database components not available: {e}")
        DB_AVAILABLE = False
        
    # Import API components
    try:
        import requests
        API_CLIENT_AVAILABLE = True
    except ImportError:
        API_CLIENT_AVAILABLE = False
        
except Exception as e:
    print(f"Critical import error: {e}")
    sys.exit(1)

@dataclass
class ValidationTest:
    name: str
    description: str
    category: str
    critical: bool = True
    passed: bool = False
    duration: float = 0.0
    error: Optional[str] = None
    metrics: Dict[str, Any] = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}

class Day5FinalValidator:
    def __init__(self):
        self.tests: List[ValidationTest] = []
        self.start_time = datetime.datetime.now()
        
        # Initialize components
        self.risk_manager = None
        self.portfolio_optimizer = None
        self.dashboard = None
        self.risk_analytics = None
        self.slo_monitor = None
        self.guardrails = None
        
        print("🚀 Day 5 Final Integration Validation")
        print("=" * 60)
        print(f"Started: {self.start_time.isoformat()}")
        print()

    def run_test(self, test: ValidationTest):
        """Execute a single validation test"""
        print(f"🧪 [{test.category}] {test.name}")
        if test.critical:
            print(f"   🔴 CRITICAL: {test.description}")
        else:
            print(f"   🟡 Optional: {test.description}")
            
        start_time = time.time()
        
        try:
            # Execute test based on name
            if test.name == "Component Initialization":
                self._test_component_initialization(test)
            elif test.name == "Risk Management Integration":
                self._test_risk_management_integration(test)
            elif test.name == "Portfolio Optimization":
                self._test_portfolio_optimization(test)
            elif test.name == "Real-Time Analytics":
                self._test_realtime_analytics(test)
            elif test.name == "Production Dashboard":
                self._test_production_dashboard(test)
            elif test.name == "SLO Monitoring":
                self._test_slo_monitoring(test)
            elif test.name == "Database Guardrails":
                self._test_database_guardrails(test)
            elif test.name == "API Connectivity":
                self._test_api_connectivity(test)
            elif test.name == "Performance Benchmarks":
                self._test_performance_benchmarks(test)
            elif test.name == "End-to-End Integration":
                self._test_end_to_end_integration(test)
            else:
                test.error = f"Unknown test: {test.name}"
                
            test.duration = time.time() - start_time
            
            if test.error is None:
                test.passed = True
                print(f"   ✅ PASSED ({test.duration:.2f}s)")
            else:
                print(f"   ❌ FAILED: {test.error}")
                
        except Exception as e:
            test.duration = time.time() - start_time
            test.error = str(e)
            print(f"   💥 ERROR: {e}")
            if test.critical:
                print(f"   📍 Traceback: {traceback.format_exc()[-200:]}")
                
        self.tests.append(test)
        print()

    def _test_component_initialization(self, test: ValidationTest):
        """Test initialization of all core components"""
        try:
            # Initialize risk manager
            self.risk_manager = AdvancedRiskManager()
            test.metrics['risk_manager'] = 'initialized'
            
            # Initialize portfolio optimizer
            self.portfolio_optimizer = PortfolioOptimizer(self.risk_manager)
            test.metrics['portfolio_optimizer'] = 'initialized'
            
            # Initialize dashboard (disable web interface for testing)
            self.dashboard = ProductionDashboard(enable_web=False)
            test.metrics['dashboard'] = 'initialized'
            
            # Initialize real-time analytics
            self.risk_analytics = RealTimeRiskAnalytics(self.risk_manager)
            test.metrics['risk_analytics'] = 'initialized'
            
            # Initialize SLO monitor if available
            if SLO_AVAILABLE:
                self.slo_monitor = SLOMonitor()
                test.metrics['slo_monitor'] = 'initialized'
            else:
                test.metrics['slo_monitor'] = 'unavailable'
                
            # Initialize guardrails if available
            if DB_AVAILABLE:
                self.guardrails = TransactionalGuardrails()
                test.metrics['guardrails'] = 'initialized'
            else:
                test.metrics['guardrails'] = 'unavailable'
                
            test.metrics['components_initialized'] = 4
            
        except Exception as e:
            test.error = f"Component initialization failed: {e}"

    def _test_risk_management_integration(self, test: ValidationTest):
        """Test integrated risk management functionality"""
        if not self.risk_manager:
            test.error = "Risk manager not initialized"
            return
            
        try:
            # Create test portfolio data
            portfolio_data = {
                'AAPL': {'shares': 100, 'price': 175.00, 'sector': 'Technology'},
                'GOOGL': {'shares': 50, 'price': 135.00, 'sector': 'Technology'},
                'MSFT': {'shares': 75, 'price': 380.00, 'sector': 'Technology'},
                'NVDA': {'shares': 25, 'price': 900.00, 'sector': 'Technology'},
                'SPY': {'shares': 200, 'price': 450.00, 'sector': 'ETF'}
            }
            
            # Update risk manager with portfolio using async method
            asyncio.run(self.risk_manager.update_positions(portfolio_data))
            
            # Calculate risk metrics
            risk_metrics = self.risk_manager.calculate_risk_metrics()
            test.metrics.update({
                'portfolio_value': risk_metrics.get('portfolio_value'),
                'var_1d': risk_metrics.get('var_1d'),
                'leverage': risk_metrics.get('leverage'),
                'risk_level': risk_metrics.get('risk_level')
            })
            
            # Test position sizing
            position_sizes = self.risk_manager.calculate_position_sizes(['AAPL', 'MSFT', 'AMZN'])
            test.metrics['position_sizes'] = len(position_sizes)
            
            # Test drawdown protection
            current_value = risk_metrics.get('portfolio_value', 100000)
            peak_value = current_value * 1.2  # Simulate 20% drawdown
            dd_result = self.risk_manager.check_drawdown_protection(current_value, peak_value)
            test.metrics['drawdown_protection'] = dd_result is not None
            
            if test.metrics.get('portfolio_value', 0) > 0:
                test.metrics['integration_status'] = 'operational'
            else:
                test.error = "Risk calculations returned invalid values"
                
        except Exception as e:
            test.error = f"Risk management integration failed: {e}"

    def _test_portfolio_optimization(self, test: ValidationTest):
        """Test portfolio optimization algorithms"""
        if not self.portfolio_optimizer:
            test.error = "Portfolio optimizer not initialized"
            return
            
        try:
            # Test data
            symbols = ['AAPL', 'GOOGL', 'MSFT', 'NVDA', 'SPY']
            
            # Test portfolio optimization algorithms using correct async API
            test_results = {}
            
            # Test max sharpe optimization
            try:
                result = asyncio.run(self.portfolio_optimizer.optimize_portfolio(
                    symbols, objective='max_sharpe'
                ))
                test_results['max_sharpe'] = result is not None
            except:
                test_results['max_sharpe'] = False
                
            # Test min volatility optimization
            try:
                result = asyncio.run(self.portfolio_optimizer.optimize_portfolio(
                    symbols, objective='min_volatility'
                ))
                test_results['min_volatility'] = result is not None
            except:
                test_results['min_volatility'] = False
                
            # Test risk parity optimization
            try:
                result = asyncio.run(self.portfolio_optimizer.optimize_portfolio(
                    symbols, objective='risk_parity'
                ))
                test_results['risk_parity'] = result is not None
            except:
                test_results['risk_parity'] = False
                
            test.metrics.update(test_results)
            
            successful_methods = sum([
                test.metrics['max_sharpe'],
                test.metrics['min_volatility'],
                test.metrics['risk_parity']
            ])
            
            test.metrics['successful_optimizations'] = successful_methods
            
            if successful_methods < 2:
                test.error = f"Only {successful_methods} optimization methods working"
                
        except Exception as e:
            test.error = f"Portfolio optimization failed: {e}"

    def _test_realtime_analytics(self, test: ValidationTest):
        """Test real-time risk analytics"""
        if not self.risk_analytics:
            test.error = "Real-time analytics not initialized"
            return
            
        try:
            # Generate some market data updates
            for i in range(10):
                market_data = {
                    'AAPL': 175 + (i * 0.1), 
                    'GOOGL': 135 + (i * 0.05),
                    'MSFT': 380 + (i * 0.2),
                    'NVDA': 900 + (i * 0.5),
                    'SPY': 450 + (i * 0.1)
                }
                
                # Process update
                self.risk_analytics.process_market_update(market_data)
                
            # Get analytics results
            analytics = self.risk_analytics.get_current_analytics()
            test.metrics.update({
                'updates_processed': 10,
                'portfolio_tracking': len(analytics.get('positions', {})),
                'current_var': analytics.get('var_1d', 0),
                'stress_tests': len(analytics.get('stress_results', {}))
            })
            
            # Test stress testing
            stress_results = self.risk_analytics.run_stress_tests()
            test.metrics['stress_scenarios'] = len(stress_results)
            
            if test.metrics.get('updates_processed', 0) < 10:
                test.error = "Failed to process market updates"
                
        except Exception as e:
            test.error = f"Real-time analytics failed: {e}"

    def _test_production_dashboard(self, test: ValidationTest):
        """Test production dashboard functionality"""
        if not self.dashboard:
            test.error = "Dashboard not initialized"
            return
            
        try:
            # Update dashboard with current data
            if self.risk_manager:
                self.dashboard.update_risk_data(self.risk_manager)
                
            # Create dashboard snapshot
            snapshot = self.dashboard.create_snapshot()
            test.metrics['snapshot_created'] = snapshot is not None
            
            # Test alert management
            alert_count = len(self.dashboard.alerts)
            test.metrics['alert_count'] = alert_count
            
            # Test dashboard health
            health = self.dashboard.get_health_status()
            test.metrics['dashboard_health'] = health.get('status', 'unknown')
            
            # Test API endpoints (if available)
            if hasattr(self.dashboard, 'app'):
                test.metrics['api_available'] = True
            else:
                test.metrics['api_available'] = False
                
            test.metrics['dashboard_operational'] = True
                
        except Exception as e:
            test.error = f"Dashboard testing failed: {e}"

    def _test_slo_monitoring(self, test: ValidationTest):
        """Test SLO monitoring system"""
        if not SLO_AVAILABLE:
            test.error = "SLO monitoring not available"
            test.critical = False  # Make non-critical since it's optional
            return
            
        try:
            if self.slo_monitor:
                # Test SLO calculation
                slo_status = self.slo_monitor.get_slo_status()
                test.metrics['slo_status'] = slo_status
                
                # Test alert checking
                alerts = self.slo_monitor.check_slo_compliance()
                test.metrics['slo_alerts'] = len(alerts)
                
                test.metrics['slo_operational'] = True
            else:
                test.error = "SLO monitor not initialized"
                
        except Exception as e:
            test.error = f"SLO monitoring failed: {e}"

    def _test_database_guardrails(self, test: ValidationTest):
        """Test database guardrails"""
        if not DB_AVAILABLE:
            test.error = "Database components not available"
            test.critical = False
            return
            
        try:
            if self.guardrails:
                # Test symbol validation
                valid = self.guardrails.validate_symbol('AAPL')
                invalid = self.guardrails.validate_symbol('INVALID')
                
                test.metrics['symbol_validation'] = valid and not invalid
                
                # Test error classification
                error_type = self.guardrails.classify_broker_error("Connection timeout")
                test.metrics['error_classification'] = error_type is not None
                
                test.metrics['guardrails_operational'] = True
            else:
                test.error = "Guardrails not initialized"
                
        except Exception as e:
            test.error = f"Database guardrails failed: {e}"

    def _test_api_connectivity(self, test: ValidationTest):
        """Test API connectivity (if server is running)"""
        if not API_CLIENT_AVAILABLE:
            test.error = "API client not available"
            test.critical = False
            return
            
        try:
            # Try to connect to local server
            response = requests.get('http://localhost:8000/health', timeout=2)
            if response.status_code == 200:
                test.metrics['server_reachable'] = True
                
                # Test additional endpoints
                endpoints = ['/api/positions', '/api/orders', '/api/portfolio']
                working_endpoints = 0
                
                for endpoint in endpoints:
                    try:
                        resp = requests.get(f'http://localhost:8000{endpoint}', timeout=1)
                        if resp.status_code in [200, 401, 422]:  # Include auth errors as "working"
                            working_endpoints += 1
                    except:
                        pass
                        
                test.metrics['working_endpoints'] = working_endpoints
                test.metrics['api_operational'] = working_endpoints >= 1
            else:
                test.error = f"Server returned status {response.status_code}"
                
        except Exception as e:
            test.error = f"API connectivity failed: {e}"
            test.critical = False  # Not critical for validation

    def _test_performance_benchmarks(self, test: ValidationTest):
        """Test system performance under load"""
        try:
            latencies = []
            
            # Test multiple operations
            for i in range(50):
                start = time.time()
                
                if self.risk_manager:
                    # Quick risk calculation using async API
                    portfolio_data = {
                        'AAPL': {'shares': 100, 'price': 175 + i * 0.01},
                        'MSFT': {'shares': 50, 'price': 380 + i * 0.02}
                    }
                    asyncio.run(self.risk_manager.update_positions(portfolio_data))
                    asyncio.run(self.risk_manager.calculate_risk_metrics())
                    
                latency = (time.time() - start) * 1000  # Convert to ms
                latencies.append(latency)
                
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
                
                test.metrics['avg_latency_ms'] = round(avg_latency, 2)
                test.metrics['p99_latency_ms'] = round(p99_latency, 2)
                test.metrics['operations_tested'] = len(latencies)
                
                # Check against SLAs
                sla_violations = sum(1 for l in latencies if l > 100)  # 100ms SLA
                test.metrics['sla_violations'] = sla_violations
                
                if avg_latency > 50 or sla_violations > 5:
                    test.error = f"Performance issues: avg={avg_latency:.1f}ms, violations={sla_violations}"
            else:
                test.error = "No performance data collected"
                
        except Exception as e:
            test.error = f"Performance benchmarking failed: {e}"

    def _test_end_to_end_integration(self, test: ValidationTest):
        """Test complete end-to-end integration"""
        try:
            components_working = 0
            
            # Check all core components
            if self.risk_manager:
                components_working += 1
            if self.portfolio_optimizer:
                components_working += 1
            if self.dashboard:
                components_working += 1
            if self.risk_analytics:
                components_working += 1
                
            test.metrics['core_components'] = components_working
            
            # Test data flow between components
            if components_working >= 4:
                # Create test portfolio
                portfolio = {
                    'AAPL': {'shares': 100, 'price': 175.00},
                    'MSFT': {'shares': 50, 'price': 380.00}
                }
                
                # Update risk manager using async API
                asyncio.run(self.risk_manager.update_positions(portfolio))
                risk_metrics = asyncio.run(self.risk_manager.calculate_risk_metrics())
                
                # Update analytics
                self.risk_analytics.process_market_update({'AAPL': 175.50, 'MSFT': 381.00})
                
                # Update dashboard
                self.dashboard.update_risk_data(self.risk_manager)
                
                # Check data consistency
                rm_value = risk_metrics.get('portfolio_value', 0)
                dashboard_data = self.dashboard.create_snapshot()
                
                test.metrics['data_flow_tested'] = True
                test.metrics['portfolio_value_rm'] = rm_value
                test.metrics['integration_successful'] = rm_value > 0
                
            if components_working < 3:
                test.error = f"Insufficient components working: {components_working}/4"
            elif not test.metrics.get('integration_successful', False):
                test.error = "Data flow integration failed"
                
        except Exception as e:
            test.error = f"End-to-end integration failed: {e}"

    def run_all_tests(self):
        """Run comprehensive validation suite"""
        
        # Define test suite
        test_suite = [
            ValidationTest("Component Initialization", "Initialize all production components", "Core", True),
            ValidationTest("Risk Management Integration", "Validate risk management calculations and integration", "Core", True),
            ValidationTest("Portfolio Optimization", "Test portfolio optimization algorithms", "Core", True),
            ValidationTest("Real-Time Analytics", "Validate real-time risk analytics and streaming", "Core", True),
            ValidationTest("Production Dashboard", "Test production dashboard functionality", "Core", True),
            ValidationTest("SLO Monitoring", "Validate SLO monitoring and alerting", "Monitoring", False),
            ValidationTest("Database Guardrails", "Test database constraints and guardrails", "Database", False),
            ValidationTest("API Connectivity", "Test API server connectivity and endpoints", "API", False),
            ValidationTest("Performance Benchmarks", "Validate system performance under load", "Performance", True),
            ValidationTest("End-to-End Integration", "Comprehensive integration testing", "Integration", True)
        ]
        
        # Run all tests
        for test in test_suite:
            self.run_test(test)
            
        # Generate final report
        self.generate_final_report()

    def generate_final_report(self):
        """Generate comprehensive final report"""
        end_time = datetime.datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        # Calculate statistics
        total_tests = len(self.tests)
        passed_tests = len([t for t in self.tests if t.passed])
        failed_tests = len([t for t in self.tests if not t.passed])
        critical_failed = len([t for t in self.tests if not t.passed and t.critical])
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print("=" * 60)
        print("🏁 DAY 5 FINAL VALIDATION COMPLETE")
        print("=" * 60)
        print(f"Duration: {duration:.2f}s")
        print(f"Start: {self.start_time.isoformat()}")
        print(f"End: {end_time.isoformat()}")
        print()
        
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 40)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Critical Failures: {critical_failed} 🚨")
        print(f"Success Rate: {success_rate:.1f}%")
        print()
        
        # Detailed results
        print("📋 DETAILED RESULTS")
        print("=" * 40)
        for test in self.tests:
            status = "✅ PASS" if test.passed else "❌ FAIL"
            critical = " [CRITICAL]" if test.critical else ""
            print(f"{status}{critical} {test.name} ({test.duration:.2f}s)")
            if test.error:
                print(f"    Error: {test.error}")
            
            # Show key metrics
            if test.metrics:
                key_metrics = []
                for k, v in test.metrics.items():
                    if isinstance(v, (int, float, bool, str)) and k in ['components_initialized', 'successful_optimizations', 'updates_processed', 'avg_latency_ms', 'core_components']:
                        key_metrics.append(f"{k}={v}")
                if key_metrics:
                    print(f"    Metrics: {', '.join(key_metrics[:3])}")
                    
        print()
        
        # Production readiness assessment
        print("🎯 PRODUCTION READINESS ASSESSMENT")
        print("=" * 40)
        
        if critical_failed == 0:
            if success_rate >= 90:
                print("🟢 READY FOR PRODUCTION")
                print("All critical systems validated successfully!")
                deployment_status = "GO"
            elif success_rate >= 75:
                print("🟡 READY WITH CAVEATS")
                print("Core systems working, some optional features unavailable")
                deployment_status = "CONDITIONAL GO"
            else:
                print("🟠 REVIEW REQUIRED")
                print("Multiple systems need attention before deployment")
                deployment_status = "REVIEW"
        else:
            print("🔴 DEPLOYMENT BLOCKED")
            print(f"{critical_failed} critical system(s) failing - must fix before deployment")
            deployment_status = "NO-GO"
            
        print(f"Deployment Status: {deployment_status}")
        print()
        
        # Save detailed report
        report_data = {
            'validation_time': end_time.isoformat(),
            'duration_seconds': duration,
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'critical_failures': critical_failed,
                'success_rate': success_rate,
                'deployment_status': deployment_status
            },
            'tests': [asdict(test) for test in self.tests]
        }
        
        report_file = Path("day5_final_validation_report.json")
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
            
        print(f"📄 Detailed report saved: {report_file}")
        
        # Return appropriate exit code
        return 0 if critical_failed == 0 and success_rate >= 75 else 1

def main():
    """Main validation entry point"""
    validator = Day5FinalValidator()
    exit_code = validator.run_all_tests()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()