"""Compare Optuna holdout metrics vs API backtest output.

This script:
- Loads an Optuna best-run JSON config from configs/
- Creates a Strategy row in the DB with those params (including costs)
- Runs BacktestService over the holdout window
- Prints headline metrics next to the Optuna log's HOLDOUT PERFORMANCE section

Usage (PowerShell):
  python scripts/compare_optuna_holdout_api.py

Notes:
- Requires DATABASE_URL and Alpaca credentials (unless USE_MOCK_DATA=1).
- Requires DB schema migrated (alembic upgrade head).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path


CONFIG_PATH = Path("configs/optuna_best_harder_holdout2025.json")

# Allow running as a script from repo root or elsewhere
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parse_optuna_holdout_from_log(log_path: Path) -> dict[str, float | int | str]:
    if not log_path.exists():
        return {"error": f"log not found: {log_path}"}

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = lines[-400:]

    # Prefer parsing within the HOLDOUT PERFORMANCE section.
    start_idx = None
    for i, line in enumerate(tail):
        if "HOLDOUT PERFORMANCE" in line:
            start_idx = i
            break

    relevant = tail[start_idx:] if start_idx is not None else tail
    joined = "\n".join(relevant)

    def _m(pattern: str) -> str | None:
        match = re.search(pattern, joined)
        return match.group(1).strip() if match else None

    out: dict[str, float | int | str] = {}
    out["total_return_pct"] = float(_m(r"Total Return:\s*([+\-]?[0-9.]+)%") or "nan")
    out["cagr_pct"] = float(_m(r"CAGR:\s*([+\-]?[0-9.]+)%") or "nan")
    out["sharpe"] = float(_m(r"Sharpe:\s*([+\-]?[0-9.]+)") or "nan")
    out["max_dd_pct"] = float(_m(r"Max DD:\s*([+\-]?[0-9.]+)%") or "nan")
    trades = _m(r"Trades:\s*(\d+)")
    if trades is not None:
        out["trades"] = int(trades)
    turnover = _m(r"Turnover:\s*([+\-]?[0-9.]+)x")
    if turnover is not None:
        out["turnover_x"] = float(turnover)
    avg_exp = _m(r"Avg exposure:\s*([+\-]?[0-9.]+)x")
    if avg_exp is not None:
        out["avg_exposure_x"] = float(avg_exp)

    return out


async def main() -> None:
    # Ensure .env is loaded for DATABASE_URL and Alpaca keys
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    symbols = payload["symbols"]
    holdout = payload["holdout"]
    costs = payload.get("costs") or {}
    params = payload.get("params") or {}
    env = payload.get("env") or {}

    start_date = date.fromisoformat(holdout["start"])
    end_date = date.fromisoformat(holdout["end"])

    # Compose strategy parameters the same way the import endpoint does
    strategy_parameters = dict(params)
    strategy_parameters.setdefault("_origin", "optuna")
    strategy_parameters.setdefault("_origin_run_id", CONFIG_PATH.stem)
    strategy_parameters.setdefault("_origin_source", payload.get("source_log"))
    if "slippage_bps" in costs:
        strategy_parameters.setdefault("slippage_bps", float(costs["slippage_bps"]))
    if "commission_per_trade" in costs:
        strategy_parameters.setdefault("commission_per_trade", float(costs["commission_per_trade"]))

    allow_leverage = env.get("OPT_ALLOW_LEVERAGE")
    if isinstance(allow_leverage, str):
        allow_leverage = allow_leverage.strip().lower() in {"1", "true", "yes", "y", "on"}
    if allow_leverage:
        strategy_parameters.setdefault("allow_leverage", True)
        strategy_parameters.setdefault("use_optuna_leverage", True)

    # Basic sanity checks
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Error: DATABASE_URL is not set (ensure .env exists or export DATABASE_URL)")

    alpaca_key = os.getenv("ALPACA_API_KEY_ID")
    alpaca_secret = os.getenv("ALPACA_API_SECRET_KEY")
    use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() in ("true", "1", "yes")
    if not use_mock_data and (not alpaca_key or not alpaca_secret):
        raise SystemExit(
            "Error: Alpaca credentials missing (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY). "
            "Either set them in .env or run with USE_MOCK_DATA=1 (won't match Optuna)."
        )

    from backend.infra.db import init_db
    from backend.infra.schemas import Strategy
    from backend.services.backtest_service import BacktestService

    engine, sessionmaker = init_db(database_url)

    strategy_id = uuid.uuid4()
    strategy_name = f"optuna_holdout_check_{strategy_id.hex[:8]}"

    async with sessionmaker() as session:
        # Create strategy row (to satisfy backtests FK)
        strategy = Strategy(
            id=strategy_id,
            name=strategy_name,
            strategy_type="technical_analysis",
            description="Temp strategy for Optuna holdout parity check",
            status="inactive",
            symbols=symbols,
            parameters=strategy_parameters,
        )
        session.add(strategy)
        await session.commit()

        service = BacktestService(session)

        # Match API route behavior (deterministic UUID derived from username)
        demo_user_uuid = str(uuid.uuid5(uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8'), "demo"))
        result = await service.run_backtest(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=10_000.0,
            parameters=None,
            user_id=demo_user_uuid,
        )

    await engine.dispose()

    optuna_log = Path(payload.get("source_log", "")) if payload.get("source_log") else None
    optuna_metrics = _parse_optuna_holdout_from_log(optuna_log) if optuna_log else {"error": "no source_log"}

    print("=== Optuna holdout (from log tail) ===")
    print(json.dumps(optuna_metrics, indent=2))

    print("\n=== API backtest (BacktestService) ===")
    api_metrics = {
        "total_return_pct": result.metrics.total_return,
        "annualized_return_pct": result.metrics.annualized_return,
        "sharpe": result.metrics.sharpe_ratio,
        "max_drawdown": result.metrics.max_drawdown,
        "total_trades": result.metrics.total_trades,
        "trade_log_len": len(result.trade_log),
        "total_commission": result.metrics.total_commission,
        "origin": result.origin,
    }
    print(json.dumps(api_metrics, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
