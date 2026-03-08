# Intra engineering control plane

## Role split
- ChatGPT / Codex: architecture, task shaping, review, acceptance
- Claude Code: implementation and local verification
- GitHub Actions: neutral referee
- Optional OpenHands: orchestration layer only

## Mandatory PR workflow
All changes to `backend/`, `tests/`, `docs/architecture/`, config files must go through pull requests. Direct pushes to `main` are prohibited for these paths.

To enforce this in GitHub:
1. Go to Settings > Branches > Add branch protection rule
2. Branch name pattern: `main`
3. Enable: "Require a pull request before merging"
4. Enable: "Require status checks to pass before merging"
5. Required checks: `organism-tests`, `config-tests`, `secret-scan`
6. Enable: "Require conversation resolution before merging"

## Loop
1. Create issue (use templates: `strategy_bug.yml` or `automation_task.yml`)
2. Write design / acceptance criteria
3. Claude Code implements on feature branch
4. Hooks run local safeguards (pre-edit secret guard, post-edit verify, artifact generation)
5. PR opens with full artifact pack
6. GitHub Actions run path-based gates (organism tests, config tests, secret scan)
7. Codex / ChatGPT reviews diff + artifacts
8. Merge and deploy to paper (`docker-compose up -d --build api`)
9. Post-close workflow emits artifacts and auto-opens issue if KPIs breach

## Artifact pack
Every PR and post-close run generates:

| File | Purpose |
|------|---------|
| `artifacts/task_report.json` | SHA, branch, changed files, test results, risks |
| `artifacts/runtime_config_snapshot.json` | All live organism constants |
| `artifacts/changed_files.json` | Categorized changed paths |
| `artifacts/test_summary.json` | Per-suite pass/fail |
| `artifacts/replay_summary.json` | Replay test results |
| `artifacts/grep_assertions.json` | Trading invariant verification |
| `docs/engineering/LIVE_AUDIT_INDEX.md` | Current SHA, changed files, live constants, open risks |

Generate locally: `python scripts/ci/generate_artifacts.py full && python scripts/ci/generate_audit_index.py`

## Trading-specific gates
Any change touching `backend/organism/` must ship with:
- runtime config snapshot
- replay or scenario artifact
- organism regression suite green
- grep assertions passing
- explicit statement whether live behavior changed

## KPI auto-issue loop
The `paper-postclose-audit` workflow runs daily at 22:15 UTC Mon-Fri and automatically opens a GitHub issue labeled `strategy,organism,bug` when:
- Test suites fail
- Replay tests fail
- Trading invariant grep checks fail
- Runtime snapshot generation fails

Future KPI metrics (wired when trade data is available via API):
- total trades, win rate, avg win, avg loss, payoff ratio
- stop_loss / FTF / horizon_timeout counts and PnL
- inverse ETF activity
- realized vs predicted return ratio
