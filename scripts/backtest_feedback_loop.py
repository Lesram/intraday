"""Backtest feedback loop (diagnose → propose overlays → re-run).

This script automates the "go back on the backtest" loop:
1) Run a backtest (research or platform engine)
2) Diagnose drawdowns / volatility / loss concentration
3) Propose overlay rules to reduce drawdown risk
4) Re-run with updated overlays for a fixed number of iterations

It does not guarantee improved performance; it surfaces heuristic adjustments
and reports metrics each iteration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.research.optuna_meta_research_engine import (  # noqa: E402
    CostModel,
    ResearchBacktestOutput,
    run_backtest_panel_detailed,
)
from scripts.optuna_meta_strategy_optimizer import (  # noqa: E402
    _platform_holdout_eval,
    fetch_price_panel,
)


@dataclass(frozen=True)
class IterationSummary:
    iteration: int
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    trades: int
    calmar: float
    updates: dict[str, Any]
    notes: list[str]


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Error: Config file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: Invalid JSON in config file: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit("Error: Config JSON must be an object")
    return payload


def _resolve_window(payload: dict[str, Any], start: str | None, end: str | None) -> tuple[str, str]:
    if start and end:
        return start, end

    holdout = payload.get("holdout")
    if isinstance(holdout, dict) and holdout.get("start") and holdout.get("end"):
        return str(holdout["start"]), str(holdout["end"])

    rng = payload.get("range")
    if isinstance(rng, dict) and rng.get("start") and rng.get("end"):
        return str(rng["start"]), str(rng["end"])

    raise SystemExit("Error: Missing backtest window. Provide --start/--end or a config holdout/range.")


def _setup_logging(verbose: bool = False, log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger("feedback_loop")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def _get_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params") or payload.get("parameters") or {}
    if not isinstance(params, dict):
        return {}
    return dict(params)


def _get_symbols(payload: dict[str, Any]) -> list[str]:
    symbols = payload.get("symbols") or []
    if not isinstance(symbols, list):
        return []
    return [str(s) for s in symbols if str(s).strip()]


def _build_costs(payload: dict[str, Any]) -> CostModel:
    costs = payload.get("costs") or {}
    if not isinstance(costs, dict):
        costs = {}
    slippage_bps = float(costs.get("slippage_bps", 0.0) or 0.0)
    commission_per_trade = float(costs.get("commission_per_trade", 0.0) or 0.0)
    return CostModel(slippage_bps=slippage_bps, commission_per_trade=commission_per_trade)


def _equity_series_from_output(out: ResearchBacktestOutput) -> list[float]:
    return [float(v) for _dt, v, _cash, _pos in out.equity_curve]


def _equity_series_from_platform_result(result: Any) -> list[float]:
    series: list[float] = []
    for point in result.equity_curve or []:
        value = point.get("value") if isinstance(point, dict) else getattr(point, "value", None)
        if value is None:
            continue
        series.append(float(value))
    return series


def _daily_returns(equity: list[float]) -> list[float]:
    if len(equity) < 2:
        return []
    arr = np.asarray(equity, dtype=float)
    prev = arr[:-1]
    curr = arr[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.where(prev == 0, 0.0, (curr - prev) / prev)
    return returns.tolist()


def _propose_overlays(
    *,
    metrics: dict[str, float | int],
    daily_returns: list[float],
    max_dd_target_pct: float,
    current_params: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    updates: dict[str, Any] = {}
    notes: list[str] = []

    max_dd_pct = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    worst_day = min(daily_returns) if daily_returns else 0.0
    realized_vol = float(np.std(daily_returns) * np.sqrt(252.0)) if daily_returns else 0.0

    dd_target_dec = max_dd_target_pct / 100.0
    dd_dec = max_dd_pct / 100.0 if max_dd_pct > 0 else 0.0

    # Kill switch when drawdown breaches target.
    if max_dd_pct > max_dd_target_pct:
        kill_dd = min(0.35, max(0.10, dd_dec * 0.8)) if dd_dec > 0 else 0.18
        updates.update(
            {
                "overlay_kill_switch": 1,
                "overlay_kill_dd_pct": round(kill_dd, 4),
                "overlay_kill_cooldown_days": int(current_params.get("overlay_kill_cooldown_days", 10) or 10),
                "overlay_kill_force_exit": 1,
            }
        )
        notes.append("Enabled kill-switch overlay to cap drawdown.")

    # Vol targeting when realized vol spikes.
    if realized_vol >= 0.25:
        target = min(0.25, max(0.12, realized_vol * 0.8))
        updates.update(
            {
                "overlay_vol_enabled": 1,
                "overlay_vol_target": round(target, 4),
                "overlay_vol_window": int(current_params.get("overlay_vol_window", 20) or 20),
                "overlay_vol_min_mult": float(current_params.get("overlay_vol_min_mult", 0.5) or 0.5),
                "overlay_vol_max_mult": float(current_params.get("overlay_vol_max_mult", 1.5) or 1.5),
            }
        )
        notes.append("Enabled volatility targeting to dampen exposure in high-vol regimes.")

    # Gap guard for large daily drops.
    if worst_day <= -0.04:
        updates.update(
            {
                "overlay_gap_enabled": 1,
                "overlay_gap_max_pct": float(current_params.get("overlay_gap_max_pct", 0.04) or 0.04),
            }
        )
        notes.append("Enabled gap guard to avoid outsized overnight moves.")

    # Risk-off stop/TP adjustments for sustained drawdown pressure.
    if max_dd_pct >= max_dd_target_pct * 0.8:
        updates.update(
            {
                "overlay_risk_off_adjust": 1,
                "overlay_risk_off_stop_mult": float(current_params.get("overlay_risk_off_stop_mult", 0.7) or 0.7),
                "overlay_risk_off_take_mult": float(current_params.get("overlay_risk_off_take_mult", 0.8) or 0.8),
            }
        )
        notes.append("Enabled risk-off stop/take multipliers for drawdown control.")

    # If drawdown is already within target, avoid tightening too much.
    if max_dd_pct <= max_dd_target_pct and not updates:
        notes.append("No overlay changes proposed; drawdown already within target.")

    # Ensure we don't loosen a strict existing kill DD.
    if "overlay_kill_dd_pct" in updates and "overlay_kill_dd_pct" in current_params:
        try:
            current_kill = float(current_params.get("overlay_kill_dd_pct") or 0.0)
            updates["overlay_kill_dd_pct"] = min(float(updates["overlay_kill_dd_pct"]), current_kill)
        except Exception:
            pass

    return updates, notes


def _score(metrics: dict[str, float | int]) -> float:
    cagr = float(metrics.get("cagr_pct", 0.0) or 0.0)
    max_dd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    return cagr / max(0.10, max_dd)


def _render_output_payload(
    *,
    engine: str,
    params: dict[str, Any],
    out: ResearchBacktestOutput,
) -> dict[str, Any]:
    trade_log: list[dict[str, Any]] = []
    for ct in out.closed_trades:
        trade_log.append(
            {
                "symbol": ct.symbol,
                "side": "sell",
                "quantity": int(ct.qty),
                "entry_date": str(ct.entry_dt.date()),
                "entry_price": float(ct.entry_price),
                "exit_date": str(ct.exit_dt.date()),
                "exit_price": float(ct.exit_price),
                "pnl": (float(ct.exit_price) - float(ct.entry_price)) * int(ct.qty),
                "pnl_percent": ((float(ct.exit_price) / float(ct.entry_price)) - 1.0) * 100.0
                if ct.entry_price
                else 0.0,
                "duration_days": (ct.exit_dt.date() - ct.entry_dt.date()).days,
                "exit_reason": ct.exit_reason,
                "commission": float(ct.commission),
            }
        )

    equity_curve = [
        {
            "date": str(dt.date()),
            "value": float(value),
            "cash": float(cash),
            "positions_value": float(pos),
        }
        for dt, value, cash, pos in out.equity_curve
    ]

    return {
        "engine": engine,
        "parameters": params,
        "metrics": {
            "total_return": out.metrics.total_return_pct,
            "annualized_return": out.metrics.cagr_pct,
            "sharpe_ratio": out.metrics.sharpe,
            "max_drawdown": out.metrics.max_drawdown_pct,
            "total_trades": out.metrics.trades,
        },
        "equity_curve": equity_curve,
        "trade_log": trade_log,
    }


def _render_platform_output_payload(*, engine: str, params: dict[str, Any], result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")
    else:
        payload = result.dict()
    payload["engine"] = engine
    payload["parameters"] = params
    return payload


def _backtest_metrics_from_output(out: ResearchBacktestOutput) -> dict[str, float | int]:
    return {
        "total_return_pct": float(out.metrics.total_return_pct),
        "cagr_pct": float(out.metrics.cagr_pct),
        "sharpe": float(out.metrics.sharpe),
        "max_drawdown_pct": float(out.metrics.max_drawdown_pct),
        "trades": int(out.metrics.trades),
    }


def _backtest_metrics_from_platform(metrics: Any) -> dict[str, float | int]:
    return {
        "total_return_pct": float(getattr(metrics, "total_return_pct", 0.0) or 0.0),
        "cagr_pct": float(getattr(metrics, "cagr_pct", 0.0) or 0.0),
        "sharpe": float(getattr(metrics, "sharpe", 0.0) or 0.0),
        "max_drawdown_pct": float(getattr(metrics, "max_drawdown_pct", 0.0) or 0.0),
        "trades": int(getattr(metrics, "trades", 0) or 0),
    }


def _run_research_backtest(
    *,
    panel_close,
    panel_open,
    market_close,
    market_open,
    params: dict[str, Any],
    costs: CostModel,
    initial_capital: float,
    execution_mode: str,
    market_buffer_side: str,
    allow_leverage: bool,
) -> ResearchBacktestOutput:
    return run_backtest_panel_detailed(
        panel_close,
        market_close,
        params,
        costs,
        initial_capital,
        panel_open=panel_open,
        market_open=market_open,
        execution_mode=execution_mode,
        market_buffer_side=market_buffer_side,
        allow_leverage=allow_leverage,
    )


def _print_iteration(summary: IterationSummary, logger: logging.Logger) -> None:
    logger.info("=" * 80)
    logger.info("ITERATION %s", summary.iteration)
    logger.info("=" * 80)
    logger.info("Total Return: %+0.2f%%", summary.total_return_pct)
    logger.info("CAGR:         %+0.2f%%", summary.cagr_pct)
    logger.info("Sharpe:       %+0.2f", summary.sharpe)
    logger.info("Max DD:       %.2f%%", summary.max_drawdown_pct)
    logger.info("Calmar:       %+0.3f", summary.calmar)
    logger.info("Trades:       %s", summary.trades)
    if summary.notes:
        logger.info("Notes:")
        for note in summary.notes:
            logger.info("  - %s", note)
    if summary.updates:
        logger.info("Overlay updates:")
        for k, v in summary.updates.items():
            logger.info("  - %s = %s", k, v)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Automated backtest feedback loop")
    parser.add_argument("--config", required=True, help="Path to optimization config JSON")
    parser.add_argument("--start", default=None, help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument(
        "--engine",
        default="research",
        choices=["research", "platform"],
        help="Backtest engine",
    )
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--max-dd", type=float, default=25.0, help="Target max drawdown percent")
    parser.add_argument("--market-symbol", default="SPY")
    parser.add_argument("--execution-mode", default="close", choices=["close", "next_open"])
    parser.add_argument("--market-buffer-side", default=os.getenv("OPT_MARKET_BUFFER_SIDE", "below"))
    parser.add_argument("--allow-leverage", action="store_true")
    parser.add_argument("--outdir", default="reports/feedback_loop")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--log-file", default=None, help="Write logs to file")

    args = parser.parse_args()

    logger = _setup_logging(args.verbose, args.log_file)

    config_path = Path(args.config)
    payload = _load_config(config_path)
    start, end = _resolve_window(payload, args.start, args.end)

    symbols = _get_symbols(payload)
    if not symbols:
        raise SystemExit("Error: No symbols provided in config.")

    params = _get_params(payload)
    costs = _build_costs(payload)

    panel_close = panel_open = market_close = market_open = None
    if args.engine == "research":
        panel_close, panel_open, market_close, market_open = await fetch_price_panel(
            symbols=symbols,
            start=start,
            end=end,
            market_symbol=args.market_symbol,
        )
    else:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass
        if not os.getenv("DATABASE_URL"):
            raise SystemExit("Error: --engine=platform requires DATABASE_URL environment variable")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    current_params = dict(params)
    summaries: list[IterationSummary] = []
    best_score = -1e9
    best_params = dict(current_params)

    for i in range(1, max(1, args.iterations) + 1):
        if args.engine == "platform":
            metrics_obj, platform_result = await _platform_holdout_eval(
                name=str(payload.get("name") or config_path.stem),
                symbols=symbols,
                start_date=date.fromisoformat(start),
                end_date=date.fromisoformat(end),
                parameters=current_params,
                costs=costs,
                initial_capital=float(args.initial_capital),
                return_result=True,
            )
            metrics = _backtest_metrics_from_platform(metrics_obj)
            equity = _equity_series_from_platform_result(platform_result)
            payload_out = _render_platform_output_payload(
                engine="platform",
                params=current_params,
                result=platform_result,
            )
        else:
            out = _run_research_backtest(
                panel_close=panel_close,
                panel_open=panel_open,
                market_close=market_close,
                market_open=market_open,
                params=current_params,
                costs=costs,
                initial_capital=float(args.initial_capital),
                execution_mode=args.execution_mode,
                market_buffer_side=args.market_buffer_side,
                allow_leverage=args.allow_leverage,
            )

            metrics = _backtest_metrics_from_output(out)
            equity = _equity_series_from_output(out)
            payload_out = _render_output_payload(engine="research", params=current_params, out=out)

        daily_returns = _daily_returns(equity)
        updates, notes = _propose_overlays(
            metrics=metrics,
            daily_returns=daily_returns,
            max_dd_target_pct=float(args.max_dd),
            current_params=current_params,
        )

        calmar = metrics["cagr_pct"] / max(0.10, metrics["max_drawdown_pct"])
        summary = IterationSummary(
            iteration=i,
            total_return_pct=float(metrics["total_return_pct"]),
            cagr_pct=float(metrics["cagr_pct"]),
            sharpe=float(metrics["sharpe"]),
            max_drawdown_pct=float(metrics["max_drawdown_pct"]),
            trades=int(metrics["trades"]),
            calmar=float(calmar),
            updates=updates,
            notes=notes,
        )
        summaries.append(summary)
        _print_iteration(summary, logger)
        (outdir / f"iteration_{i:02d}_backtest.json").write_text(
            json.dumps(payload_out, indent=2), encoding="utf-8"
        )

        score = _score(metrics)
        if score > best_score:
            best_score = score
            best_params = dict(current_params)

        if not updates:
            logger.warning("No overlay updates proposed; stopping early.")
            break

        current_params.update(updates)

    logger.info("=" * 80)
    logger.info("BEST PARAM SET (by Calmar)")
    logger.info("=" * 80)
    logger.info("%s", json.dumps(best_params, indent=2))

    (outdir / "best_params.json").write_text(json.dumps(best_params, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
