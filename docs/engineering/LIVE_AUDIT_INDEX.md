# Live Audit Index

Generated: 2026-10-05T09:24:18Z
PR: n/a
SHA: `ec9306df62`
Branch: `fix/outbox-dispatch-guards`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

Total distinct changed files: **9**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 4 | `backend/infra/outbox_worker.py`, `backend/integrations/alpaca_broker.py`, `backend/integrations/alpaca_outbox.py`, `backend/services/order_service.py` |
| Scripts | 1 | `scripts/runtime/write_runtime_snapshot.py` |
| CI | 0 | none |
| Tests | 2 | `tests/test_audit_20261005_outbox_dispatch_guards.py`, `tests/unit/test_alpaca_outbox_comprehensive.py` |
| Docs | 2 | `docs/architecture/mapss.md`, `docs/runbooks/PAPER_UPTIME.md` |
| Artifacts/evidence | 0 | none |
| Reports | 0 | none |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **0** file(s).

### Full changed-file list

- `backend/infra/outbox_worker.py`
- `backend/integrations/alpaca_broker.py`
- `backend/integrations/alpaca_outbox.py`
- `backend/services/order_service.py`
- `docs/architecture/mapss.md`
- `docs/runbooks/PAPER_UPTIME.md`
- `scripts/runtime/write_runtime_snapshot.py`
- `tests/test_audit_20261005_outbox_dispatch_guards.py`
- `tests/unit/test_alpaca_outbox_comprehensive.py`

## Configuration resolution (not engine observation)

Source: `resolved_config_snapshot.json`
Evidence scope: `offline_source_and_process_defaults_not_runtime_observation`
These values describe this generator's configuration inputs. Offline runs can contain source defaults and test-process paths; they do not establish the installed paper configuration.

```json
{
  "timeframe": "1Day",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.05,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": false,
  "phase9_shadow_engines_enabled": false
}
```

## Snapshot files

- Source/process defaults: `artifacts/runtime_defaults_snapshot.json`
- Expected configuration resolution: `artifacts/resolved_config_snapshot.json`
- Separate live-process evidence (check reachability and field provenance): `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- Displayed configuration is expected configuration, not observed engine state; inspect the separate live-process evidence and its reachability.
- 4 backend runtime file(s) changed — require targeted verification
