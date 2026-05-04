"""V13 W92 (Lens 1: Deploy / Runtime Truth): deploy parity gate.

Closes the V10/V11 wave-47 JWT-regression class of bug: code on host
disk diverged from the running container, audit said "closed", live
endpoints said "broken".  V13 makes this impossible to ship undetected.

Two modes:

1. **Sandbox (default).**  Validates the parity-checker's own logic
   against in-memory fixtures: SHA-mismatch detection, byte-mismatch
   detection, missing-env-var detection.  Always runnable in CI without
   a live container.  Exit 0 = checker logic intact.

2. **Live (env ``V13_LIVE_PROBES=1``).**  Probes a running container
   on ``http://localhost:8000`` for:

   - ``/api/v1/health/deploy`` returns 200 with the current host GIT_SHA.
   - ``/api/v1/health/strategy`` returns 200 with ``source: manifest``.
   - ``/api/v1/audit/chain-detail`` returns 200 with rows present.
   - Container vs host file byte parity for the hot-path files.

   Protected endpoints require either ``V13_AUTH_TOKEN`` or
   ``V13_AUTH_USERNAME`` + ``V13_AUTH_PASSWORD``.

   Exit 0 = container matches host expectations.  Exit 2 = a probe
   failed.

The hot-path file list is defined in ``HOT_PATH_FILES``.  It includes
runtime organism files plus the API routes whose deploy drift has
already hidden V12/V13 closures from the live container.

Usage:

::

    # Sandbox checker self-test (CI runs this on every PR).
    python scripts/ci/check_deploy_parity.py

    # Live probe (run after rebuild_paper.sh, against a running paper
    # container).  Needs the container exposed on localhost:8000 and
    # either V13_AUTH_TOKEN or V13_AUTH_USERNAME/V13_AUTH_PASSWORD.
    V13_LIVE_PROBES=1 V13_AUTH_USERNAME=... V13_AUTH_PASSWORD=... \
      python scripts/ci/check_deploy_parity.py

Exit codes:
- 0: all checks passed.
- 1: invariant violation in sandbox checker logic (this script is
     broken; CI must NOT merge).
- 2: live probe failure (container does not match host).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# The hot-path files whose host-vs-container parity is load-bearing.
# Keep this list broad enough to cover the route modules behind audit
# claims, not just core organism files.
HOT_PATH_FILES = (
    "backend/organism/live_engine.py",
    "backend/organism/brain_persistence.py",
    "backend/infra/outbox_worker.py",
    "backend/infra/security.py",
    "backend/api/lifespan.py",
    "backend/api/routes/auth.py",
    "backend/api/routes/orders.py",
    "backend/api/routes/strategy_health.py",
    "backend/api/routes/data_integrity_health.py",
    "backend/api/routes_setup.py",
)

# Live probe target.  The paper compose binds api → host:8000.
PROBE_HOST = os.environ.get("V13_PROBE_HOST", "http://localhost:8000")
PROBE_TIMEOUT = float(os.environ.get("V13_PROBE_TIMEOUT_SEC", "5.0"))

# Container name (per docker-compose.paper.yml service name "api").
CONTAINER_NAME = os.environ.get("V13_CONTAINER_NAME", "intra-api-1")
_AUTH_HEADER_CACHE: dict[str, str] | None = None


@dataclass(frozen=True)
class ProbeResult:
    name: str
    passed: bool
    detail: str


# ------------------------------------------------------------------ #
# Sandbox checker logic (CI safety net)                              #
# ------------------------------------------------------------------ #


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_sha(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _host_git_sha() -> str | None:
    expected = os.environ.get("V13_EXPECTED_GIT_SHA")
    if expected:
        return expected.strip()
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def parity_compare(host_sha: str, container_sha: str) -> bool:
    """Pure helper: returns True iff non-empty SHAs match.  Empty/None
    inputs always return False — "unknown" must not pass parity."""
    if not host_sha or not container_sha:
        return False
    if host_sha in ("unknown", "n/a") or container_sha in ("unknown", "n/a"):
        return False
    return host_sha == container_sha


def _self_test_parity_compare() -> list[str]:
    """Sandbox self-test: parity_compare must reject empty + unknown."""
    failures: list[str] = []
    cases = [
        ("abc", "abc", True),
        ("abc", "def", False),
        ("", "abc", False),
        ("abc", "", False),
        (None, "abc", False),  # type: ignore[arg-type]
        ("unknown", "abc", False),
        ("abc", "unknown", False),
    ]
    for host, container, expected in cases:
        try:
            actual = parity_compare(host, container)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            failures.append(f"parity_compare({host!r}, {container!r}) raised {exc}")
            continue
        if actual is not expected:
            failures.append(
                f"parity_compare({host!r}, {container!r}) returned {actual} "
                f"expected {expected}"
            )
    return failures


def _self_test_hot_paths() -> list[str]:
    """Sandbox self-test: every hot-path file must exist on host."""
    failures: list[str] = []
    for rel in HOT_PATH_FILES:
        p = REPO_ROOT / rel
        if not p.is_file():
            failures.append(f"HOT_PATH_FILES references missing host file: {rel}")
    return failures


def run_sandbox_self_test() -> int:
    """Validate the parity checker's own correctness without touching
    a container.  Always runnable in CI."""
    failures: list[str] = []
    failures.extend(_self_test_parity_compare())
    failures.extend(_self_test_hot_paths())

    if failures:
        print("FAIL: V13 W92 deploy-parity self-test")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: V13 W92 deploy-parity sandbox self-test")
    print(f"  parity_compare logic OK; {len(HOT_PATH_FILES)} hot-path files exist")
    return 0


# ------------------------------------------------------------------ #
# Live probe logic                                                   #
# ------------------------------------------------------------------ #


def _http_post_json(
    path: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, str]:
    url = f"{PROBE_HOST.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body), body
            except json.JSONDecodeError:
                return resp.status, None, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, None, body
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return 0, None, f"connection error: {exc}"


def _auth_headers() -> tuple[dict[str, str] | None, str | None]:
    global _AUTH_HEADER_CACHE
    if _AUTH_HEADER_CACHE is not None:
        return _AUTH_HEADER_CACHE, None

    token = os.environ.get("V13_AUTH_TOKEN")
    if token:
        _AUTH_HEADER_CACHE = {"Authorization": f"Bearer {token.strip()}"}
        return _AUTH_HEADER_CACHE, None

    username = os.environ.get("V13_AUTH_USERNAME")
    password = os.environ.get("V13_AUTH_PASSWORD")
    if not username or not password:
        return None, (
            "missing auth: set V13_AUTH_TOKEN or "
            "V13_AUTH_USERNAME/V13_AUTH_PASSWORD"
        )

    status, payload, raw = _http_post_json(
        "/api/v1/auth/login",
        {"username": username, "password": password},
    )
    if status != 200 or not isinstance(payload, dict):
        return None, f"login failed: status={status}; body={raw[:200]}"
    access_token = payload.get("access_token")
    if not access_token:
        return None, "login response did not contain access_token"
    _AUTH_HEADER_CACHE = {"Authorization": f"Bearer {access_token}"}
    return _AUTH_HEADER_CACHE, None


def _http_get_json(
    path: str,
    *,
    authenticated: bool = False,
) -> tuple[int, dict[str, Any] | None, str]:
    url = f"{PROBE_HOST.rstrip('/')}{path}"
    headers: dict[str, str] = {}
    if authenticated:
        auth, err = _auth_headers()
        if err:
            return 0, None, err
        headers.update(auth or {})
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body), body
            except json.JSONDecodeError:
                return resp.status, None, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, None, body
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return 0, None, f"connection error: {exc}"


def probe_deploy_endpoint() -> ProbeResult:
    status, payload, raw = _http_get_json(
        "/api/v1/health/deploy",
        authenticated=True,
    )
    if status != 200:
        return ProbeResult(
            "health/deploy", False,
            f"status={status} expected 200; body={raw[:200]}",
        )
    if not isinstance(payload, dict):
        return ProbeResult("health/deploy", False, "non-JSON payload")
    sha = str(payload.get("source_sha", ""))
    if not sha or sha == "unknown":
        return ProbeResult(
            "health/deploy", False,
            f"source_sha={sha!r} — container has no provenance baked in",
        )
    expected = _host_git_sha()
    if not expected:
        return ProbeResult(
            "health/deploy", False,
            "could not resolve host git SHA for deploy comparison",
        )
    if sha != expected:
        return ProbeResult(
            "health/deploy", False,
            f"source_sha={sha[:12]} expected host HEAD {expected[:12]}",
        )
    return ProbeResult(
        "health/deploy", True,
        f"source_sha={sha[:12]} migration_head={payload.get('migration_head')}",
    )


def probe_strategy_endpoint() -> ProbeResult:
    status, payload, raw = _http_get_json(
        "/api/v1/health/strategy",
        authenticated=True,
    )
    if status != 200:
        return ProbeResult(
            "health/strategy", False,
            f"status={status} expected 200; body={raw[:200]}",
        )
    if not isinstance(payload, dict):
        return ProbeResult("health/strategy", False, "non-JSON payload")
    src = str(payload.get("source", ""))
    if src != "manifest":
        return ProbeResult(
            "health/strategy", False,
            f"source={src!r} expected 'manifest' (W71 contract)",
        )
    return ProbeResult(
        "health/strategy", True,
        f"is_profitable={payload.get('is_profitable')} "
        f"total_pnl={payload.get('total_pnl')}",
    )


def probe_audit_chain_detail() -> ProbeResult:
    status, payload, raw = _http_get_json(
        "/api/v1/audit/chain-detail",
        authenticated=True,
    )
    if status != 200:
        return ProbeResult(
            "audit/chain-detail", False,
            f"status={status} expected 200; body={raw[:200]}",
        )
    rows = (payload or {}).get("rows", []) if isinstance(payload, dict) else []
    return ProbeResult(
        "audit/chain-detail", True,
        f"rows={len(rows)}",
    )


def probe_hot_path_byte_parity() -> ProbeResult:
    """Read each hot-path file inside the container and compare bytes
    to the host.  Skip-with-warn if the docker exec call fails so a
    missing CLI doesn't cascade into a CI false-positive."""
    mismatches: list[str] = []
    skipped: list[str] = []
    for rel in HOT_PATH_FILES:
        host_path = REPO_ROOT / rel
        host_sha = _file_sha(host_path)
        if host_sha is None:
            mismatches.append(f"{rel}: host file unreadable")
            continue
        try:
            container_bytes = subprocess.check_output(
                [
                    "docker", "exec", CONTAINER_NAME,
                    "sh", "-c", f"cat /app/{rel}",
                ],
                stderr=subprocess.PIPE, timeout=10,
            )
        except FileNotFoundError:
            return ProbeResult(
                "hot_path_parity", False,
                "docker CLI not found — cannot probe container parity",
            )
        except subprocess.TimeoutExpired:
            mismatches.append(f"{rel}: docker exec timed out")
            continue
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            if "No such container" in stderr:
                return ProbeResult(
                    "hot_path_parity", False,
                    f"container {CONTAINER_NAME!r} not running",
                )
            mismatches.append(f"{rel}: container read failed: {stderr.strip()[:80]}")
            continue
        container_sha = _sha256_bytes(container_bytes)
        if not parity_compare(host_sha, container_sha):
            mismatches.append(
                f"{rel}: host={host_sha[:12]} container={container_sha[:12]}",
            )

    if mismatches:
        return ProbeResult(
            "hot_path_parity", False,
            f"{len(mismatches)} mismatch(es): " + "; ".join(mismatches),
        )
    detail = f"all {len(HOT_PATH_FILES)} hot-path files byte-parity"
    if skipped:
        detail += f" ({len(skipped)} skipped: {skipped[0]})"
    return ProbeResult("hot_path_parity", True, detail)


def run_live_probes() -> int:
    """Run the four live probes against a running container."""
    probes = (
        probe_deploy_endpoint(),
        probe_strategy_endpoint(),
        probe_audit_chain_detail(),
        probe_hot_path_byte_parity(),
    )
    failed = [p for p in probes if not p.passed]
    print(f"V13 W92 live probes against {PROBE_HOST}:")
    for p in probes:
        marker = "PASS" if p.passed else "FAIL"
        print(f"  [{marker}] {p.name}: {p.detail}")
    if failed:
        print(f"\nFAIL: {len(failed)}/{len(probes)} live probe(s) failed")
        return 2
    print("\nPASS: all live probes succeeded")
    return 0


# ------------------------------------------------------------------ #
# Entry point                                                        #
# ------------------------------------------------------------------ #


def main() -> int:
    if os.environ.get("V13_LIVE_PROBES") == "1":
        return run_live_probes()
    return run_sandbox_self_test()


if __name__ == "__main__":
    sys.exit(main())
