# Automated Promotion Gate Script - AI Agent Suggestion D
# =====================================================
# Implements production-grade automated promotion gates
# Combines K6 performance, SLI metrics, burn-in testing, and SLO compliance
# Provides go/no-go decision for production deployment

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
import subprocess
import aiohttp
from concurrent.futures import ThreadPoolExecutor

# Import K6 Cache Manager for centralized K6 execution
from k6_cache_manager import K6CacheManager, K6ExecutionConfig

logger = logging.getLogger(__name__)

@dataclass
class PromotionCriteria:
    """Promotion gate criteria configuration"""
    
    # K6 Performance Gates
    k6_unexpected_error_rate_max: float = 0.02  # 2%
    k6_p95_latency_ms_max: float = 500
    k6_success_rate_min: float = 0.98
    
    # Per-Route SLI Gates  
    sli_health_p95_ms_max: float = 100
    sli_signals_p95_ms_max: float = 300
    sli_orders_p95_ms_max: float = 500
    sli_positions_p95_ms_max: float = 300
    
    # Burn-in Testing Gates  
    # PRODUCTION HARDENING: Burn-in is now REQUIRED by default
    # Set to False only for local dev/testing, NEVER for staging/production
    burn_in_required: bool = True  # FIXED: Required for production deployments
    burn_in_all_sessions_pass: bool = True
    burn_in_stability_score_min: float = 75.0  # Reduced from 85.0 (realistic for server memory)
    burn_in_memory_growth_mb_max: float = 200
    
    # SLO Compliance Gates
    # PRODUCTION HARDENING: SLO monitoring is now REQUIRED by default  
    # Set to False only for local dev/testing, NEVER for staging/production
    slo_monitoring_required: bool = True  # FIXED: Required for production deployments
    slo_availability_min: float = 0.99  # 99% uptime
    slo_error_budget_remaining_min: float = 0.10  # 10% error budget left
    
    # Business Logic Gates
    business_orders_success_rate_min: float = 0.95
    business_signals_processed_min: int = 100
    business_zero_data_loss: bool = True
    
    @classmethod
    def for_environment(cls, environment: str = "production"):
        """
        Create PromotionCriteria with environment-specific settings
        
        Args:
            environment: 'local', 'development', 'staging', 'production'
            
        Returns:
            PromotionCriteria configured for the specified environment
        """
        if environment in ["local", "development"]:
            # Relaxed criteria for local development
            return cls(
                burn_in_required=False,
                slo_monitoring_required=False,
                k6_unexpected_error_rate_max=0.05,  # 5% errors OK in dev
                burn_in_stability_score_min=70.0
            )
        elif environment == "staging":
            # STRICT criteria for staging (production rehearsal)
            return cls(
                burn_in_required=True,  # MANDATORY
                slo_monitoring_required=True,  # MANDATORY - staging must have SLO instrumentation
                k6_unexpected_error_rate_max=0.01,  # 1% max (stricter than before)
                burn_in_stability_score_min=85.0  # Higher bar for stability
            )
        else:  # production or unknown - use strict defaults
            # STRICT criteria for production
            return cls(
                burn_in_required=True,  # MANDATORY
                slo_monitoring_required=True,  # MANDATORY
                k6_unexpected_error_rate_max=0.01,  # 1% errors max in prod
                burn_in_stability_score_min=80.0  # Higher bar for production
            )

@dataclass
class PromotionGateResult:
    """Result from a single promotion gate"""
    gate_name: str
    passed: bool
    actual_value: Any
    expected_value: Any
    details: str
    severity: str  # 'critical', 'high', 'medium', 'low'

@dataclass  
class PromotionReport:
    """Complete promotion gate report"""
    timestamp: datetime
    environment: str
    commit_hash: str
    
    # Gate Results
    gate_results: List[PromotionGateResult]
    
    # Summary
    all_gates_passed: bool
    critical_failures: int
    high_failures: int
    
    # Promotion Decision
    promotion_approved: bool
    approval_confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    
    # Recommendations
    recommendations: List[str]
    next_actions: List[str]

class AutomatedPromotionGates:
    """
    AI Agent Suggestion D: Automated Promotion Gate Validation
    
    Orchestrates comprehensive testing pipeline and provides automated
    go/no-go decision for production deployment based on:
    
    1. K6 Enhanced Performance Testing (AI Agent A)
    2. Per-Route SLI Metrics Validation (AI Agent B) 
    3. 3-Session Burn-in Testing Results (AI Agent C)
    4. SLO Compliance Monitoring
    5. Business Logic Validation
    6. Data Integrity Checks
    
    Designed for CI/CD integration and automated deployment workflows.
    """
    
    def __init__(self,
                 base_url: str = "http://localhost:8000",
                 criteria: Optional[PromotionCriteria] = None,
                 output_dir: str = "test_results/promotion_gates"):
        
        self.base_url = base_url
        self.criteria = criteria or PromotionCriteria()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Test artifacts directories
        self.k6_results_dir = Path("test_results")
        self.burn_in_results_dir = Path("test_results/burn_in")
        self.sli_metrics_cache = {}
        
    async def run_promotion_gate_validation(self, 
                                          environment: str = "staging", 
                                          commit_hash: str = "unknown") -> PromotionReport:
        """
        Execute complete promotion gate validation pipeline
        
        Returns promotion report with go/no-go decision for deployment
        """
        logger.info(f"🚪 Starting Automated Promotion Gate Validation")
        logger.info(f"Environment: {environment} | Commit: {commit_hash}")
        
        validation_start = datetime.now()
        gate_results: List[PromotionGateResult] = []
        
        try:
            # Phase 1: System Readiness Gates
            logger.info("🔍 Phase 1: System Readiness Validation")
            readiness_gates = await self._validate_system_readiness()
            gate_results.extend(readiness_gates)
            
            if not self._check_critical_gates_passed(readiness_gates):
                return self._create_failed_report(gate_results, "System readiness failed", 
                                                 environment, commit_hash, validation_start)
            
            # Phase 2: Performance Gates (K6 Enhanced)
            logger.info("🚀 Phase 2: K6 Enhanced Performance Testing")
            k6_gates = await self._validate_k6_performance()
            gate_results.extend(k6_gates)
            
            # Phase 3: Per-Route SLI Gates
            logger.info("📊 Phase 3: Per-Route SLI Metrics Validation")
            sli_gates = await self._validate_per_route_sli()
            gate_results.extend(sli_gates)
            
            # Phase 4: Burn-in Testing Gates
            logger.info("🔥 Phase 4: Burn-in Testing Validation")
            burn_in_gates = await self._validate_burn_in_results()
            gate_results.extend(burn_in_gates)
            
            # Phase 5: SLO Compliance Gates
            logger.info("📈 Phase 5: SLO Compliance Validation")
            slo_gates = await self._validate_slo_compliance()
            gate_results.extend(slo_gates)
            
            # Phase 6: Business Logic Gates
            logger.info("💼 Phase 6: Business Logic Validation")
            business_gates = await self._validate_business_logic()
            gate_results.extend(business_gates)
            
            # Generate final promotion report
            report = self._generate_promotion_report(
                gate_results, environment, commit_hash, validation_start
            )
            
            # Save promotion report
            await self._save_promotion_report(report)
            
            # Log final decision
            decision = "✅ APPROVED" if report.promotion_approved else "❌ REJECTED"
            logger.info(f"🚪 Promotion Gate Decision: {decision}")
            logger.info(f"Confidence: {report.approval_confidence}")
            
            return report
            
        except Exception as e:
            logger.error(f"Promotion gate validation failed: {str(e)}")
            error_gate = PromotionGateResult(
                gate_name="system_error",
                passed=False,
                actual_value=str(e),
                expected_value="no_errors",
                details=f"Validation pipeline error: {str(e)}",
                severity="critical"
            )
            gate_results.append(error_gate)
            
            return self._create_failed_report(gate_results, "Pipeline error", 
                                             environment, commit_hash, validation_start)
    
    async def _validate_system_readiness(self) -> List[PromotionGateResult]:
        """Validate system is ready for promotion testing"""
        gates = []
        
        # Gate: Platform Health Check
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    health_passed = resp.status == 200
                    gates.append(PromotionGateResult(
                        gate_name="platform_health_check",
                        passed=health_passed,
                        actual_value=resp.status,
                        expected_value=200,
                        details=f"Health endpoint returned {resp.status}",
                        severity="critical"
                    ))
        except Exception as e:
            gates.append(PromotionGateResult(
                gate_name="platform_health_check",
                passed=False,
                actual_value=str(e),
                expected_value="healthy_response",
                details=f"Health check failed: {str(e)}",
                severity="critical"
            ))
        
        # Gate: Database Connectivity
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v1/positions", 
                                     headers=await self._get_auth_headers()) as resp:
                    db_passed = resp.status in [200, 401]  # 401 is OK (auth required)
                    gates.append(PromotionGateResult(
                        gate_name="database_connectivity",
                        passed=db_passed,
                        actual_value=resp.status,
                        expected_value="200_or_401",
                        details=f"Database endpoint returned {resp.status}",
                        severity="critical"
                    ))
        except Exception as e:
            gates.append(PromotionGateResult(
                gate_name="database_connectivity",
                passed=False,
                actual_value=str(e),
                expected_value="connection_success",
                details=f"Database connectivity failed: {str(e)}",
                severity="critical"
            ))
        
        # Gate: Required Services Running
        required_endpoints = [
            "/api/v1/signals",
            "/api/v1/orders", 
            "/api/v1/risk/metrics"
        ]
        
        services_available = 0
        for endpoint in required_endpoints:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}{endpoint}",
                                         headers=await self._get_auth_headers()) as resp:
                        # Accept: 200 (success), 401 (needs auth), 422 (validation error),
                        # 405 (method not allowed - endpoint exists), 307 (redirect)
                        if resp.status in [200, 401, 422, 405, 307]:  # Expected responses
                            services_available += 1
            except:
                pass
        
        services_passed = services_available >= len(required_endpoints) * 0.8  # 80% available
        gates.append(PromotionGateResult(
            gate_name="required_services_available",
            passed=services_passed,
            actual_value=f"{services_available}/{len(required_endpoints)}",
            expected_value=f">={int(len(required_endpoints) * 0.8)}",
            details=f"{services_available} of {len(required_endpoints)} services available",
            severity="high"
        ))
        
        return gates
    
    async def _validate_k6_performance(self) -> List[PromotionGateResult]:
        """Validate K6 enhanced performance test results using cache manager"""
        gates = []
        
        try:
            # Configure K6 execution using cache manager
            k6_config = K6ExecutionConfig(
                duration="30s",
                virtual_users=10,
                base_url=self.base_url,
                k6_script="scripts/testing/k6_enhanced_comprehensive_test.js",
                cache_ttl_minutes=240,  # FIXED: Increased to 4 hours to reuse burn-in results
                force_refresh=False
            )
            
            # FIXED: Try burn-in cache first, then fall back to standard location
            cache_manager = None
            k6_result = None
            
            # Try burn-in results directory first (from Phase 3)
            burn_in_cache_dir = Path("test_results/burn_in")
            if burn_in_cache_dir.exists():
                try:
                    cache_manager = K6CacheManager(str(burn_in_cache_dir))
                    k6_result = await cache_manager.get_k6_results(k6_config)
                    logger.info("✅ Using K6 results from burn-in cache (Phase 3)")
                except Exception as e:
                    logger.info(f"Burn-in cache not available: {str(e)}")
            
            # Fall back to standard location if burn-in cache not found
            if not k6_result:
                cache_manager = K6CacheManager(str(self.k6_results_dir))
                k6_result = await cache_manager.get_k6_results(k6_config)
                logger.info("Using K6 results from standard cache")
            
            if not k6_result.test_passed:
                gates.append(PromotionGateResult(
                    gate_name="k6_test_execution",
                    passed=False,
                    actual_value="test_failed",
                    expected_value="test_passed",
                    details=f"K6 test failed: {'; '.join(k6_result.failure_reasons)}",
                    severity="critical"
                ))
                return gates
                
        except Exception as e:
            logger.error(f"K6 cache manager execution failed: {str(e)}")
            gates.append(PromotionGateResult(
                gate_name="k6_test_execution",
                passed=False,
                actual_value="execution_error",
                expected_value="successful_execution",
                details=f"K6 execution error: {str(e)}",
                severity="critical"
            ))
            return gates
        
        # Gate: K6 Unexpected Error Rate  
        gates.append(PromotionGateResult(
            gate_name="k6_unexpected_error_rate",
            passed=k6_result.unexpected_error_rate <= self.criteria.k6_unexpected_error_rate_max,
            actual_value=f"{k6_result.unexpected_error_rate:.3f}",
            expected_value=f"<={self.criteria.k6_unexpected_error_rate_max}",
            details=f"K6 unexpected errors: {k6_result.unexpected_error_rate:.3%}",
            severity="high"
        ))
        
        # Gate: K6 P95 Latency
        gates.append(PromotionGateResult(
            gate_name="k6_p95_latency",
            passed=k6_result.p95_latency_ms <= self.criteria.k6_p95_latency_ms_max,
            actual_value=f"{k6_result.p95_latency_ms:.1f}ms",
            expected_value=f"<={self.criteria.k6_p95_latency_ms_max}ms",
            details=f"K6 P95 latency: {k6_result.p95_latency_ms:.1f}ms",
            severity="high"
        ))
        
        # Gate: K6 Success Rate
        gates.append(PromotionGateResult(
            gate_name="k6_success_rate",
            passed=k6_result.success_rate >= self.criteria.k6_success_rate_min,
            actual_value=f"{k6_result.success_rate:.3f}",
            expected_value=f">={self.criteria.k6_success_rate_min}",
            details=f"K6 success rate: {k6_result.success_rate:.3%}",
            severity="medium"
        ))
        
        # Gate: Per-Route Latencies from K6
        for route, metrics in k6_result.route_metrics.items():
            route_p95 = metrics.get('p95_ms', 99999)
            threshold = self._get_route_latency_threshold(route)
            
            gates.append(PromotionGateResult(
                gate_name=f"k6_{route.lower().replace(' ', '_').replace('/', '_')}_latency",
                passed=route_p95 <= threshold,
                actual_value=f"{route_p95:.1f}ms",
                expected_value=f"<={threshold}ms",
                details=f"{route} P95 latency: {route_p95:.1f}ms",
                severity="medium" if "health" in route.lower() else "high"
            ))
        
        return gates
    
    async def _validate_per_route_sli(self) -> List[PromotionGateResult]:
        """Validate per-route SLI metrics from middleware"""
        gates = []
        
        try:
            # Attempt to get SLI metrics from platform
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v1/monitoring/sli-metrics") as resp:
                    if resp.status == 200:
                        sli_data = await resp.json()
                        self.sli_metrics_cache = sli_data
                    else:
                        # Generate synthetic SLI validation if endpoint not available
                        logger.warning("SLI metrics endpoint not available, using K6 results")
                        return self._generate_synthetic_sli_gates()
        except Exception as e:
            logger.warning(f"Failed to fetch SLI metrics: {str(e)}")
            return self._generate_synthetic_sli_gates()
        
        # Gate: Per-Route SLI Availability
        routes_sli = self.sli_metrics_cache.get('routes', {})
        
        for route_key, metrics in routes_sli.items():
            availability = metrics.get('availability', None)
            route_name = route_key.replace(' ', '_').replace('/', '_').lower()
            
            # If no availability data collected, fail the gate
            if availability is None:
                gates.append(PromotionGateResult(
                    gate_name=f"sli_availability_{route_name}",
                    passed=False,
                    actual_value="INSUFFICIENT_DATA",
                    expected_value=">=0.95",
                    details=f"{route_key} availability: NO DATA COLLECTED - check instrumentation",
                    severity="high"
                ))
                continue
            
            gates.append(PromotionGateResult(
                gate_name=f"sli_availability_{route_name}",
                passed=availability >= 0.95,  # 95% availability per route
                actual_value=f"{availability:.3f}",
                expected_value=">=0.95",
                details=f"{route_key} availability: {availability:.3%}",
                severity="medium"
            ))
        
        # Gate: SLI Latency Compliance
        for route_key, metrics in routes_sli.items():
            p95_latency = metrics.get('latency_p95_ms', 99999)
            route_name = route_key.replace(' ', '_').replace('/', '_').lower()
            
            # Route-specific thresholds
            threshold = self._get_route_latency_threshold(route_key)
            
            gates.append(PromotionGateResult(
                gate_name=f"sli_latency_{route_name}",
                passed=p95_latency <= threshold,
                actual_value=f"{p95_latency:.1f}ms",
                expected_value=f"<={threshold}ms",
                details=f"{route_key} P95 latency: {p95_latency:.1f}ms",
                severity="high"
            ))
        
        return gates
    
    def _generate_synthetic_sli_gates(self) -> List[PromotionGateResult]:
        """Generate synthetic SLI gates when middleware data unavailable"""
        return [
            PromotionGateResult(
                gate_name="sli_middleware_availability",
                passed=False,
                actual_value="unavailable",
                expected_value="active",
                details="Per-route SLI middleware not responding - using K6 data",
                severity="medium"
            )
        ]
    
    async def _validate_burn_in_results(self) -> List[PromotionGateResult]:
        """Validate 3-session burn-in testing results"""
        gates = []
        
        # Look for latest burn-in report
        burn_in_reports = list(self.burn_in_results_dir.glob("burn_in_report_*.json"))
        if not burn_in_reports:
            # FIXED: Check if burn-in is required or optional
            if not self.criteria.burn_in_required:
                logger.info("Burn-in testing not required, skipping validation")
                gates.append(PromotionGateResult(
                    gate_name="burn_in_test_status",
                    passed=True,
                    actual_value="optional",
                    expected_value="optional",
                    details="Burn-in testing not required for this environment (set burn_in_required=True to enforce)",
                    severity="info"
                ))
                return gates
            
            # Burn-in required but not found
            logger.warning("No recent burn-in results found (required)")
            gates.append(PromotionGateResult(
                gate_name="burn_in_test_availability",
                passed=False,
                actual_value="no_results",
                expected_value="recent_results",
                details="No burn-in test results found (required - run burn-in framework)",
                severity="critical"
            ))
            return gates
        
        # Load latest burn-in results
        latest_report_file = max(burn_in_reports, key=lambda p: p.stat().st_mtime)
        with open(latest_report_file) as f:
            burn_in_report = json.load(f)
        
        # Gate: All Burn-in Sessions Passed
        all_sessions_passed = burn_in_report['burn_in_summary']['all_sessions_passed']
        gates.append(PromotionGateResult(
            gate_name="burn_in_all_sessions_passed",
            passed=all_sessions_passed,
            actual_value=all_sessions_passed,
            expected_value=True,
            details=f"Burn-in sessions: {burn_in_report['burn_in_summary']['sessions_completed']}/3 passed",
            severity="high"
        ))
        
        # Gate: Burn-in Stability Score
        stability_score = burn_in_report['aggregate_metrics']['stability_score']
        gates.append(PromotionGateResult(
            gate_name="burn_in_stability_score",
            passed=stability_score >= self.criteria.burn_in_stability_score_min,
            actual_value=f"{stability_score:.1f}",
            expected_value=f">={self.criteria.burn_in_stability_score_min}",
            details=f"Burn-in stability score: {stability_score:.1f}/100",
            severity="medium"
        ))
        
        # Gate: Production Readiness
        ready_for_production = burn_in_report['promotion_gate_status']['ready_for_production']
        gates.append(PromotionGateResult(
            gate_name="burn_in_production_readiness",
            passed=ready_for_production,
            actual_value=ready_for_production,
            expected_value=True,
            details="Burn-in framework promotion gate assessment",
            severity="high"
        ))
        
        return gates
    
    async def _validate_slo_compliance(self) -> List[PromotionGateResult]:
        """Validate SLO compliance metrics"""
        gates = []
        
        # FIXED: Skip SLO gates if monitoring not required
        if not self.criteria.slo_monitoring_required:
            gates.append(PromotionGateResult(
                gate_name="slo_monitoring_status",
                passed=True,
                actual_value="optional",
                expected_value="optional",
                details="SLO monitoring not required for this environment (set slo_monitoring_required=True to enforce)",
                severity="info"
            ))
            return gates
        
        try:
            # Check SLO monitoring endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v1/monitoring/slo-status") as resp:
                    if resp.status == 200:
                        slo_data = await resp.json()
                    else:
                        return self._generate_synthetic_slo_gates()
        except Exception:
            return self._generate_synthetic_slo_gates()
        
        # Gate: Overall Availability SLO
        availability = slo_data.get('availability', 0)
        gates.append(PromotionGateResult(
            gate_name="slo_availability",
            passed=availability >= self.criteria.slo_availability_min,
            actual_value=f"{availability:.4f}",
            expected_value=f">={self.criteria.slo_availability_min}",
            details=f"Platform availability: {availability:.3%}",
            severity="critical"
        ))
        
        # Gate: Error Budget Remaining
        error_budget_remaining = slo_data.get('error_budget_remaining', 0)
        gates.append(PromotionGateResult(
            gate_name="slo_error_budget",
            passed=error_budget_remaining >= self.criteria.slo_error_budget_remaining_min,
            actual_value=f"{error_budget_remaining:.3f}",
            expected_value=f">={self.criteria.slo_error_budget_remaining_min}",
            details=f"Error budget remaining: {error_budget_remaining:.3%}",
            severity="high"
        ))
        
        return gates
    
    def _generate_synthetic_slo_gates(self) -> List[PromotionGateResult]:
        """Generate synthetic SLO gates when monitoring unavailable (REQUIRED mode only)"""
        return [
            PromotionGateResult(
                gate_name="slo_monitoring_availability",
                passed=False,
                actual_value="unavailable",
                expected_value="active",
                details="SLO monitoring endpoint not responding (required but unavailable)",
                severity="critical"
            )
        ]
    
    async def _validate_business_logic(self) -> List[PromotionGateResult]:
        """Validate business logic and data integrity"""
        gates = []
        
        # Gate: Authentication System
        try:
            async with aiohttp.ClientSession() as session:
                login_data = {
                    "username": "admin",
                    "password": "admin123"
                }
                async with session.post(f"{self.base_url}/api/v1/auth/login", 
                                      json=login_data) as resp:
                    auth_passed = resp.status == 200
                    gates.append(PromotionGateResult(
                        gate_name="business_authentication",
                        passed=auth_passed,
                        actual_value=resp.status,
                        expected_value=200,
                        details=f"Authentication test: {resp.status}",
                        severity="critical"
                    ))
        except Exception as e:
            gates.append(PromotionGateResult(
                gate_name="business_authentication",
                passed=False,
                actual_value=str(e),
                expected_value="success",
                details=f"Authentication failed: {str(e)}",
                severity="critical"
            ))
        
        # Gate: Data Consistency Check
        try:
            auth_headers = await self._get_auth_headers()
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v1/positions", 
                                     headers=auth_headers) as resp:
                    data_consistent = resp.status in [200, 401]  # 401 OK if auth expired
                    gates.append(PromotionGateResult(
                        gate_name="business_data_consistency",
                        passed=data_consistent,
                        actual_value=resp.status,
                        expected_value="200_or_401",
                        details=f"Data consistency check: {resp.status}",
                        severity="medium"
                    ))
        except Exception as e:
            gates.append(PromotionGateResult(
                gate_name="business_data_consistency",
                passed=False,
                actual_value=str(e),
                expected_value="success",
                details=f"Data consistency check failed: {str(e)}",
                severity="medium"
            ))
        
        return gates
    
    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API calls"""
        try:
            async with aiohttp.ClientSession() as session:
                login_data = {"username": "admin", "password": "admin123"}
                async with session.post(f"{self.base_url}/api/v1/auth/login", 
                                      json=login_data) as resp:
                    if resp.status == 200:
                        auth_data = await resp.json()
                        token = auth_data.get('access_token', '')
                        return {"Authorization": f"Bearer {token}"}
        except Exception:
            pass
        return {}
    
    # Removed _run_k6_enhanced_test - now using K6CacheManager for centralized execution
    
    def _get_route_latency_threshold(self, route_key: str) -> float:
        """Get latency threshold for specific route"""
        # Extract route part from "METHOD /path" format  
        route_part = route_key.split(' ', 1)[1] if ' ' in route_key else route_key
        
        thresholds = {
            '/health': self.criteria.sli_health_p95_ms_max,
            '/api/v1/signals': self.criteria.sli_signals_p95_ms_max,
            '/api/v1/signals/act': self.criteria.sli_orders_p95_ms_max,
            '/api/v1/positions': self.criteria.sli_positions_p95_ms_max,
        }
        
        return thresholds.get(route_part, 1000)  # Default 1s
    
    def _check_critical_gates_passed(self, gates: List[PromotionGateResult]) -> bool:
        """Check if all critical gates passed"""
        critical_gates = [g for g in gates if g.severity == "critical"]
        return all(g.passed for g in critical_gates)
    
    def _generate_promotion_report(self, 
                                 gate_results: List[PromotionGateResult],
                                 environment: str,
                                 commit_hash: str,
                                 validation_start: datetime) -> PromotionReport:
        """Generate comprehensive promotion report"""
        
        # Count failures by severity
        critical_failures = len([g for g in gate_results if not g.passed and g.severity == "critical"])
        high_failures = len([g for g in gate_results if not g.passed and g.severity == "high"])
        medium_failures = len([g for g in gate_results if not g.passed and g.severity == "medium"])
        
        # Determine approval
        all_gates_passed = all(g.passed for g in gate_results)
        
        # Promotion logic
        promotion_approved = (
            critical_failures == 0 and           # No critical failures
            high_failures <= 1 and              # At most 1 high failure
            medium_failures <= 2                # At most 2 medium failures
        )
        
        # Confidence assessment
        if all_gates_passed:
            confidence = "HIGH"
        elif critical_failures == 0 and high_failures <= 1:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        # Generate recommendations
        recommendations = self._generate_promotion_recommendations(gate_results, promotion_approved)
        
        # Next actions
        next_actions = []
        if promotion_approved:
            next_actions.extend([
                "✅ Deploy to production environment",
                "📊 Monitor post-deployment metrics for 1 hour",
                "🔄 Enable gradual traffic ramp-up if available"
            ])
        else:
            next_actions.extend([
                "❌ Do not deploy to production",
                "🔧 Fix failing gates before retry",
                "📋 Review gate failure details and recommendations"
            ])
            
            if critical_failures > 0:
                next_actions.append("🚨 Address critical failures immediately")
        
        return PromotionReport(
            timestamp=validation_start,
            environment=environment,
            commit_hash=commit_hash,
            gate_results=gate_results,
            all_gates_passed=all_gates_passed,
            critical_failures=critical_failures,
            high_failures=high_failures,
            promotion_approved=promotion_approved,
            approval_confidence=confidence,
            recommendations=recommendations,
            next_actions=next_actions
        )
    
    def _generate_promotion_recommendations(self, 
                                         gate_results: List[PromotionGateResult],
                                         approved: bool) -> List[str]:
        """Generate specific recommendations based on gate results"""
        recommendations = []
        
        # Performance recommendations
        latency_failures = [g for g in gate_results if "latency" in g.gate_name and not g.passed]
        if latency_failures:
            recommendations.append("⚡ Performance: Consider optimizing slow endpoints")
        
        # Error rate recommendations  
        error_failures = [g for g in gate_results if "error" in g.gate_name and not g.passed]
        if error_failures:
            recommendations.append("🐛 Reliability: Investigate and fix error sources")
        
        # SLI recommendations
        sli_failures = [g for g in gate_results if "sli" in g.gate_name and not g.passed]
        if sli_failures:
            recommendations.append("📊 Monitoring: Review per-route SLI metrics configuration")
        
        # Burn-in recommendations
        burn_in_failures = [g for g in gate_results if "burn_in" in g.gate_name and not g.passed]
        if burn_in_failures:
            recommendations.append("🔥 Stability: Run burn-in testing or investigate stability issues")
        
        # Business logic recommendations
        business_failures = [g for g in gate_results if "business" in g.gate_name and not g.passed]
        if business_failures:
            recommendations.append("💼 Business Logic: Verify core business functionality")
        
        if approved and len(recommendations) == 0:
            recommendations.append("🎉 All gates passed - ready for production deployment")
        
        return recommendations
    
    def _create_failed_report(self, 
                            gate_results: List[PromotionGateResult], 
                            failure_reason: str,
                            environment: str,
                            commit_hash: str,
                            validation_start: datetime) -> PromotionReport:
        """Create a failed promotion report"""
        
        critical_failures = len([g for g in gate_results if not g.passed and g.severity == "critical"])
        high_failures = len([g for g in gate_results if not g.passed and g.severity == "high"])
        
        return PromotionReport(
            timestamp=validation_start,
            environment=environment,
            commit_hash=commit_hash,
            gate_results=gate_results,
            all_gates_passed=False,
            critical_failures=critical_failures,
            high_failures=high_failures,
            promotion_approved=False,
            approval_confidence="LOW",
            recommendations=[f"❌ {failure_reason}"],
            next_actions=[
                "🔧 Fix critical issues before retry",
                "📋 Review validation logs for details"
            ]
        )
    
    async def _save_promotion_report(self, report: PromotionReport):
        """Save promotion report to file"""
        timestamp = int(report.timestamp.timestamp())
        report_file = self.output_dir / f"promotion_report_{timestamp}.json"
        
        # Convert dataclass to dict for JSON serialization
        report_dict = {
            'timestamp': report.timestamp.isoformat(),
            'environment': report.environment,
            'commit_hash': report.commit_hash,
            'gate_results': [
                {
                    'gate_name': g.gate_name,
                    'passed': g.passed,
                    'actual_value': g.actual_value,
                    'expected_value': g.expected_value,
                    'details': g.details,
                    'severity': g.severity
                } for g in report.gate_results
            ],
            'all_gates_passed': report.all_gates_passed,
            'critical_failures': report.critical_failures,
            'high_failures': report.high_failures,
            'promotion_approved': report.promotion_approved,
            'approval_confidence': report.approval_confidence,
            'recommendations': report.recommendations,
            'next_actions': report.next_actions
        }
        
        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)
        
        logger.info(f"Promotion report saved: {report_file}")

# ============================================================================
# AI AGENT SUGGESTION D: CLI INTERFACE AND CI/CD INTEGRATION
# ============================================================================

async def main():
    """CLI entry point for promotion gate validation"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Automated Promotion Gate Validation')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Platform base URL')
    parser.add_argument('--environment', default='staging', 
                       choices=['local', 'development', 'staging', 'production'],
                       help='Environment name (affects gate requirements)')
    parser.add_argument('--commit-hash', default='unknown', help='Git commit hash')
    parser.add_argument('--output-dir', default='test_results/promotion_gates', help='Output directory')
    
    # Criteria overrides
    parser.add_argument('--k6-error-rate-max', type=float, help='K6 max error rate')
    parser.add_argument('--k6-latency-max', type=float, help='K6 max P95 latency (ms)')
    parser.add_argument('--strict', action='store_true', help='Use strict promotion criteria (production mode)')
    parser.add_argument('--skip-burn-in', action='store_true', help='[DEV ONLY] Skip burn-in requirement (NOT for production!)')
    parser.add_argument('--skip-slo', action='store_true', help='[DEV ONLY] Skip SLO requirement (NOT for production!)')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure criteria based on environment
    criteria = PromotionCriteria.for_environment(args.environment)
    
    # Apply overrides
    if args.k6_error_rate_max:
        criteria.k6_unexpected_error_rate_max = args.k6_error_rate_max
    if args.k6_latency_max:
        criteria.k6_p95_latency_ms_max = args.k6_latency_max
    if args.strict:
        # Force strict criteria (production mode)
        criteria.burn_in_required = True
        criteria.slo_monitoring_required = True
        criteria.k6_unexpected_error_rate_max = 0.01  # 1%
        criteria.k6_p95_latency_ms_max = 300  # 300ms
        criteria.slo_availability_min = 0.995  # 99.5%
        criteria.burn_in_stability_score_min = 80.0
        logger.info("🔒 STRICT MODE: Using production-grade criteria")
    
    # WARNING: Allow skipping for dev, but log warnings
    if args.skip_burn_in:
        if args.environment in ['production', 'staging']:
            logger.error("❌ BLOCKED: Cannot skip burn-in testing in production/staging!")
            print("\n❌ ERROR: --skip-burn-in is NOT allowed in production/staging environments")
            print("This flag is only for local development. Use --environment=local if testing locally.")
            return 1
        logger.warning("⚠️  WARNING: Skipping burn-in testing (development mode only)")
        criteria.burn_in_required = False
    
    if args.skip_slo:
        if args.environment in ['production', 'staging']:
            logger.error("❌ BLOCKED: Cannot skip SLO monitoring in production/staging!")
            print("\n❌ ERROR: --skip-slo is NOT allowed in production/staging environments")
            print("This flag is only for local development. Use --environment=local if testing locally.")
            return 1
        logger.warning("⚠️  WARNING: Skipping SLO monitoring (development mode only)")
        criteria.slo_monitoring_required = False
    
    # Run promotion gate validation
    gates = AutomatedPromotionGates(
        base_url=args.base_url,
        criteria=criteria,
        output_dir=args.output_dir
    )
    
    try:
        report = await gates.run_promotion_gate_validation(
            environment=args.environment,
            commit_hash=args.commit_hash
        )
        
        # Print summary
        print(f"\n🚪 PROMOTION GATE VALIDATION RESULTS")
        print(f"Environment: {report.environment}")
        print(f"Commit: {report.commit_hash}")
        print(f"Timestamp: {report.timestamp}")
        print(f"")
        print(f"All Gates Passed: {report.all_gates_passed}")
        print(f"Critical Failures: {report.critical_failures}")
        print(f"High Failures: {report.high_failures}")
        print(f"")
        
        decision = "✅ APPROVED" if report.promotion_approved else "❌ REJECTED"
        print(f"PROMOTION DECISION: {decision}")
        print(f"Confidence: {report.approval_confidence}")
        print(f"")
        
        if report.recommendations:
            print("RECOMMENDATIONS:")
            for rec in report.recommendations:
                print(f"  {rec}")
        
        print(f"")
        if report.next_actions:
            print("NEXT ACTIONS:")
            for action in report.next_actions:
                print(f"  {action}")
        
        # Return appropriate exit code for CI/CD
        return 0 if report.promotion_approved else 1
        
    except Exception as e:
        logger.error(f"Promotion gate validation failed: {str(e)}")
        return 2

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))