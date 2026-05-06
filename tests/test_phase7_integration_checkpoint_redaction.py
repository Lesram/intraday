from scripts.ci import phase7_integration_checkpoint as checkpoint
from scripts.ci.phase7_integration_checkpoint import _redact_sensitive_output


def test_phase7_checkpoint_redacts_compose_env_values() -> None:
    raw = """
    environment:
      ALPACA_API_KEY_ID: PK1234567890
      ALPACA_API_SECRET_KEY: supersecretvalue
      JWT_SECRET_KEY: jwtsecretvalue
      REDIS_URL: redis://:redispass@redis:6379/0
      ORGANISM_LIVE_TIMEFRAME: 1Min
"""

    redacted = _redact_sensitive_output(raw)

    assert "PK1234567890" not in redacted
    assert "supersecretvalue" not in redacted
    assert "jwtsecretvalue" not in redacted
    assert "redispass" not in redacted
    assert "ORGANISM_LIVE_TIMEFRAME: 1Min" in redacted


def test_phase7_checkpoint_redacts_container_inspect_style_values() -> None:
    raw = """
                "ALPACA_API_KEY_ID=PK1234567890",
                "ALPACA_API_SECRET_KEY=supersecretvalue",
                "SECURITY_JWT_SECRET=jwtsecretvalue",
                "GIT_SHA=abcdef",
"""

    redacted = _redact_sensitive_output(raw)

    assert "PK1234567890" not in redacted
    assert "supersecretvalue" not in redacted
    assert "jwtsecretvalue" not in redacted
    assert "GIT_SHA=abcdef" in redacted


def test_phase7_checkpoint_outbox_query_uses_real_table(monkeypatch) -> None:
    captured_sql: list[str] = []

    def fake_psql(sql: str, *, timeout: int = 15) -> dict[str, object]:
        captured_sql.append(sql)
        return {"returncode": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(checkpoint, "_psql", fake_psql)

    db = checkpoint.collect_db()

    assert db["outbox_summary"]["returncode"] == 0
    joined = "\n".join(captured_sql)
    assert "FROM outbox_events" in joined
    assert "FROM outbox;" not in joined


def test_phase7_checkpoint_operator_report_includes_visibility_snapshot() -> None:
    data = {
        "generated_at": "2026-05-06T00:00:00+00:00",
        "repo": {
            "branch": "codex/test",
            "head": "abc123",
        },
        "container": {
            "git_sha": "abc123",
            "build_time": "2026-05-06T00:00:00Z",
            "kill_switches": {
                "ORGANISM_DRAWDOWN_KILL_PCT": "0.2",
                "ORGANISM_MAX_DAILY_LOSS": "1000",
                "ORGANISM_MAX_NOTIONAL": "50000",
            },
        },
        "http": {
            "strategy_health": {
                "payload": {
                    "n_trades": 10,
                    "total_pnl": -1.5,
                    "win_rate": 0.4,
                    "sharpe_ratio_per_trade": -0.1,
                    "is_profitable": False,
                    "source": "manifest",
                },
            },
            "deploy_health": {
                "payload": {
                    "source_sha": "abc123",
                    "build_time": "2026-05-06T00:00:00Z",
                    "migration_head": "20260503_000003",
                    "runtime_config_hash": "cfg123",
                },
            },
            "data_integrity": {
                "payload": {
                    "accounting_status": "warning",
                    "realized_trades": 936,
                    "brain_total_trades": 517,
                },
            },
        },
        "db": {
            "migration_head": {"stdout": "20260503_000003"},
            "open_positions": {"stdout": "0"},
            "positions_by_symbol": {"stdout": ""},
            "orders_by_status": {"stdout": "filled:1430"},
            "outbox_summary": {"stdout": "917|2026-01-01|2026-05-06"},
        },
        "brain_and_evidence": {
            "phase5_candidate_filter_rows": 100,
            "phase6_strategy_evidence_rows": 200,
            "phase6_summary": {
                "joined_outcome_rows": 50,
                "outcome_recommendation": "hold",
            },
            "phase6_policy_actions": [],
        },
    }

    report = checkpoint.build_report(data, [])

    assert "## Operator View Snapshot" in report
    assert "Kill switches" in report
    assert "Open positions" in report
    assert "Orders by status" in report
    assert "Outbox events count/min/max" in report
