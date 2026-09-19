# CI Advisory Gates

Generated: 2026-05-04

This document makes the non-blocking CI gates explicit. These gates are
visible in CI, but they are not merge blockers until the legacy backlog is
reduced to a ratchetable baseline.

## mypy strict

Command:

```bash
./venv/bin/python -m mypy --strict backend tests --ignore-missing-imports --show-error-codes
```

Current Phase-1 result: advisory fail.

Observed blocker class:

- Missing generated-test import targets such as `backend.risk.advanced_risk`.
- Duplicate module discovery for `backend/__init__.py` as both `backend` and
  `backend.__init__`.

Promotion rule:

- Introduce a mypy ratchet or package-discovery fix first.
- Make the gate hard only after the committed baseline is stable and new
  violations fail CI.

## pip-audit

Command:

```bash
./venv/bin/python -m pip_audit
```

Current Phase-1 result: advisory fail.

Observed summary:

- 26 known vulnerabilities across 15 packages.
- Notable packages include `aiohttp`, `cryptography`, `curl-cffi`, `ecdsa`,
  `pyjwt`, `python-multipart`, `requests`, and `werkzeug`.

Promotion rule:

- Patch direct dependencies with available fixed versions.
- Replace or isolate the `python-jose` / `ecdsa` chain.
- Make the gate hard when zero Critical/High runtime dependency findings remain
  or when an allowlist file records each accepted residual with owner and expiry.

