# Post-Launch Monitoring Procedures

**Document Version**: 1.0  
**Last Updated**: 2025-01-04  
**Owner**: Platform Operations Team  

## Executive Summary

This document provides comprehensive post-launch monitoring procedures for the Algorithmic Trading Platform. These procedures integrate with existing platform monitoring infrastructure (`backend.api.routes.monitoring`, `backend.infra.observability`) and leverage the platform's proven stability baseline (**99.34/100 stability score from 186,727 test requests**).

**Critical Integration Points**:
- Existing SLI/SLO monitoring: `/api/v1/monitoring/sli-metrics`, `/api/v1/monitoring/slo-status`
- Health check endpoints: `/health`, `/healthz`, `/ready`, `/live`
- Database health: `backend.infra.db.db_health_check()`
- Broker health: `backend.infra.broker.broker_health_check()`
- Prometheus metrics scraping: `k8s/deployment.yaml` annotations

---

## 1. Monitoring Architecture

### 1.1 Existing Infrastructure

The platform has comprehensive monitoring infrastructure already in place:

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Monitoring Stack                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Health Checks                                      │
│  • /health - Basic health status                            │
│  • /healthz - Kubernetes liveness probe                     │
│  • /ready - Kubernetes readiness probe                      │
│  • /live - Application liveness                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: SLI/SLO Metrics (backend.api.routes.monitoring)   │
│  • /api/v1/monitoring/sli-metrics - Service indicators      │
│  • /api/v1/monitoring/slo-status - Objective compliance     │
│  • Error rate tracking                                       │
│  • Latency percentiles (P50, P95, P99)                      │
│  • Request volume tracking                                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Infrastructure Health                              │
│  • db_health_check() - Database connectivity                │
│  • broker_health_check() - Redis/message broker             │
│  • Alpaca API connectivity (integration layer)              │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Prometheus Metrics                                 │
│  • /metrics endpoint                                         │
│  • Automatic scraping via k8s annotations                   │
│  • Custom business metrics                                   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Monitoring Baseline (From Test Results)

Established baseline from comprehensive testing (186,727 requests):

| Metric | Baseline | Critical Threshold | Warning Threshold |
|--------|----------|-------------------|-------------------|
| **Success Rate** | 100% | < 99.5% | < 99.9% |
| **Stability Score** | 99.34/100 | < 95/100 | < 98/100 |
| **Error Rate** | 0% | > 0.5% | > 0.1% |
| **P95 Latency** | < 200ms (est.) | > 1000ms | > 500ms |
| **P99 Latency** | < 500ms (est.) | > 2000ms | > 1000ms |
| **Database Health** | 100% up | < 99% | < 99.9% |
| **Broker API Health** | 100% up | < 99% | < 99.9% |

---

## 2. Launch Day Checklist (Hour 0-24)

### Hour 0: Deployment Verification

#### 2.1 Pre-Launch Final Checks (T-15 minutes)

```bash
# 1. Run production configuration validator
python scripts/validate_production_config.py

# Expected: All checks passed, 0 critical failures

# 2. Verify TLS/HTTPS configuration
kubectl get ingress algotrading-ingress -n algotrading -o yaml | grep tls

# Expected: TLS section present with certificate

# 3. Check all pods are running
kubectl get pods -n algotrading

# Expected: All pods in "Running" state, READY 1/1

# 4. Verify environment variables
kubectl exec -n algotrading deployment/algotrading-api -- printenv | grep -E "DATABASE_URL|ALPACA"

# Expected: All critical env vars present
```

#### 2.2 Deployment Execution (T-0)

```bash
# 1. Apply TLS ingress
kubectl apply -f k8s/tls/ingress-tls.yaml

# 2. Verify ingress is ready
kubectl describe ingress algotrading-ingress -n algotrading

# Expected: Address assigned, no errors

# 3. Test HTTPS endpoint
curl -I https://your-domain.com/health

# Expected: HTTP/2 200, Strict-Transport-Security header present

# 4. Check certificate
curl -vI https://your-domain.com 2>&1 | grep -E "subject:|issuer:"

# Expected: Valid certificate from Let's Encrypt
```

#### 2.3 Immediate Post-Launch Verification (T+5 minutes)

```bash
# 1. Check all health endpoints
curl https://your-domain.com/health
curl https://your-domain.com/healthz
curl https://your-domain.com/ready

# Expected: All return 200 OK

# 2. Verify SLI metrics are reporting
curl https://your-domain.com/api/v1/monitoring/sli-metrics

# Expected: JSON response with metrics:
# {
#   "error_rate": 0.0,
#   "request_count": >0,
#   "latency_p50": <200,
#   "latency_p95": <500,
#   "latency_p99": <1000
# }

# 3. Check SLO compliance
curl https://your-domain.com/api/v1/monitoring/slo-status

# Expected: All SLOs showing "compliant"

# 4. Verify Prometheus is scraping
kubectl logs -n algotrading deployment/algotrading-api --tail=50 | grep "metrics"

# Expected: No errors in metrics collection
```

### Hours 1-6: Intensive Monitoring

**Frequency**: Every 15 minutes

**Checklist**:

```bash
#!/bin/bash
# Save as: scripts/launch_day_check.sh

echo "=== Launch Day Health Check ==="
echo "Time: $(date)"

# 1. Platform health
echo -e "\n[1/7] Platform Health..."
curl -sf https://your-domain.com/health || echo "❌ ALERT: Health check failed"

# 2. Error rate
echo -e "\n[2/7] Error Rate..."
ERROR_RATE=$(curl -sf https://your-domain.com/api/v1/monitoring/sli-metrics | jq -r '.error_rate')
echo "Error rate: ${ERROR_RATE}%"
if (( $(echo "$ERROR_RATE > 0.1" | bc -l) )); then
    echo "⚠️  WARNING: Error rate above 0.1%"
fi

# 3. Request volume
echo -e "\n[3/7] Request Volume..."
REQ_COUNT=$(curl -sf https://your-domain.com/api/v1/monitoring/sli-metrics | jq -r '.request_count')
echo "Requests in window: $REQ_COUNT"

# 4. Latency
echo -e "\n[4/7] Latency..."
P95=$(curl -sf https://your-domain.com/api/v1/monitoring/sli-metrics | jq -r '.latency_p95')
P99=$(curl -sf https://your-domain.com/api/v1/monitoring/sli-metrics | jq -r '.latency_p99')
echo "P95: ${P95}ms, P99: ${P99}ms"
if (( $(echo "$P95 > 500" | bc -l) )); then
    echo "⚠️  WARNING: P95 latency above 500ms"
fi

# 5. Database health
echo -e "\n[5/7] Database Health..."
DB_HEALTH=$(curl -sf https://your-domain.com/health | jq -r '.database')
echo "Database: $DB_HEALTH"
if [ "$DB_HEALTH" != "healthy" ]; then
    echo "❌ ALERT: Database unhealthy"
fi

# 6. Pod status
echo -e "\n[6/7] Pod Status..."
kubectl get pods -n algotrading --no-headers | awk '{print $1, $2, $3}'

# 7. Recent errors
echo -e "\n[7/7] Recent Errors..."
kubectl logs -n algotrading deployment/algotrading-api --tail=10 --since=15m | grep -i error || echo "No errors"

echo -e "\n=== Check Complete ==="
```

**Run via**:
```bash
# Make executable
chmod +x scripts/launch_day_check.sh

# Run manually
./scripts/launch_day_check.sh

# Or schedule every 15 minutes
watch -n 900 ./scripts/launch_day_check.sh
```

### Hours 6-24: Standard Monitoring

**Frequency**: Every hour

**Focus Areas**:
1. SLO compliance trends
2. Resource utilization (CPU, memory)
3. Database connection pool stats
4. Alpaca API call success rate
5. Certificate expiry (should be 90 days)

```bash
# Hourly monitoring script
#!/bin/bash
# Save as: scripts/hourly_check.sh

echo "=== Hourly Platform Check ==="
echo "Time: $(date)"

# 1. SLO compliance
echo -e "\n[SLO Compliance]"
curl -sf https://your-domain.com/api/v1/monitoring/slo-status | jq '.'

# 2. Resource usage
echo -e "\n[Resource Usage]"
kubectl top pods -n algotrading

# 3. Database connections
echo -e "\n[Database Status]"
kubectl exec -n algotrading deployment/algotrading-api -- python -c "
from backend.infra.db import get_db_session
import asyncio

async def check():
    async for session in get_db_session():
        result = await session.execute('SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()')
        print(f'Active DB connections: {result.scalar()}')
        break

asyncio.run(check())
"

# 4. Certificate status
echo -e "\n[Certificate Expiry]"
echo | openssl s_client -servername your-domain.com -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates

echo -e "\n=== Check Complete ==="
```

---

## 3. Week 1 Monitoring Schedule

### Daily Checks (Days 1-7)

**Time**: Every morning (09:00) and evening (17:00)

**Checklist**:

- [ ] **Platform Health**: All health endpoints returning 200
- [ ] **Error Rate**: < 0.1% (baseline: 0%)
- [ ] **Latency**: P95 < 500ms, P99 < 1000ms
- [ ] **SLO Compliance**: All SLOs meeting targets
- [ ] **Database Health**: 100% uptime, connection pool normal
- [ ] **Broker API**: Alpaca API calls successful
- [ ] **Certificate**: Valid and not expiring soon
- [ ] **Resource Usage**: CPU < 70%, Memory < 80%
- [ ] **Pod Status**: All pods running, no restarts
- [ ] **Recent Alerts**: Review any triggered alerts

**Documentation Template** (save each day's results):

```markdown
# Daily Health Report - Day X

**Date**: YYYY-MM-DD  
**Checked By**: [Name]  
**Check Time**: [Morning/Evening]

## Status Summary
- Overall Health: [Green/Yellow/Red]
- Critical Issues: [Count]
- Warnings: [Count]

## Metrics
| Metric | Current | Baseline | Status |
|--------|---------|----------|--------|
| Success Rate | X% | 100% | ✅/⚠️/❌ |
| Error Rate | X% | 0% | ✅/⚠️/❌ |
| P95 Latency | Xms | <200ms | ✅/⚠️/❌ |
| P99 Latency | Xms | <500ms | ✅/⚠️/❌ |
| DB Health | Up/Down | Up | ✅/⚠️/❌ |
| Request Volume | X req/min | - | ℹ️ |

## Issues Found
[List any issues, or "None"]

## Actions Taken
[List actions, or "None required"]

## Notes
[Any observations or concerns]
```

### Key Metrics to Track

#### 3.1 Availability Metrics

**Source**: Health endpoints, SLI metrics

| Metric | Collection Method | Alert Threshold |
|--------|------------------|-----------------|
| Platform uptime | `/health` endpoint | < 99.5% |
| Database availability | `db_health_check()` | < 99.5% |
| Broker API availability | Alpaca API calls | < 99.0% |
| Pod restart count | `kubectl get pods` | > 0 in 24h |

#### 3.2 Performance Metrics

**Source**: `/api/v1/monitoring/sli-metrics`

| Metric | Baseline | Warning | Critical |
|--------|----------|---------|----------|
| Request latency P50 | < 100ms | > 250ms | > 500ms |
| Request latency P95 | < 200ms | > 500ms | > 1000ms |
| Request latency P99 | < 500ms | > 1000ms | > 2000ms |
| Throughput | Variable | < 50% baseline | < 25% baseline |

#### 3.3 Error Metrics

**Source**: `/api/v1/monitoring/sli-metrics`, application logs

| Metric | Baseline | Warning | Critical |
|--------|----------|---------|----------|
| HTTP 4xx rate | 0% | > 1% | > 5% |
| HTTP 5xx rate | 0% | > 0.1% | > 0.5% |
| Database errors | 0 | > 1/hour | > 10/hour |
| Alpaca API errors | 0 | > 5/hour | > 20/hour |

#### 3.4 Business Metrics

**Source**: Application-specific endpoints

| Metric | Monitor For | Alert On |
|--------|------------|----------|
| Active users | Unexpected drops | > 50% drop |
| Order execution | Success rate | < 99% |
| Strategy execution | Completion rate | < 95% |
| ML model predictions | Availability | Model errors |

---

## 4. Alert Response Procedures

### 4.1 Critical Alerts (Immediate Response Required)

#### Alert: Platform Down (Health Check Failed)

**Detection**: `/health` returns non-200 status

**Response Steps**:
1. Check pod status: `kubectl get pods -n algotrading`
2. Check pod logs: `kubectl logs -n algotrading deployment/algotrading-api --tail=100`
3. Check recent events: `kubectl get events -n algotrading --sort-by='.lastTimestamp'`
4. If database issue: Verify DATABASE_URL and connection
5. If broker issue: Verify Alpaca API credentials
6. Escalate if not resolved in 5 minutes

**Escalation Path**:
- 0-5 min: On-call engineer investigates
- 5-15 min: Platform lead notified
- 15+ min: Emergency deployment rollback initiated

#### Alert: High Error Rate (> 0.5%)

**Detection**: SLI metrics show error_rate > 0.5%

**Response Steps**:
1. Identify error type: `kubectl logs -n algotrading deployment/algotrading-api | grep ERROR`
2. Check if specific endpoint: Review SLI metrics breakdown
3. Check database health: `curl https://your-domain.com/health`
4. Check Alpaca API: Test with `scripts/validate_production_config.py`
5. If authentication errors: Check JWT configuration
6. If database errors: Check connection pool and query performance
7. Escalate if error rate continues increasing

#### Alert: Database Connection Lost

**Detection**: `db_health_check()` returns False

**Response Steps**:
1. Verify DATABASE_URL is set: `kubectl get secret -n algotrading`
2. Test database connectivity: `kubectl exec -n algotrading deployment/algotrading-api -- python -c "from backend.infra.db import db_health_check; import asyncio; print(asyncio.run(db_health_check()))"`
3. Check PostgreSQL logs (if accessible)
4. Check connection pool: Look for "too many connections" errors
5. Restart pod if connection pool exhausted: `kubectl rollout restart -n algotrading deployment/algotrading-api`
6. Escalate if not resolved in 5 minutes

### 4.2 Warning Alerts (Monitor Closely)

#### Alert: High Latency (P95 > 500ms)

**Detection**: SLI metrics show latency_p95 > 500ms

**Response Steps**:
1. Check current request volume (may be expected under high load)
2. Review slow query log: `kubectl logs -n algotrading deployment/algotrading-api | grep "slow query"`
3. Check database performance: Connection pool, query times
4. Check external API calls: Alpaca API response times
5. Monitor for 30 minutes - escalate if sustained or worsening

#### Alert: Resource Usage High (CPU > 70%)

**Detection**: `kubectl top pods` shows high CPU/memory

**Response Steps**:
1. Check request volume (may be expected)
2. Review for memory leaks: Monitor over time
3. Check for inefficient queries or operations
4. Consider scaling: `kubectl scale deployment algotrading-api --replicas=N -n algotrading`
5. Escalate if resources continue increasing

---

## 5. Monitoring Tools and Dashboards

### 5.1 Command-Line Monitoring

```bash
# Real-time log streaming
kubectl logs -f -n algotrading deployment/algotrading-api

# Filter for errors
kubectl logs -n algotrading deployment/algotrading-api | grep -E "ERROR|CRITICAL"

# Watch pod status
watch kubectl get pods -n algotrading

# Monitor resource usage
watch kubectl top pods -n algotrading
```

### 5.2 Prometheus Queries (if Prometheus is set up)

```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Request latency P95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Pod restarts
kube_pod_container_status_restarts_total{namespace="algotrading"}

# Database connections
pg_stat_activity_count
```

### 5.3 Recommended Dashboards

If using Prometheus + Grafana, create dashboards for:

1. **Platform Overview Dashboard**
   - Request rate
   - Error rate
   - Latency percentiles (P50, P95, P99)
   - Availability (health checks)
   - Active users

2. **Infrastructure Dashboard**
   - Pod status and restarts
   - CPU and memory usage
   - Database connections
   - Network traffic
   - Disk usage

3. **Business Metrics Dashboard**
   - Order execution rate
   - Strategy performance
   - Alpaca API call success rate
   - User activity
   - Revenue metrics

4. **SLO Compliance Dashboard**
   - SLO status per objective
   - Error budget remaining
   - Time to SLO breach
   - Historical compliance

---

## 6. Week 1 Review and Adjustment

### End of Week 1 Review Meeting

**Participants**: Platform team, operations, stakeholders

**Agenda**:
1. Review week's metrics vs. baseline
2. Identify any issues or trends
3. Adjust monitoring thresholds if needed
4. Plan for transition to steady-state monitoring

**Metrics to Review**:
- Total uptime percentage
- Error rates (daily average)
- Latency trends (any degradation?)
- Alert frequency (too many? too few?)
- Resource utilization trends
- User feedback and issues

**Deliverable**: Week 1 Summary Report

```markdown
# Week 1 Post-Launch Summary

## Metrics Summary
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Uptime | 99.5% | X% | ✅/⚠️/❌ |
| Error Rate | <0.1% | X% | ✅/⚠️/❌ |
| P95 Latency | <500ms | Xms | ✅/⚠️/❌ |
| P99 Latency | <1000ms | Xms | ✅/⚠️/❌ |

## Issues Encountered
[List all issues with severity and resolution]

## Adjustments Made
[List any configuration or threshold changes]

## Recommendations
[What to do differently going forward]

## Transition Plan
[Move from intensive to steady-state monitoring]
```

---

## 7. Transition to Steady-State Monitoring

**After Week 1**, transition to regular operational monitoring:

### Daily Monitoring (Automated)
- Health checks every 5 minutes
- SLI/SLO metrics collection
- Prometheus scraping
- Alerting on threshold breaches

### Weekly Review (Manual)
- Review weekly metrics summary
- Check for trends or anomalies
- Review alert effectiveness
- Update thresholds as needed

### Monthly Review
- Comprehensive performance analysis
- Capacity planning
- SLO compliance report
- Platform optimization opportunities

---

## 8. Integration with Existing Platform

This monitoring procedure integrates seamlessly with existing platform components:

### 8.1 Using Existing Health Checks

```python
# Example: Programmatic health check
import httpx
import asyncio

async def check_platform_health():
    """Check platform using existing health endpoints."""
    async with httpx.AsyncClient() as client:
        # Use existing /health endpoint
        response = await client.get("https://your-domain.com/health")
        health_data = response.json()
        
        print(f"Status: {health_data['status']}")
        print(f"Database: {health_data['database']}")
        print(f"Timestamp: {health_data['timestamp']}")

asyncio.run(check_platform_health())
```

### 8.2 Using Existing SLI/SLO Monitoring

```python
# Example: Check SLO compliance
import httpx
import asyncio

async def check_slo_compliance():
    """Check SLO using existing monitoring endpoint."""
    async with httpx.AsyncClient() as client:
        # Use existing SLO status endpoint
        response = await client.get("https://your-domain.com/api/v1/monitoring/slo-status")
        slo_data = response.json()
        
        for slo in slo_data.get('slos', []):
            print(f"{slo['name']}: {slo['status']} ({slo['compliance']:.2f}%)")

asyncio.run(check_slo_compliance())
```

### 8.3 Using Existing Infrastructure Health

```python
# Example: Check infrastructure health
from backend.infra.db import db_health_check
from backend.infra.broker import broker_health_check
import asyncio

async def check_infrastructure():
    """Check infrastructure using existing health check functions."""
    db_healthy = await db_health_check()
    broker_healthy = await broker_health_check()
    
    print(f"Database: {'✅ Healthy' if db_healthy else '❌ Unhealthy'}")
    print(f"Broker: {'✅ Healthy' if broker_healthy else '❌ Unhealthy'}")

asyncio.run(check_infrastructure())
```

---

## 9. Troubleshooting Guide

### Common Issues and Solutions

#### Issue: TLS Certificate Not Working

**Symptoms**: HTTPS not working, certificate errors

**Diagnosis**:
```bash
kubectl describe ingress algotrading-ingress -n algotrading
kubectl describe certificate -n algotrading
kubectl logs -n cert-manager deployment/cert-manager
```

**Solution**:
1. Check cert-manager is installed and running
2. Verify DNS is pointing to ingress IP
3. Check cert-issuer is configured correctly
4. Wait for HTTP-01 challenge to complete (can take 5-10 min)

#### Issue: High Database Connection Count

**Symptoms**: "too many connections" errors

**Diagnosis**:
```bash
kubectl exec -n algotrading deployment/algotrading-api -- python -c "
from backend.infra.db import get_db_session
import asyncio
async def check():
    async for session in get_db_session():
        result = await session.execute('SELECT COUNT(*) FROM pg_stat_activity')
        print(f'Connections: {result.scalar()}')
        break
asyncio.run(check())
"
```

**Solution**:
1. Check connection pool configuration in DATABASE_URL
2. Restart pods to reset connection pool
3. Scale down if too many pods for database
4. Increase database connection limit if needed

#### Issue: Alpaca API Rate Limiting

**Symptoms**: 429 Too Many Requests errors

**Diagnosis**: Check application logs for "rate limit" errors

**Solution**:
1. Implement exponential backoff (should already be in code)
2. Reduce request frequency
3. Cache API responses where appropriate
4. Consider upgrading Alpaca API tier

---

## 10. Contact and Escalation

### On-Call Rotation

| Role | Contact | Hours | Escalation |
|------|---------|-------|------------|
| Primary Engineer | [Name/Phone] | 24/7 Week 1 | After 15 min |
| Platform Lead | [Name/Phone] | Business hours | Critical only |
| DevOps Lead | [Name/Phone] | On-call | Infrastructure issues |

### Escalation Criteria

- **Immediate**: Platform down, database down, critical data loss
- **Within 1 hour**: High error rate (>1%), persistent high latency
- **Within 4 hours**: Resource exhaustion, certificate issues, moderate issues
- **Next business day**: Performance optimization, non-critical bugs

---

## Appendix A: Monitoring Checklist Summary

### Launch Day (Hour 0-24)
- [ ] Pre-launch validator passed
- [ ] TLS certificate issued
- [ ] All health endpoints responding
- [ ] SLI metrics reporting
- [ ] Prometheus scraping working
- [ ] First 6 hours: Check every 15 minutes
- [ ] Hours 6-24: Check every hour

### Week 1 (Days 1-7)
- [ ] Daily morning check (09:00)
- [ ] Daily evening check (17:00)
- [ ] Document daily health report
- [ ] Review and respond to all alerts
- [ ] Weekly metrics trending analysis
- [ ] End of week summary report

### Ongoing (Week 2+)
- [ ] Automated monitoring active
- [ ] Weekly manual review
- [ ] Monthly comprehensive analysis
- [ ] Quarterly capacity planning
- [ ] Continuous optimization

---

**Document End**
