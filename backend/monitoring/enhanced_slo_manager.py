# Enhanced SLO Threshold Management - AI Agent Suggestions E & F
# =============================================================
# Implements dynamic SLO threshold adjustment and multi-environment validation
# Integrates with existing SLO monitoring for production-grade reliability

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import statistics
import numpy as np
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class SLOThreshold:
    """Dynamic SLO threshold configuration"""
    slo_name: str
    metric_name: str
    current_threshold: float
    baseline_threshold: float
    environment: str
    
    # Dynamic adjustment parameters
    adjustment_window_hours: int = 24
    adjustment_sensitivity: float = 0.1  # 10% sensitivity
    max_adjustment_percent: float = 0.2  # 20% max change
    
    # Historical data
    recent_values: List[float] = None
    last_adjustment: Optional[datetime] = None
    adjustment_history: List[Dict] = None
    
    def __post_init__(self):
        if self.recent_values is None:
            self.recent_values = []
        if self.adjustment_history is None:
            self.adjustment_history = []

@dataclass 
class EnvironmentSLOProfile:
    """SLO profile for specific environment"""
    environment_name: str
    risk_tolerance: str  # 'low', 'medium', 'high'
    business_criticality: str  # 'dev', 'staging', 'prod'
    
    # Environment-specific SLO thresholds
    availability_target: float
    latency_p95_target_ms: float
    latency_p99_target_ms: float
    error_rate_target: float
    
    # Burn-rate alerting thresholds
    burn_rate_1h_multiplier: float = 2.0
    burn_rate_5m_multiplier: float = 6.0
    burn_rate_1m_multiplier: float = 14.4

class EnhancedSLOManager:
    """
    AI Agent Suggestions E & F: Enhanced SLO Threshold Management
    
    Features:
    1. Dynamic Threshold Adjustment (Suggestion E)
       - Auto-adjusts SLO thresholds based on historical performance
       - Prevents alert fatigue from unrealistic thresholds
       - Maintains service quality while reducing false positives
    
    2. Multi-Environment Validation (Suggestion F)
       - Different SLO profiles for dev/staging/prod environments
       - Environment-specific risk tolerance and alerting
       - Graduated deployment validation across environments
    
    Integrates with existing backend/monitoring/slo_*.py modules
    """
    
    def __init__(self, config_file: str = "config/slo_thresholds.json"):
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load or initialize configuration
        self.thresholds: Dict[str, SLOThreshold] = {}
        self.environment_profiles: Dict[str, EnvironmentSLOProfile] = {}
        self.load_configuration()
        
        # Metrics collection
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.last_adjustment_check = datetime.now()
        
    def load_configuration(self):
        """Load SLO configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    config_data = json.load(f)
                
                # Load thresholds
                for threshold_data in config_data.get('thresholds', []):
                    threshold = SLOThreshold(**threshold_data)
                    self.thresholds[threshold.slo_name] = threshold
                
                # Load environment profiles  
                for profile_data in config_data.get('environment_profiles', []):
                    profile = EnvironmentSLOProfile(**profile_data)
                    self.environment_profiles[profile.environment_name] = profile
                
                logger.info(f"Loaded SLO configuration: {len(self.thresholds)} thresholds, {len(self.environment_profiles)} environments")
                
            except Exception as e:
                logger.error(f"Failed to load SLO config: {str(e)}")
                self._initialize_default_configuration()
        else:
            self._initialize_default_configuration()
    
    def _initialize_default_configuration(self):
        """Initialize default SLO configuration"""
        logger.info("Initializing default SLO configuration")
        
        # Default environment profiles
        self.environment_profiles = {
            'development': EnvironmentSLOProfile(
                environment_name='development',
                risk_tolerance='high',
                business_criticality='dev',
                availability_target=0.95,  # 95% (relaxed)
                latency_p95_target_ms=1000,
                latency_p99_target_ms=2000,
                error_rate_target=0.05,  # 5%
                burn_rate_1h_multiplier=5.0,  # Relaxed alerting
                burn_rate_5m_multiplier=15.0
            ),
            
            'staging': EnvironmentSLOProfile(
                environment_name='staging',
                risk_tolerance='medium',
                business_criticality='staging',
                availability_target=0.98,  # 98%
                latency_p95_target_ms=500,
                latency_p99_target_ms=1000,
                error_rate_target=0.02,  # 2%
                burn_rate_1h_multiplier=3.0,
                burn_rate_5m_multiplier=8.0
            ),
            
            'production': EnvironmentSLOProfile(
                environment_name='production',
                risk_tolerance='low',
                business_criticality='prod',
                availability_target=0.999,  # 99.9%
                latency_p95_target_ms=300,
                latency_p99_target_ms=500,
                error_rate_target=0.01,  # 1%
                burn_rate_1h_multiplier=2.0,  # Strict alerting
                burn_rate_5m_multiplier=6.0
            )
        }
        
        # Default SLO thresholds for production
        prod_profile = self.environment_profiles['production']
        
        self.thresholds = {
            'availability': SLOThreshold(
                slo_name='availability',
                metric_name='http_requests_success_rate',
                current_threshold=prod_profile.availability_target,
                baseline_threshold=prod_profile.availability_target,
                environment='production'
            ),
            
            'latency_p95': SLOThreshold(
                slo_name='latency_p95',
                metric_name='http_request_duration_p95',
                current_threshold=prod_profile.latency_p95_target_ms,
                baseline_threshold=prod_profile.latency_p95_target_ms,
                environment='production'
            ),
            
            'latency_p99': SLOThreshold(
                slo_name='latency_p99',
                metric_name='http_request_duration_p99',
                current_threshold=prod_profile.latency_p99_target_ms,
                baseline_threshold=prod_profile.latency_p99_target_ms,
                environment='production'
            ),
            
            'error_rate': SLOThreshold(
                slo_name='error_rate',
                metric_name='http_requests_error_rate',
                current_threshold=prod_profile.error_rate_target,
                baseline_threshold=prod_profile.error_rate_target,
                environment='production'
            ),
            
            # Business-specific SLOs
            'order_success_rate': SLOThreshold(
                slo_name='order_success_rate',
                metric_name='orders_success_rate',
                current_threshold=0.995,  # 99.5%
                baseline_threshold=0.995,
                environment='production'
            ),
            
            'signal_processing_latency': SLOThreshold(
                slo_name='signal_processing_latency',
                metric_name='signal_processing_duration_p95',
                current_threshold=200,  # 200ms
                baseline_threshold=200,
                environment='production'
            )
        }
        
        self.save_configuration()
    
    def save_configuration(self):
        """Save current SLO configuration to file"""
        config_data = {
            'last_updated': datetime.now().isoformat(),
            'thresholds': [asdict(threshold) for threshold in self.thresholds.values()],
            'environment_profiles': [asdict(profile) for profile in self.environment_profiles.values()]
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f, indent=2, default=str)
    
    def record_metric_value(self, slo_name: str, value: float, timestamp: Optional[datetime] = None):
        """
        Record a metric value for SLO threshold analysis
        
        AI Agent Suggestion E: Feeds dynamic threshold adjustment
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Store in metrics history
        self.metrics_history[slo_name].append({
            'timestamp': timestamp,
            'value': value
        })
        
        # Update threshold's recent values
        if slo_name in self.thresholds:
            threshold = self.thresholds[slo_name]
            threshold.recent_values.append(value)
            
            # Keep only recent values (last 24 hours worth)
            if len(threshold.recent_values) > 2880:  # 24h * 60min * 2 (30s intervals)
                threshold.recent_values = threshold.recent_values[-2880:]
        
        # Check if we should evaluate threshold adjustments
        if datetime.now() - self.last_adjustment_check > timedelta(hours=1):
            asyncio.create_task(self._evaluate_threshold_adjustments())
            self.last_adjustment_check = datetime.now()
    
    async def _evaluate_threshold_adjustments(self):
        """
        AI Agent Suggestion E: Evaluate and apply dynamic threshold adjustments
        
        Analyzes recent performance data and adjusts SLO thresholds to:
        - Reduce false positive alerts
        - Maintain service quality standards
        - Account for seasonal/environmental variations
        """
        logger.info("Evaluating SLO threshold adjustments...")
        
        for slo_name, threshold in self.thresholds.items():
            if len(threshold.recent_values) < 100:  # Need sufficient data
                continue
            
            # Skip if recently adjusted (within 6 hours)
            if (threshold.last_adjustment and 
                datetime.now() - threshold.last_adjustment < timedelta(hours=6)):
                continue
            
            adjustment_made = await self._adjust_threshold_if_needed(threshold)
            
            if adjustment_made:
                logger.info(f"Adjusted SLO threshold for {slo_name}: {threshold.current_threshold}")
        
        # Save any changes
        self.save_configuration()
    
    async def _adjust_threshold_if_needed(self, threshold: SLOThreshold) -> bool:
        """Adjust individual SLO threshold based on recent performance"""
        
        recent_values = threshold.recent_values[-1440:]  # Last 12 hours (30s intervals)
        if len(recent_values) < 50:
            return False
        
        # Calculate performance statistics
        current_p95 = np.percentile(recent_values, 95)
        current_mean = statistics.mean(recent_values)
        current_std = statistics.stdev(recent_values) if len(recent_values) > 1 else 0
        
        # Determine if adjustment is needed
        adjustment_needed = False
        new_threshold = threshold.current_threshold
        adjustment_reason = ""
        
        # For latency metrics (lower is better)
        if 'latency' in threshold.slo_name or 'duration' in threshold.slo_name:
            # If P95 consistently exceeds threshold by >20%
            if current_p95 > threshold.current_threshold * 1.2:
                # Adjust threshold upward (more lenient) but not too much
                adjustment_factor = min(1 + threshold.adjustment_sensitivity, 1.2)
                new_threshold = min(
                    threshold.current_threshold * adjustment_factor,
                    threshold.baseline_threshold * (1 + threshold.max_adjustment_percent)
                )
                adjustment_needed = True
                adjustment_reason = f"P95 ({current_p95:.1f}) exceeds threshold by >20%"
                
            # If P95 consistently well below threshold (>30% better)
            elif current_p95 < threshold.current_threshold * 0.7:
                # Adjust threshold downward (more strict) gradually
                adjustment_factor = max(1 - threshold.adjustment_sensitivity, 0.9)
                new_threshold = max(
                    threshold.current_threshold * adjustment_factor,
                    threshold.baseline_threshold * (1 - threshold.max_adjustment_percent)
                )
                adjustment_needed = True
                adjustment_reason = f"P95 ({current_p95:.1f}) well below threshold"
        
        # For availability/success rate metrics (higher is better)
        elif 'success' in threshold.slo_name or 'availability' in threshold.slo_name:
            success_rate_p5 = np.percentile(recent_values, 5)  # 5th percentile (worst performance)
            
            # If 5th percentile is below threshold (frequent violations)
            if success_rate_p5 < threshold.current_threshold:
                # Adjust threshold downward (more lenient)
                adjustment_factor = max(1 - threshold.adjustment_sensitivity, 0.95)
                new_threshold = max(
                    threshold.current_threshold * adjustment_factor,
                    threshold.baseline_threshold * (1 - threshold.max_adjustment_percent)
                )
                adjustment_needed = True
                adjustment_reason = f"P5 success rate ({success_rate_p5:.3f}) below threshold"
                
            # If mean is significantly above threshold
            elif current_mean > threshold.current_threshold * 1.05:
                # Adjust threshold upward (more strict) gradually  
                adjustment_factor = min(1 + threshold.adjustment_sensitivity * 0.5, 1.05)
                new_threshold = min(
                    threshold.current_threshold * adjustment_factor,
                    threshold.baseline_threshold * (1 + threshold.max_adjustment_percent)
                )
                adjustment_needed = True
                adjustment_reason = f"Mean success rate ({current_mean:.3f}) well above threshold"
        
        # For error rate metrics (lower is better)
        elif 'error' in threshold.slo_name:
            # Similar logic to latency but inverted
            if current_p95 > threshold.current_threshold * 2:
                # Adjust threshold upward (more lenient)
                adjustment_factor = min(1 + threshold.adjustment_sensitivity, 1.5)
                new_threshold = min(
                    threshold.current_threshold * adjustment_factor,
                    threshold.baseline_threshold * (1 + threshold.max_adjustment_percent)
                )
                adjustment_needed = True
                adjustment_reason = f"Error rate P95 ({current_p95:.4f}) exceeds threshold"
        
        # Apply adjustment if needed
        if adjustment_needed and abs(new_threshold - threshold.current_threshold) > threshold.current_threshold * 0.01:
            old_threshold = threshold.current_threshold
            threshold.current_threshold = new_threshold
            threshold.last_adjustment = datetime.now()
            
            # Record adjustment history
            threshold.adjustment_history.append({
                'timestamp': datetime.now().isoformat(),
                'old_threshold': old_threshold,
                'new_threshold': new_threshold,
                'reason': adjustment_reason,
                'performance_stats': {
                    'p95': current_p95,
                    'mean': current_mean,
                    'std': current_std,
                    'samples': len(recent_values)
                }
            })
            
            logger.info(f"Adjusted {threshold.slo_name} threshold: {old_threshold:.3f} → {new_threshold:.3f} ({adjustment_reason})")
            return True
        
        return False
    
    def get_environment_slo_thresholds(self, environment: str) -> Dict[str, Any]:
        """
        AI Agent Suggestion F: Get SLO thresholds for specific environment
        
        Returns environment-appropriate SLO thresholds for multi-environment validation
        """
        if environment not in self.environment_profiles:
            logger.warning(f"Unknown environment '{environment}', using production profile")
            environment = 'production'
        
        profile = self.environment_profiles[environment]
        
        return {
            'environment': environment,
            'profile': profile,
            'thresholds': {
                'availability_min': profile.availability_target,
                'latency_p95_max_ms': profile.latency_p95_target_ms,
                'latency_p99_max_ms': profile.latency_p99_target_ms,
                'error_rate_max': profile.error_rate_target,
                
                # Dynamic thresholds (if available for this environment)
                'dynamic_thresholds': {
                    name: threshold.current_threshold 
                    for name, threshold in self.thresholds.items()
                    if threshold.environment == environment
                }
            },
            'alerting': {
                'burn_rate_1h_multiplier': profile.burn_rate_1h_multiplier,
                'burn_rate_5m_multiplier': profile.burn_rate_5m_multiplier,
                'burn_rate_1m_multiplier': profile.burn_rate_1m_multiplier
            }
        }
    
    def validate_environment_readiness(self, environment: str, metrics: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        AI Agent Suggestion F: Validate environment readiness for deployment
        
        Checks if current environment metrics meet SLO requirements for promotion
        """
        env_config = self.get_environment_slo_thresholds(environment)
        thresholds = env_config['thresholds']
        
        validation_results = []
        all_passed = True
        
        # Check availability
        if 'availability' in metrics:
            availability = metrics['availability']
            required = thresholds['availability_min']
            passed = availability >= required
            validation_results.append(f"Availability: {availability:.3%} {'✅' if passed else '❌'} (required: {required:.3%})")
            if not passed:
                all_passed = False
        
        # Check latency P95
        if 'latency_p95_ms' in metrics:
            latency_p95 = metrics['latency_p95_ms']
            required = thresholds['latency_p95_max_ms']
            passed = latency_p95 <= required
            validation_results.append(f"Latency P95: {latency_p95:.1f}ms {'✅' if passed else '❌'} (max: {required:.1f}ms)")
            if not passed:
                all_passed = False
        
        # Check error rate
        if 'error_rate' in metrics:
            error_rate = metrics['error_rate']
            required = thresholds['error_rate_max']
            passed = error_rate <= required
            validation_results.append(f"Error Rate: {error_rate:.3%} {'✅' if passed else '❌'} (max: {required:.3%})")
            if not passed:
                all_passed = False
        
        return all_passed, validation_results
    
    def create_environment_specific_promotion_criteria(self, environment: str) -> Dict[str, Any]:
        """
        Create promotion criteria tailored for specific environment
        
        Used by automated promotion gates to get environment-appropriate thresholds
        """
        env_config = self.get_environment_slo_thresholds(environment)
        thresholds = env_config['thresholds']
        
        return {
            'environment': environment,
            'k6_criteria': {
                'unexpected_error_rate_max': thresholds['error_rate_max'],
                'p95_latency_ms_max': thresholds['latency_p95_max_ms'],
                'success_rate_min': thresholds['availability_min']
            },
            'sli_criteria': {
                'health_p95_ms_max': min(100, thresholds['latency_p95_max_ms'] * 0.3),
                'signals_p95_ms_max': thresholds['latency_p95_max_ms'],
                'orders_p95_ms_max': thresholds['latency_p95_max_ms'] * 1.5,
                'positions_p95_ms_max': thresholds['latency_p95_max_ms']
            },
            'burn_in_criteria': {
                'all_sessions_pass': True,
                'stability_score_min': 90 if environment == 'production' else 80,
                'memory_growth_mb_max': 200 if environment == 'production' else 400
            },
            'slo_criteria': {
                'availability_min': thresholds['availability_min'],
                'error_budget_remaining_min': 0.10 if environment == 'production' else 0.05
            }
        }
    
    def get_threshold_adjustment_report(self) -> Dict[str, Any]:
        """Get report of recent threshold adjustments for monitoring"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_thresholds': len(self.thresholds),
            'recent_adjustments': [],
            'threshold_summary': {}
        }
        
        for name, threshold in self.thresholds.items():
            # Recent adjustments (last 7 days)
            recent_adjustments = [
                adj for adj in threshold.adjustment_history
                if datetime.fromisoformat(adj['timestamp']) > datetime.now() - timedelta(days=7)
            ]
            
            if recent_adjustments:
                report['recent_adjustments'].extend([
                    {
                        'slo_name': name,
                        **adj
                    } for adj in recent_adjustments
                ])
            
            # Threshold summary
            report['threshold_summary'][name] = {
                'current_threshold': threshold.current_threshold,
                'baseline_threshold': threshold.baseline_threshold,
                'environment': threshold.environment,
                'adjustment_count_7d': len(recent_adjustments),
                'last_adjustment': threshold.last_adjustment.isoformat() if threshold.last_adjustment else None,
                'recent_values_count': len(threshold.recent_values)
            }
        
        return report

# ============================================================================
# AI AGENT SUGGESTIONS E & F: INTEGRATION WITH EXISTING SLO MONITORING
# ============================================================================

class SLOIntegrationHelper:
    """Helper class to integrate enhanced SLO management with existing systems"""
    
    def __init__(self, slo_manager: EnhancedSLOManager):
        self.slo_manager = slo_manager
    
    def update_prometheus_alerts(self, environment: str = 'production'):
        """
        Generate Prometheus alerting rules based on current SLO thresholds
        
        Integrates with existing backend/monitoring/slo_alerts.py
        """
        env_config = self.slo_manager.get_environment_slo_thresholds(environment)
        thresholds = env_config['thresholds']
        alerting = env_config['alerting']
        
        # Generate Prometheus rules YAML
        alert_rules = {
            'groups': [
                {
                    'name': f'slo_alerts_{environment}',
                    'rules': [
                        {
                            'alert': f'HighErrorRate_{environment}',
                            'expr': f'http_requests_error_rate > {thresholds["error_rate_max"]}',
                            'for': '5m',
                            'labels': {
                                'severity': 'high' if environment == 'production' else 'medium',
                                'environment': environment
                            },
                            'annotations': {
                                'summary': f'{environment} error rate exceeds SLO threshold',
                                'description': f'Error rate {{ $value }} exceeds {thresholds["error_rate_max"]:.3%} threshold'
                            }
                        },
                        {
                            'alert': f'HighLatency_{environment}',
                            'expr': f'http_request_duration_p95 > {thresholds["latency_p95_max_ms"] / 1000}',
                            'for': '10m',
                            'labels': {
                                'severity': 'high' if environment == 'production' else 'medium',
                                'environment': environment
                            },
                            'annotations': {
                                'summary': f'{environment} latency exceeds SLO threshold',
                                'description': f'P95 latency {{ $value }}s exceeds {thresholds["latency_p95_max_ms"]}ms threshold'
                            }
                        }
                    ]
                }
            ]
        }
        
        return alert_rules
    
    def get_slo_dashboard_config(self, environment: str = 'production') -> Dict[str, Any]:
        """
        Generate Grafana dashboard configuration for SLO monitoring
        
        Integrates with existing backend/monitoring/slo_dashboard.py
        """
        env_config = self.slo_manager.get_environment_slo_thresholds(environment)
        thresholds = env_config['thresholds']
        
        dashboard_config = {
            'dashboard': {
                'title': f'SLO Monitoring - {environment.title()}',
                'panels': [
                    {
                        'title': 'Availability SLO',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': 'http_requests_success_rate',
                                'legendFormat': 'Success Rate'
                            }
                        ],
                        'thresholds': [
                            {'color': 'red', 'value': 0},
                            {'color': 'yellow', 'value': thresholds['availability_min'] * 0.95},
                            {'color': 'green', 'value': thresholds['availability_min']}
                        ]
                    },
                    {
                        'title': 'Latency SLO',
                        'type': 'timeseries',
                        'targets': [
                            {
                                'expr': 'http_request_duration_p95',
                                'legendFormat': 'P95 Latency'
                            }
                        ],
                        'thresholds': [
                            {
                                'value': thresholds['latency_p95_max_ms'] / 1000,
                                'color': 'red',
                                'op': 'gt'
                            }
                        ]
                    }
                ]
            }
        }
        
        return dashboard_config

# ============================================================================
# AI AGENT SUGGESTIONS E & F: CLI INTERFACE
# ============================================================================

async def main():
    """CLI entry point for enhanced SLO management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced SLO Threshold Management')
    parser.add_argument('--config-file', default='config/slo_thresholds.json', help='SLO configuration file')
    parser.add_argument('--environment', default='production', help='Environment to manage')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # View command
    view_parser = subparsers.add_parser('view', help='View current SLO thresholds')
    view_parser.add_argument('--environment', help='Environment to view')
    
    # Adjust command
    adjust_parser = subparsers.add_parser('adjust', help='Force threshold adjustment evaluation')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate threshold adjustment report')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate environment readiness')
    validate_parser.add_argument('--metrics-file', required=True, help='JSON file with current metrics')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize SLO manager
    slo_manager = EnhancedSLOManager(config_file=args.config_file)
    
    if args.command == 'view':
        env = args.environment or 'production'
        config = slo_manager.get_environment_slo_thresholds(env)
        
        print(f"\n📊 SLO Thresholds for {env.title()}")
        print(f"Risk Tolerance: {config['profile'].risk_tolerance}")
        print(f"Business Criticality: {config['profile'].business_criticality}")
        print(f"")
        
        thresholds = config['thresholds']
        print("Current Thresholds:")
        print(f"  Availability: {thresholds['availability_min']:.3%}")
        print(f"  Latency P95: {thresholds['latency_p95_max_ms']:.0f}ms")
        print(f"  Latency P99: {thresholds['latency_p99_max_ms']:.0f}ms")
        print(f"  Error Rate: {thresholds['error_rate_max']:.3%}")
        
        if thresholds['dynamic_thresholds']:
            print(f"")
            print("Dynamic Thresholds:")
            for name, value in thresholds['dynamic_thresholds'].items():
                print(f"  {name}: {value}")
        
    elif args.command == 'adjust':
        await slo_manager._evaluate_threshold_adjustments()
        print("✅ Threshold adjustment evaluation completed")
    
    elif args.command == 'report':
        report = slo_manager.get_threshold_adjustment_report()
        print(f"\n📊 SLO Threshold Adjustment Report")
        print(f"Generated: {report['timestamp']}")
        print(f"Total Thresholds: {report['total_thresholds']}")
        print(f"Recent Adjustments (7d): {len(report['recent_adjustments'])}")
        
        if report['recent_adjustments']:
            print(f"\nRecent Adjustments:")
            for adj in report['recent_adjustments'][-5:]:  # Show last 5
                print(f"  {adj['slo_name']}: {adj['old_threshold']} → {adj['new_threshold']} ({adj['reason']})")
    
    elif args.command == 'validate':
        if not Path(args.metrics_file).exists():
            print(f"❌ Metrics file not found: {args.metrics_file}")
            return 1
        
        with open(args.metrics_file) as f:
            metrics = json.load(f)
        
        passed, results = slo_manager.validate_environment_readiness(args.environment, metrics)
        
        print(f"\n🔍 Environment Readiness Validation - {args.environment.title()}")
        print(f"Overall Status: {'✅ READY' if passed else '❌ NOT READY'}")
        print(f"")
        
        for result in results:
            print(f"  {result}")
        
        return 0 if passed else 1
    
    else:
        parser.print_help()
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))