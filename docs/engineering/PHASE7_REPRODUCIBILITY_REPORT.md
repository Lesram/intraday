# Phase 7.5 Reproducibility And Dependency Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
HEAD reviewed: `73c0ce30ac8e0cbbefa00b6793989b092eb6bb5a`

## Executive Summary

P7.5 found that the paper runtime can be rebuilt from a clean Docker path today,
but the build is not fully reproducible in the strict sense. The Dockerfile uses
the pinned `requirements.lock` file for runtime Python dependencies, which is
good. The base image tag, apt package inputs, CI dependency path, and build
provenance workflow still allow drift.

The highest-risk finding is the dependency split: `requirements.lock` is exact
and rebuildable, but currently has known vulnerabilities; `requirements.txt`
audits clean today only because every requirement is floating. CI mostly installs
`requirements.txt`, while Docker installs `requirements.lock`, so CI and runtime
can silently test different dependency graphs.

No live trading behavior changed during this P7.5 slice. The running paper
container remains healthy on the current pushed commit.

## Current State

| Surface | Evidence | Status |
|---------|----------|--------|
| Docker runtime dependency install | `Dockerfile` installs `pip install -r requirements.lock`. | Reproducible Python runtime packages. |
| Docker base image | `FROM python:3.12-slim` in builder and runtime stages. Current local digest: `python@sha256:ccc7089399c8bb65dd1fb3ed6d55efa538a3f5e7fca3f5988ac3b5b87e593bf0`. | Floating tag; future rebuilds may change base OS/Python patch. |
| OS packages | `apt-get update && apt-get install` for build/runtime packages. | Floating Debian package set. |
| Requirements spec | `requirements.txt`: 57 entries, 57 floating specs. | Not reproducible. |
| Runtime lock | `requirements.lock`: 173 exact pins, 0 floating specs. | Reproducible but security-stale. |
| Dev requirements | `requirements-dev.txt`: 33 unique entries, 37 floating lines, 4 duplicate package declarations. | Not reproducible. |
| CI install path | CI and PR workflows install `requirements.txt`; Docker installs `requirements.lock`. | CI/runtime dependency drift risk. |
| Compose config | `docker compose -f docker-compose.paper.yml config --quiet` passes. Full config resolves local secrets, so it must not be pasted into reports unredacted. | Valid but sensitive. |
| Live container provenance | `GIT_SHA=73c0ce30ac8e0cbbefa00b6793989b092eb6bb5a`, `IMAGE_SHA` same, `BUILD_TIME=unknown`. | Source SHA good; build time missing on current manual deploy. |

## Fresh Rebuild Evidence

No-cache smoke build:

```bash
docker build --no-cache --target runtime -t intra-api:p75-repro-smoke-73c0ce3 .
```

Result: PASS. The image built successfully without cache and without replacing
the running paper container.

Smoke image:

| Field | Value |
|-------|-------|
| Tag | `intra-api:p75-repro-smoke-73c0ce3` |
| Image id | `sha256:a3f1ab6527f0a396c68c0d73eea4bec8ee6e5180fcbdf294cfe2a8c7a2ada2df` |
| Size | 1,227,338,207 bytes |
| Python | 3.12.13 |
| `pip freeze` count | 174 |
| `pip freeze` hash | `77e2c91cb451786bc20a83bc2a24f09563d6eb604dbcd36bf574434fdf58627d` |

Provenance-smoke build:

```bash
VCS_REF=$(git rev-parse HEAD)
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker build --target runtime \
  --build-arg VCS_REF="$VCS_REF" \
  --build-arg BUILD_DATE="$BUILD_DATE" \
  -t intra-api:p75-provenance-smoke-73c0ce3 .
```

Result: PASS. OCI labels correctly stamped revision and created time when build
args were set before invoking `docker build`.

## Dependency Audit

`pip-audit -r requirements.lock --progress-spinner off`:

- FAIL: 29 known vulnerabilities across 14 packages.
- Affected packages include `aiohttp`, `requests`, `black`, `cryptography`,
  `curl-cffi`, `ecdsa`, `pillow`, `pyasn1`, `pygments`, `pyjwt`, `pytest`,
  `python-dotenv`, `python-multipart`, and `werkzeug`.

`pip-audit -r requirements.txt --progress-spinner off`:

- PASS: no known vulnerabilities found.
- Interpretation: this is not proof the runtime is safe. It shows that floating
  specs resolve to newer versions today, while the exact runtime lock remains
  stale.

## Risks

| Severity | Risk | Why It Matters | Recommendation |
|----------|------|----------------|----------------|
| High | CI/runtime dependency drift | CI tests floating `requirements.txt`; Docker runs locked `requirements.lock`. A green CI run may not test the deployed dependency graph. | Make PR and CI install the lock for runtime tests, or regenerate the lock from a reviewed constraints workflow and test that exact lock. |
| High | Vulnerable exact runtime lock | Reproducibility is currently preserving stale vulnerable versions. | Run a dedicated dependency-remediation PR: regenerate lock, run security scan, full organism/replay suites, artifact pack, and container rebuild. |
| Medium | Floating base image tag | `python:3.12-slim` can move across Python patch/base OS changes. | Pin base image by digest or record accepted digest in a checked report with an explicit update cadence. |
| Medium | Floating apt packages | Debian packages can change between rebuilds even when Python deps are locked. | Consider snapshot-based apt sources or accept as best-effort with a documented rebuild cadence. |
| Medium | Missing `BUILD_TIME` in current live container | Current manual rebuild set SHA but not build time. | Prefer `scripts/deploy/rebuild_paper.sh` or always export both `VCS_REF` and `BUILD_DATE`. |
| Medium | Compose config resolves secrets | `docker compose config` expands local secrets. | Treat generated compose config as sensitive; only record redacted summaries in artifacts. |
| Low | Dev requirements are floating and duplicated | Developer and CI tool versions can drift. | Split runtime/dev locks or generate a dev lock after runtime lock remediation. |

## What Is Reproducible Today

- Runtime Python dependency versions inside Docker are reproducible from
  `requirements.lock`.
- The app image can be built from scratch today on this Mac/Docker environment.
- The image can expose a correct source SHA and build time when build args are
  supplied correctly.
- The running container reports the current source SHA and remains healthy.

## What Is Only Best-Effort Today

- Base OS and Python patch lineage, because `python:3.12-slim` is a moving tag.
- Debian package versions, because `apt-get update` pulls latest repository
  state.
- CI parity with runtime, because CI uses `requirements.txt` and Docker uses
  `requirements.lock`.
- Security freshness of the runtime dependency graph, because the exact lock has
  known vulnerabilities.

## Recommendation

Do not change trading logic during dependency remediation. The next P7.5 action
should be a contained dependency-parity PR:

1. Decide whether CI runtime jobs must install `requirements.lock`.
2. Regenerate `requirements.lock` from reviewed runtime inputs.
3. Run `pip-audit -r requirements.lock`.
4. Run the full organism/replay/artifact gates.
5. Rebuild the paper container with both `VCS_REF` and `BUILD_DATE`.
6. Verify `/healthz`, deploy parity, runtime snapshot, and strategy health.
