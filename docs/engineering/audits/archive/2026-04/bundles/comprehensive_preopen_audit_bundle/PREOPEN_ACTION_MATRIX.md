# Pre-Open Action Matrix

## A. SAFE TO SHIP BEFORE MONDAY OPEN

**Nothing.** No P0/P1 blockers found. The platform is mechanically clean, brain is durable, and the Exp1A observation must remain uncontaminated.

## B. PREPARE OFFLINE, DO NOT SHIP BEFORE MONDAY

| Item | Status | Expected value | Risk | Next step |
|---|---|---|---|---|
| Exp2: suppress PSQ/SH in chop | Committed at `d79cae0` | +$25-30/4d | Very low | Deploy after Exp1A observation |
| Exp3 prep: confidence side-by-side logging | Committed at `ce06d41` | Diagnostic (enables Exp3B) | Zero (read-only) | Deploy stacked with Exp2 |
| Observation tooling | Committed at `6754223` | Operational (automated reports) | Zero (standalone script) | Use Monday post-close |

## C. OBSERVE FIRST, DECIDE LATER

| Item | Depends on | Decision criteria |
|---|---|---|
| Deploy Exp2 | Exp1A 3-5 session results | If Exp1A succeeds OR fails, Exp2 deploys next |
| Exp3B: revert to learning-mode confidence in chop | Exp3 instrumentation data | If confidence_bt_only would have outperformed confidence_live |
| Exp1B: widen CUT_FULL to -2.5R | Exp1A observation | Only if Exp1A shows min-hold is insufficient |

## D. BACKLOG / LATER

| Item | Why later | Effort |
|---|---|---|
| `transfer_knowledge.json` gap in force_save_brain | Cosmetic, non-blocking | Small |
| Log rotation / historical error cleanup | Noise, not functional | Small |
| Alert channel wiring (Slack/email for diagnostics) | Operational, not urgent | Medium |
| Opening-range block widening (30→60 min) | Low incremental value after Exp1A | Small |
| PREFLIGHT 2 warnings investigation | Investigate what they are | Tiny |
| Automated wipe-window monitoring | May be unnecessary after Patch F | Small |
