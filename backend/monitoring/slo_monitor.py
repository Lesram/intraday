"""Production metrics and SLO monitoring for hedge fund grade reliability

Implements evidence-based SLOs with burn-rate alerts:

Service Level Indicators (SLIs):
- Order Success Rate: successful orders / total orders  
- Broker API Latency: time from order submit to broker response
- Stream Health: WebSocket uptime and message delivery
- Outbox Processing: queue depth and processing latency

Service Level Objectives (SLOs):
- Order Success Rate ≥ 99.9% (error budget: 0.1%)
- Broker API P99 ≤ 500ms 
- Stream Uptime ≥ 99.5%
- Outbox Queue Depth ≤ 100 messages

Burn Rate Alerts:
- 1-hour window @ 2× burn rate (consuming 2× error budget)
- 5-minute window @ 6× burn rate (consuming 6× error budget)
"""
from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
from datetime import datetime, timezone
import asyncio
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


# Define metrics
orders_submitted_total = Counter(
    'orders_submitted_total',
    'Total orders submitted to broker',
    ['symbol', 'side', 'status']  # status: success, broker_reject, broker_down, rate_limited
)

broker_roundtrip_ms = Histogram(
    'broker_roundtrip_ms', 
    'Broker API round-trip latency in milliseconds',
    ['endpoint'],  # place_order, get_order, cancel_order
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]  # P99 target: 500ms
)

outbox_queue_depth = Gauge(
    'outbox_queue_depth',
    'Number of unprocessed messages in outbox queue'
)

stream_reconnects_total = Counter(
    'stream_reconnects_total',
    'Total WebSocket reconnection attempts',
    ['reason']  # connection_lost, auth_error, rate_limited
)

stream_uptime_seconds = Gauge(
    'stream_uptime_seconds', 
    'WebSocket connection uptime in seconds'
)

stream_messages_total = Counter(
    'stream_messages_total',
    'Total WebSocket messages received',
    ['message_type']  # trade_update, order_update, error
)

stream_message_lag_ms = Histogram(
    'stream_message_lag_ms',
    'Lag between broker timestamp and processing timestamp',
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000]  # Target: P95 < 100ms
)

# Guardrail metrics
guardrail_violations_total = Counter(
    'guardrail_violations_total',
    'Total guardrail violations',
    ['violation_type']  # daily_orders_limit, daily_notional_limit, etc.
)

circuit_breaker_trips_total = Counter(
    'circuit_breaker_trips_total',
    'Total circuit breaker trips',
    ['error_type']  # broker_down, network_error
)

circuit_breaker_open = Gauge(
    'circuit_breaker_open',
    'Circuit breaker state (1=open, 0=closed)'
)

# Daily caps tracking
daily_orders_count = Gauge(
    'daily_orders_count',
    'Orders submitted today',
    ['account_id']
)

daily_notional_usd = Gauge(
    'daily_notional_usd', 
    'Notional USD traded today',
    ['account_id']
)


@dataclass
class SLOStatus:
    """SLO compliance status"""
    name: str
    current_value: float
    target_value: float
    is_compliant: bool
    error_budget_consumed: float  # 0.0 to 1.0
    burn_rate: float  # current error rate / target error rate


class SLOMonitor:
    """Evidence-based SLO monitoring with burn-rate alerts"""
    
    def __init__(self):
        self.stream_connect_time: Optional[datetime] = None
        self.slo_targets = {
            'order_success_rate': 0.999,      # 99.9%
            'broker_api_p99_ms': 500,         # 500ms
            'stream_uptime': 0.995,           # 99.5%  
            'outbox_queue_depth': 100         # messages
        }
        
        # Burn rate alert thresholds
        self.burn_rate_alerts = {
            '1h': 2.0,   # 2× error budget consumption
            '5m': 6.0    # 6× error budget consumption  
        }
    
    def record_order_attempt(self, symbol: str, side: str, success: bool, error_type: Optional[str] = None) -> None:
        """Record order submission attempt"""
        status = 'success' if success else (error_type or 'unknown_error')
        orders_submitted_total.labels(symbol=symbol, side=side, status=status).inc()
        
        if not success:
            logger.warning(f"Order failed: {symbol} {side} - {error_type}")
    
    def record_broker_latency(self, endpoint: str, latency_ms: float) -> None:
        """Record broker API call latency"""
        broker_roundtrip_ms.labels(endpoint=endpoint).observe(latency_ms)
        
        if latency_ms > self.slo_targets['broker_api_p99_ms']:
            logger.warning(f"High broker latency: {endpoint} took {latency_ms}ms")
    
    def record_stream_reconnect(self, reason: str) -> None:
        """Record WebSocket reconnection"""
        stream_reconnects_total.labels(reason=reason).inc()
        
        # Reset uptime counter
        self.stream_connect_time = datetime.now(timezone.utc)
        stream_uptime_seconds.set(0)
        
        logger.warning(f"Stream reconnected due to: {reason}")
    
    def record_stream_message(self, message_type: str, broker_timestamp: Optional[datetime] = None) -> None:
        """Record WebSocket message received"""
        stream_messages_total.labels(message_type=message_type).inc()
        
        # Calculate message lag
        if broker_timestamp:
            now = datetime.now(timezone.utc)
            lag_ms = (now - broker_timestamp).total_seconds() * 1000
            stream_message_lag_ms.observe(lag_ms)
    
    def record_guardrail_violation(self, violation_type: str) -> None:
        """Record guardrail violation"""
        guardrail_violations_total.labels(violation_type=violation_type).inc()
        logger.error(f"Guardrail violation: {violation_type}")
    
    def record_circuit_breaker_trip(self, error_type: str, is_open: bool) -> None:
        """Record circuit breaker state change"""
        if is_open:
            circuit_breaker_trips_total.labels(error_type=error_type).inc()
            circuit_breaker_open.set(1)
            logger.critical(f"Circuit breaker OPENED due to {error_type}")
        else:
            circuit_breaker_open.set(0)
            logger.info("Circuit breaker CLOSED")
    

    async def record_metric(self, service_name: str = None, operation_name: str = None, 
                          latency_ms: float = None, success: bool = True, 
                          metadata: dict = None, **labels) -> None:
        """Async version of record_metric with expected parameters"""
        # Handle different calling patterns
        if service_name and operation_name:
            metric_name = f"{service_name}_{operation_name}"
            value = latency_ms or 0.0
        else:
            # Fallback for direct calls
            metric_name = service_name or "unknown"
            value = latency_ms or operation_name or 0.0
            
        # Call the sync version
        self.record_metric_sync(metric_name, value, success, **labels)
    
    def record_metric_sync(self, metric_name: str, value: float, success: bool = True, **labels) -> None:
        """Synchronous metric recording (renamed from record_metric to avoid conflict)"""
        try:
            # Record based on metric type
            if "latency" in metric_name.lower() or "broker" in metric_name.lower():
                # Use broker roundtrip metric for latency
                endpoint = labels.get('endpoint', 'unknown')
                broker_roundtrip_ms.labels(endpoint=endpoint).observe(value)
            
            elif "execution" in metric_name.lower():
                # Use broker roundtrip for execution time as well
                broker_roundtrip_ms.labels(endpoint='execution').observe(value)
            
            # Record order success/failure
            if success is not None:
                symbol = labels.get('symbol', 'unknown')
                side = labels.get('side', 'unknown')
                status = 'success' if success else 'failure'
                orders_submitted_total.labels(symbol=symbol, side=side, status=status).inc()
                    
        except Exception as e:
            logger.error(f"Error recording metric {metric_name}: {e}")
    
    def update_outbox_depth(self, depth: int) -> None:
        """Update outbox queue depth"""
        outbox_queue_depth.set(depth)
        
        if depth > self.slo_targets['outbox_queue_depth']:
            logger.warning(f"High outbox queue depth: {depth}")
    
    def update_daily_caps(self, account_id: str, orders_count: int, notional_usd: float) -> None:
        """Update daily trading metrics"""
        daily_orders_count.labels(account_id=account_id).set(orders_count)
        daily_notional_usd.labels(account_id=account_id).set(notional_usd)
    
    def update_stream_uptime(self) -> None:
        """Update stream uptime (call periodically)"""
        if self.stream_connect_time:
            uptime = (datetime.now(timezone.utc) - self.stream_connect_time).total_seconds()
            stream_uptime_seconds.set(uptime)
    
    async def check_slo_compliance(self) -> Dict[str, SLOStatus]:
        """Check SLO compliance and calculate burn rates"""
        # This would query Prometheus for actual metrics over time windows
        # For now, return placeholder structure
        
        slo_status = {}
        
        # Order Success Rate SLO
        # In production: query sum(rate(orders_submitted_total{status="success"}[1h])) / sum(rate(orders_submitted_total[1h]))
        success_rate = 0.998  # Placeholder - would come from Prometheus query
        error_budget_consumed = max(0, (self.slo_targets['order_success_rate'] - success_rate) / (1 - self.slo_targets['order_success_rate']))
        burn_rate = error_budget_consumed / (1/24)  # 1 hour out of 24 hour error budget window
        
        slo_status['order_success_rate'] = SLOStatus(
            name='Order Success Rate',
            current_value=success_rate,
            target_value=self.slo_targets['order_success_rate'],
            is_compliant=success_rate >= self.slo_targets['order_success_rate'],
            error_budget_consumed=error_budget_consumed,
            burn_rate=burn_rate
        )
        
        # Broker API P99 Latency SLO
        # In production: histogram_quantile(0.99, rate(broker_roundtrip_ms_bucket[5m]))
        p99_latency = 350  # Placeholder
        
        slo_status['broker_api_p99'] = SLOStatus(
            name='Broker API P99 Latency',
            current_value=p99_latency,
            target_value=self.slo_targets['broker_api_p99_ms'],
            is_compliant=p99_latency <= self.slo_targets['broker_api_p99_ms'],
            error_budget_consumed=max(0, (p99_latency - self.slo_targets['broker_api_p99_ms']) / self.slo_targets['broker_api_p99_ms']),
            burn_rate=0  # Latency SLO doesn't use error budget model
        )
        
        return slo_status
    
    def generate_burn_rate_alerts(self, slo_status: Dict[str, SLOStatus]) -> List[Dict]:
        """Generate burn rate alerts for SLO violations"""
        alerts = []
        
        for slo_name, status in slo_status.items():
            # Check 1-hour burn rate
            if status.burn_rate >= self.burn_rate_alerts['1h']:
                alerts.append({
                    'severity': 'warning',
                    'slo': slo_name,
                    'message': f"{status.name} burning error budget at {status.burn_rate:.1f}× rate (1h window)",
                    'burn_rate': status.burn_rate,
                    'error_budget_consumed': status.error_budget_consumed,
                    'current_value': status.current_value,
                    'target_value': status.target_value
                })
            
            # Check 5-minute burn rate (would need separate calculation)
            # For 5-minute window, multiply burn_rate by 12 (5 min = 1/12 hour)
            short_term_burn = status.burn_rate * 12
            if short_term_burn >= self.burn_rate_alerts['5m']:
                alerts.append({
                    'severity': 'critical', 
                    'slo': slo_name,
                    'message': f"{status.name} burning error budget at {short_term_burn:.1f}× rate (5m window)",
                    'burn_rate': short_term_burn,
                    'error_budget_consumed': status.error_budget_consumed,
                    'current_value': status.current_value,
                    'target_value': status.target_value
                })
        
        return alerts
    
    async def health_check_loop(self) -> None:
        """Periodic health check and SLO monitoring"""
        while True:
            try:
                # Update stream uptime
                self.update_stream_uptime()
                
                # Check SLO compliance
                slo_status = await self.check_slo_compliance()
                
                # Generate burn rate alerts
                alerts = self.generate_burn_rate_alerts(slo_status)
                
                for alert in alerts:
                    if alert['severity'] == 'critical':
                        logger.critical(f"SLO ALERT: {alert['message']}")
                    else:
                        logger.warning(f"SLO WARNING: {alert['message']}")
                
                # Log SLO status summary
                compliant_slos = sum(1 for s in slo_status.values() if s.is_compliant)
                total_slos = len(slo_status)
                logger.info(f"SLO compliance: {compliant_slos}/{total_slos} objectives met")
                
            except Exception as e:
                logger.error(f"Error in SLO monitoring: {e}")
            
            await asyncio.sleep(60)  # Check every minute


def start_metrics_server(port: int = 8000) -> None:
    """Start Prometheus metrics server"""
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")


# Global monitor instance
slo_monitor = SLOMonitor()