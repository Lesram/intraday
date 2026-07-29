# Top Blockers & Backlog — as of 2026-04-24T04:00Z

## Immediate DEPLOY 2 blockers (from DEPLOY_VERIFICATION_DEPLOY2_33d6138.md)
Cannot cleanly checkout/rebuild `33d6138` until resolved. Preflight HARD STOP.

1. **Worktree not clean on 4 files** — all are *reverts* matching `ce06d41` md5, not forward edits.
   - `backend/organism/adaptive_exits.py` — reverts Exp4 chop trailing giveback
   - `backend/organism/pyramider.py` — reverts G3 NaN/Inf pyramid guard
   - `monitoring/memory_monitoring.json` — monitoring threshold change
   - `scripts/generate_experiment_observation_report.py` — reverts observation tooling giveback section
   - Decision required: **keep reverts** (partial rollback) or **restore HEAD** (full 33d6138 deploy).

2. **Paper-mode risk envs not explicitly set** (required by DEPLOY 2 preflight #8):
   - `ORGANISM_MAX_NOTIONAL` — absent
   - `ORGANISM_MAX_DAILY_LOSS` — absent
   - Expected values per hand-off: `=0` (caps ship inert / disabled).

3. **`SLACK_WEBHOOK_URL` absent** (required by DEPLOY 2 preflight #9):
   - 33d6138's marquee change is alert wiring; without a sink URL, the end-to-end verification of the alert path is not meaningful.
   - Decision required: supply a URL now, or acknowledge alerts ship silent and verify later.

## Top real-money blockers (from REAL_MONEY_GAP_MAP.md)

| Rank | Gap | Current | Target | Severity |
|---|---|---|---|---|
| 1 | **Expectancy/trade** | −$1.92 (improving to -$0.41 last 100) | >+$0.50 sustained ≥3wk | LARGE |
| 2 | **Win rate** | 18.8% lifetime / ~34% recent | >30% sustained | LARGE |
| 3 | **Sharpe (recent)** | Negative | >1.0 annualized | LARGE |
| 4 | **Consecutive positive sessions** | 0 | ≥10 | NOT STARTED |
| 5 | Daily max-loss auto-halt | Not live (code shipped in 33d6138 but container is ce06d41) | −$500/day | MEDIUM |
| 6 | Weekly drawdown halt | None | −$1500/week | MEDIUM |
| 7 | Sector concentration cap | None | ≤40% one sector | MEDIUM |
| 8 | Automated dashboard + alerts | Manual (33d6138 adds hooks but no URL wired) | Auto | MEDIUM |
| 9 | Position max-loss auto-close | None (stops only) | −$200/pos | SMALL |

## Backlog — Phase C (from CLAUDE.md, next 2 weeks)

1. Clean separation of ranking_score / direction / expected_return / size
2. True microstructure alpha (order-flow imbalance, depth)
3. Staged learning → production transition (4 stages: 0→1→2→3)

## Documentation debt
- ~90+ untracked `*_REPORT.md` files at repo root
- ~30 untracked `*_bundle/` audit directories at repo root
- `backend.zip`, `tests.zip`, `organism_brain.zip`, etc. untracked archives
- Large untracked `docs/engineering/*` trees (gated_persistence_final, incident_recovery_wave, last_mile_audit, master_remediation, no_trade_*, preopen_j6_*, residual_*, weekend_*)
- None of this affects runtime; cleanup is a separate housekeeping task.
