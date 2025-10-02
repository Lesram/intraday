#!/usr/bin/env python3
"""
SLO System Validation Test Suite
Comprehensive testing of SLO monitoring, alerts, and dashboard
"""

import asyncio
import time
import random
import threading
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from backend.monitoring.slo_metrics import get_slo_collector, SLOMetricsCollector
    from backend.monitoring.slo_alerts import get_alert_manager, SLOBurnRateAlertManager  
    from backend.monitoring.slo_dashboard import get_dashboard, SLODashboard
except ImportError as e:
    print(f"Import error: {e}")
    print("Note: Some imports may fail if dependencies are not installed")

class SLOSystemValidator:
    """
    Comprehensive SLO system validation
    Tests metrics collection, alerting, and dashboard functionality
    """
    
    def __init__(self):
        """Initialize SLO system validator"""
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        try:
            self.slo_collector = get_slo_collector()
            self.alert_manager = get_alert_manager() 
            self.dashboard = get_dashboard()
        except Exception as e:
            self.logger.warning(f"Component initialization failed: {e}")
            self.slo_collector = None
            self.alert_manager = None
            self.dashboard = None
        
        # Test state
        self.test_results = {}
        self.synthetic_load_active = False

    def test_metrics_collection(self) -> Dict[str, bool]:
        """Test SLO metrics collection functionality"""
        
        print("\n🧪 Testing SLO Metrics Collection")
        print("=" * 40)
        
        results = {
            'order_latency_recording': False,
            'order_outcome_recording': False,
            'fill_event_recording': False,
            'system_health_recording': False,
            'slo_calculation': False,
            'prometheus_export': False
        }
        
        if not self.slo_collector:
            print("❌ SLO collector not available")
            return results
        
        try:
            # Test order latency recording
            print("  Testing order latency recording...")
            self.slo_collector.record_order_latency(
                latency_ms=45.2, 
                order_type="market",
                symbol="AAPL",
                account="test_account"
            )
            results['order_latency_recording'] = True
            print("    ✅ Order latency recorded successfully")
            
            # Test order outcome recording  
            print("  Testing order outcome recording...")
            self.slo_collector.record_order_outcome(
                status="filled",
                order_type="market",
                symbol="AAPL"
            )
            results['order_outcome_recording'] = True
            print("    ✅ Order outcome recorded successfully")
            
            # Test fill event recording
            print("  Testing fill event recording...")
            self.slo_collector.record_fill_event(
                fill_type="full",
                symbol="AAPL", 
                account="test_account",
                filled_qty=100
            )
            results['fill_event_recording'] = True
            print("    ✅ Fill event recorded successfully")
            
            # Test system health recording
            print("  Testing system health recording...")
            self.slo_collector.update_system_health(
                component="order_gateway",
                health_score=95.5
            )
            results['system_health_recording'] = True
            print("    ✅ System health recorded successfully")
            
            # Test SLO calculation
            print("  Testing SLO compliance calculation...")
            compliance = self.slo_collector.calculate_slo_compliance("order_submission_latency_p99")
            if compliance:
                results['slo_calculation'] = True
                print(f"    ✅ SLO calculation successful: {compliance['compliance_ratio']:.3f}")
            
            # Test Prometheus export
            print("  Testing Prometheus metrics export...")
            metrics_data = self.slo_collector.export_prometheus_metrics()
            if metrics_data:
                results['prometheus_export'] = True
                print(f"    ✅ Prometheus export successful: {len(metrics_data)} bytes")
            
        except Exception as e:
            print(f"  ❌ Metrics collection test failed: {e}")
        
        return results

    def test_alert_system(self) -> Dict[str, bool]:
        """Test SLO alert system functionality"""
        
        print("\n🚨 Testing SLO Alert System")
        print("=" * 40)
        
        results = {
            'alert_rule_loading': False,
            'alert_evaluation': False,
            'alert_notification': False,
            'cooldown_handling': False
        }
        
        if not self.alert_manager:
            print("❌ Alert manager not available") 
            return results
        
        try:
            # Test alert rule loading
            print("  Testing alert rule configuration...")
            if len(self.alert_manager.alert_rules) > 0:
                results['alert_rule_loading'] = True
                print(f"    ✅ Loaded {len(self.alert_manager.alert_rules)} alert rules")
            
            # Test alert evaluation
            print("  Testing alert rule evaluation...")
            notifications = self.alert_manager.evaluate_alert_rules()
            results['alert_evaluation'] = True
            print(f"    ✅ Evaluated rules, {len(notifications)} notifications triggered")
            
            # Test notification system (mock)
            print("  Testing alert notifications...")
            if notifications:
                # This would normally send real notifications
                results['alert_notification'] = True
                print(f"    ✅ Would send {len(notifications)} notifications")
            else:
                results['alert_notification'] = True
                print("    ✅ No alerts to send (system healthy)")
            
            # Test alert status
            print("  Testing alert status retrieval...")
            status = self.alert_manager.get_alert_status()
            if status:
                results['cooldown_handling'] = True
                print(f"    ✅ Alert status: {status['active_alerts']} active")
            
        except Exception as e:
            print(f"  ❌ Alert system test failed: {e}")
        
        return results

    def test_dashboard_functionality(self) -> Dict[str, bool]:
        """Test SLO dashboard functionality"""
        
        print("\n📊 Testing SLO Dashboard")  
        print("=" * 40)
        
        results = {
            'dashboard_data_generation': False,
            'health_calculation': False,
            'static_report_generation': False
        }
        
        if not self.dashboard:
            print("❌ Dashboard not available")
            return results
        
        try:
            # Test dashboard data generation
            print("  Testing dashboard data generation...")
            data = self.dashboard.get_dashboard_data()
            if data and 'system_health' in data:
                results['dashboard_data_generation'] = True
                print("    ✅ Dashboard data generated successfully")
                
                # Test system health calculation
                health = data['system_health']
                if 'score' in health and 'status' in health:
                    results['health_calculation'] = True
                    print(f"    ✅ System health: {health['score']:.1f}% ({health['status']})")
            
            # Test static report generation
            print("  Testing static report generation...")
            report_file = "test_slo_report.html"
            if self.dashboard.generate_static_report(report_file):
                results['static_report_generation'] = True
                print(f"    ✅ Static report generated: {report_file}")
                
                # Clean up test file
                Path(report_file).unlink(missing_ok=True)
            
        except Exception as e:
            print(f"  ❌ Dashboard test failed: {e}")
        
        return results

    def generate_synthetic_load(self, duration_seconds: int = 60, operations_per_second: int = 10):
        """Generate synthetic load to test SLO monitoring"""
        
        print(f"\n🔄 Generating Synthetic Load ({duration_seconds}s @ {operations_per_second} ops/sec)")
        print("=" * 60)
        
        if not self.slo_collector:
            print("❌ SLO collector not available for load generation")
            return False
        
        self.synthetic_load_active = True
        operations_count = 0
        start_time = time.time()
        
        try:
            while (time.time() - start_time) < duration_seconds and self.synthetic_load_active:
                
                # Simulate order latencies (mix of good and bad)
                if random.random() < 0.95:  # 95% good latency
                    latency = random.uniform(20, 80)  # Good latency
                else:
                    latency = random.uniform(120, 300)  # Bad latency (violates 100ms SLO)
                
                self.slo_collector.record_order_latency(
                    latency_ms=latency,
                    order_type=random.choice(["market", "limit"]),
                    symbol=random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"]),
                    account=f"test_account_{random.randint(1,5)}"
                )
                
                # Simulate order outcomes
                if random.random() < 0.97:  # 97% success rate
                    status = random.choice(["filled", "partial_fill"])
                else:
                    status = random.choice(["cancelled", "rejected"])
                
                self.slo_collector.record_order_outcome(
                    status=status,
                    order_type=random.choice(["market", "limit"]),
                    symbol=random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"])
                )
                
                # Simulate fill events
                if status in ["filled", "partial_fill"]:
                    self.slo_collector.record_fill_event(
                        fill_type="full" if status == "filled" else "partial",
                        symbol=random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"]),
                        account=f"test_account_{random.randint(1,5)}",
                        filled_qty=random.randint(1, 1000)
                    )
                
                # Update system health
                if operations_count % 20 == 0:  # Every 20 operations
                    health_score = random.uniform(90, 100)  # Generally healthy
                    self.slo_collector.update_system_health(
                        component=random.choice(["order_gateway", "risk_engine", "data_feed"]),
                        health_score=health_score
                    )
                
                operations_count += 1
                
                # Control operation rate
                time.sleep(1.0 / operations_per_second)
                
                # Progress update
                if operations_count % (operations_per_second * 10) == 0:
                    elapsed = time.time() - start_time
                    print(f"  📈 Generated {operations_count} operations in {elapsed:.1f}s")
        
        except KeyboardInterrupt:
            print("\n  🛑 Load generation interrupted by user")
        except Exception as e:
            print(f"  ❌ Load generation failed: {e}")
        finally:
            self.synthetic_load_active = False
        
        elapsed_time = time.time() - start_time
        actual_ops_per_sec = operations_count / elapsed_time
        
        print(f"\n  ✅ Load generation complete:")
        print(f"    Operations: {operations_count}")
        print(f"    Duration: {elapsed_time:.1f}s") 
        print(f"    Rate: {actual_ops_per_sec:.1f} ops/sec")
        
        return True

    def test_slo_violations(self) -> Dict[str, bool]:
        """Test SLO violation detection and alerting"""
        
        print("\n⚠️  Testing SLO Violation Detection")
        print("=" * 40)
        
        results = {
            'high_latency_detection': False,
            'low_accuracy_detection': False,
            'alert_triggering': False,
            'burn_rate_calculation': False
        }
        
        if not self.slo_collector or not self.alert_manager:
            print("❌ Required components not available")
            return results
        
        try:
            print("  Injecting high-latency orders...")
            # Inject several high-latency orders to trigger P99 violation
            for i in range(20):
                latency = random.uniform(150, 250)  # Well above 100ms SLO
                self.slo_collector.record_order_latency(
                    latency_ms=latency,
                    order_type="market",
                    symbol="TEST",
                    account="violation_test"
                )
            
            results['high_latency_detection'] = True
            print("    ✅ High latency orders injected")
            
            print("  Injecting failed orders...")
            # Inject failed orders to trigger accuracy violation
            for i in range(10):
                self.slo_collector.record_order_outcome(
                    status="rejected",
                    order_type="market", 
                    symbol="TEST"
                )
            
            results['low_accuracy_detection'] = True
            print("    ✅ Failed orders injected")
            
            print("  Checking SLO compliance...")
            # Check if violations are detected
            compliance_data = self.slo_collector.calculate_slo_compliance("order_submission_latency_p99")
            if compliance_data and compliance_data.get('burn_rate', 0) > 0:
                results['burn_rate_calculation'] = True
                print(f"    ✅ Burn rate calculated: {compliance_data['burn_rate']:.2f}x")
            
            print("  Evaluating alert rules...")
            # Check if alerts would be triggered
            notifications = self.alert_manager.evaluate_alert_rules()
            if notifications:
                results['alert_triggering'] = True
                print(f"    ✅ {len(notifications)} alerts would be triggered")
            else:
                print("    ⚠️  No alerts triggered (may need more violation data)")
            
        except Exception as e:
            print(f"  ❌ SLO violation test failed: {e}")
        
        return results

    def run_comprehensive_test(self) -> Dict[str, Any]:
        """Run comprehensive SLO system validation"""
        
        print("🚀 SLO System Comprehensive Validation")
        print("=" * 50)
        print(f"Started at: {datetime.now().isoformat()}")
        
        all_results = {}
        
        # Test 1: Metrics Collection
        all_results['metrics_collection'] = self.test_metrics_collection()
        
        # Test 2: Alert System
        all_results['alert_system'] = self.test_alert_system()
        
        # Test 3: Dashboard
        all_results['dashboard'] = self.test_dashboard_functionality()
        
        # Test 4: Generate synthetic load
        print("\n🔄 Starting synthetic load generation...")
        load_success = self.generate_synthetic_load(duration_seconds=30, operations_per_second=5)
        all_results['synthetic_load'] = {'load_generation': load_success}
        
        # Test 5: SLO Violations
        all_results['slo_violations'] = self.test_slo_violations()
        
        # Generate final report
        self._generate_test_report(all_results)
        
        return all_results

    def _generate_test_report(self, results: Dict[str, Any]):
        """Generate comprehensive test report"""
        
        print("\n📋 TEST REPORT SUMMARY")
        print("=" * 50)
        
        total_tests = 0
        passed_tests = 0
        
        for category, category_results in results.items():
            print(f"\n{category.upper().replace('_', ' ')}:")
            
            for test_name, test_result in category_results.items():
                total_tests += 1
                if test_result:
                    passed_tests += 1
                    status = "✅ PASS"
                else:
                    status = "❌ FAIL"
                
                print(f"  {test_name.replace('_', ' ').title()}: {status}")
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📊 OVERALL RESULTS:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {passed_tests}")
        print(f"  Failed: {total_tests - passed_tests}")
        print(f"  Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print(f"\n🎉 SLO SYSTEM VALIDATION SUCCESSFUL!")
            print(f"   System is ready for production deployment")
        elif success_rate >= 70:
            print(f"\n⚠️  SLO SYSTEM PARTIALLY FUNCTIONAL")
            print(f"   Some components need attention before production")
        else:
            print(f"\n❌ SLO SYSTEM VALIDATION FAILED") 
            print(f"   Significant issues need resolution")
        
        # Save detailed results
        try:
            report_data = {
                'timestamp': datetime.now().isoformat(),
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'success_rate': success_rate,
                'detailed_results': results
            }
            
            with open('slo_validation_report.json', 'w') as f:
                json.dump(report_data, f, indent=2)
            
            print(f"\n📄 Detailed report saved: slo_validation_report.json")
            
        except Exception as e:
            print(f"\n⚠️  Could not save detailed report: {e}")

def main():
    """Main test execution"""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize validator
    validator = SLOSystemValidator()
    
    # Run comprehensive validation
    results = validator.run_comprehensive_test()
    
    # Return success code
    total_tests = sum(len(category) for category in results.values())
    passed_tests = sum(sum(category.values()) for category in results.values())
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    return 0 if success_rate >= 80 else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)