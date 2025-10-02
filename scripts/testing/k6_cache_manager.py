# K6 Cache Manager - Centralized K6 Execution and Result Caching
# =============================================================
# Eliminates redundant K6 executions across multiple test suites
# Provides unified K6 script management and intelligent result caching
# Used by: automated_promotion_gates.py, burn_in_framework.py, test_layer5_business_workflows.py

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import hashlib
# Using standard async file operations instead of aiofiles to avoid extra dependency

logger = logging.getLogger(__name__)

@dataclass
class K6ExecutionConfig:
    """Configuration for K6 test execution"""
    
    # Test Parameters
    duration: str = "30s"           # Test duration (e.g., "30s", "5m")
    virtual_users: int = 10         # Number of virtual users
    base_url: str = "http://localhost:8000"  # Target base URL
    
    # Script Configuration  
    k6_script: str = "scripts/testing/k6_enhanced_comprehensive_test.js"
    scenarios: List[str] = None     # Specific scenarios to run
    
    # Output Configuration
    results_dir: str = "test_results"
    summary_output: bool = True     # Generate summary JSON
    html_report: bool = False       # Generate HTML report
    
    # Caching Configuration
    cache_ttl_minutes: int = 30     # How long results are considered fresh
    force_refresh: bool = False     # Force new execution even if cached results exist
    
    def __post_init__(self):
        if self.scenarios is None:
            self.scenarios = []
    
    def get_cache_key(self) -> str:
        """Generate unique cache key for this configuration"""
        # Include key parameters that affect test results
        key_data = {
            "duration": self.duration,
            "virtual_users": self.virtual_users, 
            "base_url": self.base_url,
            "k6_script": self.k6_script,
            "scenarios": sorted(self.scenarios) if self.scenarios else []
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

@dataclass
class K6TestResult:
    """Standardized K6 test results"""
    
    # Execution Metadata
    execution_id: str
    cache_key: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    
    # Test Configuration
    config: K6ExecutionConfig
    
    # Performance Metrics
    total_requests: int = 0
    failed_requests: int = 0  
    success_rate: float = 0.0
    
    # Latency Metrics (milliseconds)
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    
    # Error Analysis
    unexpected_error_rate: float = 0.0
    error_details: Dict[str, int] = None
    
    # Per-Route Metrics
    route_metrics: Dict[str, Dict[str, Any]] = None
    
    # Raw Results
    raw_summary: Dict[str, Any] = None
    raw_output: str = ""
    
    # Status
    test_passed: bool = False
    failure_reasons: List[str] = None
    
    def __post_init__(self):
        if self.error_details is None:
            self.error_details = {}
        if self.route_metrics is None:
            self.route_metrics = {}
        if self.failure_reasons is None:
            self.failure_reasons = []

class K6CacheManager:
    """
    Centralized K6 execution and intelligent result caching
    
    Features:
    - Eliminates redundant K6 executions across test suites
    - Intelligent caching with configurable TTL
    - Unified K6 script management
    - Standardized result format for all consumers
    - Async execution with proper resource management
    - Comprehensive error handling and logging
    """
    
    def __init__(self, 
                 default_results_dir: str = "test_results",
                 default_cache_ttl_minutes: int = 30):
        """
        Initialize K6 Cache Manager
        
        Args:
            default_results_dir: Default directory for storing K6 results
            default_cache_ttl_minutes: Default cache TTL in minutes
        """
        self.results_dir = Path(default_results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
        self.cache_dir = self.results_dir / "k6_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.default_cache_ttl = default_cache_ttl_minutes
        self._execution_lock = asyncio.Lock()  # Prevent concurrent K6 executions
        
        logger.info(f"K6 Cache Manager initialized - Results: {self.results_dir}, Cache: {self.cache_dir}")
    
    async def get_k6_results(self, config: K6ExecutionConfig) -> K6TestResult:
        """
        Get K6 test results - from cache if fresh, otherwise execute new test
        
        Args:
            config: K6 execution configuration
            
        Returns:
            K6TestResult with performance metrics and analysis
            
        Raises:
            Exception: If K6 execution fails and no fallback available
        """
        cache_key = config.get_cache_key()
        
        # Check for cached results first (unless force refresh)
        if not config.force_refresh:
            cached_result = await self._get_cached_result(cache_key, config.cache_ttl_minutes)
            if cached_result:
                logger.info(f"Using cached K6 results (key: {cache_key})")
                return cached_result
        
        # Execute new K6 test
        logger.info(f"Executing new K6 test (key: {cache_key})")
        async with self._execution_lock:  # Prevent concurrent K6 runs
            result = await self._execute_k6_test(config, cache_key)
            
        # Cache the results
        await self._cache_result(result)
        
        return result
    
    async def _get_cached_result(self, cache_key: str, ttl_minutes: int) -> Optional[K6TestResult]:
        """Get cached K6 result if it exists and is fresh"""
        cache_file = self.cache_dir / f"k6_result_{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if result is fresh
            result_time = datetime.fromisoformat(cache_data['end_time'])
            age_minutes = (datetime.now() - result_time).total_seconds() / 60
            
            if age_minutes > ttl_minutes:
                logger.info(f"Cached result expired (age: {age_minutes:.1f}m, TTL: {ttl_minutes}m)")
                return None
            
            # Reconstruct K6TestResult from cached data
            config_data = cache_data['config']
            config = K6ExecutionConfig(**config_data)
            
            result = K6TestResult(
                execution_id=cache_data['execution_id'],
                cache_key=cache_data['cache_key'],
                start_time=datetime.fromisoformat(cache_data['start_time']),
                end_time=datetime.fromisoformat(cache_data['end_time']),
                duration_seconds=cache_data['duration_seconds'],
                config=config,
                total_requests=cache_data.get('total_requests', 0),
                failed_requests=cache_data.get('failed_requests', 0),
                success_rate=cache_data.get('success_rate', 0.0),
                avg_latency_ms=cache_data.get('avg_latency_ms', 0.0),
                p95_latency_ms=cache_data.get('p95_latency_ms', 0.0),
                p99_latency_ms=cache_data.get('p99_latency_ms', 0.0),
                min_latency_ms=cache_data.get('min_latency_ms', 0.0),
                max_latency_ms=cache_data.get('max_latency_ms', 0.0),
                unexpected_error_rate=cache_data.get('unexpected_error_rate', 0.0),
                error_details=cache_data.get('error_details', {}),
                route_metrics=cache_data.get('route_metrics', {}),
                raw_summary=cache_data.get('raw_summary', {}),
                raw_output=cache_data.get('raw_output', ''),
                test_passed=cache_data.get('test_passed', False),
                failure_reasons=cache_data.get('failure_reasons', [])
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to load cached result: {str(e)}")
            return None
    
    async def _execute_k6_test(self, config: K6ExecutionConfig, cache_key: str) -> K6TestResult:
        """Execute K6 test with given configuration"""
        execution_id = f"k6_{int(time.time())}_{cache_key}"
        start_time = datetime.now()
        
        # Validate K6 script exists
        k6_script_path = Path(config.k6_script)
        if not k6_script_path.exists():
            raise Exception(f"K6 script not found: {config.k6_script}")
        
        # Prepare output files
        summary_file = self.results_dir / f"k6-summary-{execution_id}.json"
        
        # Build K6 command
        cmd = [
            "k6", "run",
            "--duration", config.duration,
            "--vus", str(config.virtual_users),
            "--summary-export", str(summary_file)
        ]
        
        # Add HTML report if requested
        if config.html_report:
            html_file = self.results_dir / f"k6-report-{execution_id}.html"
            cmd.extend(["--out", f"web-dashboard={html_file}"])
        
        # Add script path
        cmd.append(str(k6_script_path))
        
        # Set environment variables for K6 script
        import os
        env = os.environ.copy()
        env["BASE_URL"] = config.base_url
        
        try:
            # Execute K6 test
            logger.info(f"Running K6: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            
            stdout, _ = await process.communicate()
            raw_output = stdout.decode('utf-8', errors='replace')
            
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            # Process results
            result = await self._process_k6_results(
                execution_id, cache_key, config, start_time, end_time, 
                duration_seconds, summary_file, raw_output, process.returncode
            )
            
            return result
            
        except Exception as e:
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            logger.error(f"K6 execution failed: {str(e)}")
            
            # Return failed result
            return K6TestResult(
                execution_id=execution_id,
                cache_key=cache_key,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                config=config,
                test_passed=False,
                failure_reasons=[f"K6 execution failed: {str(e)}"],
                raw_output=str(e)
            )
    
    async def _process_k6_results(self, execution_id: str, cache_key: str, config: K6ExecutionConfig,
                                start_time: datetime, end_time: datetime, duration_seconds: float,
                                summary_file: Path, raw_output: str, return_code: int) -> K6TestResult:
        """Process K6 execution results into standardized format"""
        
        result = K6TestResult(
            execution_id=execution_id,
            cache_key=cache_key,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            config=config,
            raw_output=raw_output
        )
        
        try:
            # Load K6 summary JSON if available
            if summary_file.exists():
                with open(summary_file, 'r') as f:
                    summary_data = json.load(f)
                result.raw_summary = summary_data
                
                # Extract standard metrics
                await self._extract_standard_metrics(result, summary_data)
                
                # Extract route-specific metrics
                await self._extract_route_metrics(result, summary_data)
                
                # Evaluate test success
                result.test_passed = self._evaluate_test_success(result, return_code)
            else:
                result.failure_reasons.append("K6 summary file not generated")
                logger.warning(f"K6 summary file not found: {summary_file}")
        
        except Exception as e:
            result.failure_reasons.append(f"Result processing failed: {str(e)}")
            logger.error(f"Failed to process K6 results: {str(e)}")
        
        return result
    
    async def _extract_standard_metrics(self, result: K6TestResult, summary_data: Dict[str, Any]):
        """Extract standard performance metrics from K6 summary"""
        try:
            metrics = summary_data.get('metrics', {})
            
            # HTTP request metrics
            http_reqs = metrics.get('http_reqs', {})
            if http_reqs:
                result.total_requests = int(http_reqs.get('count', 0))
            
            # HTTP failures
            http_req_failed = metrics.get('http_req_failed', {})
            if http_req_failed:
                failed_rate = float(http_req_failed.get('rate', 0))
                result.failed_requests = int(result.total_requests * failed_rate)
                result.success_rate = 1.0 - failed_rate
            
            # Latency metrics
            http_req_duration = metrics.get('http_req_duration', {})
            if http_req_duration:
                values = http_req_duration.get('values', {})
                result.avg_latency_ms = float(values.get('avg', 0))
                result.p95_latency_ms = float(values.get('p(95)', 0))
                result.p99_latency_ms = float(values.get('p(99)', 0))
                result.min_latency_ms = float(values.get('min', 0))
                result.max_latency_ms = float(values.get('max', 0))
            
            # Unexpected error rate (custom metric from enhanced K6 script)
            unexpected_errors = metrics.get('unexpected_error_rate', {})
            if unexpected_errors:
                result.unexpected_error_rate = float(unexpected_errors.get('rate', 0))
            
        except Exception as e:
            logger.warning(f"Failed to extract standard metrics: {str(e)}")
    
    async def _extract_route_metrics(self, result: K6TestResult, summary_data: Dict[str, Any]):
        """Extract per-route performance metrics from K6 summary"""
        try:
            # This will depend on how the enhanced K6 script reports per-route metrics
            # For now, we'll parse from the raw output or look for tagged metrics
            
            metrics = summary_data.get('metrics', {})
            
            # Look for route-tagged metrics (if K6 script uses tags)
            for metric_name, metric_data in metrics.items():
                if 'tags' in metric_data:
                    # Process tagged metrics for routes
                    pass  # Implementation depends on K6 script tagging strategy
                    
        except Exception as e:
            logger.warning(f"Failed to extract route metrics: {str(e)}")
    
    def _evaluate_test_success(self, result: K6TestResult, return_code: int) -> bool:
        """Evaluate if K6 test passed based on metrics and return code"""
        if return_code != 0:
            result.failure_reasons.append(f"K6 exited with code {return_code}")
            return False
        
        # Success criteria (can be made configurable)
        success_criteria = [
            (result.success_rate >= 0.95, f"Success rate too low: {result.success_rate:.3f}"),
            (result.unexpected_error_rate <= 0.05, f"Unexpected error rate too high: {result.unexpected_error_rate:.3f}"),
            (result.p95_latency_ms <= 1000, f"P95 latency too high: {result.p95_latency_ms:.1f}ms"),
        ]
        
        passed = True
        for criterion, failure_msg in success_criteria:
            if not criterion:
                result.failure_reasons.append(failure_msg)
                passed = False
        
        return passed
    
    async def _cache_result(self, result: K6TestResult):
        """Cache K6 test result for future use"""
        try:
            cache_file = self.cache_dir / f"k6_result_{result.cache_key}.json"
            
            # Convert result to JSON-serializable format
            cache_data = {
                'execution_id': result.execution_id,
                'cache_key': result.cache_key,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'duration_seconds': result.duration_seconds,
                'config': asdict(result.config),
                'total_requests': result.total_requests,
                'failed_requests': result.failed_requests,
                'success_rate': result.success_rate,
                'avg_latency_ms': result.avg_latency_ms,
                'p95_latency_ms': result.p95_latency_ms,
                'p99_latency_ms': result.p99_latency_ms,
                'min_latency_ms': result.min_latency_ms,
                'max_latency_ms': result.max_latency_ms,
                'unexpected_error_rate': result.unexpected_error_rate,
                'error_details': result.error_details,
                'route_metrics': result.route_metrics,
                'raw_summary': result.raw_summary,
                'raw_output': result.raw_output,
                'test_passed': result.test_passed,
                'failure_reasons': result.failure_reasons
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.info(f"Cached K6 result: {cache_file}")
            
        except Exception as e:
            logger.warning(f"Failed to cache K6 result: {str(e)}")
    
    async def clear_cache(self, older_than_hours: Optional[int] = None):
        """Clear cached K6 results"""
        try:
            cache_files = list(self.cache_dir.glob("k6_result_*.json"))
            
            if older_than_hours is not None:
                cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
                cache_files = [f for f in cache_files if 
                              datetime.fromtimestamp(f.stat().st_mtime) < cutoff_time]
            
            for cache_file in cache_files:
                cache_file.unlink()
            
            logger.info(f"Cleared {len(cache_files)} cached K6 results")
            
        except Exception as e:
            logger.warning(f"Failed to clear cache: {str(e)}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            cache_files = list(self.cache_dir.glob("k6_result_*.json"))
            
            if not cache_files:
                return {"cache_files": 0, "total_size_mb": 0, "oldest": None, "newest": None}
            
            total_size = sum(f.stat().st_size for f in cache_files)
            timestamps = [datetime.fromtimestamp(f.stat().st_mtime) for f in cache_files]
            
            return {
                "cache_files": len(cache_files),
                "total_size_mb": total_size / (1024 * 1024),
                "oldest": min(timestamps).isoformat(),
                "newest": max(timestamps).isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {str(e)}")
            return {"error": str(e)}

# Convenience function for simple usage
async def get_k6_results(duration: str = "30s", 
                        virtual_users: int = 10,
                        base_url: str = "http://localhost:8000",
                        cache_ttl_minutes: int = 30,
                        force_refresh: bool = False) -> K6TestResult:
    """
    Convenience function to get K6 results with default configuration
    
    Args:
        duration: Test duration (e.g., "30s", "5m")  
        virtual_users: Number of concurrent users
        base_url: Target application base URL
        cache_ttl_minutes: How long to consider cached results fresh
        force_refresh: Force new execution even if cached results exist
        
    Returns:
        K6TestResult with performance metrics
    """
    config = K6ExecutionConfig(
        duration=duration,
        virtual_users=virtual_users,
        base_url=base_url,
        cache_ttl_minutes=cache_ttl_minutes,
        force_refresh=force_refresh
    )
    
    cache_manager = K6CacheManager()
    return await cache_manager.get_k6_results(config)

# Note: os module imported locally where needed