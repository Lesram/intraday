"""Compare Optuna HOLDOUT metrics vs a UI-exported backtest JSON.

Usage (PowerShell):
  python scripts/compare_optuna_vs_ui_backtest.py \
	--ui-json "C:\\Users\\Marsel\\Downloads\\backtest_<id>.json" \
	--rerun-backend

What it does:
- Parses Optuna HOLDOUT PERFORMANCE metrics from the Optuna source log referenced by
  configs/optuna_best_harder_holdout2025.json.
- Loads the UI backtest JSON and prints its headline metrics.
- If --rerun-backend is set, loads the referenced Strategy from the DB and re-runs
  BacktestService for the same window/capital, then compares UI-vs-rerun.

Notes:
- Requires DATABASE_URL when using --rerun-backend.
- UI JSON is expected to be an API backtest payload (same shape as stored BacktestResult).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path


CONFIG_PATH = Path("configs/optuna_best_harder_holdout2025.json")


@dataclass(frozen=True)
class Headline:
	total_return_pct: float
	cagr_pct: float
	sharpe: float
	max_dd_pct: float
	trades: int | None = None


def _parse_optuna_holdout_from_log(log_path: Path) -> Headline:
	text = log_path.read_text(encoding="utf-8", errors="ignore")

	# Prefer parsing within the HOLDOUT PERFORMANCE section.
	start = re.search(r"^=+\s*$\nHOLDOUT PERFORMANCE.*?$\n^=+\s*$", text, flags=re.MULTILINE)
	section = text[start.start() :] if start else text

	def _m(pattern: str) -> str:
		m = re.search(pattern, section)
		if not m:
			raise ValueError(f"Could not parse pattern: {pattern}")
		return m.group(1).strip()

	total_return = float(_m(r"Total Return:\s*([+\-]?[0-9.]+)%"))
	cagr = float(_m(r"CAGR:\s*([+\-]?[0-9.]+)%"))
	sharpe = float(_m(r"Sharpe:\s*([+\-]?[0-9.]+)"))
	max_dd = float(_m(r"Max DD:\s*([+\-]?[0-9.]+)%"))

	trades: int | None
	try:
		trades = int(_m(r"Trades:\s*(\d+)"))
	except Exception:
		trades = None

	return Headline(
		total_return_pct=total_return,
		cagr_pct=cagr,
		sharpe=sharpe,
		max_dd_pct=max_dd,
		trades=trades,
	)


def _headline_from_ui_json(payload: dict) -> Headline:
	metrics = payload.get("metrics") or {}

	# API stores these as percent values (not decimals): e.g. 84.78 means 84.78%
	total_return = float(metrics.get("total_return"))
	cagr = float(metrics.get("annualized_return"))
	sharpe = float(metrics.get("sharpe_ratio"))
	max_dd = float(metrics.get("max_drawdown"))

	trades = metrics.get("total_trades")
	trades_int = int(trades) if trades is not None else None

	return Headline(
		total_return_pct=total_return,
		cagr_pct=cagr,
		sharpe=sharpe,
		max_dd_pct=max_dd,
		trades=trades_int,
	)


def _fmt(h: Headline) -> str:
	trades = "?" if h.trades is None else str(h.trades)
	return (
		f"return={h.total_return_pct:.2f}%  "
		f"cagr={h.cagr_pct:.2f}%  "
		f"sharpe={h.sharpe:.2f}  "
		f"maxDD={h.max_dd_pct:.2f}%  "
		f"trades={trades}"
	)


async def _rerun_backend(ui_payload: dict) -> tuple[Headline, dict]:
	try:
		from dotenv import load_dotenv

		load_dotenv()
	except Exception:
		pass

	database_url = os.getenv("DATABASE_URL")
	if not database_url:
		raise SystemExit("Error: DATABASE_URL is not set (required for --rerun-backend)")

	strategy_id = uuid.UUID(str(ui_payload["strategy_id"]))
	start_date = date.fromisoformat(ui_payload["start_date"])
	end_date = date.fromisoformat(ui_payload["end_date"])
	initial_capital = float(ui_payload.get("initial_capital") or 100000.0)

	from backend.infra.db import init_db
	from backend.infra.schemas import Strategy
	from backend.services.backtest_service import BacktestService

	engine, sessionmaker = init_db(database_url)

	async with sessionmaker() as session:
		strategy = await session.get(Strategy, strategy_id)
		if strategy is None:
			raise SystemExit(f"Error: Strategy not found in DB: {strategy_id}")

		parameters = strategy.parameters or {}
		toggles = {
			"strategy_type": getattr(strategy, "strategy_type", None),
			"allow_leverage": parameters.get("allow_leverage"),
			"use_optuna_leverage": parameters.get("use_optuna_leverage"),
			"max_gross_exposure": parameters.get("max_gross_exposure"),
			"use_optuna_position_size": parameters.get("use_optuna_position_size"),
			"position_size_pct": parameters.get("position_size_pct"),
			"use_optuna_max_positions": parameters.get("use_optuna_max_positions"),
			"max_positions": parameters.get("max_positions"),
			"use_optuna_min_position_dollars": parameters.get("use_optuna_min_position_dollars"),
			"min_position_dollars": parameters.get("min_position_dollars"),
			"opt_market_buffer_side": parameters.get("opt_market_buffer_side"),
			"slippage_bps": parameters.get("slippage_bps"),
			"commission_per_trade": parameters.get("commission_per_trade"),
			"_origin": parameters.get("_origin"),
			"_origin_run_id": parameters.get("_origin_run_id"),
		}

		service = BacktestService(session)
		demo_user_uuid = str(
			uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "demo")
		)

		result = await service.run_backtest(
			strategy=strategy,
			start_date=start_date,
			end_date=end_date,
			initial_capital=initial_capital,
			parameters=None,  # match default API route behavior
			user_id=demo_user_uuid,
		)

	await engine.dispose()

	rerun_headline = Headline(
		total_return_pct=float(result.metrics.total_return),
		cagr_pct=float(result.metrics.annualized_return),
		sharpe=float(result.metrics.sharpe_ratio),
		max_dd_pct=float(result.metrics.max_drawdown),
		trades=int(result.metrics.total_trades) if result.metrics.total_trades is not None else None,
	)

	return rerun_headline, toggles


async def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--ui-json", required=True, help="Path to UI backtest JSON")
	parser.add_argument(
		"--rerun-backend", action="store_true", help="Re-run backend using DB strategy"
	)
	args = parser.parse_args()

	config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
	source_log = Path(config["source_log"])

	optuna_holdout = _parse_optuna_holdout_from_log(source_log)

	ui_payload = json.loads(Path(args.ui_json).read_text(encoding="utf-8"))
	ui_headline = _headline_from_ui_json(ui_payload)

	print("=== Optuna HOLDOUT (from log) ===")
	print(_fmt(optuna_holdout))

	print("\n=== UI Backtest JSON ===")
	print(
		f"id={ui_payload.get('id')}  strategy_id={ui_payload.get('strategy_id')}  origin={ui_payload.get('origin')}"
	)
	print(_fmt(ui_headline))

	delta = Headline(
		total_return_pct=ui_headline.total_return_pct - optuna_holdout.total_return_pct,
		cagr_pct=ui_headline.cagr_pct - optuna_holdout.cagr_pct,
		sharpe=ui_headline.sharpe - optuna_holdout.sharpe,
		max_dd_pct=ui_headline.max_dd_pct - optuna_holdout.max_dd_pct,
		trades=(ui_headline.trades - optuna_holdout.trades)
		if (ui_headline.trades is not None and optuna_holdout.trades is not None)
		else None,
	)

	print("\n=== UI minus Optuna ===")
	print(_fmt(delta))

	if args.rerun_backend:
		rerun, toggles = await _rerun_backend(ui_payload)

		print("\n=== Backend rerun (DB strategy) ===")
		print(_fmt(rerun))

		print("\n=== Strategy toggles seen by backend ===")
		print(json.dumps(toggles, indent=2))

		rerun_delta = Headline(
			total_return_pct=rerun.total_return_pct - ui_headline.total_return_pct,
			cagr_pct=rerun.cagr_pct - ui_headline.cagr_pct,
			sharpe=rerun.sharpe - ui_headline.sharpe,
			max_dd_pct=rerun.max_dd_pct - ui_headline.max_dd_pct,
			trades=(rerun.trades - ui_headline.trades)
			if (rerun.trades is not None and ui_headline.trades is not None)
			else None,
		)
		print("\n=== Rerun minus UI ===")
		print(_fmt(rerun_delta))


if __name__ == "__main__":
	asyncio.run(main())