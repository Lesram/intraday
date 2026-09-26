"""Probe only owned, disposable UI/proxy containers against a synthetic API.

This proves HTTP routing, websocket upgrades and upstream replacement recovery;
the stub is NOT the trading API and does not certify authentication or trading.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


PYTHON_IMAGE = "python:3.12-slim@sha256:ccc7089399c8bb65dd1fb3ed6d55efa538a3f5e7fca3f5988ac3b5b87e593bf0"
STUB = r'''
import base64, hashlib, json, struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            key = self.headers['Sec-WebSocket-Key']
            digest = hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', base64.b64encode(digest).decode())
            self.end_headers()
            head = self.rfile.read(2)
            if len(head) != 2: return
            size = head[1] & 127
            if size > 125: return
            mask = self.rfile.read(4)
            body = self.rfile.read(size)
            body = bytes(value ^ mask[i % 4] for i, value in enumerate(body))
            self.wfile.write(bytes([0x81, len(body)]) + body)
            self.wfile.flush()
            self.close_connection = True
            return
        body = json.dumps({'path': self.path, 'authorization': self.headers.get('Authorization'), 'host': self.headers.get('Host')}).encode()
        self.send_response(503 if urlsplit(self.path).path.endswith('/reject') else 200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
'''


def docker(*args: str, timeout: int = 90, merge_output: bool = False) -> str:
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr[-2000:]}")
    return (result.stdout + (result.stderr if merge_output else "")).strip()


def fetch(base: str, path: str):
    request = urllib.request.Request(base + path, headers={"Authorization": "Bearer synthetic-ui-probe"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), dict(response.headers)


def read_exact(stream: socket.socket, count: int) -> bytes:
    result = b""
    while len(result) < count:
        chunk = stream.recv(count - len(result))
        if not chunk:
            raise AssertionError("Unexpected websocket EOF")
        result += chunk
    return result


def websocket_echo(port: int, path: str):
    key = base64.b64encode(uuid.uuid4().bytes).decode()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.settimeout(5)
        connection.sendall((f"GET {path}?token=synthetic-proxy-check HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        headers = b""
        while not headers.endswith(b"\r\n\r\n"):
            headers += read_exact(connection, 1)
            assert len(headers) < 16384
        assert headers.startswith(b"HTTP/1.1 101"), headers
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        assert accept.lower() in headers.lower()
        payload, mask = b"proxy-echo", b"abcd"
        connection.sendall(bytes([0x81, 0x80 | len(payload)]) + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))
        head = read_exact(connection, 2)
        assert head == bytes([0x81, len(payload)])
        assert read_exact(connection, len(payload)) == payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = "intra-ui-probe-" + uuid.uuid4().hex[:12]
    network, ingress, api, ui, holder = (prefix + suffix for suffix in ("-net", "-ingress", "-api", "-ui", "-holder"))
    result = {"scope": "Synthetic HTTP/websocket proxy; no trading startup, credentials or installed services", "image": args.image, "checks": [], "passed": False}
    network_created = False
    ingress_created = False
    created: list[str] = []
    try:
        docker("image", "inspect", args.image)
        docker("pull", PYTHON_IMAGE, timeout=180)
        docker("network", "create", "--internal", network)
        network_created = True
        # Docker does not publish host ports for an internal-only network.
        # Only the credential-free UI joins this disposable ingress bridge;
        # the synthetic API remains internal with no published ports.
        docker("network", "create", ingress)
        ingress_created = True
        with tempfile.TemporaryDirectory(prefix="intra-ui-probe-") as scratch:
            stub = Path(scratch) / "stub.py"
            stub.write_text(STUB)

            def start_api():
                created.append(api)
                docker("run", "-d", "--name", api, "--network", network, "--network-alias", "api", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--mount", f"type=bind,src={stub},dst=/stub.py,readonly", PYTHON_IMAGE, "python", "-B", "/stub.py")

            start_api()
            created.append(ui)
            docker("run", "-d", "--name", ui, "--network", ingress, "-p", "127.0.0.1::8080", "--read-only", "--tmpfs", "/tmp:size=64m,mode=1777", "--user", "101:101", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--memory", "128m", "--cpus", "0.5", args.image)
            docker("network", "connect", network, ui)
            port = int(docker("port", ui, "8080/tcp").rsplit(":", 1)[1])
            base = f"http://127.0.0.1:{port}"
            for attempt in range(50):
                try:
                    if fetch(base, "/ui-health")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError("Frontend did not start")
            assert json.loads(fetch(base, "/ui-health")[1])["scope"] == "frontend"
            index = fetch(base, "/")[1]
            assert b'<div id="root">' in index
            assert fetch(base, "/portfolio")[1] == index
            assert fetch(base, "/assets/does-not-exist.js")[0] == 404
            result["checks"].append("Static health, SPA deep-link refresh and missing-asset refusal")
            status, body, _ = fetch(base, "/api/v1/probe?marker=synthetic")
            payload = json.loads(body)
            assert status == 200 and payload["path"] == "/api/v1/probe?marker=synthetic"
            assert payload["authorization"] == "Bearer synthetic-ui-probe"
            assert payload["host"] == f"127.0.0.1:{port}"
            status, body, _ = fetch(base, "/api/v1/reject")
            assert status == 503 and body != index
            result["checks"].append("API path/query/auth/host forwarding and truthful upstream503")
            for path in ("/api/v1/scanner/ws", "/api/v1/market-data/ws", "/socket.io/"):
                websocket_echo(port, path)
            result["checks"].append("All three websocket routes upgrade and carry a frame")
            old_ip = json.loads(docker("inspect", api))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
            docker("rm", "-f", api)
            created.remove(api)
            assert fetch(base, "/api/v1/probe")[0] in (502, 504)
            # Hold the old address to prove recovery uses a new DNS answer.
            created.append(holder)
            docker("run", "-d", "--name", holder, "--network", network, "--ip", old_ip, "--read-only", "--cap-drop", "ALL", PYTHON_IMAGE, "python", "-c", "import time; time.sleep(90)")
            start_api()
            new_ip = json.loads(docker("inspect", api))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
            assert new_ip != old_ip
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if fetch(base, "/api/v1/probe")[0] == 200:
                    break
                time.sleep(0.25)
            else:
                raise AssertionError("Proxy did not recover after API address replacement")
            result["checks"].append("API disappearance stays unavailable; replacement at a different IP recovers")
            logs = docker("logs", ui, merge_output=True)
            (args.output_dir / "proxy.log").write_text(logs + "\n")
            assert "synthetic-proxy-check" not in logs and "synthetic-ui-probe" not in logs, "Authentication marker leaked to frontend logs"
            result["checks"].append("Access logs omit authentication query and header")
            result["image_id"] = docker("image", "inspect", args.image, "--format", "{{.Id}}")
            result["passed"] = True
    except (AssertionError, RuntimeError, ValueError, KeyError, IndexError,
            OSError, subprocess.SubprocessError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup = []
        for name in reversed(created):
            try:
                docker("rm", "-f", name)
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                cleanup.append(str(error))
        if network_created:
            try:
                docker("network", "rm", network)
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                cleanup.append(str(error))
        if ingress_created:
            try:
                docker("network", "rm", ingress)
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                cleanup.append(str(error))
        result["cleanup_errors"] = cleanup
        result["passed"] = result["passed"] and not cleanup
        (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
