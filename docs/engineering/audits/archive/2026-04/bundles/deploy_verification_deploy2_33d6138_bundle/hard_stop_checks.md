# DEPLOY 2 — Hard-stop checks (deploy did NOT proceed)

| # | Check | PASS/FAIL | Evidence |
|---|-------|-----------|----------|
| 1 | target commit 33d6138 deployed | FAIL | Running container file hashes match ce06d41 exactly (kelly_sizer, ml_signal, brain_persistence, live_engine, settings) |
| 2 | current container healthy | PASS | docker inspect → Health=healthy, Running=true, RestartCount=0, Uptime≈20h |
| 3 | Exp1A preserved | PASS (in running ce06d41 — not re-verified in 33d6138) | `_CHOP_MIN_HOLD_BARS = 10` at live_engine.py:1936 in container |
| 4 | Exp2 present | PASS (in running ce06d41) | `inverse_etf_suppressed_chop` at live_engine.py:2437,2444 in container |
| 5 | Exp3 present and read-only | PASS (in running ce06d41) | `confidence_bt_only`, `confidence_ml_component`, `gate_pass_live` present at live_engine.py:2170,2248,2249 |
| 6 | Exp4 present | FAIL | ABSENT in running container (ce06d41). Also REVERTED in worktree (md5 of adaptive_exits.py in worktree == ce06d41 md5; 40 lines deleted vs HEAD) |
| 7 | G1/G2/G3 present | FAIL | G3 ABSENT in container AND reverted in worktree (pyramider.py md5 == ce06d41). G1/G2 ABSENT in container (would be present if deploy ran, since live_engine.py in worktree matches 33d6138) |
| 8 | H1/H2 present | FAIL | ABSENT in container (ce06d41). Worktree kelly_sizer.py + ml_signal.py match 33d6138 — but deploy did not proceed |
| 9 | CAP/HALT present | FAIL | ABSENT in container (ce06d41). Only older `_max_notional = portfolio_value * 0.05` per-position cap present, NOT the bb5cbb5 circuit breaker |
| 10 | CAP/HALT disabled in paper | N/A (code not live) | `ORGANISM_MAX_NOTIONAL` and `ORGANISM_MAX_DAILY_LOSS` not set in .env or container env. Would default to 0 via `_env_float` fallback IF deploy happened |
| 11 | H5 present | FAIL | ABSENT in container. Worktree settings.py matches 33d6138 — but deploy did not proceed |
| 12 | alert wiring present | FAIL | alerting.py exists in container (identical md5 pre/post), but the 4 send_alert() call sites from 33d6138 are NOT in the container. SLACK_WEBHOOK_URL is also UNSET |
| 13 | Full Patch F protections preserved | PARTIAL (in container ce06d41) | Patch F protections pre-date ce06d41 and remain in the running container. Not re-verified under 33d6138 |
| 14 | force-save succeeded | FAIL | NOT CALLED — deploy did not proceed |
| 15 | manifest sync correct | PASS | manifest.gen=115, learning_state.gen=115; trades=370/370; pnl=-619.75/-619.75; sharpe=3.4363/3.4363. Synced |
| 16 | no blocker before next paper session | CONDITIONAL | Paper-mode session tomorrow will proceed with ce06d41 code (unchanged). No blocker for continuing under the CURRENT (pre-deploy) stack. DEPLOY 2 itself is blocked |

**VERDICT: HARD STOP** — multiple preflight failures; deploy did not proceed.
