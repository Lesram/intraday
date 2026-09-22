"""Exercise actual pytest collection before any external fixture can run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.ci.nightly_test_contract import REPLAY_NODES


ROOT = Path(__file__).resolve().parents[1]


def prepare(tmp_path):
    modules = {}
    for node in sorted(REPLAY_NODES):
        module, *parts = node.split("::")
        modules.setdefault(module, []).append(parts)
    for module, tests in modules.items():
        path = tmp_path / module
        path.parent.mkdir(parents=True, exist_ok=True)
        text = ""
        for parts in tests:
            if len(parts) == 2:
                text += f"class {parts[0]}:\n    def {parts[1]}(self):\n        assert True\n"
            else:
                text += f"def {parts[0]}():\n    assert True\n"
        path.write_text(text)
    real = tmp_path / "tests/real_tests"
    real.mkdir()
    (real / "test_external.py").write_text('''import pytest
@pytest.fixture
def api_base_url():
    raise AssertionError("External API fixture must never run")
@pytest.fixture
def wrapper(api_base_url):
    return api_base_url
def test_external(wrapper):
    raise AssertionError("External test must never run")
def test_local_database_contract():
    assert True
''')
    (tmp_path / "tests/test_local.py").write_text('''import pytest
@pytest.fixture
def data_client():
    return "mock"
def test_mock_remains_required(data_client):
    assert data_client == "mock"
''')


def run(tmp_path, lane, *extra):
    manifest = tmp_path / "selection.json"
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "TMPDIR"}}
    env.update(PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([
        sys.executable, "-m", "pytest", "tests/", "-q", "-o", "addopts=",
        "-p", "scripts.ci.nightly_test_contract", "--intra-nightly-lane=" + lane,
        "--intra-nightly-manifest=" + str(manifest), *extra,
    ], cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)
    return result, json.loads(manifest.read_text()) if manifest.exists() else None


@pytest.mark.parametrize("lane,expected_count", [("core", 2), ("replay", 7)])
def test_real_collection_partitions_without_running_external_fixtures(tmp_path, lane, expected_count):
    prepare(tmp_path)
    result, manifest = run(tmp_path, lane)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{expected_count} passed" in result.stdout
    assert manifest["external_verification"] == "UNAVAILABLE"
    assert len(manifest["selected_after_marker_filter"]) == expected_count
    assert manifest["external_tests"] == [{
        "nodeid": "tests/real_tests/test_external.py::test_external",
        "dependencies": ["api_base_url"], "status": "UNAVAILABLE",
    }]
    if lane == "core":
        assert "tests/real_tests/test_external.py::test_local_database_contract" in manifest["selected_after_marker_filter"]
        assert "tests/test_local.py::test_mock_remains_required" in manifest["selected_after_marker_filter"]
    else:
        assert set(manifest["selected_after_marker_filter"]) == REPLAY_NODES


def test_missing_required_replay_case_fails_collection(tmp_path):
    prepare(tmp_path)
    (tmp_path / "tests/test_replay_simulator.py").unlink()
    result, manifest = run(tmp_path, "core")
    assert result.returncode != 0
    assert "Required replay nodes missing" in result.stderr
    assert manifest is None


def test_replay_lane_refuses_active_coverage(tmp_path):
    prepare(tmp_path)
    (tmp_path / "tests/conftest.py").write_text('''def pytest_configure(config):
    config.pluginmanager.register(object(), "_cov")
''')
    result, manifest = run(tmp_path, "replay")
    assert result.returncode != 0
    assert "without coverage instrumentation" in result.stderr
    assert manifest is None


def test_required_core_failure_is_fatal(tmp_path):
    prepare(tmp_path)
    with (tmp_path / "tests/test_local.py").open("a") as output:
        output.write("\ndef test_failure():\n    assert False\n")
    result, manifest = run(tmp_path, "core")
    assert result.returncode == 1
    assert "1 failed" in result.stdout
    assert manifest["external_verification"] == "UNAVAILABLE"


def test_external_module_probe_is_never_imported(tmp_path):
    prepare(tmp_path)
    path = tmp_path / "tests/test_order_validation.py"
    path.write_text('''raise AssertionError("Import-time installed API probe must never execute")
def test_validate_order(live_token):
    raise AssertionError("Installed API test must never execute")
''')
    result, manifest = run(tmp_path, "core")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
    assert manifest["external_modules_withheld_before_import"] == ["tests/test_order_validation.py"]
    rows = {row["nodeid"]: row for row in manifest["external_tests"]}
    external = rows["tests/test_order_validation.py::test_validate_order"]
    assert external["status"] == "UNAVAILABLE"
    assert "import-time" in external["reason"]


@pytest.mark.parametrize("change", ["new_case", "removed_case", "syntax_error"])
def test_external_module_inventory_drift_fails_before_import(tmp_path, change):
    prepare(tmp_path)
    source = 'raise AssertionError("Import must not execute")\n'
    if change == "new_case":
        source += "def test_validate_order():\n    pass\ndef test_new_ordinary_unit_case():\n    pass\n"
    elif change == "removed_case":
        source += "def helper():\n    pass\n"
    else:
        source += "this is not valid Python !!!\n"
    (tmp_path / "tests/test_order_validation.py").write_text(source)
    result, manifest = run(tmp_path, "core")
    assert result.returncode != 0
    assert "External test inventory drift" in result.stdout + result.stderr or "Cannot inspect external test module" in result.stdout + result.stderr
    assert manifest is None


def test_partial_external_module_retains_ordinary_database_tests(tmp_path):
    prepare(tmp_path)
    (tmp_path / "tests/test_idempotency.py").write_text('''class TestDatabaseIdempotencyConstraints:
    def test_orders_constraint_exists(self):
        assert True
class TestOrderIdempotency:
    def test_duplicate_idempotency_key_returns_same_order(self):
        raise AssertionError("External order submission must never run")
    def test_duplicate_client_order_id_rejected(self):
        raise AssertionError("External order submission must never run")
    def test_different_orders_get_different_ids(self):
        raise AssertionError("External order submission must never run")
''')
    result, manifest = run(tmp_path, "core")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout
    assert "tests/test_idempotency.py::TestDatabaseIdempotencyConstraints::test_orders_constraint_exists" in manifest["selected_after_marker_filter"]
    assert len(manifest["external_tests"]) == 4
    assert "tests/test_idempotency.py" not in manifest["external_modules_withheld_before_import"]


def test_preimport_inventory_matches_actual_definitions_without_executing_them():
    from scripts.ci.nightly_test_contract import (
        EXTERNAL_NODES, PREIMPORT_EXTERNAL_MODULES, _declared_test_nodes,
    )
    assert len(EXTERNAL_NODES) == 44
    assert len(PREIMPORT_EXTERNAL_MODULES) == 10
    for module in PREIMPORT_EXTERNAL_MODULES:
        expected = {node for node in EXTERNAL_NODES if node.split("::", 1)[0] == module}
        assert _declared_test_nodes(ROOT / module, module) == expected
    assert not any("TestDatabaseIdempotencyConstraints" in node for node in EXTERNAL_NODES)


@pytest.mark.parametrize("extra", [
    "from helpers import test_unregistered_case\n",
    "test_unregistered_case = lambda: None\n",
    "if True:\n    def test_unregistered_case():\n        pass\n",
    "class TestUnregistered(BaseCases):\n    pass\n",
])
def test_unregistered_indirect_cases_cannot_disappear(tmp_path, extra):
    prepare(tmp_path)
    (tmp_path / "tests/test_order_validation.py").write_text(
        "def test_validate_order():\n    pass\n" + extra
    )
    result, manifest = run(tmp_path, "core")
    assert result.returncode != 0
    assert "External test inventory" in result.stdout + result.stderr
    assert manifest is None


@pytest.mark.parametrize("expression,count", [
    ("no_such_replay_case", 0),
    ("test_replay_with_crash_data", 1),
])
def test_filtered_required_replay_fails_with_durable_actual_selection(tmp_path, expression, count):
    prepare(tmp_path)
    result, manifest = run(tmp_path, "replay", "-k", expression)
    assert result.returncode != 0
    assert "Required replay selection changed after filtering" in result.stdout + result.stderr
    assert len(manifest["selected_after_marker_filter"]) == count
    assert manifest["required_replay_selection"]["status"] == "FAIL"
    assert len(manifest["required_replay_selection"]["missing_nodes"]) == 7 - count
    assert manifest["required_replay_selection"]["unexpected_nodes"] == []


def test_core_filtering_is_still_allowed_and_reported(tmp_path):
    prepare(tmp_path)
    result, manifest = run(tmp_path, "core", "-k", "mock_remains_required")
    assert result.returncode == 0, result.stdout + result.stderr
    assert manifest["selected_after_marker_filter"] == [
        "tests/test_local.py::test_mock_remains_required"
    ]
    assert "required_replay_selection" not in manifest
