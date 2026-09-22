"""Partition secret-free nightly validation without hiding unavailable integrations.

Loaded explicitly with ``-p scripts.ci.nightly_test_contract``. No external
execution option is provided: that requires a separately provisioned test host
and disposable account, never the installed paper account.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


REPLAY_NODES = frozenset({
    "tests/test_organism_integration_smoke.py::TestMultiTickLifecycleInvariants::test_10_tick_invariants",
    "tests/test_organism_live_engine.py::TestMultiRunRegression::test_brain_persistence_across_runs",
    "tests/test_replay_simulator.py::test_replay_with_crash_data",
    "tests/test_replay_simulator.py::test_replay_daily_timeframe_uses_wider_stops",
    "tests/test_replay_simulator.py::test_replay_no_throttle_blocking",
    "tests/test_v13_w100_live_tick_coverage.py::test_w100_entries_gate_signals_generated_on_uptrend",
    "tests/test_v13_w100_live_tick_coverage.py::test_w100_position_management_loop_produces_exits_on_downturn",
})
EXTERNAL_FIXTURES = frozenset({
    "api_base_url", "http_client", "authenticated_client", "data_client",
    "paper_broker", "alpaca_paper_config", "require_market_open",
})


# These legacy diagnostics perform real API/account/DB operations outside
# real_tests. This is an explicit inventory, not a directory/name-pattern skip.
EXTERNAL_NODES = {
    "tests/test_analytics_api_full.py::test_analytics_api": "Hardcoded application PostgreSQL DSN; diagnostic returns booleans rather than asserting failures",
    "tests/test_analytics_endpoint.py::test_analytics": "Hardcoded application PostgreSQL DSN; diagnostic returns booleans rather than asserting failures",
    "tests/test_api_endpoint_validation.py::test_api_endpoint": "Hardcoded application PostgreSQL DSN; diagnostic returns booleans rather than asserting failures",
    "tests/test_idempotency.py::TestOrderIdempotency::test_different_orders_get_different_ids": "Only TestOrderIdempotency class: requests to installed API and submits orders; database constraint class should remain core",
    "tests/test_idempotency.py::TestOrderIdempotency::test_duplicate_client_order_id_rejected": "Only TestOrderIdempotency class: requests to installed API and submits orders; database constraint class should remain core",
    "tests/test_idempotency.py::TestOrderIdempotency::test_duplicate_idempotency_key_returns_same_order": "Only TestOrderIdempotency class: requests to installed API and submits orders; database constraint class should remain core",
    "tests/test_order_lifecycle.py::TestOrderLifecycle::test_order_idempotency": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::TestOrderLifecycle::test_order_lifecycle_with_paper_trading": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::TestOrderLifecycle::test_order_via_orders_endpoint": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::TestOrderLifecycle::test_order_via_signals_act_endpoint": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::test_order_idempotency": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::test_order_lifecycle_orders": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::test_order_lifecycle_signals_act": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_lifecycle.py::test_paper_trading_integration": "Requests to installed API localhost:8000; order submissions; import-time health and authentication probes",
    "tests/test_order_validation.py::test_validate_order": "Requests to installed API localhost:8000 and live-token fixture; import-time health probe",
    "tests/test_portfolio_api.py::test_portfolio_service": "Concrete Alpaca broker account client and installed portfolio service; no isolated provider fixture",
    "tests/test_position_management.py::test_add_to_position_validation": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_close_position_validation": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_fetch_positions": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_calculations": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_detail_fields": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_fields": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_filtering": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_sorting": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_position_statistics": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_position_management.py::test_real_time_compatibility": "Manual installed-API/position workflow; import-time health probe; positions are not an isolated fixture",
    "tests/test_pretrade_validation.py::test_checks_count": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_cost_estimation": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_insufficient_funds": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_invalid_symbol": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_limit_order": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_valid_market_buy": "Manual installed-API workflow; import-time health probe",
    "tests/test_pretrade_validation.py::test_zero_quantity": "Manual installed-API workflow; import-time health probe",
    "tests/test_trades_api.py::test_trades": "Manual access-token prompt and installed APIlocalhost:8000; currently permanently skipped",
    "tests/test_websocket_integration.py::TestWebSocketBroadcasting::test_broadcast_sequence": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketBroadcasting::test_broadcast_to_multiple_clients": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketBroadcasting::test_broadcast_to_single_user": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketConnection::test_connect_with_invalid_token": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketConnection::test_connect_with_valid_token": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketConnection::test_connect_without_token": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketReconnection::test_reconnect_after_disconnect": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketSubscriptions::test_multiple_subscriptions": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketSubscriptions::test_subscribe_to_portfolio": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server",
    "tests/test_websocket_integration.py::TestWebSocketUserIsolation::test_user_isolation": "Installed websocket API localhost:8000; opt-in flag does not provision isolated server"
}
# Every test in these exact modules is an external diagnostic. Some probe the
# installed API at import time; inspect their declared cases before importing.
PREIMPORT_EXTERNAL_MODULES = frozenset(('tests/test_analytics_api_full.py', 'tests/test_analytics_endpoint.py', 'tests/test_api_endpoint_validation.py', 'tests/test_order_lifecycle.py', 'tests/test_order_validation.py', 'tests/test_portfolio_api.py', 'tests/test_position_management.py', 'tests/test_pretrade_validation.py', 'tests/test_trades_api.py', 'tests/test_websocket_integration.py'))


def _declared_test_nodes(path, relative):
    """Read pytest-shaped definitions without executing module-level probes."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    except (OSError, SyntaxError) as exc:
        raise pytest.UsageError(f"Cannot inspect external test module: {relative}") from exc
    nodes = set()

    def inspect_statements(statements, prefix):
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    nodes.add(prefix + "::" + node.name)
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("Test"):
                    if node.bases:
                        raise pytest.UsageError("External test inventory uses unsupported inheritance: " + relative)
                    inspect_statements(node.body, prefix + "::" + node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    if bound.startswith(("test_", "Test")) or bound == "*":
                        raise pytest.UsageError("External test inventory has imported test definitions: " + relative)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(item, ast.Name) and item.id.startswith(("test_", "Test"))
                       for target in targets for item in ast.walk(target)):
                    raise pytest.UsageError("External test inventory has dynamic test definitions: " + relative)
            elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
                    # Script-only runners are never pytest module definitions.
                    inspect_statements(node.orelse, prefix)
                    continue
                inspect_statements(node.body, prefix)
                inspect_statements(getattr(node, "orelse", []), prefix)
                inspect_statements(getattr(node, "finalbody", []), prefix)
                for handler in getattr(node, "handlers", []):
                    inspect_statements(handler.body, prefix)

    inspect_statements(tree.body, relative)
    return nodes


def pytest_ignore_collect(collection_path, config):
    if not config.getoption("--intra-nightly-lane"):
        return None
    try:
        relative = collection_path.relative_to(config.rootpath).as_posix()
    except ValueError:
        return None
    if relative not in PREIMPORT_EXTERNAL_MODULES:
        return None
    expected = {node for node in EXTERNAL_NODES if node.split("::", 1)[0] == relative}
    if _declared_test_nodes(collection_path, relative) != expected:
        raise pytest.UsageError(
            "External test inventory drift: " + relative
            + "; review new/removed cases before withholding this module"
        )
    ignored = getattr(config, "_intra_nightly_preimport_external", set())
    ignored.update(expected)
    config._intra_nightly_preimport_external = ignored
    return True


def _external_row(nodeid, dependencies, reason=None):
    row = {"nodeid": nodeid, "dependencies": dependencies, "status": "UNAVAILABLE"}
    if reason:
        row["reason"] = reason
    return row


def pytest_addoption(parser):
    group = parser.getgroup("intra nightly")
    group.addoption("--intra-nightly-lane", choices=("core", "replay"))
    group.addoption("--intra-nightly-manifest")


def classify(item):
    if item.nodeid in EXTERNAL_NODES:
        return "external", ["dedicated_external_installation"]
    # The fixture names here belong to real_tests; identically named mocks in
    # other modules remain required. fixturenames includes transitive fixtures.
    if item.nodeid.startswith("tests/real_tests/"):
        dependencies = sorted(EXTERNAL_FIXTURES.intersection(item.fixturenames))
        if dependencies:
            return "external", dependencies
    if item.nodeid in REPLAY_NODES:
        return "replay", []
    return "core", []


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    lane = config.getoption("--intra-nightly-lane")
    if not lane:
        return
    manifest = config.getoption("--intra-nightly-manifest")
    if not manifest:
        raise pytest.UsageError("A nightly lane requires a durable selection manifest")
    found = {item.nodeid for item in items}
    missing = sorted(REPLAY_NODES - found)
    if missing:
        raise pytest.UsageError("Required replay nodes missing: " + ", ".join(missing))
    if lane == "replay" and config.pluginmanager.hasplugin("_cov"):
        raise pytest.UsageError("The replay lane must run without coverage instrumentation")
    selected, deselected = [], []
    external = [
        _external_row(nodeid, ["dedicated_external_installation"], EXTERNAL_NODES[nodeid])
        for nodeid in getattr(config, "_intra_nightly_preimport_external", set())
    ]
    for item in items:
        kind, dependencies = classify(item)
        (selected if kind == lane else deselected).append(item)
        if kind == "external":
            external.append(_external_row(item.nodeid, dependencies, EXTERNAL_NODES.get(item.nodeid)))
    path = Path(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "lane": lane,
        "scope": "isolated software validation; not runtime or broker certification",
        "selected_before_marker_filter": sorted(item.nodeid for item in selected),
        "required_replay_nodes": sorted(REPLAY_NODES),
        "external_verification": "UNAVAILABLE",
        "external_reason": "Dedicated API and disposable broker/data credentials not provisioned",
        "external_modules_withheld_before_import": sorted(
            {node.split("::", 1)[0] for node in getattr(config, "_intra_nightly_preimport_external", set())}
        ),
        "external_tests": sorted(external, key=lambda row: row["nodeid"]),
    }, indent=2) + "\n")
    config._intra_nightly_manifest = path
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_collection_finish(session):
    path = getattr(session.config, "_intra_nightly_manifest", None)
    if path:
        payload = json.loads(path.read_text())
        selected = {item.nodeid for item in session.items}
        payload["selected_after_marker_filter"] = sorted(selected)
        invalid_replay = False
        if payload["lane"] == "replay":
            missing = sorted(REPLAY_NODES - selected)
            unexpected = sorted(selected - REPLAY_NODES)
            invalid_replay = bool(missing or unexpected)
            payload["required_replay_selection"] = {
                "status": "FAIL" if invalid_replay else "PASS",
                "missing_nodes": missing,
                "unexpected_nodes": unexpected,
            }
        # Persist the actual selection and failed validation before refusing the
        # run. -k, -m, or PYTEST_ADDOPTS must not turn required replay green.
        path.write_text(json.dumps(payload, indent=2) + "\n")
        if invalid_replay:
            raise pytest.UsageError(
                "Required replay selection changed after filtering; inspect the selection manifest"
            )


def pytest_terminal_summary(terminalreporter):
    if getattr(terminalreporter.config, "_intra_nightly_manifest", None):
        terminalreporter.write_sep("=", "External integration verification: UNAVAILABLE")
        terminalreporter.write_line("See the selection manifest. A passing lane does not certify the paper runtime.")
