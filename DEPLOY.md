# Deployment Guide for Algorithmic Trading Platform

This guide covers the complete deployment strategy including canary deployments, SLO-based promotion/rollback, and operational procedures.

## 🚀 Deployment Strategy

### Overview

Our deployment strategy follows a **canary deployment pattern** with automatic promotion/rollback based on real-time SLO (Service Level Objective) monitoring. This ensures production stability while enabling rapid, safe deployments.

### Key Features

- **Canary Deployments**: Gradual traffic shifting with configurable percentages
- **SLO-Based Decisions**: Automatic promotion/rollback based on Prometheus metrics
- **Zero-Downtime**: Blue-green style deployments with traffic splitting
- **Automatic Rollback**: Immediate rollback on SLO threshold violations
- **Comprehensive Monitoring**: Real-time metrics and alerting

## 📊 Service Level Objectives (SLOs)

### Production SLO Thresholds

| Metric | Threshold | Monitoring Window |
|--------|-----------|------------------|
| Error Rate | < 1.0% | 5-minute rolling average |
| P95 Response Time | < 2.0 seconds | 5-minute rolling average |
| P99 Response Time | < 5.0 seconds | 5-minute rolling average |

### Canary Decision Logic

- **Promote**: All SLO metrics within thresholds for entire monitoring period
- **Rollback**: Any SLO metric exceeds threshold for 3 consecutive checks
- **Monitoring Duration**: Configurable (default: 15 minutes)

## 🛠 Deployment Process

### 1. Automated Canary Deployment

Triggered via GitHub Actions workflow dispatch:

```bash
# Via GitHub UI or API
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOUR_ORG/algotrading-platform/actions/workflows/canary-deployment.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "version": "v1.2.3",
      "canary_percentage": "10",
      "slo_check_duration": "15"
    }
  }'
```

### 2. Manual Deployment Commands

For emergency deployments or troubleshooting:

```bash
# Deploy specific version to staging
make deploy-staging VERSION=v1.2.3

# Run smoke tests
make smoke-test ENVIRONMENT=staging

# Deploy to production (manual)
make deploy-prod VERSION=v1.2.3

# Check deployment status
kubectl get deployments -n trading-platform-production
```

### 3. Deployment Phases

#### Phase 1: Validation (2-3 minutes)
- Input validation (version format, percentages)
- Pre-deployment checks
- Infrastructure readiness verification

#### Phase 2: Canary Deployment (3-5 minutes)
- Deploy canary version alongside stable
- Configure traffic splitting (e.g., 10% canary, 90% stable)
- Health check verification
- Smoke test execution

#### Phase 3: SLO Monitoring (5-60 minutes, configurable)
- Real-time metrics collection from Prometheus
- SLO threshold monitoring
- Automated decision making
- Continuous health assessment

#### Phase 4: Promotion or Rollback (2-3 minutes)
- **Success**: Promote canary to stable, remove old version
- **Failure**: Rollback canary, restore 100% stable traffic
- Cleanup and notification

## 🔧 Configuration

### Environment Variables

```bash
# Deployment Configuration
PROMETHEUS_URL=http://prometheus.monitoring.svc.cluster.local:9090
STAGING_NAMESPACE=trading-platform-staging
PROD_NAMESPACE=trading-platform-production

# SLO Thresholds (can be overridden)
MAX_ERROR_RATE=1.0          # Percentage
MAX_P95_LATENCY=2.0         # Seconds
MAX_P99_LATENCY=5.0         # Seconds

# Canary Settings
DEFAULT_CANARY_PERCENTAGE=10
DEFAULT_SLO_CHECK_DURATION=15  # Minutes
MAX_SLO_VIOLATIONS=3        # Before rollback
```

### Kubernetes Resources

Required secrets in your cluster:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: deployment-secrets
  namespace: trading-platform-production
data:
  kube-config: <base64-encoded-kubeconfig>
  prometheus-url: <base64-encoded-prometheus-url>
```

## 📝 Runbook: How We Deploy

### Normal Deployment Process

1. **Prepare Release**
   ```bash
   # Create release branch
   git checkout -b release/v1.2.3

   # Update version in pyproject.toml
   # Update CHANGELOG.md
   # Run full test suite
   make test-all

   # Create and push tag
   git tag -a v1.2.3 -m "Release v1.2.3"
   git push origin v1.2.3
   ```

2. **Trigger Canary Deployment**
   - Go to GitHub Actions → Canary Deployment
   - Click "Run workflow"
   - Enter version: `v1.2.3`
   - Set canary percentage: `10` (for low-risk) or `25` (for high-confidence)
   - Set monitoring duration: `15` minutes (standard) or `30` (for major changes)

3. **Monitor Deployment**
   - Watch GitHub Actions progress
   - Monitor Grafana dashboards for real-time metrics
   - Check Slack notifications for status updates

4. **Verification**
   - If promoted: Verify all services running new version
   - If rolled back: Investigate logs and metrics, fix issues
   - Update deployment status in team channels

### Emergency Deployment

For critical hotfixes:

1. **Fast-Track Process**
   ```bash
   # Skip normal release process
   git checkout main
   # Apply hotfix
   # Immediate tag and deploy
   git tag -a v1.2.4-hotfix -m "Critical security fix"
   git push origin v1.2.4-hotfix
   ```

2. **Accelerated Canary**
   - Use 5% canary traffic
   - 10-minute SLO monitoring
   - Manual approval for promotion

## 🔄 Rollback Procedures

### Automatic Rollback Triggers

The system automatically rolls back when:
- Error rate exceeds 1% for 3 consecutive checks
- P95 latency exceeds 2 seconds for 3 consecutive checks
- P99 latency exceeds 5 seconds for 3 consecutive checks
- Health checks fail consistently
- Critical alerts fire

### Manual Rollback

```bash
# Immediate rollback to previous version
kubectl rollout undo deployment/trading-platform -n trading-platform-production

# Rollback to specific version
kubectl rollout undo deployment/trading-platform --to-revision=N -n trading-platform-production

# Verify rollback
kubectl rollout status deployment/trading-platform -n trading-platform-production

# Clean up canary resources
kubectl delete deployment trading-platform-canary -n trading-platform-production
kubectl delete virtualservice trading-platform-canary -n trading-platform-production
```

### Rollback Verification

After rollback:
1. Check all pods are running and healthy
2. Verify metrics return to normal levels
3. Run smoke tests to confirm functionality
4. Update incident tracking and notifications

## 🚨 Emergency Procedures

### Circuit Breaker: Kill Switch

For immediate traffic halt:

```bash
# Scale down to zero (emergency stop)
kubectl scale deployment trading-platform --replicas=0 -n trading-platform-production

# Or redirect to maintenance page
kubectl apply -f k8s/maintenance-mode.yaml
```

### Database Rollback

For schema changes:

```bash
# Run migration rollback
python -m alembic downgrade -1

# Or restore from backup
pg_restore -h $DB_HOST -U $DB_USER -d trading_platform backup_YYYYMMDD.sql
```

### Network Issues

Traffic rerouting:

```bash
# Switch to backup region/cluster
kubectl apply -f k8s/failover-config.yaml

# Update DNS to point to backup
# (External DNS management required)
```

## 📊 Monitoring and Observability

### Key Dashboards

1. **Deployment Dashboard**
   - Canary vs Stable traffic distribution
   - SLO metric trends
   - Deployment timeline and status

2. **SLO Monitoring Dashboard**
   - Real-time error rates
   - Latency percentiles (P50, P95, P99)
   - SLO burn rate and error budget

3. **Infrastructure Dashboard**
   - Pod status and resource usage
   - Network metrics and latency
   - Database performance

### Alert Channels

- **Critical**: PagerDuty + Slack #alerts
- **Warning**: Slack #deployments
- **Info**: Slack #trading-platform

### Metrics Collection

Key metrics tracked during deployments:

```promql
# Error rate by version
sum(rate(intraday_http_requests_total{status=~"5..",deployment_version="v1.2.3"}[5m]))
/ sum(rate(intraday_http_requests_total{deployment_version="v1.2.3"}[5m])) * 100

# P95 latency by version
histogram_quantile(0.95,
  rate(intraday_http_request_duration_seconds_bucket{deployment_version="v1.2.3"}[5m])
)

# Canary traffic percentage
sum(rate(intraday_http_requests_total{version="canary"}[5m]))
/ sum(rate(intraday_http_requests_total[5m])) * 100
```

## 🛡 Security Considerations

### Deployment Security

- All deployments require GitHub branch protection
- Kubernetes RBAC with least-privilege access
- Signed container images with cosign
- Network policies restricting inter-service communication

### Secrets Management

- Kubernetes secrets for sensitive configuration
- Vault integration for database credentials
- Rotation policies for API keys and certificates

### Audit Trail

All deployment activities are logged:
- GitHub Actions execution logs
- Kubernetes audit logs
- Prometheus metrics retention
- Incident response documentation

## 📚 Troubleshooting

### Common Issues

#### 1. Canary Deployment Stuck

**Symptoms**: Deployment shows "Progressing" but never completes

**Resolution**:
```bash
# Check pod status
kubectl get pods -n trading-platform-production -l version=canary

# Check events
kubectl describe deployment trading-platform-canary -n trading-platform-production

# Check resource constraints
kubectl top pods -n trading-platform-production
```

#### 2. SLO Check Failures

**Symptoms**: Metrics show violations but service appears healthy

**Resolution**:
1. Verify Prometheus connectivity
2. Check metric label consistency
3. Validate query syntax in workflow
4. Review baseline metrics before deployment

#### 3. Rollback Not Working

**Symptoms**: Rollback command succeeds but traffic still going to canary

**Resolution**:
```bash
# Manually remove traffic splitting
kubectl delete virtualservice trading-platform-canary -n trading-platform-production

# Force service selector update
kubectl patch service trading-platform -n trading-platform-production \
  --patch '{"spec":{"selector":{"app":"trading-platform","version":"stable"}}}'
```

### Getting Help

1. **Check Runbooks**: This document and `/docs/runbooks/`
2. **Slack Channels**: #trading-platform, #sre-support
3. **On-Call Engineer**: Use PagerDuty for critical issues
4. **Documentation**: Internal wiki and GitHub issues

## 📈 Deployment Metrics

### Success Criteria

- **Deployment Success Rate**: > 95%
- **Mean Time to Deploy**: < 20 minutes
- **Mean Time to Rollback**: < 5 minutes
- **SLO Compliance**: > 99.9% during deployments

### Continuous Improvement

- Weekly deployment retrospectives
- Monthly SLO review and threshold adjustment
- Quarterly disaster recovery drills
- Annual deployment process audit

---

## Quick Reference

### Common Commands

```bash
# Deploy canary (via workflow)
gh workflow run canary-deployment.yml -f version=v1.2.3 -f canary_percentage=10

# Check deployment status
kubectl get deployments -A | grep trading-platform

# Manual rollback
kubectl rollout undo deployment/trading-platform -n trading-platform-production

# View logs
kubectl logs -f deployment/trading-platform -n trading-platform-production

# Scale deployment
kubectl scale deployment trading-platform --replicas=5 -n trading-platform-production

# Emergency stop
kubectl scale deployment trading-platform --replicas=0 -n trading-platform-production
```

### Emergency Contacts

- **On-Call Engineer**: PagerDuty escalation
- **Platform Team**: @platform-team in Slack
- **Security Team**: security@yourcompany.com
- **Executive Escalation**: CTO/VP Engineering

---

*Last Updated: 2025-08-10*
*Document Version: 2.0*
*Next Review: 2025-09-10*
