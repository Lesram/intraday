# Pull Request

## Summary

<!-- 1-3 bullets on what this PR does. Focus on WHY, not WHAT (the diff says what). -->

-
-

## Test plan

<!-- Bulleted markdown checklist of TODOs the reviewer can run. -->

- [ ]
- [ ]

---

<!--
═══════════════════════════════════════════════════════════════════════
V6 W / V7 W2 — AUDIT-WAVE PR CHECKLIST

If your commit message starts with `fix(audit-wave...)`, the following
checklist is REQUIRED. CI enforces the non-decorative subset via
scripts/ci/check_wave_markers.py: finding IDs are required, cited grep
commands must be runnable, and V12+ audit-wave ranges are hard-gated.
The grep/count/test-delta fields remain useful reviewer evidence.

The pattern that produced V-T-1, V-T-2, X-4, X-8, U-RF4 across
multiple rounds is incomplete same-class scans on prior fixes.
This checklist is the durable defense.
═══════════════════════════════════════════════════════════════════════
-->

## Audit-wave PR checklist (only required if `fix(audit-wave...)`)

- [ ] **Finding-IDs closed** (e.g. `AA-C-1`, `DD-1`):
- [ ] **Same-class scan command** (paste the exact `grep` you ran):
  ```
  grep -rn '...' backend/
  ```
- [ ] **Same-class scan result count: 0** (assert; if non-zero, list each surviving site and explain why it's excluded)
- [ ] **Behavioral test added** (not just structural — must fail on revert): `tests/test_...`
- [ ] **Source-of-truth marker** added in changed code (e.g. `# V7 AA-C-1 / Wave-23a (date): ...`)
- [ ] **Deploy verified**: container healthy after `docker-compose up -d --force-recreate`; brain coherent (`gen / trades / ml_is_trained` unchanged); paste the PRE→POST diff
