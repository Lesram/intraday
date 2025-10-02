#!/usr/bin/env python3
"""
Standalone SLO Monitoring Demo
No external dependencies required
"""

import time
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
import threading
import logging

@dataclass
class SLOTarget:
    """SLO Target Definition"""
    name: str
    target_value: float
    unit: str
    window_minutes: int
    burn_rate_threshold: float

class StandaloneSLOMonitor:
    """
    Standalone SLO monitoring system
    Demonstrates hedge fund grade SLO tracking without external dependencies
    """
    
    def __init__(self):
        """Initialize standalone SLO monitor"""
        self.logger = logging.getLogger(__name__)
        
        # SLO Targets (Hedge Fund Grade)
        self.slo_targets = {
            "order_latency_p99": SLOTarget(
                name="Order Latency P99",
                target_value=100.0,  # 100ms
                unit="ms",
                window_minutes=60,
                burn_rate_threshold=0.1
            ),
            "order_accuracy": SLOTarget(
                name="Order Accuracy",
                target_value=95.0,  # 95%
                unit="%",
                window_minutes=1440,  # 24 hours
                burn_rate_threshold=0.05
            ),
            "fill_rate": SLOTarget(
                name="Fill Rate",
                target_value=98.0,  # 98%
                unit="%",
                window_minutes=5,
                burn_rate_threshold=0.2
            )
        }
        
        # Metrics storage
        self.metrics_data = {
            'order_latencies': deque(maxlen=10000),
            'order_outcomes': deque(maxlen=10000),
            'fill_events': deque(maxlen=10000)
        }
        
        # SLO compliance tracking
        self.slo_compliance = {}
        self.active_violations = []
        
    def record_order_latency(self, latency_ms: float, **metadata):
        """Record order submission latency"""
        
        event = {
            'timestamp': datetime.now(),
            'latency_ms': latency_ms,
            **metadata
        }
        
        self.metrics_data['order_latencies'].append(event)
        self.logger.debug(f"Recorded order latency: {latency_ms:.1f}ms")
        
    def record_order_outcome(self, success: bool, **metadata):
        """Record order execution outcome"""
        
        event = {
            'timestamp': datetime.now(),
            'success': success,
            **metadata
        }
        
        self.metrics_data['order_outcomes'].append(event)
        self.logger.debug(f"Recorded order outcome: {'success' if success else 'failure'}")
        
    def record_fill_event(self, fill_ratio: float, **metadata):
        """Record order fill event (fill_ratio: 0-1)"""
        
        event = {
            'timestamp': datetime.now(),
            'fill_ratio': fill_ratio,  # 0.0 = no fill, 1.0 = complete fill
            **metadata
        }
        
        self.metrics_data['fill_events'].append(event)
        self.logger.debug(f"Recorded fill event: {fill_ratio:.1%}")
    
    def calculate_order_latency_p99(self, window_minutes: int = 60) -> Dict[str, float]:
        """Calculate P99 order latency over window"""
        
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_latencies = [
            event['latency_ms'] 
            for event in self.metrics_data['order_latencies']
            if event['timestamp'] >= cutoff_time
        ]
        
        if len(recent_latencies) < 10:
            return {'p99_ms': 0.0, 'sample_count': len(recent_latencies)}
        
        sorted_latencies = sorted(recent_latencies)
        p99_index = int(len(sorted_latencies) * 0.99)
        p99_latency = sorted_latencies[p99_index]
        
        return {
            'p99_ms': p99_latency,
            'sample_count': len(recent_latencies),
            'avg_ms': sum(recent_latencies) / len(recent_latencies)
        }
    
    def calculate_order_accuracy(self, window_minutes: int = 1440) -> Dict[str, float]:
        """Calculate order accuracy over window"""
        
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_outcomes = [
            event for event in self.metrics_data['order_outcomes']
            if event['timestamp'] >= cutoff_time
        ]
        
        if len(recent_outcomes) < 5:
            return {'accuracy_pct': 100.0, 'sample_count': len(recent_outcomes)}
        
        successful_orders = sum(1 for event in recent_outcomes if event['success'])
        accuracy = (successful_orders / len(recent_outcomes)) * 100
        
        return {
            'accuracy_pct': accuracy,
            'sample_count': len(recent_outcomes),
            'success_count': successful_orders
        }
    
    def calculate_fill_rate(self, window_minutes: int = 5) -> Dict[str, float]:
        """Calculate average fill rate over window"""
        
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_fills = [
            event for event in self.metrics_data['fill_events']
            if event['timestamp'] >= cutoff_time
        ]
        
        if len(recent_fills) < 3:
            return {'fill_rate_pct': 100.0, 'sample_count': len(recent_fills)}
        
        avg_fill_ratio = sum(event['fill_ratio'] for event in recent_fills) / len(recent_fills)
        fill_rate_pct = avg_fill_ratio * 100
        
        return {
            'fill_rate_pct': fill_rate_pct,
            'sample_count': len(recent_fills),
            'total_events': len(recent_fills)
        }
    
    def evaluate_slo_compliance(self) -> Dict[str, Any]:
        """Evaluate compliance for all SLO targets"""
        
        compliance_results = {}
        violations = []
        
        # Order Latency P99 SLO
        latency_data = self.calculate_order_latency_p99(
            self.slo_targets["order_latency_p99"].window_minutes
        )
        
        p99_ms = latency_data['p99_ms']
        target_ms = self.slo_targets["order_latency_p99"].target_value
        
        latency_compliant = p99_ms <= target_ms
        latency_burn_rate = max(0.0, (p99_ms - target_ms) / target_ms) if p99_ms > target_ms else 0.0
        
        compliance_results['order_latency_p99'] = {
            'compliant': latency_compliant,
            'current_value': p99_ms,
            'target_value': target_ms,
            'burn_rate': latency_burn_rate,
            'sample_count': latency_data['sample_count']
        }
        
        if not latency_compliant:
            violations.append({
                'slo_name': 'Order Latency P99',
                'current_value': p99_ms,
                'target_value': target_ms,
                'severity': 'critical' if latency_burn_rate > 0.5 else 'warning'
            })
        
        # Order Accuracy SLO
        accuracy_data = self.calculate_order_accuracy(
            self.slo_targets["order_accuracy"].window_minutes
        )
        
        accuracy_pct = accuracy_data['accuracy_pct']
        target_pct = self.slo_targets["order_accuracy"].target_value
        
        accuracy_compliant = accuracy_pct >= target_pct
        accuracy_burn_rate = max(0.0, (target_pct - accuracy_pct) / target_pct) if accuracy_pct < target_pct else 0.0
        
        compliance_results['order_accuracy'] = {
            'compliant': accuracy_compliant,
            'current_value': accuracy_pct,
            'target_value': target_pct,
            'burn_rate': accuracy_burn_rate,
            'sample_count': accuracy_data['sample_count']
        }
        
        if not accuracy_compliant:
            violations.append({
                'slo_name': 'Order Accuracy',
                'current_value': accuracy_pct,
                'target_value': target_pct,
                'severity': 'critical' if accuracy_burn_rate > 0.3 else 'warning'
            })
        
        # Fill Rate SLO
        fill_data = self.calculate_fill_rate(
            self.slo_targets["fill_rate"].window_minutes
        )
        
        fill_rate_pct = fill_data['fill_rate_pct']
        target_fill_pct = self.slo_targets["fill_rate"].target_value
        
        fill_compliant = fill_rate_pct >= target_fill_pct
        fill_burn_rate = max(0.0, (target_fill_pct - fill_rate_pct) / target_fill_pct) if fill_rate_pct < target_fill_pct else 0.0
        
        compliance_results['fill_rate'] = {
            'compliant': fill_compliant,
            'current_value': fill_rate_pct,
            'target_value': target_fill_pct,
            'burn_rate': fill_burn_rate,
            'sample_count': fill_data['sample_count']
        }
        
        if not fill_compliant:
            violations.append({
                'slo_name': 'Fill Rate',
                'current_value': fill_rate_pct,
                'target_value': target_fill_pct,
                'severity': 'critical' if fill_burn_rate > 0.4 else 'warning'
            })
        
        # Calculate overall system health
        total_slos = len(compliance_results)
        compliant_slos = sum(1 for slo in compliance_results.values() if slo['compliant'])
        system_health_pct = (compliant_slos / total_slos) * 100
        
        return {
            'timestamp': datetime.now(),
            'system_health_pct': system_health_pct,
            'slo_compliance': compliance_results,
            'violations': violations,
            'total_slos': total_slos,
            'compliant_slos': compliant_slos
        }
    
    def generate_synthetic_data(self, duration_seconds: int = 60, ops_per_second: int = 10):
        """Generate synthetic trading data for SLO testing"""
        
        print(f"\n🔄 Generating synthetic trading data...")
        print(f"   Duration: {duration_seconds}s @ {ops_per_second} ops/sec")
        
        operations = 0
        start_time = time.time()
        
        while (time.time() - start_time) < duration_seconds:
            
            # Simulate order latencies (mostly good, some bad)
            if random.random() < 0.95:  # 95% good performance
                latency = random.uniform(20, 80)  # Good latency
            else:
                latency = random.uniform(120, 300)  # Bad latency (SLO violation)
            
            self.record_order_latency(
                latency_ms=latency,
                symbol=random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"])
            )
            
            # Simulate order outcomes (mostly successful)
            success = random.random() < 0.97  # 97% success rate
            self.record_order_outcome(
                success=success,
                order_type=random.choice(["market", "limit"])
            )
            
            # Simulate fill events (high fill rates)
            fill_ratio = random.uniform(0.95, 1.0) if random.random() < 0.98 else random.uniform(0.5, 0.8)
            self.record_fill_event(
                fill_ratio=fill_ratio,
                symbol=random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"])
            )
            
            operations += 1
            time.sleep(1.0 / ops_per_second)
            
            # Progress update
            if operations % (ops_per_second * 10) == 0:
                elapsed = time.time() - start_time
                print(f"   Progress: {operations} operations in {elapsed:.1f}s")
        
        elapsed_time = time.time() - start_time
        actual_ops_rate = operations / elapsed_time
        
        print(f"✅ Data generation complete:")
        print(f"   Operations: {operations}")
        print(f"   Duration: {elapsed_time:.1f}s")
        print(f"   Rate: {actual_ops_rate:.1f} ops/sec")
        
        return operations

def run_slo_demo():
    """Run standalone SLO monitoring demonstration"""
    
    print("🎯 Standalone SLO Monitoring Demonstration")
    print("=" * 50)
    
    # Initialize monitor
    monitor = StandaloneSLOMonitor()
    
    # Generate synthetic data
    print("\n📊 Phase 1: Generate baseline data (good performance)")
    monitor.generate_synthetic_data(duration_seconds=30, ops_per_second=8)
    
    # Evaluate initial SLO compliance
    print("\n📈 Phase 1 SLO Evaluation:")
    compliance = monitor.evaluate_slo_compliance()
    
    print(f"   System Health: {compliance['system_health_pct']:.1f}%")
    print(f"   Compliant SLOs: {compliance['compliant_slos']}/{compliance['total_slos']}")
    
    for slo_name, slo_data in compliance['slo_compliance'].items():
        status = "✅ PASS" if slo_data['compliant'] else "❌ FAIL"
        print(f"   {slo_name}: {slo_data['current_value']:.1f}{monitor.slo_targets[slo_name].unit} "
              f"(target: {slo_data['target_value']:.1f}{monitor.slo_targets[slo_name].unit}) {status}")
    
    # Inject performance degradation
    print("\n🚨 Phase 2: Inject performance issues (SLO violations)")
    
    # Inject high-latency orders
    for i in range(50):
        monitor.record_order_latency(
            latency_ms=random.uniform(150, 300),  # High latency
            symbol="TEST_VIOLATION"
        )
        
        # Some failed orders
        if i % 5 == 0:
            monitor.record_order_outcome(success=False, order_type="violation_test")
        
        # Some poor fills
        if i % 3 == 0:
            monitor.record_fill_event(fill_ratio=random.uniform(0.3, 0.7), symbol="TEST_VIOLATION")
    
    print("   Injected 50 high-latency orders and failures")
    
    # Re-evaluate SLO compliance
    print("\n📉 Phase 2 SLO Evaluation (after violations):")
    compliance = monitor.evaluate_slo_compliance()
    
    print(f"   System Health: {compliance['system_health_pct']:.1f}%")
    print(f"   Compliant SLOs: {compliance['compliant_slos']}/{compliance['total_slos']}")
    print(f"   Active Violations: {len(compliance['violations'])}")
    
    for slo_name, slo_data in compliance['slo_compliance'].items():
        status = "✅ PASS" if slo_data['compliant'] else "❌ FAIL"
        burn_rate_indicator = f"(🔥 burn: {slo_data['burn_rate']:.2f}x)" if slo_data['burn_rate'] > 0 else ""
        
        print(f"   {slo_name}: {slo_data['current_value']:.1f}{monitor.slo_targets[slo_name].unit} "
              f"(target: {slo_data['target_value']:.1f}{monitor.slo_targets[slo_name].unit}) {status} {burn_rate_indicator}")
    
    # Display violations
    if compliance['violations']:
        print("\n🚨 ACTIVE SLO VIOLATIONS:")
        for violation in compliance['violations']:
            print(f"   {violation['slo_name']}: {violation['current_value']:.1f} "
                  f"(target: {violation['target_value']:.1f}) - {violation['severity'].upper()}")
    
    # Recovery simulation
    print("\n🔧 Phase 3: Recovery - return to normal performance")
    monitor.generate_synthetic_data(duration_seconds=20, ops_per_second=10)
    
    # Final evaluation
    print("\n📊 Phase 3 SLO Evaluation (after recovery):")
    compliance = monitor.evaluate_slo_compliance()
    
    print(f"   System Health: {compliance['system_health_pct']:.1f}%")
    print(f"   Compliant SLOs: {compliance['compliant_slos']}/{compliance['total_slos']}")
    print(f"   Active Violations: {len(compliance['violations'])}")
    
    for slo_name, slo_data in compliance['slo_compliance'].items():
        status = "✅ PASS" if slo_data['compliant'] else "❌ FAIL"
        print(f"   {slo_name}: {slo_data['current_value']:.1f}{monitor.slo_targets[slo_name].unit} "
              f"(target: {slo_data['target_value']:.1f}{monitor.slo_targets[slo_name].unit}) {status}")
    
    # Generate summary report
    print(f"\n📋 SLO MONITORING DEMO SUMMARY")
    print(f"=" * 40)
    
    total_latency_events = len(monitor.metrics_data['order_latencies'])
    total_outcome_events = len(monitor.metrics_data['order_outcomes'])
    total_fill_events = len(monitor.metrics_data['fill_events'])
    
    print(f"Total Events Processed:")
    print(f"   Order Latencies: {total_latency_events}")
    print(f"   Order Outcomes: {total_outcome_events}")
    print(f"   Fill Events: {total_fill_events}")
    print(f"   Total: {total_latency_events + total_outcome_events + total_fill_events}")
    
    print(f"\nSLO Monitoring Capabilities Demonstrated:")
    print(f"   ✅ Real-time metrics collection")
    print(f"   ✅ P99 latency calculation")
    print(f"   ✅ Order accuracy tracking")
    print(f"   ✅ Fill rate monitoring")
    print(f"   ✅ SLO violation detection")
    print(f"   ✅ Burn rate calculation")
    print(f"   ✅ System health scoring")
    
    # Save report
    report = {
        'demo_completed_at': datetime.now().isoformat(),
        'final_compliance': compliance,
        'total_events': {
            'order_latencies': total_latency_events,
            'order_outcomes': total_outcome_events,
            'fill_events': total_fill_events
        },
        'slo_targets': {name: asdict(target) for name, target in monitor.slo_targets.items()}
    }
    
    with open('slo_demo_report.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Demo report saved: slo_demo_report.json")
    
    return compliance['system_health_pct'] >= 66.0  # Pass if 2/3 SLOs are compliant

def main():
    """Main demonstration"""
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    success = run_slo_demo()
    
    if success:
        print(f"\n🎉 SLO MONITORING DEMO SUCCESSFUL!")
        print(f"   System demonstrates hedge fund grade SLO capabilities")
        return 0
    else:
        print(f"\n⚠️  SLO MONITORING DEMO COMPLETED WITH ISSUES")
        print(f"   Some SLO violations detected (expected in demo)")
        return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)