# Incident Response Runbook — Intra Trading Platform

**Last Updated:** 2026-02-22
**Applies to:** Organism live engine (paper + production)

---

## Table of Contents

1. [Drawdown Kill Triggered](#1-drawdown-kill-triggered)
2. [Data Feed Failure During Market Hours](#2-data-feed-failure-during-market-hours)
3. [Broker API Outage / Stream Disconnect](#3-broker-api-outage--stream-disconnect)
4. [Brain Corruption on Restart](#4-brain-corruption-on-restart)
5. [Manual "Flat All Positions"](#5-manual-flat-all-positions)
6. [Rollback Procedure](#6-rollback-procedure)
7. [Prometheus Alert Thresholds](#7-prometheus-alert-thresholds)

---

## 1. Drawdown Kill Triggered

**What happens:** When portfolio drawdown exceeds `ORGANISM_DRAWDOWN_KILL_PCT` (default 8%), the engine calls `governance.trigger_drawdown_kill()`, sets `entries_blocked = True`, and logs `"Drawdown kill triggered"`. Exits continue running. No new entries are allowed.

**Prometheus alert:** `organism_halted_with_positions_total > 0`

### Diagnosis

```bash
# Check engine logs for drawdown kill
docker logs intra-api-1 2>&1 | grep -i "drawdown kill"

# Check current governance state
curl -s http://localhost:8000/api/v1/organism/status \
  -H "Authorization: Bearer $TOKEN" | jq '.governance'

# Check current equity and drawdown
curl -s http://localhost:8000/api/v1/organism/decisions \
  -H "Authorization: Bearer $TOKEN" | jq '.equity, .drawdown_pct'
```

### Response

1. **Verify positions are being managed.** Exits continue running automatically even after drawdown kill. Confirm via logs: `"exits still active"`.
2. **Assess cause.** Check if the drawdown is from a market-wide move or a single concentrated loss.
3. **If legitimate market move:** Wait for positions to exit via adaptive exits or safety net. The engine will not enter new trades until governance is manually resumed.
4. **If false positive (e.g., bad price data):**
   ```bash
   # Resume trading after investigation
   curl -X POST http://localhost:8000/api/v1/organism/resume \
     -H "Authorization: Bearer $TOKEN"
   ```
5. **If positions need immediate exit:** See [Manual Flat All Positions](#5-manual-flat-all-positions).

### Recovery

After all positions are closed and the cause is understood:
```bash
# Reset governance state
curl -X POST http://localhost:8000/api/v1/organism/resume \
  -H "Authorization: Bearer $TOKEN"

# Verify engine resumes normal ticking
docker logs -f intra-api-1 2>&1 | grep "tick completed"
```

---

## 2. Data Feed Failure During Market Hours

**What happens:** When `_fetch_and_compute_features()` returns fewer than 3 symbols, the engine sets `entries_blocked = True` with message `"Insufficient features"`. Exits continue via broker price fallback (using `current_price` from `get_all_positions()`).

**Prometheus alert:** `organism_entries_blocked_total` sustained increase

### Diagnosis

```bash
# Check for feature fetch failures
docker logs intra-api-1 2>&1 | grep -i "insufficient features\|fetch.*fail\|data.*error"

# Check Alpaca data API status
curl -s https://api.alpaca.markets/v2/clock \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" | jq .

# Test data fetch manually
curl -s "http://localhost:8000/api/v1/organism/decisions" \
  -H "Authorization: Bearer $TOKEN" | jq '.features_count'
```

### Response

1. **No operator action needed immediately.** The engine continues managing exits via broker price fallback. This is the designed safe mode.
2. **Check if Alpaca's data API is down** — if so, wait for recovery.
3. **If the issue is local** (network, DNS, container), restart the API container:
   ```bash
   docker-compose restart api
   ```
4. **If data is partially available** (some symbols work), the engine will resume normal entries once >= 3 symbols have features.

---

## 3. Broker API Outage / Stream Disconnect

**What happens:** The Alpaca WebSocket stream (`alpaca_stream.py`) has automatic reconnection with exponential backoff. If the REST API is also down, order submissions will fail and be logged.

**Prometheus alert:** Stream queue high-water-mark or reconnection count increase

### Diagnosis

```bash
# Check stream status
docker logs intra-api-1 2>&1 | grep -i "stream\|reconnect\|websocket"

# Check Alpaca API status page
# https://status.alpaca.markets/

# Verify broker connectivity
curl -s https://paper-api.alpaca.markets/v2/account \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" | jq '.status'
```

### Response

1. **Stream disconnect:** Automatic reconnection handles this. Monitor logs for `"Reconnected"` messages.
2. **REST API down:** Order submissions will fail with logged errors. Existing positions are held; adaptive exits will queue but not execute until API recovers.
3. **Extended outage (> 15 min):**
   - Consider pausing the engine to prevent stale decisions:
     ```bash
     curl -X POST http://localhost:8000/api/v1/organism/halt \
       -H "Authorization: Bearer $TOKEN"
     ```
   - Monitor Alpaca status page for recovery ETA.
   - Resume after connectivity is restored.

### Recovery

The stream auto-reconnects. After REST API recovery:
```bash
# Force a reconciliation to catch up on fills
curl -X POST http://localhost:8000/api/v1/organism/tick \
  -H "Authorization: Bearer $TOKEN"

# Verify positions match broker
curl -s http://localhost:8000/api/v1/organism/decisions \
  -H "Authorization: Bearer $TOKEN" | jq '.positions'
```

---

## 4. Brain Corruption on Restart

**What happens:** `brain_persistence.py` uses atomic writes (write to temp file, then `os.replace()`) with 5 rolling backups. On load, if the primary file is corrupt, it tries backups in reverse order. If all backups are corrupt, the brain starts fresh with safe defaults.

### Diagnosis

```bash
# Check brain files
ls -la organism_brain/

# Check for corruption recovery in logs
docker logs intra-api-1 2>&1 | grep -i "brain\|corrupt\|backup\|fallback"

# Verify brain loaded correctly
curl -s http://localhost:8000/api/v1/organism/status \
  -H "Authorization: Bearer $TOKEN" | jq '.brain_loaded'
```

### Response

1. **Automatic recovery works in most cases.** The brain will load from the most recent valid backup.
2. **If brain starts fresh (all backups corrupt):**
   - The engine operates safely with default parameters.
   - ML model and evolution state are lost — the engine will retrain from scratch.
   - Position state is NOT stored in the brain (it comes from the broker) — no position data is lost.
3. **To manually restore from a backup:**
   ```bash
   # List available backups
   ls -la organism_brain/*.bak.*

   # Copy a known-good backup over the primary
   cp organism_brain/brain_state.json.bak.1 organism_brain/brain_state.json

   # Restart the engine
   docker-compose restart api
   ```

---

## 5. Manual "Flat All Positions"

**Use when:** Emergency liquidation needed — drawdown kill with unacceptable ongoing losses, or end-of-day before a weekend/holiday.

### Procedure

```bash
# Step 1: Halt the engine to prevent new entries
curl -X POST http://localhost:8000/api/v1/organism/halt \
  -H "Authorization: Bearer $TOKEN"

# Step 2: Cancel all open orders
curl -X DELETE "https://paper-api.alpaca.markets/v2/orders" \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY"

# Step 3: Close all positions via Alpaca
curl -X DELETE "https://paper-api.alpaca.markets/v2/positions" \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY"

# Step 4: Verify all positions closed
curl -s "https://paper-api.alpaca.markets/v2/positions" \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" | jq 'length'
# Expected: 0

# Step 5: Run reconciliation to update internal state
curl -X POST http://localhost:8000/api/v1/organism/tick \
  -H "Authorization: Bearer $TOKEN"

# Step 6 (when ready to resume):
curl -X POST http://localhost:8000/api/v1/organism/resume \
  -H "Authorization: Bearer $TOKEN"
```

**For production (live money):** Replace `paper-api.alpaca.markets` with `api.alpaca.markets`.

---

## 6. Rollback Procedure

### Application Rollback

```bash
# Step 1: Halt the engine
curl -X POST http://localhost:8000/api/v1/organism/halt \
  -H "Authorization: Bearer $TOKEN"

# Step 2: Identify the last known-good commit
git log --oneline -10

# Step 3: Checkout the target commit
git checkout <commit-hash>

# Step 4: Rebuild and restart
docker-compose up -d --build api

# Step 5: Verify the engine starts correctly
docker logs -f intra-api-1 2>&1 | head -50

# Step 6: Resume trading
curl -X POST http://localhost:8000/api/v1/organism/resume \
  -H "Authorization: Bearer $TOKEN"
```

### Configuration Rollback

Environment variables are in `.env` (gitignored) and `docker-compose.yml`:

```bash
# Key configuration to check
grep -E "ORGANISM_|DRAWDOWN|RECONCILIATION" .env

# To revert a config change, edit .env and restart
docker-compose up -d --build api
```

### Database Rollback

The platform uses Alembic migrations:

```bash
# Check current migration
docker exec intra-api-1 alembic current

# Downgrade one step
docker exec intra-api-1 alembic downgrade -1

# Restart after migration change
docker-compose restart api
```

---

## 7. Prometheus Alert Thresholds

Configure these alerts in your monitoring system (Prometheus/Grafana):

| Metric | Alert Condition | Severity | Action |
|---|---|---|---|
| `organism_halted_with_positions_total` | > 0 | **Critical** | Engine halted with open positions. See [Drawdown Kill](#1-drawdown-kill-triggered). |
| `organism_safety_net_triggered_total` | increase > 3 in 1h | **Warning** | Safety net firing frequently — review exit parameters or market conditions. |
| `organism_entries_blocked_total` | sustained increase for > 5 min | **Warning** | Entries blocked — check data feed or governance state. See [Data Feed Failure](#2-data-feed-failure-during-market-hours). |
| `organism_exits_skipped_no_data_total` | > 0 | **Warning** | Exits attempted without feature data — broker price fallback used. |
| `organism_sector_cap_blocked_total` | increase > 10 in 1h | **Info** | Sector concentration limits working — no action needed unless unexpected. |
| Stream reconnection count | increase > 3 in 15 min | **Warning** | Unstable connection. See [Broker API Outage](#3-broker-api-outage--stream-disconnect). |

### Setting Up Alerts

The platform exposes Prometheus metrics at `/metrics`. Example Prometheus alerting rule:

```yaml
groups:
  - name: organism_safety
    rules:
      - alert: OrganismHaltedWithPositions
        expr: organism_halted_with_positions_total > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Organism engine halted with open positions"
          runbook_url: "docs/INCIDENT_RESPONSE_RUNBOOK.md#1-drawdown-kill-triggered"

      - alert: SafetyNetFiringFrequently
        expr: increase(organism_safety_net_triggered_total[1h]) > 3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Safety net exit triggered multiple times in past hour"

      - alert: EntriesBlockedSustained
        expr: increase(organism_entries_blocked_total[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Organism entries blocked for sustained period"
```
