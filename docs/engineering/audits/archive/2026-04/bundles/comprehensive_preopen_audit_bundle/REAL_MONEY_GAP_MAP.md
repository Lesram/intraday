# Real-Money Gap Map

**Current stage**: Stage 0 (paper only)
**Verdict**: NOT READY for real money. Earliest realistic timeline: 4-8 weeks of positive paper edge.

## Gap analysis by category

### 1. Structural / mechanical readiness
| Item | Current | Target | Gap |
|---|---|---|---|
| Brain persistence | Full Patch F deployed, 8 structural prevention classes | Same | ✅ CLOSED |
| Force-save recovery | Working, verified | Same | ✅ CLOSED |
| Manifest sync | Fully synced, read-back invariant active | Same | ✅ CLOSED |
| Container stability | 0 restarts, healthy, auto-reconnect | Same | ✅ CLOSED |
| EOD flatten | Working, verified every session | Same | ✅ CLOSED |

### 2. Paper expectancy / edge quality
| Item | Current | Target | Gap |
|---|---|---|---|
| Expectancy/trade | −$1.92 | >+$0.50 sustained over ≥3 weeks | **LARGE** |
| Win rate | 18.8% | >30% | **LARGE** |
| Sharpe (recent) | Negative | >1.0 annualized | **LARGE** |
| Consecutive positive sessions | 0 | ≥10 | **NOT STARTED** |

**This is the primary blocker.** All other gaps are secondary until the algorithm demonstrates positive edge.

### 3. Drawdown / risk control
| Item | Current | Target | Gap |
|---|---|---|---|
| Per-trade stop | ATR-based adaptive exits | Same | ✅ OK |
| Daily max loss | None (only per-trade stops) | −$500/day auto-halt | MEDIUM |
| Weekly max drawdown | None | −$1500/week auto-halt | MEDIUM |
| Position max loss | None (stops only) | −$200/position auto-close | SMALL |

### 4. Symbol concentration
| Item | Current | Target | Gap |
|---|---|---|---|
| Max single-symbol exposure | 8 positions max (MAX_OPEN_POSITIONS) | Same or tighter | OK |
| Sector concentration | No sector limit | ≤40% one sector | MEDIUM |
| Inverse ETF allocation | Over-allocated in chop (Exp2 addresses) | Regime-gated | IN PROGRESS |

### 5. Operational controls / kill switches
| Item | Current | Target | Gap |
|---|---|---|---|
| Manual halt | `POST /organism/halt` | Same | ✅ OK |
| Force-save | `POST /organism/save?force=true` | Same | ✅ OK |
| Freeze adaptation | `POST /organism/freeze` | Same | ✅ OK |
| Automated drawdown halt | Not implemented | Auto-halt at −N% intraday | MEDIUM |
| Position reconciliation | Every 15 min | Same | ✅ OK |

### 6. Monitoring / alerting
| Item | Current | Target | Gap |
|---|---|---|---|
| Health monitoring | GET endpoints, manual | Automated dashboard + alerts | MEDIUM |
| Diagnostic scheduler | Pre-open + post-close auto | Same + alert channels | SMALL |
| Observation tooling | Script ready, not deployed | Deploy + automate | SMALL |
| Wipe detection | Full Patch F guards | Same | ✅ OK |

### 7. Change-control discipline
| Item | Current | Target | Gap |
|---|---|---|---|
| Staged experiment workflow | Proven (A→F, Exp1A→2→3) | Same | ✅ OK |
| Commit-before-deploy | Enforced | Same | ✅ OK |
| Post-deploy verification | Proven (signature checks) | Same | ✅ OK |
| Rollback plan | Per-commit revert | Same | ✅ OK |

## Staged rollout ladder

### Stage 0: Paper only (CURRENT)
- Goal: prove positive expectancy over ≥3 consecutive weeks
- Criteria to advance: expectancy >+$0.50/trade, win rate >30%, max drawdown <3% equity
- Estimated time: 4-8 weeks from now, depending on experiment outcomes

### Stage 1: Tiny live capital ($5,000)
- Prerequisites: Stage 0 criteria met + daily max-loss auto-halt + monitoring dashboard
- Risk: max $500/week loss (10% of capital)
- Duration: 2-4 weeks
- Criteria to advance: same expectancy metrics hold with real fills/slippage

### Stage 2: Controlled scale-up ($25,000)
- Prerequisites: Stage 1 criteria met + 2+ weeks of positive real-money performance
- Risk: max $2,500/week loss
- Duration: 4-8 weeks
- Criteria to advance: Sharpe >1.0, max intraday drawdown <2%

### Stage 3: Real deployment candidate ($50,000+)
- Prerequisites: Stage 2 criteria met + sector concentration limits + full alerting stack
- This is the point where the system is considered production-grade

## Bottom line

The platform is **mechanically ready** for real money (persistence, controls, change-control). It is **algorithmically NOT ready** — negative expectancy must become positive first. The experiment pipeline (Exp1A → Exp2 → Exp3) is the path to closing that gap. Real-money timeline depends entirely on how quickly the experiments produce positive edge.
