"""The local UI must not acquire trading credentials or expose remote access."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_operator_ui_is_local_and_has_no_trading_state_or_credentials():
    compose = yaml.safe_load((ROOT / "docker-compose.paper.yml").read_text())
    ui = compose["services"]["frontend"]
    assert ui["ports"] == ["127.0.0.1:5173:8080"]
    assert not ui.get("env_file") and not ui.get("environment")
    assert not ui.get("volumes")
    assert ui["read_only"] is True
    assert ui["user"] not in ("root", "0", "0:0")
    assert ui["cap_drop"] == ["ALL"] and not ui.get("cap_add")
    assert "no-new-privileges:true" in ui["security_opt"]
    assert ui["restart"] == "unless-stopped"
    assert ui["depends_on"]["api"]["condition"] == "service_healthy"


def test_ui_build_context_allows_only_frontend_sources():
    # A separate context allowlist protects against accidentally copying an
    # operator's frontend .env or the backend's credentials/models into images.
    rules = (ROOT / "frontend/Dockerfile.dockerignore").read_text().splitlines()
    assert rules[0] == "**"
    allowed = [line[1:] for line in rules[1:] if line.startswith("!")]
    assert allowed and all(path.startswith("frontend/") for path in allowed)
    assert "frontend/**" not in allowed
    assert not any(".env" in path or "node_modules" in path for path in allowed)
    assert {"frontend/src/**", "frontend/public/**", "frontend/package-lock.json"} <= set(allowed)
