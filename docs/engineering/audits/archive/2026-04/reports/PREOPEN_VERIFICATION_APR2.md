# Pre-Open Verification — Apr 2, 2026

# 1. Verdict

**READY**

The running container is the persistence-fixed build (3534346). All five critical fixes are verified present in the deployed code. The brain volume mount is durable (RW). The account is ACTIVE, flat, and unblocked. No pre-open anomalies suggest today's session would be an invalid persistence test. This is the first session where the complete split persistence model is deployed from the start.

# 2. Deployment Verification

| Check | Result |
|---|---|
| Deployed SHA | Cannot determine exact commit SHA (git not in container). Code verification below confirms it matches 3534346 content. |
| Repo HEAD SHA | `8f1e65785521573668b4ec067d58f40fe0cdf5fe` |
| HEAD differs from deployed | YES — HEAD is `8f1e657` (handoff doc), deployed is `3534346` (persistence fix). Delta is docs-only, no code difference. |
| Container created | 2026-04-02T03:21:20Z |
| Restart count | 0 |

### Code Verification (container grep results)

| Fix | Present | Line(s) |
|---|---|---|
| `save_essential_state()` in brain_persistence.py | YES | 500 |
| `save_essential_state()` call in live_engine.py | YES | 4218 |
| Gate-block message: "persisting all runtime truth" | YES | 4215 |
| Watchdog tick update on essential save | YES | 4242 |
| `reconciliation_adjustment` tag | YES | 3641 |
| `_last_regime if self._last_regime` (regime_at_exit fix) | YES | 3623 |
| Stale metadata pruning (`stale_symbols`) | YES | 819-826 |

All seven fix signatures are confirmed present. The gate-block message format is the NEW format ("persisting all runtime truth"), not the old format ("exit_levels + entry_metadata persisted separately"). This confirms the container runs the 3534346 code, not 53cc1ad.

# 3. Runtime / Environment Verification

| Check | Value |
|---|---|
| APP_ENVIRONMENT | `development` (correct) |
| ALPACA_PAPER | `true` |
| USE_MOCK_DATA | `false` |
| USE_MOCK_BROKER | `false` |
| Container status | Up 3 hours (healthy) |
| API health | `{"status":"ok"}` at 06:15:51Z |
| Brain volume mount | `./organism_brain:/app/organism_brain` — RW, bind mount, rprivate propagation |
| Restart count | 0 (no unexpected restarts) |

Volume mount is confirmed durable: `"RW": true`, type `bind`, source `/Users/marselkei/VS/intra/organism_brain`. Brain writes from the container will persist to the host filesystem.

# 4. Pre-Open State Snapshot

### Brain Manifest
```json
{
  "brain_format_version": 2,
  "saved_at": "2026-04-02T03:21:20.551783+00:00",
  "generation": 0,
  "total_runs": 96,
  "total_trades": 161,
  "cumulative_pnl": -714.26,
  "best_sharpe": 0,
  "ml_is_trained": true,
  "feature_count": 79
}
```

| Field | Value |
|---|---|
| total_trades | 161 |
| cumulative_pnl | -714.26 |
| saved_at | 2026-04-02T03:21:20Z |
| generation | 0 |
| ml_is_trained | true |
| feature_count | 79 |
| best_sharpe | 0 (reset from backup; was 1.1611 pre-data-loss) |

### Trade History
- Total lines: 162 (161 trades + header)
- Last entry: `QQQ ... 2026-03-31T16:48:18` (trailing_stop, +$17.78)
- Note: The last 3 entries include the XLK `live_close` artifact (+$174) from Mar 31. This is a known stale-fill artifact, not a strategy trade.

### Account
| Field | Value |
|---|---|
| Equity | $111,644.66 |
| Cash | $111,644.66 |
| Buying power | $446,382.04 |
| Status | ACTIVE |
| Trading blocked | false |
| Account blocked | false |
| Long market value | $0 |
| Open positions | 0 (FLAT) |
| Day trade count | 43 |

System starts flat with no open positions.

### Orphan State
- `exit_levels`: Contains `AMZN` entry (residual from Mar 31 backup CORE-013 persist)
- `entry_metadata`: Empty (stale metadata was pruned)
- `pending_entry`: Empty

The orphan AMZN exit_levels without corresponding entry_metadata is harmless — no trade will be recorded without entry_metadata present. If the organism enters AMZN today, it will create fresh entry_metadata and the exit_levels will be overwritten by the new position's levels.

# 5. Config Truth

### docker-compose.paper.yml (relevant)
```yaml
volumes:
  - ./logs:/app/logs
  - ./data:/app/data
  - ./organism_brain:/app/organism_brain

environment:
  - APP_ENVIRONMENT=development
  - ALPACA_PAPER=true
  - USE_MOCK_DATA=false
  - USE_MOCK_BROKER=false
```

### Live Environment (from container)
```
APP_ENVIRONMENT=development
ALPACA_PAPER=true
USE_MOCK_DATA=false
USE_MOCK_BROKER=false
PYTHONPATH=/app
OTEL_SERVICE_NAME=algotrading-api-paper
OTEL_ENABLED=true
```

No config drift detected. Brain volume mount is present in both compose file and live mounts.

# 6. Startup / Pre-Open Anomaly Scan

### Startup Sequence (03:21:20 – 03:21:29 UTC)
1. Database ready, migrations complete, 5 critical tables present
2. Brain loaded: gen=0, runs=96, trades=161
3. ML models restored into signal generator
4. Learner state restored: gen=0, trades=161
5. Evolution freeze active (161/300 trades)
6. Universe selector restored: 22 symbols, PSQ+SH protected present
7. Exit levels restored for 1 position (AMZN — residual, see Section 4)
8. Regime Kelly stats restored
9. ML calibration restored
10. Alpha weights sum warning: 0.9497 (pre-existing, cosmetic)
11. Transfer learning warm-start skipped (evolution freeze)
12. PREFLIGHT: 15/18 checks passed (0 critical, 3 warnings)
13. Scheduler starting: tick_interval=10s, brain_loaded=True, streaming=True

### Anomalies
- **Alpha weights sum 0.9497**: Pre-existing cosmetic warning. Not actionable.
- **PREFLIGHT 15/18 (3 warnings)**: Warning-only, 0 critical. Consistent with prior sessions.
- **AMZN exit_levels without entry_metadata**: Residual from backup. Harmless.
- **No stale metadata pruning logged**: No stale entry_metadata existed to prune (entry_metadata was empty in the backup). This means the pruning code path was not exercised, but that's correct — there was nothing to prune.
- **No reconciliation events**: None during pre-market startup. Expected.
- **No errors, no exceptions, no tracebacks**: Clean startup.

None of these anomalies would make today's session an invalid persistence test.

# 7. Hard-Stop Checks

| # | Check | Result |
|---|---|---|
| 1 | Running container is on 3534346 | **PASS** — all 7 code signatures verified. Gate-block message format confirms new code. |
| 2 | save_essential_state exists in running container | **PASS** — present at line 500 in brain_persistence.py |
| 3 | Brain volume mount present and durable | **PASS** — bind mount, RW=true, verified via docker inspect |
| 4 | APP_ENVIRONMENT is correct | **PASS** — `development` |
| 5 | Account is ACTIVE, flat, unblocked | **PASS** — equity $111,644.66, 0 positions, trading_blocked=false |
| 6 | No material config drift | **PASS** — compose file matches live environment |
| 7 | No pre-open anomaly invalidates persistence test | **PASS** — clean startup, no errors |

**All 7 checks PASS. No HARD STOP.**

# 8. Files Produced

```
preopen_verification_apr2/
├── repo_head_sha.txt
├── deployed_sha.txt
├── container_code_verification.txt
├── env_snapshot.txt
├── container_status.txt
├── docker_inspect_mounts.txt
├── api_health.txt
├── brain_manifest_preopen.json
├── learning_state_preopen.json
├── trade_history_tail.txt
├── account_snapshot_preopen.json
├── positions_snapshot_preopen.json
├── config_snapshot.txt
├── preopen_log_scan.txt
```
