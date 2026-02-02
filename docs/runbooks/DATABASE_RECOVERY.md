# Database Recovery Runbook

## Overview
Procedures for recovering from PostgreSQL database issues including corruption, connection failures, and data loss scenarios.

## Severity Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| P1 | Database completely unavailable | Immediate |
| P2 | Partial database failure (read-only, replication lag) | 15 minutes |
| P3 | Performance degradation | 1 hour |
| P4 | Planned maintenance | Scheduled |

## Quick Reference Commands

```bash
# Check database status
docker-compose exec postgres pg_isready -U postgres

# Check replication status (if using replicas)
docker-compose exec postgres psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check active connections
docker-compose exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check for locks
docker-compose exec postgres psql -U postgres -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

## Scenario 1: Database Connection Failure

### Symptoms
- Application logs show `connection refused` or `timeout` errors
- Health check endpoint returns unhealthy for database
- Order submissions fail with 500 errors

### Diagnosis
1. Check if PostgreSQL container is running:
   ```bash
   docker-compose ps postgres
   ```

2. Check PostgreSQL logs:
   ```bash
   docker-compose logs --tail=100 postgres
   ```

3. Verify network connectivity:
   ```bash
   docker-compose exec backend ping postgres
   ```

### Resolution Steps

#### Step 1: Restart PostgreSQL (if container is unhealthy)
```bash
docker-compose restart postgres
# Wait 30 seconds for startup
sleep 30
docker-compose exec postgres pg_isready -U postgres
```

#### Step 2: Check connection limits
```sql
-- Connect to postgres
SHOW max_connections;
SELECT count(*) FROM pg_stat_activity;

-- If at limit, identify and kill idle connections
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'idle' 
AND query_start < NOW() - INTERVAL '10 minutes';
```

#### Step 3: If all else fails - full container recreation
```bash
# WARNING: Only if data volume is intact
docker-compose stop postgres
docker-compose rm postgres
docker-compose up -d postgres
```

## Scenario 2: Database Corruption

### Symptoms
- Errors like `invalid page in block` or `could not read block`
- Checksum verification failures
- Queries returning inconsistent results

### Resolution Steps

#### Step 1: Stop all writes immediately
```bash
# Activate kill switch to stop trading
curl -X POST http://localhost:8000/api/v1/risk/kill-switch \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Database corruption detected"}'
```

#### Step 2: Create emergency backup of current state
```bash
docker-compose exec postgres pg_dump -U postgres -Fc trading_platform > emergency_backup_$(date +%Y%m%d_%H%M%S).dump
```

#### Step 3: Run consistency check
```sql
-- Check for corrupted indexes
SELECT schemaname, relname, indexrelname, idx_scan, idx_tup_read 
FROM pg_stat_user_indexes 
WHERE idx_scan = 0 AND idx_tup_read = 0;

-- Reindex if needed
REINDEX DATABASE trading_platform;
```

#### Step 4: Restore from backup (if needed)
```bash
# Stop application
docker-compose stop backend

# Restore from most recent backup
docker-compose exec -T postgres pg_restore -U postgres -d trading_platform --clean < backup_file.dump

# Restart application
docker-compose start backend
```

## Scenario 3: High Replication Lag (Multi-AZ deployments)

### Symptoms
- Stale reads on replica nodes
- Inconsistent position/order data
- Alerts from monitoring

### Resolution Steps

1. Check replication lag:
   ```sql
   SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
          pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes
   FROM pg_stat_replication;
   ```

2. If lag > 1GB, consider:
   - Increase `wal_keep_segments`
   - Check network bandwidth between primary and replica
   - Verify replica is not CPU/IO bound

3. Force replica resync (last resort):
   ```bash
   # On replica
   pg_basebackup -h primary_host -U replication -D /var/lib/postgresql/data -Fp -Xs -P
   ```

## Backup Verification

### Daily Backup Test (should be automated)
```bash
# Create test database
createdb -U postgres backup_test

# Restore latest backup to test database
pg_restore -U postgres -d backup_test /backups/latest.dump

# Run validation queries
psql -U postgres -d backup_test -c "SELECT count(*) FROM orders;"
psql -U postgres -d backup_test -c "SELECT count(*) FROM positions;"

# Compare counts with production
# Alert if > 1% difference

# Cleanup
dropdb -U postgres backup_test
```

## Escalation Path

1. **On-call SRE**: First 15 minutes
2. **Database Team Lead**: If unresolved after 15 minutes
3. **Engineering Director**: If P1 unresolved after 30 minutes or data loss confirmed
4. **Executive notification**: If trading halted > 1 hour

## Post-Incident

1. Create incident ticket
2. Preserve all logs from incident window
3. Schedule post-mortem within 48 hours
4. Update this runbook with learnings
