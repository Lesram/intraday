# Phase 7.8 Security And Access-Control Sanity Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`

## Executive Summary

P7.8 found and fixed a real read-side RBAC gap. Before this slice, a valid
default `user` token could read operator-sensitive paper-runtime surfaces:
strategy PnL, deploy provenance, data-integrity drift, system orders, and the
organism brain. Order cancellation and settings access were already blocked,
debug endpoints were absent, and logout blacklist behavior worked.

The fix keeps trading behavior unchanged and tightens only API visibility:
operator/trading health and order visibility now require trader/admin or admin
roles, and all organism endpoints require admin. This is appropriate for a
personal autonomous trading platform where public self-registration should not
create any path to inspect trading state.

## Initial Live Probe

Probe target: paper container at `http://localhost:8000`, before P7.8 code was
deployed.

| Probe | Result |
|-------|--------|
| Admin login and `/api/v1/auth/me` | PASS, `200`. |
| Admin logout blacklist | PASS, token returned `401` after logout. |
| Unauthenticated `/api/v1/settings/organism` | PASS, `401`. |
| Debug endpoints `/test/http-401`, `/api/v1/test/http-401`, `/test/http-500` | PASS, `404`. |
| User-role `/api/v1/settings/organism` | PASS, `403`. |
| User-role `/api/v1/orders/{id}/cancel` | PASS, `403`. |
| User-role `/api/v1/health/strategy` | FAIL, `200`. |
| User-role `/api/v1/health/deploy` | FAIL, `200`. |
| User-role `/api/v1/health/data-integrity` | FAIL, `200`. |
| User-role `/api/v1/orders/` | FAIL, `200`, included system orders. |
| User-role `/api/v1/organism/brain` | FAIL, `200`. |

## Fixes Applied

| Surface | Change | Intended boundary |
|---------|--------|-------------------|
| `GET /api/v1/orders/` | Uses trader/admin dependency instead of generic authentication. | Default user cannot inspect system or trading orders. |
| `GET /api/v1/health/strategy` | Requires trader/admin. | PnL and promotion-relevant expectancy are operator/trader data. |
| `GET /api/v1/health/deploy` | Requires admin. | Build SHA, migration head, and runtime config hash are operator data. |
| `GET /api/v1/health/data-integrity` | Requires admin. | Ledger/brain drift is operator data. |
| `/api/v1/organism/*` | Router-level admin dependency. | Brain, decisions, diagnostics, and controls are admin-only. |

## Verification

Local verification before deploy:

- `pytest -q tests/test_phase7_security_sanity.py tests/test_wave68_fixes.py tests/test_wave50_fixes.py tests/test_v12_strategy_expectancy.py tests/test_v12_w78_deploy_health.py tests/test_v12_w74_data_integrity.py --timeout=30`: `44 passed`.
- Required organism safety/replay bundle: `137 passed`.
- `scripts/ci/verify_findings_ledger.py`: PASS.
- `scripts/ci/forbid_marker_only_critical_high.py`: PASS.
- `scripts/ci/lint_ratchet.py`: PASS, current `3748`, baseline `3801`.
- `scripts/ci/generate_artifacts.py full`: PASS, `8 passed, 0 failed`.

Post-deploy live validation was run against the rebuilt paper container:

```bash
./venv/bin/python scripts/ci/phase7_security_sanity.py \
  --base-url http://localhost:8000 \
  --output artifacts/phase7/security_sanity.json
```

Result: PASS, `19 passed, 0 failed`.

Deployed evidence:

- Container `GIT_SHA`: `498844afa84ff2305410c630cbd3992dcc17d3c5`.
- Admin login, `/me`, settings, strategy health, deploy health, data-integrity,
  and orders all returned `200`.
- Admin logout returned `200`; the same token returned `401 token_revoked`
  afterward.
- Default `user` token could call `/api/v1/auth/me` but was rejected from
  `/api/v1/health/strategy`, `/api/v1/health/deploy`,
  `/api/v1/health/data-integrity`, `/api/v1/orders/`, order cancel, and
  `/api/v1/organism/brain`.
- Public `/api/v1/settings/organism` returned `401`.
- Debug/test endpoints returned `404`.

## Remaining Risks

- Public self-registration still exists. P7.8 makes default users unable to see
  the most sensitive operator surfaces, but Phase 7 close should decide whether
  self-registration belongs in paper/live at all.
- Some other authenticated read surfaces may still be broader than a strict
  single-operator platform needs. P7.8 fixed the high-value paper-runtime
  surfaces first; a later least-privilege pass should review scanner, portfolio,
  chart, and model endpoints.
- This slice changes visibility only. It does not change order submission,
  sizing, exits, strategy ranking, or paper-trading behavior.
