#!/usr/bin/env python3
"""Check the built login page in an isolated, unauthenticated local browser.

Requires frontend dependencies, cached agent-browser@0.38.1 and its Chromium
(or AGENT_BROWSER_EXECUTABLE_PATH). Does not install dependencies or sign in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "http://127.0.0.1:5197"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'none'; "
    "form-action 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'"
)
DOM_CHECK = """(() => {
  const visible = e => !!e && e.getClientRects().length > 0 &&
    getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
  const user = document.querySelector('input[aria-label="Username or email"]');
  const password = document.querySelector('input[aria-label="Password"][type="password"]');
  const submit = [...document.querySelectorAll('button[type="submit"]')]
    .find(e => e.innerText.trim() === 'Sign In');
  const root = document.querySelector('#root');
  return {
    login_url: location.origin === 'http://127.0.0.1:5197' && location.pathname === '/login',
    username_visible: visible(user), password_visible: visible(password),
    signin_visible: visible(submit) && !submit.disabled,
    fields_empty: !!user && !!password && user.value === '' && password.value === '',
    recovery_visible: !!root && root.innerText.includes('Password recovery is currently unavailable.'),
    nonblank: visible(root) && root.innerText.trim().length > 50,
    no_error_overlay: !document.querySelector('vite-error-overlay') &&
      !document.body.innerText.includes('Something went wrong'),
    transport_violations: window.__previewSmokeViolations || []
  };
})()"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    deadline = started + 150
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    dist = args.dist_dir.resolve()
    report: dict = {"status": "failed", "url": ORIGIN + "/login", "browser_version": "0.38.1"}
    # An allowlist prevents inherited browser profiles, auth, plugins and proxies.
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "PLAYWRIGHT_BROWSERS_PATH")
        if key in os.environ
    }
    env["AGENT_BROWSER_DEFAULT_TIMEOUT"] = "15000"
    session = "preview-" + uuid.uuid4().hex[:12]
    preview = None
    browser_started = False
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def command(argv: list[str], timeout: float = 25) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("smoke check exceeded its150-second work deadline")
        result = subprocess.run(
            argv,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=min(timeout, remaining),
            check=False,
        )
        if result.returncode:
            # Avoid recording subprocess output that could contain unexpected page data.
            raise RuntimeError(f"command failed: {Path(argv[0]).name} (exit{result.returncode})")
        return result.stdout

    try:
        if not (dist / "index.html").is_file():
            raise RuntimeError("production dist/index.html is missing; build frontend first")
        report["index_sha256"] = hashlib.sha256((dist / "index.html").read_bytes()).hexdigest()
        manifest = {
            str(path.relative_to(dist)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(dist.rglob("*"))
            if path.is_file()
        }
        report["dist_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest()
        report["checkout_sha"] = command(["git", "rev-parse", "HEAD"]).strip()
        report["checkout_source_dirty"] = bool(
            command(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "frontend",
                    "scripts/ci/check_frontend_preview.py",
                ]
            ).strip()
        )
        report["build_provenance"] = (
            "dist bytes hashed; checkout identity alone does not attest build origin"
        )
        report["checker_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        version = command(["npx", "--no-install", "agent-browser@0.38.1", "--version"]).strip()
        if version != "agent-browser 0.38.1":
            raise RuntimeError("unexpected agent-browser version")
        with tempfile.TemporaryDirectory(prefix="intra-preview-smoke-") as scratch:
            tmp = Path(scratch)
            config = tmp / "vite.config.mjs"
            config.write_text(
                "export default "
                + json.dumps(
                    {
                        "build": {"outDir": str(dist)},
                        "server": {"proxy": {}},
                        "preview": {
                            "host": "127.0.0.1",
                            "port": 5197,
                            "strictPort": True,
                            "proxy": {},
                            "headers": {"Content-Security-Policy": CSP, "X-Intra-Smoke": session},
                        },
                    }
                )
                + ";\n"
            )
            browser_config = tmp / "browser.json"
            browser_config.write_text("{}\n")
            init = tmp / "init.js"
            init.write_text(
                "window.__previewSmokeViolations = [];\n"
                "addEventListener('securitypolicyviolation', e => "
                "window.__previewSmokeViolations.push(e.effectiveDirective));\n"
            )
            browser = [
                "npx",
                "--no-install",
                "agent-browser@0.38.1",
                "--config",
                str(browser_config),
                "--session",
                session,
                "--namespace",
                session,
                "--allowed-domains",
                "127.0.0.1",
                "--idle-timeout",
                "60s",
                "--json",
            ]
            executable = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
            if executable:
                browser += ["--executable-path", executable]

            def browse(*items: str) -> dict:
                response = json.loads(command([*browser, *items]))
                if not isinstance(response, dict) or response.get("success") is not True:
                    raise RuntimeError(f"browser command failed: {items[0]}")
                data = response.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError(f"unexpected browser response: {items[0]}")
                return data

            try:
                with (out / "preview.log").open("w") as log:
                    preview = subprocess.Popen(
                        [
                            "node",
                            str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                            "preview",
                            "--config",
                            str(config),
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "5197",
                            "--strictPort",
                        ],
                        cwd=ROOT / "frontend",
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    ready_until = min(deadline, time.monotonic() + 15)
                    while True:
                        if preview.poll() is not None:
                            raise RuntimeError("owned preview exited before becoming ready")
                        try:
                            with local_http.open(ORIGIN + "/login", timeout=1) as response:
                                if (
                                    response.headers.get("Content-Security-Policy") == CSP
                                    and response.headers.get("X-Intra-Smoke") == session
                                    and hashlib.sha256(response.read()).hexdigest()
                                    == report["index_sha256"]
                                    and preview.poll() is None
                                ):
                                    break
                        except (OSError, urllib.error.URLError):
                            pass
                        if time.monotonic() >= ready_until:
                            raise RuntimeError("owned preview did not become ready")
                        time.sleep(0.1)
                    browser_started = True
                    browse("--init-script", str(init), "open", ORIGIN + "/login")
                    browse("wait", "--load", "networkidle")
                    # React/lazy route effects must settle before inspecting the actual form.
                    checks = browse("eval", DOM_CHECK).get("result")
                    errors = browse("errors").get("errors")
                    if not isinstance(errors, list):
                        raise RuntimeError("browser page-error response has unexpected schema")
                    browse("screenshot", str(out / "login.png"))
                    report["checks"] = checks
                    report["page_error_count"] = len(errors)
                    # Error type only: never persist page messages, URLs, request bodies or auth data.
                    report["page_error_types"] = [
                        "TypeError" if "TypeError" in str(item) else "JavaScriptError"
                        for item in errors
                    ]
                    expected = {
                        "login_url",
                        "username_visible",
                        "password_visible",
                        "signin_visible",
                        "fields_empty",
                        "recovery_visible",
                        "nonblank",
                        "no_error_overlay",
                    }
                    if not isinstance(checks, dict) or not all(
                        checks.get(key) is True for key in expected
                    ):
                        raise RuntimeError("production login DOM contract failed")
                    if errors or checks.get("transport_violations"):
                        raise RuntimeError("page errors or prohibited transport attempts detected")
                    if preview.poll() is not None:
                        raise RuntimeError("owned preview exited during browser verification")
                    report["status"] = "passed"
            finally:
                try:
                    if browser_started:
                        closed = subprocess.run(
                            [*browser, "close"],
                            cwd=ROOT,
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=10,
                            check=False,
                        )
                        report["browser_closed"] = (
                            closed.returncode == 0
                            and json.loads(closed.stdout).get("success") is True
                        )
                        if not report["browser_closed"]:
                            report["status"] = "failed"
                except (OSError, ValueError, subprocess.SubprocessError):
                    report["browser_closed"] = False
                    report["status"] = "failed"
                finally:
                    if preview is not None:
                        if preview.poll() is None:
                            os.killpg(preview.pid, signal.SIGTERM)
                            try:
                                preview.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                os.killpg(preview.pid, signal.SIGKILL)
                                preview.wait(timeout=3)
                        report["preview_stopped"] = preview.poll() is not None
                    if browser_started and report.get("browser_closed") is not True:
                        report["status"] = "failed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["failure"] = str(exc)[:240]
        report["status"] = "failed"
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":

    def interrupted(_signum: int, _frame: object) -> None:
        raise RuntimeError("smoke check interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "frontend/dist")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/frontend_preview")
    raise SystemExit(run(parser.parse_args()))
