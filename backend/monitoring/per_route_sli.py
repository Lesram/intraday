# Per-Route SLI Metrics Middleware - AI Agent Suggestion B
# =========================================================
# Implements production-grade per-route SLI metrics collection for FastAPI
# Provides route-specific latency, success rates, and Prometheus metrics
# Integrates with existing SLO monitoring for automated promotion gates

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
from prometheus_client import Counter, Histogram, Gauge
import time
import asyncio
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# AI AGENT SUGGESTION B: PER-ROUTE PROMETHEUS METRICS
# ============================================================================

# Per-route latency histogram (with route labels)
route_request_duration = Histogram(
    'http_request_duration_seconds',
    'Request latency by route and method',
    ['method', 'route', 'status_code']
)

# Per-route request counter
route_request_total = Counter(
    'http_requests_total',
    'Total requests by route, method and status',
    ['method', 'route', 'status_code']
)

# Per-route SLI success rate
route_success_rate = Gauge(
    'http_route_success_rate',
    'Success rate per route (2xx responses)',
    ['method', 'route']
)

# Per-route error rate by type
route_error_rate = Gauge(
    'http_route_error_rate',
    'Error rate per route by error type',
    ['method', 'route', 'error_type']
)

# Active request gauge per route
active_requests_per_route = Gauge(
    'http_active_requests',
    'Current active requests per route',
    ['method', 'route']
)

# Business-specific SLI metrics
business_operation_duration = Histogram(
    'business_operation_duration_seconds',
    'Business operation latency',
    ['operation', 'outcome']
)

business_operation_total = Counter(
    'business_operations_total',
    'Total business operations',
    ['operation', 'outcome']
)

class PerRouteSLIMiddleware(BaseHTTPMiddleware):
    """
    AI Agent Suggestion B: Per-route SLI metrics collection middleware
    
    Collects detailed metrics per API route for:
    - Request latency (P50, P95, P99)
    - Success rates (2xx vs 4xx vs 5xx)
    - Active request counts
    - Business operation outcomes
    
    Designed for integration with Prometheus and SLO monitoring.
    """
    
    def __init__(self, app, enable_detailed_logging: bool = False):
        super().__init__(app)
        self.enable_detailed_logging = enable_detailed_logging
        self.route_stats: Dict[str, Dict[str, Any]] = {}
        
    async def dispatch(self, request: Request, call_next):
        # Extract route information
        route_info = self._extract_route_info(request)
        method = request.method
        route_path = route_info['path']
        route_key = f"{method} {route_path}"
        
        # Track active requests
        active_requests_per_route.labels(
            method=method, 
            route=route_path
        ).inc()
        
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate metrics
            duration = time.time() - start_time
            status_code = response.status_code
            
            # Record Prometheus metrics
            self._record_prometheus_metrics(
                method, route_path, status_code, duration
            )
            
            # Record business metrics if applicable
            await self._record_business_metrics(
                request, response, route_info, duration
            )
            
            # Update in-memory route stats for SLO calculations
            self._update_route_stats(route_key, status_code, duration)
            
            if self.enable_detailed_logging:
                logger.info(
                    f"Route: {route_key} | "
                    f"Status: {status_code} | "
                    f"Duration: {duration:.3f}s | "
                    f"User: {getattr(request.state, 'user_id', 'anonymous')}"
                )
            
            return response
            
        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            
            route_request_duration.labels(
                method=method,
                route=route_path,
                status_code='500'
            ).observe(duration)
            
            route_request_total.labels(
                method=method,
                route=route_path,
                status_code='500'
            ).inc()
            
            self._update_route_stats(route_key, 500, duration)
            
            logger.error(f"Route {route_key} error: {str(e)}")
            raise
            
        finally:
            # Decrement active requests
            active_requests_per_route.labels(
                method=method,
                route=route_path
            ).dec()
    
    def _extract_route_info(self, request: Request) -> Dict[str, str]:
        """Extract normalized route information from request"""
        # Get the route path, normalizing path parameters
        path = str(request.url.path)
        
        # Normalize common path parameters to avoid metric explosion
        normalized_path = self._normalize_path(path)
        
        return {
            'path': normalized_path,
            'raw_path': path,
            'query': str(request.url.query) if request.url.query else None
        }
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalize paths to reduce cardinality for Prometheus labels
        
        Examples:
        /api/v1/orders/12345 -> /api/v1/orders/{order_id}
        /api/v1/users/abc123/positions -> /api/v1/users/{user_id}/positions
        """
        import re
        
        # Common patterns to normalize
        patterns = [
            (r'/api/v1/orders/[^/]+', '/api/v1/orders/{order_id}'),
            (r'/api/v1/users/[^/]+', '/api/v1/users/{user_id}'),
            (r'/api/v1/positions/[^/]+', '/api/v1/positions/{position_id}'),
            (r'/api/v1/signals/[^/]+', '/api/v1/signals/{signal_id}'),
            (r'/api/v1/portfolios/[^/]+', '/api/v1/portfolios/{portfolio_id}'),
        ]
        
        normalized = path
        for pattern, replacement in patterns:
            normalized = re.sub(pattern, replacement, normalized)
        
        return normalized
    
    def _record_prometheus_metrics(self, method: str, route: str, status: int, duration: float):
        """Record per-route Prometheus metrics"""
        status_str = str(status)
        
        # Record latency
        route_request_duration.labels(
            method=method,
            route=route,
            status_code=status_str
        ).observe(duration)
        
        # Record request count
        route_request_total.labels(
            method=method,
            route=route,
            status_code=status_str
        ).inc()
        
        # Update success rate (calculated from counters)
        # Note: Prometheus gauges are updated periodically by SLO monitoring
    
    async def _record_business_metrics(self, request: Request, response: Response, route_info: Dict, duration: float):
        """Record business-specific SLI metrics"""
        route = route_info['path']
        method = request.method
        status = response.status_code
        
        # Map API routes to business operations
        business_op = self._map_route_to_business_operation(method, route)
        
        if business_op:
            outcome = 'success' if 200 <= status < 400 else 'error'
            
            business_operation_duration.labels(
                operation=business_op,
                outcome=outcome
            ).observe(duration)
            
            business_operation_total.labels(
                operation=business_op,
                outcome=outcome
            ).inc()
    
    def _map_route_to_business_operation(self, method: str, route: str) -> str:
        """Map API routes to business operation names"""
        operations = {
            'POST /api/v1/auth/login': 'user_authentication',
            'POST /api/v1/signals/act': 'signal_processing',
            'GET /api/v1/positions': 'portfolio_query',
            'GET /api/v1/orders': 'order_status_query', 
            'POST /api/v1/orders': 'order_submission',
            'GET /api/v1/signals': 'signal_query',
            'GET /api/v1/risk/metrics': 'risk_assessment',
            'GET /health': 'health_check',
        }
        
        route_key = f"{method} {route}"
        return operations.get(route_key, 'unknown_operation')
    
    def _update_route_stats(self, route_key: str, status_code: int, duration: float):
        """Update in-memory route statistics for SLO calculations"""
        if route_key not in self.route_stats:
            self.route_stats[route_key] = {
                'total_requests': 0,
                'success_count': 0,
                'error_count': 0,
                'latencies': [],
                'last_update': time.time()
            }
        
        stats = self.route_stats[route_key]
        stats['total_requests'] += 1
        stats['latencies'].append(duration)
        stats['last_update'] = time.time()
        
        if 200 <= status_code < 400:
            stats['success_count'] += 1
        else:
            stats['error_count'] += 1
        
        # Keep only recent latencies (last 1000 requests) to prevent memory bloat
        if len(stats['latencies']) > 1000:
            stats['latencies'] = stats['latencies'][-1000:]
    
    def get_route_sli_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        Get current SLI metrics for all routes
        Used by SLO monitoring and promotion gate validation
        """
        current_time = time.time()
        sli_metrics = {}
        
        for route_key, stats in self.route_stats.items():
            if stats['total_requests'] == 0:
                continue
            
            latencies = stats['latencies']
            
            # Calculate SLI metrics
            success_rate = stats['success_count'] / stats['total_requests']
            error_rate = stats['error_count'] / stats['total_requests']
            
            # Calculate latency percentiles
            if latencies:
                sorted_latencies = sorted(latencies)
                n = len(sorted_latencies)
                p50 = sorted_latencies[int(n * 0.5)]
                p95 = sorted_latencies[int(n * 0.95)] if n > 20 else sorted_latencies[-1]
                p99 = sorted_latencies[int(n * 0.99)] if n > 100 else sorted_latencies[-1]
                avg_latency = sum(latencies) / len(latencies)
            else:
                p50 = p95 = p99 = avg_latency = 0
            
            sli_metrics[route_key] = {
                'success_rate': success_rate,
                'error_rate': error_rate,
                'p50_latency_ms': p50 * 1000,
                'p95_latency_ms': p95 * 1000,
                'p99_latency_ms': p99 * 1000,
                'avg_latency_ms': avg_latency * 1000,
                'total_requests': stats['total_requests'],
                'requests_per_minute': self._calculate_requests_per_minute(stats, current_time)
            }
        
        return sli_metrics
    
    def _calculate_requests_per_minute(self, stats: Dict, current_time: float) -> float:
        """Calculate requests per minute based on recent activity"""
        # Simple calculation - could be enhanced with sliding window
        time_diff = current_time - stats['last_update']
        if time_diff > 0:
            return (stats['total_requests'] / (time_diff / 60))
        return 0.0
    
    def reset_stats(self):
        """Reset all route statistics (useful for testing)"""
        self.route_stats.clear()

# ============================================================================
# AI AGENT SUGGESTION B: SLO INTEGRATION HELPER
# ============================================================================

class SLOMetricsExporter:
    """
    Exports per-route SLI metrics to SLO monitoring system
    Integrates with existing backend/monitoring/slo_*.py modules
    """
    
    def __init__(self, sli_middleware: PerRouteSLIMiddleware):
        self.sli_middleware = sli_middleware
        self.logger = logging.getLogger(__name__)
    
    async def export_to_slo_system(self) -> Dict[str, Any]:
        """
        Export current SLI metrics for SLO monitoring
        
        Returns format compatible with backend/monitoring/slo_monitor.py
        """
        route_metrics = self.sli_middleware.get_route_sli_metrics()
        
        slo_export = {
            'timestamp': time.time(),
            'metrics_type': 'per_route_sli',
            'routes': {}
        }
        
        for route_key, metrics in route_metrics.items():
            # Convert to SLO monitoring format
            slo_export['routes'][route_key] = {
                'availability': metrics['success_rate'],
                'latency_p95_ms': metrics['p95_latency_ms'],
                'latency_p99_ms': metrics['p99_latency_ms'],
                'error_rate': metrics['error_rate'],
                'throughput_rpm': metrics['requests_per_minute'],
                
                # SLO compliance flags (thresholds from AI Agent K6 test)
                'slo_compliance': {
                    'availability_ok': metrics['success_rate'] >= 0.98,  # 98% success rate
                    'latency_ok': self._check_route_latency_slo(route_key, metrics['p95_latency_ms']),
                    'error_rate_ok': metrics['error_rate'] <= 0.02,  # 2% error rate
                }
            }
        
        return slo_export
    
    def _check_route_latency_slo(self, route_key: str, p95_latency_ms: float) -> bool:
        """Check if route meets latency SLO from AI Agent K6 thresholds"""
        # SLO thresholds from enhanced K6 test
        latency_slos = {
            'GET /health': 100,  # ms
            'GET /api/v1/signals': 300,
            'POST /api/v1/signals/act': 500,
            'GET /api/v1/positions': 300,
            'GET /api/v1/orders': 400,
            'POST /api/v1/auth/login': 200,
        }
        
        # Extract route part from "METHOD /path" format
        route_part = route_key.split(' ', 1)[1] if ' ' in route_key else route_key
        threshold = latency_slos.get(route_part, 1000)  # Default 1s threshold
        
        return p95_latency_ms <= threshold

# ============================================================================
# AI AGENT SUGGESTION B: FASTAPI INTEGRATION
# ============================================================================

def create_sli_middleware_with_integration(app, enable_logging: bool = False) -> PerRouteSLIMiddleware:
    """
    Factory function to create and configure per-route SLI middleware
    
    Usage in backend/api/factory.py:
        from backend.monitoring.per_route_sli import create_sli_middleware_with_integration
        
        sli_middleware = create_sli_middleware_with_integration(app, enable_logging=True)
        app.add_middleware(PerRouteSLIMiddleware, enable_detailed_logging=True)
    """
    middleware = PerRouteSLIMiddleware(app, enable_detailed_logging=enable_logging)
    
    # Register middleware with FastAPI
    app.add_middleware(PerRouteSLIMiddleware, enable_detailed_logging=enable_logging)
    
    logger.info("Per-route SLI middleware configured successfully")
    return middleware


# ============================================================================
# AI AGENT SUGGESTION B: PROMETHEUS ENDPOINT
# ============================================================================

def get_prometheus_metrics_handler():
    """
    Return FastAPI endpoint handler for Prometheus metrics scraping
    
    Usage in backend/api/routes/monitoring.py:
        from backend.monitoring.per_route_sli import get_prometheus_metrics_handler
        
        @router.get("/metrics")
        async def metrics():
            return get_prometheus_metrics_handler()()
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    
    def metrics_endpoint():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )
    
    return metrics_endpoint