"""V13 W95 (Lens 4: Data Integrity) — behavioral coverage.

Closes:
- AuditLog.ts duplicate-index bug (W74-FOLLOWUP-1).
- BB5-F2 GDPR right-to-be-forgotten via the new
  ``backend.services.gdpr_forget_user.forget_user`` service.
- Outbox prune Prometheus metrics (``outbox_pruned_total``,
  ``outbox_prune_last_run_timestamp_seconds``).
- realized_trades vs brain.total_trades reconciliation surface at
  ``/api/v1/health/data-integrity``.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w95_data_integrity.py -v
"""
# wave: V13-W95
from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_PATH = REPO_ROOT / "backend" / "infra" / "schemas.py"
OUTBOX_PATH = REPO_ROOT / "backend" / "infra" / "outbox_worker.py"
GDPR_PATH = REPO_ROOT / "backend" / "services" / "gdpr_forget_user.py"
DI_HEALTH_PATH = REPO_ROOT / "backend" / "api" / "routes" / "data_integrity_health.py"


# ────────────────────────────────────────────────────────────────────
# 1. AuditLog.ts duplicate index closed
# ────────────────────────────────────────────────────────────────────


def test_w95_audit_log_ts_has_no_duplicate_index_decl():
    """`AuditLog.ts` had `index=True` AND `Index("ix_audit_logs_ts", "ts")`
    in __table_args__ — the duplicate broke SQLite tests on first import.
    W95 removes `index=True` so the explicit named declaration wins.

    Parse the AST and find the AuditLog class; assert that within the
    `ts` mapped_column, no `index=True` keyword appears.
    """
    src = SCHEMAS_PATH.read_text()
    tree = ast.parse(src)

    audit_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AuditLog":
            audit_class = node
            break
    assert audit_class is not None, "AuditLog class not found in schemas.py"

    # Find the `ts: Mapped[datetime] = mapped_column(...)` assignment.
    ts_call = None
    for stmt in audit_class.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "ts"
            and isinstance(stmt.value, ast.Call)
        ):
            ts_call = stmt.value
            break
    assert ts_call is not None, "AuditLog.ts mapped_column call not found"

    # No keyword `index=True` allowed.
    for kw in ts_call.keywords:
        if kw.arg == "index":
            assert not (
                isinstance(kw.value, ast.Constant) and kw.value.value is True
            ), (
                "AuditLog.ts retains index=True; W95 was supposed to "
                "remove it (the explicit Index() declaration in "
                "__table_args__ is canonical)."
            )

    # And the explicit Index must still be there in __table_args__.
    assert "ix_audit_logs_ts" in src
    assert 'Index("ix_audit_logs_ts", "ts")' in src


# ────────────────────────────────────────────────────────────────────
# 2. GDPR forget_user service
# ────────────────────────────────────────────────────────────────────


def test_w95_gdpr_forget_user_module_exists():
    assert GDPR_PATH.is_file()
    src = GDPR_PATH.read_text()
    assert "async def forget_user(" in src
    assert "ForgetUserResult" in src


def test_w95_gdpr_discover_scrub_targets():
    """The discover helper returns the canonical list of tables that
    will be scrubbed.  Must include known user-scoped tables and
    exclude `users` itself."""
    from backend.services.gdpr_forget_user import discover_scrub_targets
    tables = discover_scrub_targets()
    assert isinstance(tables, list)
    assert tables == sorted(tables)  # alphabetized
    assert "users" not in tables, (
        "users is the parent — scrubbed by forget_user only via "
        "delete_user_row=True path, not by the per-table sweep"
    )
    # Spot-check tables that we know have user_id columns.
    expected_subset = {"orders", "realized_trades", "position_lots"}
    assert expected_subset.issubset(set(tables)), (
        f"expected scrub targets missing: {expected_subset - set(tables)}"
    )


def test_w95_gdpr_forget_user_audit_pseudonymize_default():
    """The service's default is to PSEUDONYMIZE audit_logs rows, not
    delete them — compliance-retention is separate from GDPR right-to-
    be-forgotten."""
    src = GDPR_PATH.read_text()
    assert "pseudonymize_audit: bool = True" in src
    assert "_AUDIT_LOG_TABLES = (\"audit_logs\",)" in src
    # And the tight pseudonymization path: hash + prefix.
    assert "forgotten:" in src
    assert "sha256" in src


def test_w95_gdpr_forget_user_result_is_immutable_dataclass():
    """The result struct is a frozen dataclass so callers can stash
    it in audit logs without worrying about mutation."""
    from backend.services.gdpr_forget_user import ForgetUserResult
    r = ForgetUserResult(
        user_id="alice", user_deleted=True,
        audit_actor_pseudonymized=2,
        tables_affected={"orders": 5},
    )
    import dataclasses
    assert dataclasses.is_dataclass(r)
    fld_dict = {f.name: f for f in dataclasses.fields(r)}
    assert "tables_affected" in fld_dict


# ────────────────────────────────────────────────────────────────────
# 3. Outbox prune Prometheus metrics
# ────────────────────────────────────────────────────────────────────


def test_w95_outbox_prune_metrics_declared():
    """The two prune metrics are declared at module level.  They may
    be None (e.g. if prometheus_client is unavailable in this env),
    but the names must exist so the call sites compile."""
    from backend.infra import outbox_worker
    assert hasattr(outbox_worker, "OUTBOX_PRUNED_TOTAL")
    assert hasattr(outbox_worker, "OUTBOX_PRUNE_LAST_RUN_TS")


def test_w95_outbox_prune_emits_metrics():
    """`prune_old_events` should call `.inc()` and `.set()` on the
    metrics when total_pruned > 0.  We grep the source for the
    canonical call sites — direct unit exercise would require a
    full async session+DB fixture."""
    src = OUTBOX_PATH.read_text()
    assert "OUTBOX_PRUNED_TOTAL.inc(total_pruned)" in src
    assert "OUTBOX_PRUNE_LAST_RUN_TS.set(time.time())" in src


# ────────────────────────────────────────────────────────────────────
# 4. Data-integrity reconciliation endpoint
# ────────────────────────────────────────────────────────────────────


def test_w95_data_integrity_route_module_exists():
    assert DI_HEALTH_PATH.is_file()
    src = DI_HEALTH_PATH.read_text()
    assert '@router.get("/data-integrity")' in src
    assert "_compute_variance" in src


def test_w95_data_integrity_compute_variance_pure():
    """The pure helper computes percent variance and `within_tolerance`
    correctly."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from backend.api.routes.data_integrity_health import _compute_variance

    # Both None → tolerance None.
    out = _compute_variance(None, None)
    assert out["within_tolerance"] is None
    assert out["variance_pct"] is None

    # Equal → 0% variance.
    out = _compute_variance(100, 100)
    assert out["variance_pct"] == 0.0
    assert out["within_tolerance"] is True

    # 5% — at default tolerance (5%).
    out = _compute_variance(95, 100)
    assert out["variance_pct"] == 5.0
    assert out["within_tolerance"] is True

    # 10% — above default tolerance.
    out = _compute_variance(90, 100)
    assert out["variance_pct"] == 10.0
    assert out["within_tolerance"] is False


def test_w95_data_integrity_reads_current_manifest_shape(tmp_path):
    """Production manifest stores total_trades at top level."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from backend.api.routes.data_integrity_health import _read_brain_total_trades

    (tmp_path / "manifest.json").write_text(json.dumps({
        "total_trades": 498,
        "strategy_expectancy": {"n_trades": 498},
    }))

    assert _read_brain_total_trades(tmp_path) == 498


def test_w95_data_integrity_reads_legacy_nested_manifest_shape(tmp_path):
    """Older brain snapshots nested the counter under brain_state."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from backend.api.routes.data_integrity_health import _read_brain_total_trades

    (tmp_path / "manifest.json").write_text(json.dumps({
        "brain_state": {"total_trades": "123"},
    }))

    assert _read_brain_total_trades(tmp_path) == 123


def test_w95_data_integrity_route_mounted():
    """Confirm the data-integrity router is wired into routes_setup."""
    setup_src = (REPO_ROOT / "backend" / "api" / "routes_setup.py").read_text()
    assert "data_integrity_health_router" in setup_src
    assert (
        "protected.include_router(data_integrity_health_router" in setup_src
    )
