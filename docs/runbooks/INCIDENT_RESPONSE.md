# Trading Platform Operational Runbooks

This document provides comprehensive runbooks for managing critical incidents and maintaining operational excellence in the algorithmic trading platform.

## 🚨 Emergency Contacts

| Role | Primary | Backup | Phone | Slack |
|------|---------|---------|-------|-------|
| **On-Call Engineer** | @oncall-primary | @oncall-backup | +1-xxx-xxx-xxxx | #alerts |
| **Trading Desk** | @trading-lead | @trading-backup | +1-xxx-xxx-xxxx | #trading |
| **Risk Manager** | @risk-manager | @risk-deputy | +1-xxx-xxx-xxxx | #risk |
| **DevOps Lead** | @devops-lead | @devops-backup | +1-xxx-xxx-xxxx | #devops |
| **CTO** | @cto | @engineering-vp | +1-xxx-xxx-xxxx | #leadership |

## 📊 SLO Definitions and Thresholds

### Critical SLOs
- **Order Latency P95**: < 2 seconds
- **Order Latency P99**: < 5 seconds
- **Error Rate**: < 1%
- **System Availability**: > 99.9%
- **Market Data Latency**: < 100ms

### Warning Thresholds
- **Order Latency P95**: 1.5-2.0 seconds
- **Order Latency P99**: 4.0-5.0 seconds
- **Error Rate**: 0.5-1.0%
- **System Availability**: 99.5-99.9%
- **Market Data Latency**: 80-100ms

---

## 🚨 CRITICAL ALERTS

### ALERT: High Order Latency (P95 > 2s)

**Severity**: Critical  
**Impact**: Customer orders experiencing delays, potential market opportunity loss  
**SLO**: Order Latency P95 < 2 seconds

#### Immediate Response (0-5 minutes)
1. **Acknowledge** alert in PagerDuty and Slack #alerts
2. **Check** system status dashboard: `https://monitoring.trading-platform.com/dashboard`
3. **Verify** if this is affecting live trading:
   ```bash
   # Check current trading mode
   curl -H "Authorization: Bearer $API_TOKEN" \
        https://api.trading-platform.com/health/safety-status
   ```
4. **If P99 > 10 seconds**: Immediately activate emergency halt
   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
        -d '{"reason": "High latency emergency halt", "activated_by": "oncall"}' \
        https://api.trading-platform.com/admin/emergency-halt
   ```

#### Investigation (5-15 minutes)
1. **Check Prometheus** for latency breakdown:
   ```promql
   histogram_quantile(0.95, 
     rate(order_processing_duration_seconds_bucket[5m])
   ) by (service)
   ```

2. **Identify bottleneck**:
   - **Database**: Check `pg_stat_activity` for long-running queries
   - **External APIs**: Check circuit breaker states
   - **Queue depth**: Check Redis/RabbitMQ queue sizes
   - **Resource usage**: Check CPU/memory on critical nodes

3. **Check for external factors**:
   - Market volatility causing high volume
   - Broker API issues
   - Network connectivity problems

#### Mitigation Steps
1. **Database bottleneck**:
   ```bash
   # Scale database connections
   kubectl scale deployment postgres-primary --replicas=2
   
   # Kill long-running queries if safe
   psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
            WHERE state = 'active' AND query_start < now() - interval '30 seconds';"
   ```

2. **Queue backlog**:
   ```bash
   # Scale order processors
   kubectl scale deployment order-processor --replicas=5
   
   # Check queue health
   redis-cli info | grep "instantaneous_ops_per_sec"
   ```

3. **External API issues**:
   ```bash
   # Check circuit breaker states
   curl https://api.trading-platform.com/health/circuit-breakers
   
   # Reset circuit breakers if needed (use caution)
   curl -X POST https://api.trading-platform.com/admin/circuit-breakers/reset
   ```

#### Recovery
1. **Monitor** latency returning to normal (< 1.5s P95)
2. **Gradually resume** trading if halted:
   ```bash
   # Move to dry run first
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
        -d '{"mode": "dry_run", "authorized_by": "oncall"}' \
        https://api.trading-platform.com/admin/trading-mode
   
   # Then to live after validation
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
        -d '{"mode": "live", "authorized_by": "oncall"}' \
        https://api.trading-platform.com/admin/trading-mode
   ```

3. **Post-incident**:
   - Document root cause in #incidents
   - Schedule post-mortem within 24 hours
   - Update runbook if needed

---

### ALERT: High Error Rate (>1%)

**Severity**: Critical  
**Impact**: Failed orders, potential financial loss, customer impact  
**SLO**: Error Rate < 1%

#### Immediate Response (0-3 minutes)
1. **Check error patterns**:
   ```promql
   rate(http_requests_total{status=~"5.."}[5m]) / 
   rate(http_requests_total[5m]) * 100
   ```

2. **If error rate >5%**: Immediately halt trading
3. **Check recent deployments**:
   ```bash
   kubectl rollout history deployment/trading-service
   ```

#### Investigation (3-10 minutes)
1. **Categorize errors**:
   - **5xx errors**: Server-side issues
   - **4xx errors**: Client-side/validation issues
   - **Timeout errors**: Performance/connectivity issues

2. **Check logs** for error patterns:
   ```bash
   # Recent errors
   kubectl logs deployment/trading-service --since=10m | grep ERROR
   
   # Error frequency
   kubectl logs deployment/trading-service --since=1h | grep ERROR | wc -l
   ```

3. **External dependencies**:
   ```bash
   # Broker API health
   curl https://broker-api.example.com/health
   
   # Market data provider
   curl https://market-data.example.com/health
   ```

#### Mitigation Steps
1. **Recent deployment issue**:
   ```bash
   # Rollback to previous version
   kubectl rollout undo deployment/trading-service
   kubectl rollout status deployment/trading-service
   ```

2. **External API failures**:
   ```bash
   # Check circuit breaker status
   curl https://api.trading-platform.com/health/circuit-breakers
   
   # Manually trigger circuit breaker if needed
   curl -X POST https://api.trading-platform.com/admin/circuit-breakers/BROKER_API/open
   ```

3. **Database connectivity**:
   ```bash
   # Check database connections
   kubectl exec -it postgres-primary-0 -- psql -c "SELECT count(*) FROM pg_stat_activity;"
   
   # Restart connection pool if needed
   kubectl restart deployment/pgbouncer
   ```

#### Recovery
1. **Verify error rate** drops below 0.5%
2. **Test critical paths** manually before full resumption
3. **Gradually increase** traffic if using circuit breakers

---

### ALERT: System Down / Zero Availability

**Severity**: Critical  
**Impact**: Complete service outage, all trading halted  
**SLO**: Availability > 99.9%

#### Immediate Response (0-2 minutes)
1. **Verify outage** from multiple locations
2. **Check infrastructure**:
   ```bash
   # Kubernetes cluster health
   kubectl get nodes
   kubectl get pods --all-namespaces | grep -v Running
   
   # Load balancer status
   curl -I https://api.trading-platform.com/health
   ```

#### Investigation (2-5 minutes)
1. **Check recent changes**:
   - Recent deployments
   - Infrastructure changes
   - DNS updates

2. **System resources**:
   ```bash
   # Node resources
   kubectl top nodes
   
   # Critical pod status
   kubectl get pods -n trading-system
   ```

3. **External dependencies**:
   - Cloud provider status pages
   - CDN status
   - DNS resolution

#### Mitigation Steps
1. **Pod failures**:
   ```bash
   # Restart failed pods
   kubectl delete pods -l app=trading-service
   
   # Scale up if resource issues
   kubectl scale deployment trading-service --replicas=3
   ```

2. **Node failures**:
   ```bash
   # Cordon failing nodes
   kubectl cordon <failing-node>
   
   # Drain workloads
   kubectl drain <failing-node> --ignore-daemonsets
   ```

3. **Database issues**:
   ```bash
   # Check database cluster
   kubectl exec -it postgres-primary-0 -- pg_isready
   
   # Failover if needed
   kubectl patch postgresql postgres-cluster --type='merge' -p='{"spec":{"switchover":{}}}'
   ```

---

## ⚠️ WARNING ALERTS

### ALERT: Circuit Breaker Open

**Severity**: Warning  
**Impact**: Degraded functionality for external integrations

#### Response Steps
1. **Identify affected service**:
   ```bash
   curl https://api.trading-platform.com/health/circuit-breakers | jq '.[] | select(.state == "OPEN")'
   ```

2. **Check service health**:
   ```bash
   # Test external service directly
   curl -w "%{http_code}" https://external-service.com/health
   ```

3. **Review error patterns**:
   ```promql
   rate(circuit_breaker_requests_total{state="OPEN"}[5m])
   ```

4. **Reset if service recovered**:
   ```bash
   curl -X POST https://api.trading-platform.com/admin/circuit-breakers/SERVICE_NAME/reset
   ```

### ALERT: High Queue Depth

**Severity**: Warning  
**Impact**: Potential processing delays

#### Response Steps
1. **Check queue sizes**:
   ```bash
   # Redis queues
   redis-cli llen order_processing_queue
   redis-cli llen risk_analysis_queue
   
   # RabbitMQ queues
   rabbitmqctl list_queues name messages
   ```

2. **Scale processors**:
   ```bash
   kubectl scale deployment order-processor --replicas=5
   kubectl scale deployment risk-analyzer --replicas=3
   ```

3. **Monitor processing rate**:
   ```promql
   rate(queue_messages_processed_total[5m])
   ```

---

## 🔍 INVESTIGATION TOOLS

### Prometheus Queries

```promql
# Order latency percentiles
histogram_quantile(0.95, rate(order_processing_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(order_processing_duration_seconds_bucket[5m]))

# Error rates by service
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Circuit breaker states
circuit_breaker_state

# Queue depths
queue_depth{queue_name=~".*"}

# Database connection pool
database_connections_active
database_connections_idle

# Memory/CPU usage
container_memory_usage_bytes
rate(container_cpu_usage_seconds_total[5m])
```

### Log Analysis

```bash
# Error patterns in last hour
kubectl logs deployment/trading-service --since=1h | grep ERROR | sort | uniq -c | sort -nr

# Slow queries
kubectl logs deployment/trading-service --since=30m | grep "slow query" | tail -20

# Failed external calls
kubectl logs deployment/trading-service --since=15m | grep -i "timeout\|connection refused\|502\|503\|504"

# Order processing timeline
kubectl logs deployment/order-processor --since=10m | grep "order_id:12345" | sort
```

### Database Queries

```sql
-- Active connections
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

-- Long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
FROM pg_stat_activity 
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes';

-- Lock contention
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity 
  ON blocked_activity.pid = blocked_locks.pid;

-- Order status distribution
SELECT status, count(*) FROM orders 
WHERE created_at > now() - interval '1 hour' 
GROUP BY status;
```

---

## 📈 HEALTH CHECKS

### Manual Health Verification

```bash
# Overall system health
curl https://api.trading-platform.com/health

# Safety system status
curl https://api.trading-platform.com/health/safety-status

# Database connectivity
kubectl exec -it postgres-primary-0 -- pg_isready

# External APIs
curl -w "%{http_code}" https://broker-api.example.com/health
curl -w "%{http_code}" https://market-data.example.com/health

# Queue health
redis-cli ping
rabbitmqctl node_health_check
```

### Smoke Tests

```bash
# Test order submission (dry run)
curl -X POST -H "Authorization: Bearer $TEST_TOKEN" \
     -d '{"symbol": "AAPL", "quantity": 1, "price": 150.0, "type": "limit"}' \
     https://api.trading-platform.com/orders

# Test market data
curl https://api.trading-platform.com/market-data/AAPL

# Test risk calculation
curl -X POST -H "Authorization: Bearer $TEST_TOKEN" \
     -d '{"portfolio": {"AAPL": 100}, "proposed_trade": {"symbol": "AAPL", "quantity": 10}}' \
     https://api.trading-platform.com/risk/calculate
```

---

## 📋 COMMUNICATION TEMPLATES

### Incident Communication

**Initial Alert (within 5 minutes)**
```
🚨 TRADING PLATFORM INCIDENT

Status: INVESTIGATING
Impact: [Brief description]
Started: [timestamp]
SLO Impact: [Yes/No - which SLOs]

We are investigating reports of [issue]. 
Updates every 15 minutes or as significant changes occur.

Next update: [timestamp + 15min]
```

**Status Update**
```
📋 TRADING PLATFORM INCIDENT UPDATE

Status: [INVESTIGATING/IDENTIFIED/FIXING/MONITORING]
Impact: [Updated description]
Root Cause: [If identified]
ETA: [If known]

Actions taken:
- [Action 1]
- [Action 2]

Next update: [timestamp + 15min]
```

**Resolution**
```
✅ TRADING PLATFORM INCIDENT RESOLVED

Status: RESOLVED
Duration: [total time]
Root Cause: [Brief summary]
Impact: [Final assessment]

Resolution:
- [What fixed it]

Follow-up:
- Post-mortem scheduled for [date/time]
- [Any ongoing monitoring]
```

### Escalation Criteria

**Escalate to Trading Desk**:
- Any trading halt > 5 minutes
- Error rate > 2%
- P99 latency > 10 seconds
- Data integrity issues

**Escalate to CTO**:
- Incidents lasting > 30 minutes
- Financial impact > $10,000
- Data breach or security incident
- Regulatory compliance impact

---

## 🔄 POST-INCIDENT PROCEDURES

### Immediate (within 2 hours)
1. **Ensure full service restoration**
2. **Document timeline** in incident tracking system
3. **Collect all relevant logs** and metrics
4. **Notify affected customers** if needed

### Within 24 hours
1. **Schedule post-mortem** meeting
2. **Assign post-mortem facilitator**
3. **Collect preliminary timeline**
4. **Identify key stakeholders**

### Post-Mortem Template
```markdown
# Post-Mortem: [Incident Title]

## Summary
- **Date**: 
- **Duration**: 
- **Impact**: 
- **Root Cause**: 

## Timeline
- [timestamp] Initial alert
- [timestamp] Investigation began
- [timestamp] Root cause identified
- [timestamp] Fix deployed
- [timestamp] Full resolution

## Root Cause Analysis
[Detailed technical explanation]

## Action Items
| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| [Action 1] | @person | YYYY-MM-DD | Open |

## Lessons Learned
- What went well
- What could be improved
- Prevention measures
```

---

## 🛠️ MAINTENANCE PROCEDURES

### Database Maintenance
```bash
# Weekly vacuum and analyze
kubectl exec -it postgres-primary-0 -- psql -c "VACUUM ANALYZE;"

# Check index usage
kubectl exec -it postgres-primary-0 -- psql -c "
  SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
  FROM pg_stat_user_indexes
  ORDER BY idx_tup_read DESC;"

# Database size monitoring
kubectl exec -it postgres-primary-0 -- psql -c "
  SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname))
  FROM pg_database
  ORDER BY pg_database_size(pg_database.datname) DESC;"
```

### Certificate Renewal
```bash
# Check certificate expiration
curl -s https://api.trading-platform.com | openssl x509 -noout -enddate

# Renew Let's Encrypt certificates
kubectl annotate certificate trading-platform-tls cert-manager.io/issue-temporary-certificate="true"
```

---

This runbook should be reviewed monthly and updated after each major incident.

**Last Updated**: [Current Date]  
**Next Review**: [Date + 1 month]  
**Document Owner**: DevOps Team
