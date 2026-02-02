# Broker Failover Runbook

## Overview
Procedures for managing broker connectivity failures and executing failover to backup brokers.

## Broker Priority Order

| Priority | Broker | Type | Use Case |
|----------|--------|------|----------|
| 1 | Alpaca | Primary | Production trading |
| 2 | Alpaca Paper | Backup | Production fallback / Paper trading |
| 3 | Manual | Emergency | Human-in-the-loop execution |

## Health Check Endpoints

```bash
# Overall broker health
curl http://localhost:8000/api/v1/brokers/health -H "Authorization: Bearer $TOKEN"

# Individual broker status
curl http://localhost:8000/api/v1/brokers/alpaca/status -H "Authorization: Bearer $TOKEN"

# Failover manager status
curl http://localhost:8000/api/v1/brokers/failover/status -H "Authorization: Bearer $TOKEN"
```

## Automatic Failover

The system automatically fails over to backup brokers when:
- Primary broker API returns 5xx errors for 3+ consecutive requests
- Connection timeout exceeds 30 seconds
- Rate limit exhausted (429 response)
- Authentication failure (401/403) - requires manual intervention

### Monitoring Automatic Failover

```bash
# Watch failover events
docker-compose logs -f backend | grep -E "(failover|broker.*switch|broker.*reconnect)"

# Prometheus metrics
curl http://localhost:9090/api/v1/query?query=broker_failover_count_total
```

## Manual Failover Procedures

### Scenario 1: Planned Maintenance

```bash
# Step 1: Drain orders from primary
curl -X POST http://localhost:8000/api/v1/brokers/alpaca/drain \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 300}'

# Step 2: Switch to backup
curl -X POST http://localhost:8000/api/v1/brokers/failover/switch \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_broker": "alpaca_paper", "reason": "Planned maintenance"}'

# Step 3: Verify switch
curl http://localhost:8000/api/v1/brokers/active -H "Authorization: Bearer $TOKEN"

# Step 4: After maintenance, switch back
curl -X POST http://localhost:8000/api/v1/brokers/failover/switch \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_broker": "alpaca", "reason": "Maintenance complete"}'
```

### Scenario 2: Emergency Failover (Primary Down)

```bash
# Step 1: Immediate switch (skips drain)
curl -X POST http://localhost:8000/api/v1/brokers/failover/emergency \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Primary broker unresponsive"}'

# Step 2: Check pending orders from primary
curl "http://localhost:8000/api/v1/orders?broker=alpaca&status=submitted" \
  -H "Authorization: Bearer $TOKEN"

# Step 3: Resubmit critical orders to backup
curl -X POST http://localhost:8000/api/v1/orders/resubmit-to-active \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_ids": ["id1", "id2"]}'
```

### Scenario 3: Authentication Failure

When broker returns 401/403:

1. **Do NOT automatically failover** - credentials may be compromised

2. **Immediately halt new order submission**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/brokers/alpaca/pause \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

3. **Rotate credentials**:
   - Log into broker dashboard
   - Generate new API keys
   - Update secrets in K8s/env vars
   - Restart application

4. **Resume trading**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/brokers/alpaca/resume \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

## WebSocket Stream Failover

### Symptoms of WebSocket Issues
- No real-time order updates
- Stale position data
- Missing fill notifications

### Diagnosis
```bash
# Check WebSocket connection status
curl http://localhost:8000/api/v1/brokers/websocket/status -H "Authorization: Bearer $TOKEN"

# Check reconnection attempts
docker-compose logs backend | grep -E "(websocket|ws:)" | tail -50
```

### Resolution
```bash
# Force WebSocket reconnection
curl -X POST http://localhost:8000/api/v1/brokers/websocket/reconnect \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# If still failing, restart stream handler
docker-compose restart backend-stream
```

## Rate Limit Management

### Alpaca Rate Limits
- REST API: 200 requests/minute
- WebSocket: Unlimited (connection-based)
- Order submission: 50/second

### When Rate Limited

1. System automatically backs off exponentially
2. Orders queued in outbox
3. If persistent:
   ```bash
   # Check current rate limit status
   curl http://localhost:8000/api/v1/brokers/alpaca/rate-limit -H "Authorization: Bearer $TOKEN"
   
   # Reduce order frequency temporarily
   curl -X PATCH http://localhost:8000/api/v1/settings/order-throttle \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"max_orders_per_second": 10}'
   ```

## Failover Testing

### Monthly Failover Drill (Scheduled)

```bash
# 1. Announce drill to team
# 2. During low-volume period (10am-11am)

# Simulate primary failure
curl -X POST http://localhost:8000/api/v1/brokers/test/simulate-failure \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"broker": "alpaca", "duration_seconds": 300}'

# Monitor failover
watch -n 5 'curl -s http://localhost:8000/api/v1/brokers/active'

# Submit test order during failover
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "qty": 1, "side": "buy", "type": "market"}'

# Verify order executed on backup broker
# End simulation
curl -X POST http://localhost:8000/api/v1/brokers/test/end-simulation \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Metrics to Monitor

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| `broker_connection_status` | 0 (disconnected) | Page on-call |
| `broker_failover_count` | >2/hour | Investigate |
| `broker_latency_p99` | >500ms | Check network |
| `broker_error_rate` | >5% | Prepare failover |
| `outbox_queue_depth` | >100 | Check broker |

## Contact Information

| Role | Contact | When |
|------|---------|------|
| Alpaca Support | support@alpaca.markets | API issues |
| On-call SRE | PagerDuty | Failover needed |
| Trading Ops | #trading-ops Slack | Order issues |
