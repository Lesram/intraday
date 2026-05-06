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
