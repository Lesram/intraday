# Track DDD v11 — Dependency Posture (NEW LENS)

**Date:** 2026-05-02
**Branch:** `rc-1.5-curated` @ `3778344`
**Working dir:** `/Users/marselkei/VS/intra`
**Mode:** read-only

## Method recap

| Check | Tool | Result |
|---|---|---|
| Python CVEs (OSV) | `./venv/bin/pip-audit -r requirements.txt --strict --vulnerability-service=osv` | 1 known vuln |
| Python CVEs (PyPI) | `./venv/bin/pip-audit -r requirements.txt --strict` | 0 known vulns |
| Pin discipline | grep `requirements.txt` | 51 floating (`>=`), 0 pinned (`==`), out of 92 lines |
| Docker base | grep `^FROM` Dockerfile* | `python:3.12-slim` (no patch tag) in both Dockerfile + Dockerfile.production |
| Frontend audit | `cd frontend && npm audit --json` | 20 vulns: 0 critical / 13 high / 7 moderate / 0 low |
| Outdated Python | `./venv/bin/pip list --outdated` | ~70 packages behind; none > 1 major behind |
| Installed Python pkgs | `./venv/bin/pip list \| wc -l` | 202 installed |
| Direct git/URL deps | grep `^https://\|^git+` requirements*.txt | none (clean) |
| Dependabot/Renovate | `ls .github/dependabot.yml renovate.json` | **absent** |
| pip-licenses | `./venv/bin/pip-licenses` | not installed (skip) |

---

## Findings

### F1 — HIGH: Transitive `ecdsa` CVE-2024-23342 via `python-jose`

`pip-audit` against the **OSV** vulnerability service flagged:

```
Name   Version   ID              Fix Versions
-----  -------   --------------  ------------
ecdsa  0.19.2    CVE-2024-23342  (no fix available)
```

Confirmed transitive root: `requirements.txt` line `python-jose[cryptography]>=3.3.0`. `pip show python-jose` reports `Requires: ecdsa, pyasn1, rsa`. CVE-2024-23342 is the well-known Minerva timing-attack on the pure-Python `ecdsa` library; the maintainers have stated they will not fix (the lib is not constant-time by design). PyPI's vulnerability service does **not** flag it (so `pip-audit --strict` without `--vulnerability-service=osv` returns "No known vulnerabilities found" — V8 AA2's earlier finding is technically reproducible only against the PyPI service).

**Why this is a real exposure here:** `python-jose` is used for JWT/auth signing (the `[cryptography]` extra suggests intent to use the cryptography backend, but `ecdsa` is still pulled in as a hard requirement). If any code path actually instantiates an EC algorithm (e.g. `ES256`, `ES384`) through `python-jose`, signing operations are timing-attack-exposed.

**Recommendation:** migrate from `python-jose` to `pyjwt[crypto]` (already pinned PyJWT 2.11 is installed) or to `joserfc`. Both eliminate the `ecdsa` dependency. Audit the codebase for `from jose import` / `python_jose` usage and switch. If migration is not appetizing, restrict JWT algorithms to RSA/HMAC only and document the risk acceptance.

**Severity:** HIGH (cryptographic / known unpatched CVE in production dep tree).

---

### F2 — HIGH: Frontend has 13 high-severity npm vulns including direct `axios` and `vite`

`npm audit` summary: 20 vulnerabilities — 13 high / 7 moderate / 0 critical / 0 low.

Direct (non-transitive) advisories in the frontend `package.json`:

| Package | Declared range | Severity | Issue |
|---|---|---|---|
| `axios` | `^1.12.2` | HIGH | GHSA-43fc-jf86-j433 (DoS via `__proto__` in mergeConfig, CVSS 7.5); GHSA-3p68-rc4w-qgx5 (NO_PROXY → SSRF); GHSA-fvcv-3m26-pcqx (Cloud metadata exfil) — fix in `1.15.0`. |
| `vite` | `^7.1.7` | HIGH | range 7.0.0 - 7.3.1 affected, fix available. |
| `mermaid` | `^11.12.3` | MODERATE | dompurify chain. |

Other high transitive: chevrotain, langium, lodash-es, minimatch, picomatch, rollup, socket.io-parser, flatted. All have `fixAvailable: true`.

`npm audit fix` (or controlled bumps to `axios@^1.15` and `vite@^7.4`) should clear most of these. Axios in particular is a direct, prod-runtime dependency used by the frontend dashboard for backend API calls — SSRF / DoS in the auth/control plane has direct impact.

**Severity:** HIGH (production frontend, direct deps, all fixes available).

---

### F3 — MEDIUM: Zero pinned versions — every requirement is floating (`>=`)

Of 92 lines in `requirements.txt`, **51 are `>=` floats and 0 are `==` pins**. Critical packages all float:

```
fastapi>=0.100.0          # currently 0.129.0 installed; latest 0.136.1
sqlalchemy>=2.0.0         # currently 2.0.46
alpaca-py>=0.8.0          # currently 0.43.2 — that is a 35-minor jump from the floor
bcrypt>=4.0.0             # currently 4.2.1; latest 5.0.0 (major drift)
python-jose[cryptography]>=3.3.0
```

Consequences:

- **Reproducibility broken**: a Docker build today and a Docker build next month from the same source SHA can resolve to materially different transitive trees. Combined with the `python:3.12-slim` (unpinned patch — see F4) base image, the runtime is non-deterministic.
- **Silent vulnerability acquisition**: a future transitive update could introduce a CVE without any code-on-disk change.
- **Diff-friction during incident response**: rolling back to "the version that worked" is impossible without a `pip freeze` lockfile.

The `MEMORY.md` "Deploy gate" already calls out that code-on-disk ≠ deployed-to-container; floating pins make that drift worse because even rebuilding the same SHA can change behavior.

**Recommendation:** generate `requirements.lock` (or migrate to `uv` / `pip-tools` / `poetry`) and pin every transitive in CI-built images. Keep `requirements.txt` as the high-level intent file with `>=` if desired, but build images from the lock.

**Severity:** MEDIUM (latent / process risk, not an active CVE — but amplifies F1, F2, F4).

---

### F4 — MEDIUM: Docker base `python:3.12-slim` has no patch tag, no Dependabot/Renovate config

```
Dockerfile:            FROM python:3.12-slim AS builder  / runtime
Dockerfile.production: FROM python:3.12-slim AS builder  / production
```

`python:3.12-slim` is a moving tag — Docker Hub re-tags it as new patch releases ship. Two builds on different days can pull different Python patch versions and different Debian base layers, including different system OpenSSL / libc patch levels. Combined with F3 this means the production paper-trading container is end-to-end non-reproducible.

Additionally:

- No `.github/dependabot.yml` exists.
- No `renovate.json` (root or `.github/`) exists.

So there is **no automated mechanism** to surface upstream CVE bumps for either Python or npm packages. The current posture is "audit when an external lens is run" (i.e., this V11 audit) which is exactly how F1 and F2 accumulated unnoticed.

**Recommendation (lowest cost, highest leverage):**
1. Pin Docker base to a digest: `FROM python:3.12.7-slim-bookworm@sha256:...` in both Dockerfiles.
2. Add `.github/dependabot.yml` with `pip` (weekly) + `npm` (weekly) + `docker` (weekly) ecosystems, security updates only at first to keep noise low.
3. Re-run `pip-audit` and `npm audit` in CI (the existing `.github/workflows/pr-verify.yml` is the natural home).

**Severity:** MEDIUM (process gap; combined with F3 it explains how F1/F2 exist undetected).

---

## Inventory snapshots

### Python — outdated, > 1 minor behind (selected)
```
alpaca-py     0.43.2 -> 0.43.4
bcrypt        4.2.1  -> 5.0.0   (major)
cryptography  46.0.5 -> 47.0.0  (major)
fastapi       0.129.0 -> 0.136.1
keras         3.13.2 -> 3.14.0
prawcore      2.4.0  -> 3.0.2   (major)
protobuf      6.33.5 -> 7.34.1  (major)
peewee        3.19.0 -> 4.0.5   (major)
sqlalchemy    2.0.46 -> 2.0.49
starlette     0.52.1 -> 1.0.0   (major; coupled with fastapi)
tensorflow    2.20.0 -> 2.21.0
torch         2.10.0 -> 2.11.0
transformers  5.2.0  -> 5.7.0
wrapt         1.17.3 -> 2.1.2   (major)
```
None are >1 major behind; bcrypt / cryptography / starlette / protobuf / peewee / wrapt are exactly 1 major behind.

### Python supply-chain surface
- 202 packages installed.
- 0 direct git+ / https URL requirements (clean).

### Frontend npm direct vulns
- `axios ^1.12.2` (HIGH x3 advisories)
- `vite ^7.1.7` (HIGH)
- `mermaid ^11.12.3` (MODERATE)

---

## Recommended pins / actions (priority order)

1. **Resolve `ecdsa` exposure** — migrate `python-jose` → `pyjwt[crypto]` (or accept risk + restrict JWT algs to non-EC). Removes F1.
2. **Bump frontend** — `axios@^1.15`, `vite@^7.4`, run `npm audit fix`. Clears most of F2.
3. **Add Dependabot config** — `.github/dependabot.yml` for pip + npm + docker. Closes F4 process gap.
4. **Lock Python deps** — `pip freeze > requirements.lock`, build Docker images from the lock. Closes F3.
5. **Pin Docker base** — replace `python:3.12-slim` with a digest-pinned tag in both Dockerfiles.

## Total findings: 4 (within the 1–4 quality bar).
