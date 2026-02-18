"""
Optimization run API routes.

Provides access to best optimization configs stored in /configs and
allows creating strategies from those runs.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.services.strategy_service import StrategyService
from backend.api.routes.strategy import transform_strategy_response


router = APIRouter(prefix="/optimizations", tags=["Optimizations"])


class OptimizationRunSummary(BaseModel):
    id: str
    name: str
    created_at: str
    source_log: str | None = None
    symbols: list[str] = Field(default_factory=list)
    range: dict[str, Any] | None = None
    holdout: dict[str, Any] | None = None
    env: dict[str, Any] | None = None
    costs: dict[str, Any] | None = None
    strategy_type: str
    parameters: dict[str, Any]
    origin: str


class OptimizationStrategyCreate(BaseModel):
    name: str | None = None
    description: str | None = None
    strategy_type: str | None = None
    symbols: list[str] | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _configs_dir() -> Path:
    return _repo_root() / "configs"


def _normalize_run(file_path: Path, payload: dict[str, Any]) -> OptimizationRunSummary:
    params = payload.get("params") or payload.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}

    created_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
    source_log = payload.get("source_log")
    if isinstance(source_log, str):
        source_log = source_log.replace("\\", "/")

    inferred_origin = "optuna" if "optuna" in file_path.name.lower() or source_log else "backend"

    inferred = payload.get("strategy_type") or payload.get("strategyType")
    if inferred:
        strategy_type = str(inferred)
    else:
        meta_keys = {"w_ensemble", "w_momentum", "w_meanrev", "w_statarb", "decision_threshold"}
        if any(k in params for k in meta_keys):
            strategy_type = "optuna_meta"
        else:
            strategy_type = "technical_analysis" if "rsi_buy" in params or "sma_fast" in params else "hybrid"

    env = payload.get("env")
    if not isinstance(env, dict):
        env = None

    costs = payload.get("costs")
    if not isinstance(costs, dict):
        costs = None

    return OptimizationRunSummary(
        id=file_path.stem,
        name=payload.get("name", file_path.stem),
        created_at=created_at,
        source_log=source_log,
        symbols=payload.get("symbols", []) if isinstance(payload.get("symbols", []), list) else [],
        range=payload.get("range"),
        holdout=payload.get("holdout"),
        env=env,
        costs=costs,
        strategy_type=strategy_type,
        parameters=params,
        origin=inferred_origin,
    )


def _load_run_by_id(run_id: str) -> OptimizationRunSummary:
    configs_dir = _configs_dir()
    if not configs_dir.exists():
        raise HTTPException(status_code=404, detail="Configs directory not found")

    for path in configs_dir.glob("*.json"):
        if path.stem != run_id:
            continue
        try:
            payload = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read config: {exc}")

        try:
            import json

            data = json.loads(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in config: {exc}")

        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Optimization config is not a JSON object")

        return _normalize_run(path, data)

    raise HTTPException(status_code=404, detail=f"Optimization run '{run_id}' not found")


@router.get("", response_model=list[OptimizationRunSummary])
async def list_optimization_runs(
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> list[OptimizationRunSummary]:
    configs_dir = _configs_dir()
    if not configs_dir.exists():
        return []

    runs: list[OptimizationRunSummary] = []
    for path in configs_dir.glob("*.json"):
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(data, dict):
            continue
        if "params" not in data and "parameters" not in data:
            continue

        runs.append(_normalize_run(path, data))

    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


@router.get("/{run_id}", response_model=OptimizationRunSummary)
async def get_optimization_run(
    run_id: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> OptimizationRunSummary:
    return _load_run_by_id(run_id)


@router.post("/{run_id}/strategy", response_model=dict[str, Any], status_code=201)
async def create_strategy_from_optimization(
    run_id: str,
    payload: OptimizationStrategyCreate,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, Any]:
    run = _load_run_by_id(run_id)

    parameters = dict(run.parameters)
    parameters.setdefault("_origin", run.origin)
    parameters.setdefault("_origin_run_id", run.id)
    if run.source_log:
        parameters.setdefault("_origin_source", run.source_log)

    # Preserve optimization cost assumptions for parity in UI backtests.
    # These are stored alongside params in the created Strategy record.
    slippage_bps = None
    commission_per_trade = None

    if isinstance(run.costs, dict):
        slippage_bps = run.costs.get("slippage_bps")
        commission_per_trade = run.costs.get("commission_per_trade")

    if (slippage_bps is None or commission_per_trade is None) and isinstance(run.env, dict):
        if slippage_bps is None:
            slippage_bps = run.env.get("OPT_FIXED_SLIPPAGE_BPS")
        if commission_per_trade is None:
            commission_per_trade = run.env.get("OPT_FIXED_COMMISSION_PER_TRADE")

    try:
        if slippage_bps is not None:
            parameters.setdefault("slippage_bps", float(slippage_bps))
    except (TypeError, ValueError):
        pass

    try:
        if commission_per_trade is not None:
            parameters.setdefault("commission_per_trade", float(commission_per_trade))
    except (TypeError, ValueError):
        pass

    if isinstance(run.env, dict):
        allow_leverage = run.env.get("OPT_ALLOW_LEVERAGE")
        if isinstance(allow_leverage, str):
            allow_leverage = allow_leverage.strip().lower() in {"1", "true", "yes", "y", "on"}
        if allow_leverage:
            parameters.setdefault("allow_leverage", True)
            parameters.setdefault("use_optuna_leverage", True)

        market_buffer_side = run.env.get("OPT_MARKET_BUFFER_SIDE")
        if isinstance(market_buffer_side, str) and market_buffer_side.strip():
            parameters.setdefault("opt_market_buffer_side", market_buffer_side.strip().lower())

    # For Optuna-origin runs, enable feature toggles when corresponding params exist.
    if run.origin == "optuna":
        if "position_size_pct" in parameters:
            parameters.setdefault("use_optuna_position_size", True)
        if "max_positions" in parameters:
            parameters.setdefault("use_optuna_max_positions", True)
        if "min_position_dollars" in parameters:
            parameters.setdefault("use_optuna_min_position_dollars", True)

    name = payload.name or f"{run.name} (imported)"
    description = payload.description or (
        f"Imported from optimization run '{run.name}'"
    )

    inferred_strategy_type = payload.strategy_type or run.strategy_type
    if inferred_strategy_type is None and run.origin == "optuna":
        meta_keys = {"w_ensemble", "w_momentum", "w_meanrev", "w_statarb", "decision_threshold"}
        if any(k in parameters for k in meta_keys):
            inferred_strategy_type = "optuna_meta"

    if inferred_strategy_type is None:
        inferred_strategy_type = "technical_analysis"

    strategy_data = {
        "name": name,
        "description": description,
        "strategy_type": inferred_strategy_type,
        "symbols": payload.symbols or run.symbols,
        "parameters": parameters,
    }

    service = StrategyService(session, current_user.username)
    created = await service.create_strategy(strategy_data)

    return transform_strategy_response(created)
