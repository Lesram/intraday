# Intra engineering control plane

## Role split
- ChatGPT / Codex: architecture, task shaping, review, acceptance
- Claude Code: implementation and local verification
- GitHub Actions: neutral referee
- Optional OpenHands: orchestration layer only

## Loop
1. Create issue
2. Write design / acceptance criteria
3. Claude Code implements on branch
4. Hooks run local safeguards
5. PR opens
6. GitHub Actions run path-based gates
7. Codex / ChatGPT reviews diff + artifacts
8. Merge and deploy to paper
9. Post-close workflow emits artifacts and opens next task if KPIs fail

## Trading-specific gates
Any change touching `backend/organism/` must ship with:
- runtime config snapshot
- replay or scenario artifact
- organism regression suite green
- explicit statement whether live behavior changed

## KPI loop
The post-close audit should compute at minimum:
- total trades
- win rate
- avg win
- avg loss
- payoff ratio
- stop_loss count and PnL
- FTF count and PnL
- horizon_timeout count and PnL
- inverse ETF activity
- realized vs predicted return ratio

If any fail threshold, auto-open a GitHub issue.
