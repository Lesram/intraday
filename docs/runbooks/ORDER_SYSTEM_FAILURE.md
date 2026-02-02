# Order System Failure Runbook

## Overview
Procedures for diagnosing and recovering from order system failures, including broker connectivity issues, order queue backlogs, and reconciliation problems.

## Critical Metrics

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Order latency (P99) | <200ms | <500ms | >500ms |
| Outbox queue depth | <100 | <500 | >500 |
| Failed order rate | <1% | <5% | >5% |
| Broker reconnect count/hr | 0-2 | 3-5 | >5 |

## Quick Diagnostics

```bash
# Check order service health
curl http://localhost:8000/health | jq

# Check outbox queue depth
curl http://localhost:8000/api/v1/system/outbox/stats -H "Authorization: Bearer $ADMIN_TOKEN"

# Check broker connectivity
curl http://localhost:8000/api/v1/brokers/health -H "Authorization: Bearer $ADMIN_TOKEN"

# Recent failed orders
curl "http://localhost:8000/api/v1/orders?status=rejected&limit=10" -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Scenario 1: Orders Not Being Submitted to Broker

### Symptoms
- Orders stuck in `accepted` status
- Outbox queue growing
- No broker_order_id being assigned

### Diagnosis

1. Check outbox processor status:
   ```bash
   curl http://localhost:8000/api/v1/system/outbox/stats -H "Authorization: Bearer $TOKEN"
   ```

2. Check broker connection:
   ```python
   # In Python console or via API
   from backend.brokers.failover import BrokerFailoverManager
   manager = BrokerFailoverManager()
   print(await manager.get_active_broker_status())
   ```

3. Check application logs:
   ```bash
   docker-compose logs --tail=200 backend | grep -E "(outbox|broker|order)"
   ```

### Resolution Steps

#### Step 1: Restart outbox processor
```bash
# If using separate worker
docker-compose restart outbox-worker

# If in main app, trigger manual processing
curl -X POST http://localhost:8000/api/v1/system/outbox/process -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### Step 2: Check broker credentials
```bash
# Verify environment variables are set
echo $APCA_API_KEY_ID
echo $APCA_API_SECRET_KEY
# Should show non-empty values (don't log actual values)
```

#### Step 3: Force broker reconnection
```bash
curl -X POST http://localhost:8000/api/v1/brokers/reconnect -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### Step 4: Manual order retry (for stuck orders)
```bash
# Get stuck order IDs
curl "http://localhost:8000/api/v1/orders?status=accepted&created_before=5m" -H "Authorization: Bearer $TOKEN"

# Retry specific order
curl -X POST http://localhost:8000/api/v1/orders/{order_id}/retry -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Scenario 2: High Order Latency

### Symptoms
- Order submission P99 > 500ms
- User complaints about slow order confirmations
- SLO violations

### Diagnosis

1. Check database query performance:
   ```sql
   SELECT query, calls, mean_time, max_time 
   FROM pg_stat_statements 
   WHERE query LIKE '%orders%' 
   ORDER BY mean_time DESC LIMIT 10;
   ```

2. Check async lock contention:
   ```bash
   # In logs, look for lock acquisition times
   docker-compose logs backend | grep -E "lock.*acquire|lock.*release"
   ```

3. Check Redis performance:
   ```bash
   redis-cli --latency
   redis-cli info | grep -E "(used_memory|connected_clients)"
   ```

### Resolution Steps

1. **If database slow**: See DATABASE_RECOVERY.md

2. **If lock contention**:
   ```bash
   # Increase worker pool size temporarily
   docker-compose exec backend env WORKER_CONCURRENCY=20 python -c "..."
   ```

3. **If Redis slow**:
   ```bash
   # Clear rate limit keys if necessary
   redis-cli KEYS "ratelimit:*" | xargs redis-cli DEL
   ```

## Scenario 3: Order Reconciliation Mismatch

### Symptoms
- Local order status differs from broker
- Position quantities don't match
- P&L calculations incorrect

### Diagnosis

```bash
# Run reconciliation check
curl -X POST http://localhost:8000/api/v1/system/reconciliation/check \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Resolution Steps

#### Step 1: Identify mismatched orders
```sql
-- Compare local vs broker status
SELECT o.id, o.status AS local_status, o.broker_order_id
FROM orders o
WHERE o.status IN ('submitted', 'partially_filled')
AND o.updated_at < NOW() - INTERVAL '5 minutes';
```

#### Step 2: Fetch latest status from broker
```bash
curl -X POST http://localhost:8000/api/v1/orders/sync-from-broker \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_ids": ["order-id-1", "order-id-2"]}'
```

#### Step 3: Force position reconciliation
```bash
curl -X POST http://localhost:8000/api/v1/positions/reconcile \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Scenario 4: Circuit Breaker Tripped

### Symptoms
- All orders being rejected
- Logs show "circuit breaker open"
- Trading halted unexpectedly

### Diagnosis

```bash
# Check circuit breaker status
curl http://localhost:8000/api/v1/risk/circuit-breaker/status -H "Authorization: Bearer $TOKEN"
```

### Resolution Steps

1. **Determine why CB tripped**:
   - Check recent error logs
   - Look for broker API errors
   - Check for daily loss limit breach

2. **If false positive, reset CB**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/reset \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "False positive - manual reset after investigation"}'
   ```

3. **If legitimate breach**:
   - Do NOT reset automatically
   - Escalate to risk management
   - Wait for explicit approval

## Emergency Kill Switch

### When to Use
- Suspected rogue algorithm
- Flash crash detected
- Uncontrolled position growth
- Security incident

### Activation
```bash
# IMMEDIATE: Cancel all orders and halt trading
curl -X POST http://localhost:8000/api/v1/risk/emergency-stop \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Emergency stop - describe reason", "cancel_open_orders": true}'
```

### Deactivation (requires dual approval in production)
```bash
# Only after investigation complete
curl -X POST http://localhost:8000/api/v1/risk/trading/resume \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin1,admin2", "reason": "Investigation complete"}'
```

## Escalation Matrix

| Scenario | First Responder | Escalate After | Final Escalation |
|----------|----------------|----------------|------------------|
| Orders stuck | On-call SRE | 15 min | Trading desk lead |
| High latency | On-call SRE | 30 min | Platform team |
| Reconciliation | Trading ops | 1 hour | Finance + Eng |
| Circuit breaker | Risk team | Immediately | CTO/CRO |
| Kill switch | Anyone | N/A | All stakeholders |

## Post-Incident Checklist

- [ ] All orders reconciled with broker
- [ ] Position quantities verified
- [ ] P&L recalculated if needed
- [ ] Incident ticket created
- [ ] Root cause identified
- [ ] Runbook updated with learnings
