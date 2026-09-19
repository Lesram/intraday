# Risk Blockers Register

| ID | Title | Sev | Status | Category | Next action |
|---|---|---|---|---|---|
| EVO-300 | Evolution freeze exits at trade 300 | **P2** | IMMINENT (7 trades away) | algorithm | Review evolved_params.json NOW |
| G1 | Exit-level restore at DEBUG | P2 | OFFLINE READY | mechanical | Deploy with next batch |
| G2 | Cooldown on exit failure | P2 | OFFLINE READY | mechanical | Deploy with next batch |
| G3 | NaN pyramid guard | P2 | OFFLINE READY | mechanical | Deploy with next batch |
| H1 | Production risk-budget dead | P2 | KNOWN | algorithm | Code before real money |
| H2 | Feature drift crash | P2 | KNOWN | structural | Code before real money |
| H5 | Settings API bypass | P3 | KNOWN | ops | Fix before real money |
| CAP | Per-trade notional cap | P2 | NOT CODED | risk | Scope after G1/G2/G3 |
| HALT | Daily max-loss halt | P2 | NOT CODED | risk | Scope after G1/G2/G3 |
| DEAD | Exploration dead code | P3 | KNOWN | architecture | Delete when convenient |
| RUNNER | runner.py loaded unused | P3 | KNOWN | architecture | Remove from lifespan |
| NIGHTLY | Nightly scheduler disabled | P3 | KNOWN | architecture | Evaluate after real-money prep |
| Exp1A | Chop min-hold gate | — | LIVE, KEEP | experiment | Continue |
| Exp2 | PSQ/SH chop suppression | — | LIVE, HELPING | experiment | Continue |
| Exp3 | Confidence instrumentation | — | LIVE, PRODUCING DATA | experiment | Analyze |
| Exp4 | Trailing-stop giveback | P3 | OFFLINE | experiment | Queued |
