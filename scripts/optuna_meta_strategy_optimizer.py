"""\
Optuna Walk-Forward Optimizer for a Regime-Switch Meta-Strategy
===============================================================

Goal: push returns while controlling risk and overfitting.

- Uses Alpaca historical daily bars (stocks)
- Aligns symbols on common trading dates
- Simulates realistic execution with configurable slippage + commissions
- Uses walk-forward splits (train -> test) and keeps a final holdout

This is a research harness (not yet wired into live trading execution).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv


@dataclass(frozen=True)
class CostModel:
    slippage_bps: float  # e.g. 5 = 0.05%
    commission_per_trade: float  # flat fee per fill


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    trades: int
    turnover: float  # notional traded / initial capital
    avg_gross_exposure: float  # average long exposure as fraction of equity


def _turnover_from_platform_trades(trades: list[dict] | list[object], initial_capital: float) -> float:
    if not trades or initial_capital <= 0:
        return 0.0
    notional = 0.0
    for t in trades:
        # Trade is usually a Pydantic model with attributes.
        qty = getattr(t, "quantity", None) if not isinstance(t, dict) else t.get("quantity")
        entry_price = getattr(t, "entry_price", None) if not isinstance(t, dict) else t.get("entry_price")
        exit_price = getattr(t, "exit_price", None) if not isinstance(t, dict) else t.get("exit_price")
        try:
            q = float(qty)
            ep = float(entry_price)
        except Exception:
            continue
        notional += abs(q * ep)
        if exit_price is not None:
            try:
                xp = float(exit_price)
                notional += abs(q * xp)
            except Exception:
                pass
    return float(notional / initial_capital)


def _avg_gross_exposure_from_platform_equity(equity_curve: list[dict] | list[object]) -> float:
    if not equity_curve:
        return 0.0
    exposures: list[float] = []
    for pt in equity_curve:
        value = getattr(pt, "value", None) if not isinstance(pt, dict) else pt.get("value")
        positions_value = (
            getattr(pt, "positions_value", None) if not isinstance(pt, dict) else pt.get("positions_value")
        )
        try:
            v = float(value)
            pv = float(positions_value)
        except Exception:
            continue
        if v <= 0:
            continue
        exposures.append(max(0.0, pv / v))
    return float(np.mean(exposures)) if exposures else 0.0


async def _platform_holdout_eval(
    *,
    name: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    parameters: dict[str, float],
    costs: CostModel,
    initial_capital: float,
    return_result: bool = False,
) -> BacktestMetrics | tuple[BacktestMetrics, Any]:
    """Run holdout using the platform BacktestService for true parity with UI/backend."""

    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("OPT_ENGINE=platform requires DATABASE_URL (PostgreSQL)")

    from backend.infra.db import init_db
    from backend.infra.schemas import Strategy
    from backend.services.backtest_service import BacktestService

    engine, sessionmaker = init_db(database_url)

    # Build platform parameter dict.
    platform_params: dict[str, object] = {str(k): float(v) for k, v in parameters.items()}
    platform_params.setdefault("_origin", "optuna")
    platform_params.setdefault("slippage_bps", float(costs.slippage_bps))
    platform_params.setdefault("commission_per_trade", float(costs.commission_per_trade))
    platform_params.setdefault("use_optuna_position_size", True)
    platform_params.setdefault("use_optuna_max_positions", True)
    platform_params.setdefault("use_optuna_min_position_dollars", True)

    # Mirror harness market buffer side into the platform param (platform also reads env).
    mbs = os.getenv("OPT_MARKET_BUFFER_SIDE", "below").strip().lower()
    if mbs:
        platform_params.setdefault("opt_market_buffer_side", mbs)

    allow_leverage_raw = os.getenv("OPT_ALLOW_LEVERAGE")
    if isinstance(allow_leverage_raw, str) and allow_leverage_raw.strip():
        allow_leverage = allow_leverage_raw.strip().lower() in {"1", "true", "yes", "on"}
        if allow_leverage:
            platform_params.setdefault("allow_leverage", True)
            platform_params.setdefault("use_optuna_leverage", True)

    # Ensure a stable strategy row exists for FK constraints.
    # Use a deterministic UUID so repeated runs reuse the same Strategy.
    strategy_uuid = uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), f"optuna_harness::{name}")
    safe_name = (name[:90] + " (h)") if len(name) > 95 else name

    async with sessionmaker() as session:
        strategy = await session.get(Strategy, strategy_uuid)
        if strategy is None:
            strategy = Strategy(
                id=strategy_uuid,
                name=safe_name,
                strategy_type="optuna_meta",
                description="Autocreated by Optuna harness (platform engine eval)",
                symbols=symbols,
                parameters={},
            )
            session.add(strategy)
            await session.commit()
        else:
            changed = False
            if getattr(strategy, "strategy_type", None) != "optuna_meta":
                strategy.strategy_type = "optuna_meta"
                changed = True
            if getattr(strategy, "symbols", None) != symbols:
                strategy.symbols = symbols
                changed = True
            if changed:
                await session.commit()

        service = BacktestService(session)
        demo_user_uuid = str(
            uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "optuna_harness")
        )

        result = await service.run_backtest(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=float(initial_capital),
            parameters=platform_params,  # override params per eval
            user_id=demo_user_uuid,
        )

    await engine.dispose()

    turnover = _turnover_from_platform_trades(result.trade_log, initial_capital)
    avg_exposure = _avg_gross_exposure_from_platform_equity(result.equity_curve)

    metrics = BacktestMetrics(
        total_return_pct=float(result.metrics.total_return),
        cagr_pct=float(result.metrics.annualized_return),
        sharpe=float(result.metrics.sharpe_ratio),
        max_drawdown_pct=float(result.metrics.max_drawdown),
        trades=int(result.metrics.total_trades),
        turnover=float(turnover),
        avg_gross_exposure=float(avg_exposure),
    )

    if return_result:
        return metrics, result

    return metrics


def _cagr(final_value: float, initial_value: float, trading_days: int) -> float:
    if trading_days <= 0 or initial_value <= 0:
        return 0.0
    years = trading_days / 252.0
    if years <= 0:
        return 0.0
    return (final_value / initial_value) ** (1.0 / years) - 1.0


def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / np.where(peak == 0, 1, peak)
    return float(np.max(dd))


def _sharpe(daily_returns: np.ndarray) -> float:
    if daily_returns.size < 2:
        return 0.0
    std = float(np.std(daily_returns))
    if std <= 0:
        return 0.0
    return float(np.mean(daily_returns) / std * np.sqrt(252.0))


def _sma(series: np.ndarray, period: int) -> float:
    if series.size == 0:
        return 0.0
    if period <= 0:
        return float(series[-1])
    # If we don't have enough history for the requested period, use the
    # available history rather than the last price (which can create brittle
    # gating behavior in early samples).
    if series.size < period:
        return float(np.mean(series))
    return float(np.mean(series[-period:]))


def _rsi(series: np.ndarray, period: int = 14) -> float:
    if series.size < period + 1:
        return 50.0
    delta = np.diff(series)
    recent = delta[-period:]
    gains = recent[recent > 0].sum() / period
    losses = (-recent[recent < 0]).sum() / period
    if losses <= 0:
        return 100.0
    rs = gains / losses
    return float(100.0 - (100.0 / (1.0 + rs)))


def _bollinger(series: np.ndarray, period: int = 20, k: float = 2.0) -> tuple[float, float, float]:
    if series.size < period:
        last = float(series[-1])
        return last, last, last
    window = series[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window))
    return mid + k * std, mid, mid - k * std


def _macd(series: np.ndarray) -> tuple[float, float]:
    # Lightweight MACD approximation using EMAs
    if series.size < 26:
        return 0.0, 0.0

    def ema(values: np.ndarray, period: int) -> float:
        if values.size < period:
            return float(values[-1])
        alpha = 2.0 / (period + 1.0)
        e = float(np.mean(values[:period]))
        for v in values[period:]:
            e = (float(v) - e) * alpha + e
        return e

    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    macd = ema12 - ema26
    signal = macd * 0.9  # coarse but stable
    return float(macd), float(signal)


def _trend_regime(series: np.ndarray, sma_fast: int, sma_slow: int, trend_threshold: float) -> bool:
    # Trend if normalized MA spread exceeds threshold
    if series.size < max(sma_fast, sma_slow):
        return False
    fast = _sma(series, sma_fast)
    slow = _sma(series, sma_slow)
    if slow == 0:
        return False
    spread = abs(fast - slow) / abs(slow)
    return spread >= trend_threshold


def _meta_signal(
    prices: np.ndarray,
    params: dict[str, float],
) -> tuple[str, float]:
    """Return (action, confidence) where action in {buy,sell,hold}."""

    rsi_buy = params["rsi_buy"]
    rsi_sell = params["rsi_sell"]

    sma_fast = int(params["sma_fast"])
    sma_slow = int(params["sma_slow"])

    band_tol = params["band_tolerance"]
    entry_z = params["entry_threshold"]

    trend_threshold = params["trend_threshold"]

    if prices.size < max(60, sma_slow, 26):
        return "hold", 0.0

    current = float(prices[-1])

    # Regime gate
    in_trend = _trend_regime(prices, sma_fast=sma_fast, sma_slow=sma_slow, trend_threshold=trend_threshold)

    # Indicators
    rsi = _rsi(prices, 14)
    macd, macd_sig = _macd(prices)
    sma_f = _sma(prices, sma_fast)
    sma_s = _sma(prices, sma_slow)
    bb_u, bb_m, bb_l = _bollinger(prices, 20)

    # Z-score (single-series)
    lookback = 60
    window = prices[-lookback:]
    mean = float(np.mean(window))
    std = float(np.std(window))
    z = (current - mean) / std if std > 0 else 0.0

    # Weighted votes (different weights per regime)
    # Trend regime: momentum + trend-following + ensemble votes
    # Range regime: mean-reversion + stat-arb + ensemble votes
    buy_votes = 0.0
    sell_votes = 0.0

    # Ensemble-like: RSI + MACD + trend + BB equally weighted
    # (weights are then scaled by regime weights)
    ens_buy = ens_sell = 0.0
    if rsi < rsi_buy:
        ens_buy += 0.25
    elif rsi > rsi_sell:
        ens_sell += 0.25

    if macd > macd_sig:
        ens_buy += 0.25
    else:
        ens_sell += 0.25

    if current > sma_f > sma_s:
        ens_buy += 0.25
    elif current < sma_f < sma_s:
        ens_sell += 0.25

    if current < bb_l * (1.0 + 2.0 * band_tol):
        ens_buy += 0.25
    elif current > bb_u * (1.0 - 2.0 * band_tol):
        ens_sell += 0.25

    # Mean reversion
    mr_buy = 0.0
    mr_sell = 0.0
    if current < bb_l * (1.0 + band_tol) and rsi < rsi_buy:
        mr_buy = min(0.9, (rsi_buy - rsi) / 20.0)
    elif current > bb_u * (1.0 - band_tol) and rsi > rsi_sell:
        mr_sell = min(0.9, (rsi - rsi_sell) / 20.0)

    # Momentum
    mom_buy = 0.0
    mom_sell = 0.0
    if macd > macd_sig and current > sma_f > sma_s:
        mom_buy = min(0.85, abs(macd - macd_sig) * 10.0)
    elif macd < macd_sig and current < sma_f < sma_s:
        mom_sell = min(0.85, abs(macd - macd_sig) * 10.0)

    # Stat-arb
    sa_buy = 0.0
    sa_sell = 0.0
    if z < -entry_z:
        sa_buy = min(0.9, abs(z) / 5.0)
    elif z > entry_z:
        sa_sell = min(0.9, abs(z) / 5.0)

    # Regime weights
    w_ens_raw = max(0.0, params["w_ensemble"])
    w_mom_raw = max(0.0, params["w_momentum"])
    w_mr_raw = max(0.0, params["w_meanrev"])
    w_sa_raw = max(0.0, params["w_statarb"])
    w_sum = w_ens_raw + w_mom_raw + w_mr_raw + w_sa_raw
    if w_sum <= 0:
        return "hold", 0.0
    w_ens = w_ens_raw / w_sum
    w_mom = w_mom_raw / w_sum
    w_mr = w_mr_raw / w_sum
    w_sa = w_sa_raw / w_sum

    # Blend regimes slightly to avoid brittle switching.
    if in_trend:
        buy_votes += w_ens * ens_buy + w_mom * mom_buy + 0.25 * w_mr * mr_buy + 0.25 * w_sa * sa_buy
        sell_votes += w_ens * ens_sell + w_mom * mom_sell + 0.25 * w_mr * mr_sell + 0.25 * w_sa * sa_sell
    else:
        buy_votes += w_ens * ens_buy + w_mr * mr_buy + w_sa * sa_buy + 0.25 * w_mom * mom_buy
        sell_votes += w_ens * ens_sell + w_mr * mr_sell + w_sa * sa_sell + 0.25 * w_mom * mom_sell

    # Decision
    threshold = params["decision_threshold"]
    if buy_votes >= threshold and buy_votes > sell_votes:
        return "buy", min(1.0, buy_votes)
    if sell_votes >= threshold and sell_votes > buy_votes:
        return "sell", min(1.0, sell_votes)
    return "hold", 0.0


def run_backtest_panel(
    panel: pd.DataFrame,
    market: pd.Series,
    params: dict[str, float],
    costs: CostModel,
    initial_capital: float,
    *,
    panel_open: pd.DataFrame | None = None,
    market_open: pd.Series | None = None,
) -> BacktestMetrics:
    """Backtest on an aligned panel (index=dates, columns=symbols, values=close).

    Execution modes:
    - OPT_EXECUTION_MODE=close (default): signal + execute on same close (research-only).
    - OPT_EXECUTION_MODE=next_open: signal on prior close, execute on next open (more live-like).
    """

    warmup = int(params["warmup"])
    stop_loss = params["stop_loss_pct"]
    take_profit = params["take_profit_pct"]
    # Interpreted as a NOTIONAL cap per position (fraction of equity).
    position_size_pct = params["position_size_pct"]
    # Risk-based sizing: fraction of equity at risk if stop loss is hit.
    risk_per_trade_pct = float(params.get("risk_per_trade_pct", 0.0))
    max_gross_exposure = float(params.get("max_gross_exposure", 1.0))
    max_positions = int(params["max_positions"])
    min_hold_days = int(params.get("min_hold_days", 0))
    market_sma = int(params.get("market_sma", 200))
    market_buffer = float(params.get("market_buffer", 0.0))
    market_force_exit = bool(int(params.get("market_force_exit", 1)))
    market_trim_risk_off = bool(int(params.get("market_trim_risk_off", 0)))
    risk_off_exposure_mult = float(params.get("risk_off_exposure_mult", 0.5))
    risk_off_exposure_mult = float(np.clip(risk_off_exposure_mult, 0.0, 1.0))

    # Market buffer semantics are surprisingly easy to get backwards.
    # - "below" (default, backwards compatible): risk_on if price >= SMA * (1 - buffer)
    # - "above": risk_on if price >= SMA * (1 + buffer)
    # "above" is typically the strict trend filter people intend.
    market_buffer_side = os.getenv("OPT_MARKET_BUFFER_SIDE", "below").strip().lower()

    allow_leverage_raw = os.getenv("OPT_ALLOW_LEVERAGE")
    high_return_mode_raw = os.getenv("OPT_HIGH_RETURN_MODE")
    high_return_mode = str(high_return_mode_raw or "0").strip().lower() in {"1", "true", "yes", "on"}
    allow_leverage = (
        (str(allow_leverage_raw).strip().lower() in {"1", "true", "yes", "on"})
        if allow_leverage_raw is not None
        else high_return_mode
    )

    execution_mode = os.getenv("OPT_EXECUTION_MODE", "close").strip().lower()
    next_open_mode = execution_mode in {"next_open", "nextopen", "open_next", "open"}
    if next_open_mode:
        if panel_open is None or market_open is None:
            raise RuntimeError("OPT_EXECUTION_MODE=next_open requires panel_open and market_open")
        if not panel_open.index.equals(panel.index):
            raise RuntimeError("panel_open index must match panel index")
        if not market_open.index.equals(market.index):
            raise RuntimeError("market_open index must match market index")

    cash = float(initial_capital)
    positions: dict[str, dict[str, float]] = {}

    equity = []
    gross_exposures = []
    turnover_notional = 0.0
    trades = 0

    symbols = list(panel.columns)
    closes = panel.to_numpy(dtype=float)
    market_prices = market.to_numpy(dtype=float)
    opens = panel_open.to_numpy(dtype=float) if panel_open is not None else None
    market_opens = market_open.to_numpy(dtype=float) if market_open is not None else None

    def market_on(idx: int) -> bool:
        if idx < market_sma:
            return True
        window = market_prices[idx - market_sma : idx]
        if not np.isfinite(window).all() or not np.isfinite(market_prices[idx]):
            return True
        sma = float(np.mean(window))
        if sma <= 0:
            return True
        if market_buffer_side in {"above", "strict", "over"}:
            threshold = sma * (1.0 + market_buffer)
        else:
            threshold = sma * (1.0 - market_buffer)
        return float(market_prices[idx]) >= threshold

    if next_open_mode:
        # Signal on day (i-1) close, execute on day i open, mark equity on day i close.
        for i in range(warmup + 1, closes.shape[0]):
            decision_i = i - 1
            risk_on = market_on(decision_i)

            # 1) exits (decided on close, executed next open)
            for symbol in list(positions.keys()):
                j = symbols.index(symbol)
                price_close = float(closes[decision_i, j])
                price_open = float(opens[i, j])
                pos = positions[symbol]
                entry = float(pos["entry_price"])
                qty = float(pos["qty"])
                pnl_pct = (price_close - entry) / entry if entry else 0.0

                held_days = int(decision_i - int(pos.get("entry_i", decision_i)))

                action, _conf = _meta_signal(closes[: decision_i + 1, j], params)
                should_exit = (pnl_pct <= -stop_loss) or (pnl_pct >= take_profit) or (
                    action == "sell" and held_days >= min_hold_days
                )

                if market_force_exit and (not risk_on):
                    should_exit = True

                if should_exit:
                    exec_price = price_open * (1.0 - costs.slippage_bps / 10000.0)
                    notional = exec_price * qty
                    cash += notional
                    cash -= costs.commission_per_trade
                    turnover_notional += abs(notional)
                    trades += 1
                    del positions[symbol]

            # 2) risk-off trimming (decided on close, executed next open)
            if (not risk_on) and (not market_force_exit) and market_trim_risk_off and positions:
                positions_value_for_trim = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_for_trim += float(closes[decision_i, jj]) * float(pos["qty"])
                equity_now_close = cash + positions_value_for_trim

                risk_off_cap = max(0.0, max_gross_exposure * risk_off_exposure_mult)
                target_positions_value = equity_now_close * risk_off_cap

                if positions_value_for_trim > target_positions_value and equity_now_close > 0:
                    ranked: list[tuple[int, float, str]] = []
                    for sym in positions.keys():
                        jj = symbols.index(sym)
                        action, conf = _meta_signal(closes[: decision_i + 1, jj], params)
                        if action == "sell":
                            bucket = 0
                        elif action == "hold":
                            bucket = 1
                        else:
                            bucket = 2
                        ranked.append((bucket, float(conf), sym))
                    ranked.sort(key=lambda x: (x[0], x[1]))

                    for _bucket, _conf, sym in ranked:
                        if positions_value_for_trim <= target_positions_value:
                            break
                        jj = symbols.index(sym)
                        price_open = float(opens[i, jj])
                        pos = positions.get(sym)
                        if pos is None:
                            continue
                        qty = float(pos["qty"])
                        exec_price = price_open * (1.0 - costs.slippage_bps / 10000.0)
                        notional = exec_price * qty
                        cash += notional
                        cash -= costs.commission_per_trade
                        turnover_notional += abs(notional)
                        trades += 1
                        positions_value_for_trim -= float(closes[decision_i, jj]) * qty
                        del positions[sym]

            # 3) entries (decided on close, executed next open)
            open_slots = max_positions - len(positions)
            if open_slots > 0 and risk_on:
                positions_value_open = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_open += float(opens[i, jj]) * float(pos["qty"])
                equity_now_open = cash + positions_value_open

                candidates: list[tuple[str, float, float]] = []
                for symbol in symbols:
                    if symbol in positions:
                        continue
                    j = symbols.index(symbol)
                    action, conf = _meta_signal(closes[: decision_i + 1, j], params)
                    if action == "buy" and conf > 0:
                        candidates.append((symbol, float(conf), float(opens[i, j])))

                candidates.sort(key=lambda x: x[1], reverse=True)

                for symbol, conf, price_open in candidates[:open_slots]:
                    exec_price = price_open * (1.0 + costs.slippage_bps / 10000.0)

                    gross_notional_open = 0.0
                    for sym, pos in positions.items():
                        jj = symbols.index(sym)
                        gross_notional_open += float(opens[i, jj]) * float(pos["qty"])

                    gross_room = max(0.0, equity_now_open * max_gross_exposure - gross_notional_open)
                    notional_cap = equity_now_open * position_size_pct

                    if risk_per_trade_pct > 0 and stop_loss > 0:
                        risk_budget_dollars = equity_now_open * risk_per_trade_pct
                        risk_based_notional = risk_budget_dollars / stop_loss
                        desired_notional = min(risk_based_notional, notional_cap)
                    else:
                        desired_notional = notional_cap

                    if allow_leverage and equity_now_open > 0:
                        max_borrow = max(0.0, equity_now_open * max(0.0, max_gross_exposure - 1.0))
                        cash_room = cash + max_borrow
                    else:
                        cash_room = cash

                    budget = min(cash_room, gross_room, desired_notional)
                    if budget < float(params["min_position_dollars"]):
                        continue

                    qty = int(budget / exec_price)
                    if qty <= 0:
                        continue

                    notional = exec_price * qty
                    cash -= notional
                    cash -= costs.commission_per_trade
                    turnover_notional += abs(notional)
                    trades += 1

                    positions[symbol] = {"entry_price": exec_price, "qty": float(qty), "entry_i": float(i)}

            # 4) equity mark-to-market on close
            positions_value = 0.0
            for symbol, pos in positions.items():
                j = symbols.index(symbol)
                positions_value += float(closes[i, j]) * float(pos["qty"])

            equity_now = cash + positions_value
            equity.append(equity_now)
            gross_exposures.append(positions_value / equity_now if equity_now > 0 else 0.0)

    else:
        for i in range(warmup, closes.shape[0]):
            risk_on = market_on(i)

            # 1) exits
            for symbol in list(positions.keys()):
                j = symbols.index(symbol)
                price = float(closes[i, j])
                pos = positions[symbol]
                entry = pos["entry_price"]
                qty = pos["qty"]
                pnl_pct = (price - entry) / entry if entry else 0.0

                held_days = int(i - int(pos.get("entry_i", i)))

                # signal-based exit
                action, _conf = _meta_signal(closes[: i + 1, j], params)
                should_exit = (pnl_pct <= -stop_loss) or (pnl_pct >= take_profit) or (
                    action == "sell" and held_days >= min_hold_days
                )

                # Market risk-off: get flatter quickly.
                if market_force_exit and (not risk_on):
                    should_exit = True

                if should_exit:
                    exec_price = price * (1.0 - costs.slippage_bps / 10000.0)
                    notional = exec_price * qty
                    cash += notional
                    cash -= costs.commission_per_trade
                    turnover_notional += abs(notional)
                    trades += 1
                    del positions[symbol]

            # 2) entries
            open_slots = max_positions - len(positions)
            # If risk-off and not forcing exits, optionally trim exposure rather than
            # liquidating everything. This tends to be less brittle than full exits.
            if (not risk_on) and (not market_force_exit) and market_trim_risk_off and positions:
                positions_value_for_trim = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_for_trim += float(closes[i, jj]) * pos["qty"]
                equity_now = cash + positions_value_for_trim

                # Base cap is max_gross_exposure; in risk-off we shrink it.
                risk_off_cap = max(0.0, max_gross_exposure * risk_off_exposure_mult)
                target_positions_value = equity_now * risk_off_cap

                if positions_value_for_trim > target_positions_value and equity_now > 0:
                    ranked: list[tuple[int, float, str]] = []
                    for sym in positions.keys():
                        jj = symbols.index(sym)
                        action, conf = _meta_signal(closes[: i + 1, jj], params)
                        # Sell signals first, then low-confidence holds.
                        if action == "sell":
                            bucket = 0
                        elif action == "hold":
                            bucket = 1
                        else:
                            bucket = 2
                        ranked.append((bucket, float(conf), sym))
                    ranked.sort(key=lambda x: (x[0], x[1]))

                    for _bucket, _conf, sym in ranked:
                        if positions_value_for_trim <= target_positions_value:
                            break
                        jj = symbols.index(sym)
                        price = float(closes[i, jj])
                        pos = positions.get(sym)
                        if pos is None:
                            continue
                        qty = pos["qty"]
                        exec_price = price * (1.0 - costs.slippage_bps / 10000.0)
                        notional = exec_price * qty
                        cash += notional
                        cash -= costs.commission_per_trade
                        turnover_notional += abs(notional)
                        trades += 1
                        positions_value_for_trim -= float(closes[i, jj]) * qty
                        del positions[sym]

            if open_slots > 0 and risk_on:
                # Equity-aware sizing: use current equity as the sizing base (but never exceed available cash).
                positions_value_for_sizing = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_for_sizing += float(closes[i, jj]) * pos["qty"]
                equity_now = cash + positions_value_for_sizing

            # simple scan, pick highest-confidence buy signals
            candidates: list[tuple[str, float, float]] = []
            for symbol in symbols:
                if symbol in positions:
                    continue
                j = symbols.index(symbol)
                action, conf = _meta_signal(closes[: i + 1, j], params)
                if action == "buy" and conf > 0:
                    candidates.append((symbol, conf, float(closes[i, j])))

            candidates.sort(key=lambda x: x[1], reverse=True)

            for symbol, conf, price in candidates[:open_slots]:
                exec_price = price * (1.0 + costs.slippage_bps / 10000.0)
                # Current gross exposure (notional) before adding a new position.
                gross_notional = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    gross_notional += float(closes[i, jj]) * pos["qty"]

                # Hard cap on gross exposure (as fraction of equity).
                gross_room = max(0.0, equity_now * max_gross_exposure - gross_notional)

                # Notional cap for a single position.
                notional_cap = equity_now * position_size_pct

                # Risk-based sizing: size so that stop-loss implies ~risk_per_trade_pct loss of equity.
                # If risk_per_trade_pct is 0, fall back to old behavior (notional cap only).
                if risk_per_trade_pct > 0 and stop_loss > 0:
                    risk_budget_dollars = equity_now * risk_per_trade_pct
                    risk_based_notional = risk_budget_dollars / stop_loss
                    desired_notional = min(risk_based_notional, notional_cap)
                else:
                    desired_notional = notional_cap

                # Funding constraint:
                # - Default: cash-only.
                # - If leverage is allowed: permit cash to go negative up to the
                #   implied borrow limit from max_gross_exposure.
                if allow_leverage and equity_now > 0:
                    max_borrow = max(0.0, equity_now * max(0.0, max_gross_exposure - 1.0))
                    cash_room = cash + max_borrow
                else:
                    cash_room = cash

                budget = min(cash_room, gross_room, desired_notional)
                if budget < float(params["min_position_dollars"]):
                    continue

                qty = int(budget / exec_price)
                if qty <= 0:
                    continue

                notional = exec_price * qty
                cash -= notional
                cash -= costs.commission_per_trade
                turnover_notional += abs(notional)
                trades += 1

                positions[symbol] = {"entry_price": exec_price, "qty": float(qty), "entry_i": float(i)}

            # 3) equity
            positions_value = 0.0
            for symbol, pos in positions.items():
                j = symbols.index(symbol)
                positions_value += float(closes[i, j]) * pos["qty"]

            equity_now = cash + positions_value
            equity.append(equity_now)
            gross_exposures.append(positions_value / equity_now if equity_now > 0 else 0.0)

    if not equity:
        return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0)

    equity_arr = np.asarray(equity, dtype=float)
    daily_returns = np.diff(equity_arr) / np.where(equity_arr[:-1] == 0, 1, equity_arr[:-1])

    final_value = float(equity_arr[-1])
    total_return_pct = (final_value / initial_capital - 1.0) * 100.0
    cagr_pct = _cagr(final_value, initial_capital, trading_days=len(equity_arr)) * 100.0
    sharpe = _sharpe(daily_returns)
    max_dd_pct = _max_drawdown(equity_arr) * 100.0

    turnover = turnover_notional / initial_capital if initial_capital > 0 else 0.0
    avg_gross_exposure = float(np.mean(gross_exposures)) if gross_exposures else 0.0

    return BacktestMetrics(
        total_return_pct=total_return_pct,
        cagr_pct=cagr_pct,
        sharpe=sharpe,
        max_drawdown_pct=max_dd_pct,
        trades=trades,
        turnover=turnover,
        avg_gross_exposure=avg_gross_exposure,
    )
def build_walkforward_splits(
    index: pd.DatetimeIndex,
    *,
    holdout_override: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> tuple[list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]], tuple[pd.Timestamp, pd.Timestamp]]:
    """Return (splits, holdout_range).

    By default the final half-year (H2) window is held out.
    If holdout_override is provided, the walk-forward splits stop strictly
    before holdout_override[0] to avoid leakage.
    """

    def _half_year_boundaries(y0: int, yN: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        boundaries: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        for y in range(y0, yN + 1):
            boundaries.append((pd.Timestamp(y, 1, 1), pd.Timestamp(y, 6, 30)))
            boundaries.append((pd.Timestamp(y, 7, 1), pd.Timestamp(y, 12, 31)))
        return boundaries

    if index.size == 0:
        raise ValueError("Cannot build walk-forward splits on empty index")

    idx_min = pd.Timestamp(index.min()).normalize()
    idx_max = pd.Timestamp(index.max()).normalize()

    holdout_range: tuple[pd.Timestamp, pd.Timestamp] | None = None
    wf_end: pd.Timestamp | None = None

    if holdout_override is not None:
        hs, he = holdout_override
        hs = pd.Timestamp(hs).normalize()
        he = pd.Timestamp(he).normalize()
        if he < hs:
            raise ValueError("holdout_override end must be >= start")
        if he < idx_min or hs > idx_max:
            raise ValueError("holdout_override is outside available data range")
        holdout_range = (hs, he)
        wf_end = (hs - pd.Timedelta(days=1)).normalize()
        if wf_end < idx_min:
            raise ValueError("holdout_override starts before available data; no room for walk-forward")

    # Half-year windows from the available index (or up to wf_end when overridden).
    y0 = int(idx_min.year)
    yN = int((wf_end.year if wf_end is not None else idx_max.year))
    boundaries = _half_year_boundaries(y0, yN)

    # Keep boundaries that intersect the walk-forward portion of the data.
    if wf_end is not None:
        boundaries = [b for b in boundaries if b[0] <= wf_end and b[1] <= wf_end and not (b[1] < idx_min)]
    else:
        boundaries = [b for b in boundaries if not (b[1] < idx_min or b[0] > idx_max)]

    if len(boundaries) < 2:
        raise ValueError("Not enough data to create at least one walk-forward window")

    # Default holdout is the final available half-year window.
    if holdout_range is None:
        holdout_range = boundaries[-1]
        boundaries_wf = boundaries
    else:
        boundaries_wf = boundaries

    # Build walk-forward: train = window k, test = window k+1
    splits: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    for k in range(len(boundaries_wf) - 1):
        train = boundaries_wf[k]
        test = boundaries_wf[k + 1]
        # stop before final holdout in default mode
        if holdout_override is None and test == holdout_range:
            break
        splits.append((train[0], train[1], test[0], test[1]))

    return splits, holdout_range


def slice_panel(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return panel.loc[(panel.index >= start) & (panel.index <= end)].copy()


async def fetch_price_panel(
    symbols: list[str],
    start: str,
    end: str,
    market_symbol: str = "SPY",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    from backend.data.alpaca_client import AlpacaClient

    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError("Missing ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY in .env")

    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)

    close_series: list[pd.Series] = []
    open_series: list[pd.Series] = []
    for sym in symbols:
        df = client.get_historical_data(symbol=sym, timeframe="1Day", start=start, end=end)
        if df.empty:
            raise RuntimeError(f"No data for {sym}")
        df = df.set_index("timestamp")
        close_series.append(df["close"].rename(sym))
        open_series.append(df["open"].rename(sym))

    market_df = client.get_historical_data(symbol=market_symbol, timeframe="1Day", start=start, end=end)
    if market_df.empty:
        raise RuntimeError(f"No data for market symbol {market_symbol}")
    market_df = market_df.set_index("timestamp")
    market_close = market_df["close"].rename(market_symbol)
    market_open = market_df["open"].rename(market_symbol)

    panel_close = pd.concat(close_series, axis=1, join="inner").sort_index()
    panel_open = pd.concat(open_series, axis=1, join="inner").sort_index()
    panel_close = panel_close[~panel_close.index.duplicated(keep="last")]
    panel_open = panel_open[~panel_open.index.duplicated(keep="last")]
    market_close = market_close[~market_close.index.duplicated(keep="last")].sort_index()
    market_open = market_open[~market_open.index.duplicated(keep="last")].sort_index()

    # Alpaca timestamps are typically tz-aware; make them tz-naive for clean slicing/comparisons.
    if isinstance(panel_close.index, pd.DatetimeIndex) and panel_close.index.tz is not None:
        panel_close.index = panel_close.index.tz_convert(None)
    if isinstance(panel_open.index, pd.DatetimeIndex) and panel_open.index.tz is not None:
        panel_open.index = panel_open.index.tz_convert(None)
    if isinstance(market_close.index, pd.DatetimeIndex) and market_close.index.tz is not None:
        market_close.index = market_close.index.tz_convert(None)
    if isinstance(market_open.index, pd.DatetimeIndex) and market_open.index.tz is not None:
        market_open.index = market_open.index.tz_convert(None)

    # Align the tradable universe to the market index dates.
    common_index = panel_close.index.intersection(panel_open.index).intersection(market_close.index).intersection(market_open.index)
    panel_close = panel_close.loc[common_index]
    panel_open = panel_open.loc[common_index]
    market_close = market_close.loc[common_index]
    market_open = market_open.loc[common_index]

    return panel_close, panel_open, market_close, market_open


def objective_factory(
    panel: pd.DataFrame,
    panel_open: pd.DataFrame,
    market_open: pd.Series,
    splits,
    dd_cap_pct: float,
    initial_capital: float,
):
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return float(default)
        try:
            return float(raw.strip())
        except Exception:
            return float(default)

    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return int(default)
        try:
            return int(float(raw.strip()))
        except Exception:
            return int(default)

    objective_mode = os.getenv("OPT_OBJECTIVE", "robust_cagr").strip().lower()

    # Calmar-first objective weights. Defaults favor Calmar, but still consider Sharpe/CAGR.
    # These weights only apply when OPT_OBJECTIVE is set to calmar/calmar_combo.
    w_calmar = float(np.clip(_env_float("OPT_W_CALMAR", 1.0), 0.0, 10.0))
    w_sharpe = float(np.clip(_env_float("OPT_W_SHARPE", 0.35), 0.0, 10.0))
    w_cagr = float(np.clip(_env_float("OPT_W_CAGR", 0.35), 0.0, 10.0))

    high_return_mode = _env_bool("OPT_HIGH_RETURN_MODE", False)

    # Search-space controls (defaults chosen to preserve existing behavior unless
    # OPT_HIGH_RETURN_MODE=1 is enabled).
    pos_size_min = float(np.clip(_env_float("OPT_POSITION_SIZE_PCT_MIN", 0.05), 0.01, 1.0))
    pos_size_max_default = 0.60 if high_return_mode else 0.35
    pos_size_max = float(np.clip(_env_float("OPT_POSITION_SIZE_PCT_MAX", pos_size_max_default), pos_size_min, 1.5))

    risk_per_trade_max_default = 0.05 if high_return_mode else 0.02
    risk_per_trade_max = float(np.clip(_env_float("OPT_RISK_PER_TRADE_PCT_MAX", risk_per_trade_max_default), 0.0, 0.20))

    max_gex_min = float(np.clip(_env_float("OPT_MAX_GROSS_EXPOSURE_MIN", 0.60), 0.10, 5.0))
    max_gex_max_default = 2.00 if high_return_mode else 1.00
    max_gex_max = float(np.clip(_env_float("OPT_MAX_GROSS_EXPOSURE_MAX", max_gex_max_default), max_gex_min, 5.0))

    max_positions_max_default = 12 if high_return_mode else 10
    max_positions_max = int(np.clip(_env_int("OPT_MAX_POSITIONS_MAX", max_positions_max_default), 2, 50))
    max_positions_min = int(np.clip(_env_int("OPT_MAX_POSITIONS_MIN", 2), 1, max_positions_max))

    # Penalty weights (lower weights -> more aggressive/high-variance solutions).
    dd_w = float(np.clip(_env_float("OPT_PENALTY_DD_W", 1.5 if high_return_mode else 3.0), 0.0, 50.0))
    neg_w = float(np.clip(_env_float("OPT_PENALTY_NEG_W", 2.0 if high_return_mode else 2.5), 0.0, 50.0))
    turn_w = float(np.clip(_env_float("OPT_PENALTY_TURN_W", 0.25 if high_return_mode else 0.8), 0.0, 50.0))
    instab_w = float(np.clip(_env_float("OPT_PENALTY_INSTAB_W", 0.25 if high_return_mode else 0.6), 0.0, 50.0))
    exposure_w = float(np.clip(_env_float("OPT_PENALTY_EXPOSURE_W", 8.0 if high_return_mode else 20.0), 0.0, 200.0))
    trade_avg_w = float(np.clip(_env_float("OPT_PENALTY_TRADES_AVG_W", 0.8 if high_return_mode else 1.5), 0.0, 50.0))
    trade_min_w = float(np.clip(_env_float("OPT_PENALTY_TRADES_MIN_W", 1.2 if high_return_mode else 2.0), 0.0, 50.0))

    fixed_slippage_bps_raw = os.getenv("OPT_FIXED_SLIPPAGE_BPS")
    fixed_slippage_bps: float | None = None
    if fixed_slippage_bps_raw is not None and fixed_slippage_bps_raw.strip() != "":
        try:
            fixed_slippage_bps = float(np.clip(float(fixed_slippage_bps_raw.strip()), 0.0, 50.0))
        except Exception:
            fixed_slippage_bps = None

    fixed_commission_raw = os.getenv("OPT_FIXED_COMMISSION_PER_TRADE")
    fixed_commission: float | None = None
    if fixed_commission_raw is not None and fixed_commission_raw.strip() != "":
        try:
            fixed_commission = float(np.clip(float(fixed_commission_raw.strip()), 0.0, 20.0))
        except Exception:
            fixed_commission = None

    # Expect market series to be attached on the panel as a side-channel by closure.
    market_sma_override_raw = os.getenv("OPT_MARKET_SMA")
    market_sma_override: int | None = None
    if market_sma_override_raw is not None:
        try:
            v = int(float(market_sma_override_raw.strip()))
            market_sma_override = int(np.clip(v, 20, 400))
        except Exception:
            market_sma_override = None

    market_buffer_override_raw = os.getenv("OPT_MARKET_BUFFER")
    market_buffer_override: float | None = None
    if market_buffer_override_raw is not None:
        try:
            v = float(market_buffer_override_raw.strip())
            market_buffer_override = float(np.clip(v, 0.0, 0.1))
        except Exception:
            market_buffer_override = None

    force_exit_override_raw = os.getenv("OPT_MARKET_FORCE_EXIT")
    force_exit_override: int | None = None
    if force_exit_override_raw is not None:
        force_exit_override_raw = force_exit_override_raw.strip()
        if force_exit_override_raw in {"0", "1"}:
            force_exit_override = int(force_exit_override_raw)

    trim_override_raw = os.getenv("OPT_MARKET_TRIM_RISK_OFF")
    trim_override: int | None = None
    if trim_override_raw is not None:
        trim_override_raw = trim_override_raw.strip()
        if trim_override_raw in {"0", "1"}:
            trim_override = int(trim_override_raw)

    risk_off_exposure_mult_override_raw = os.getenv("OPT_RISK_OFF_EXPOSURE_MULT")
    risk_off_exposure_mult_override: float | None = None
    if risk_off_exposure_mult_override_raw is not None:
        try:
            v = float(risk_off_exposure_mult_override_raw.strip())
            risk_off_exposure_mult_override = float(np.clip(v, 0.0, 1.0))
        except Exception:
            risk_off_exposure_mult_override = None

    recency_weight = float(os.getenv("OPT_RECENCY_WEIGHT", "0"))
    recency_weight = float(np.clip(recency_weight, 0.0, 1.0))

    # Constrain warmup so it is always feasible for the walk-forward test windows.
    # This avoids wasting a large fraction of Optuna trials on invalid configs.
    if "__MARKET__" in panel.columns:
        _trade_panel_for_len = panel.drop(columns=["__MARKET__"])
    else:
        _trade_panel_for_len = panel

    min_test_len = None
    for (_tr_s, _tr_e, _te_s, _te_e) in splits:
        _tp = slice_panel(_trade_panel_for_len, _te_s, _te_e)
        _n = len(_tp)
        if min_test_len is None or _n < min_test_len:
            min_test_len = _n
    min_test_len = int(min_test_len or 0)
    warmup_max = max(20, min(120, min_test_len - 30))
    warmup_min = max(20, min(60, warmup_max))

    def objective(trial) -> float:
        params: dict[str, float] = {
            # Trading / risk
            "warmup": trial.suggest_int("warmup", warmup_min, warmup_max),
            "stop_loss_pct": trial.suggest_float("stop_loss_pct", 0.02, 0.10),
            "take_profit_pct": trial.suggest_float("take_profit_pct", 0.05, 0.35),
            # Notional cap per position (fraction of equity).
            "position_size_pct": trial.suggest_float("position_size_pct", pos_size_min, pos_size_max),
            # Risk budget per trade (fraction of equity at risk at the stop).
            "risk_per_trade_pct": trial.suggest_float("risk_per_trade_pct", 0.0, risk_per_trade_max),
            # Optional gross exposure cap (still bounded by cash; >1 has no effect without leverage).
            "max_gross_exposure": trial.suggest_float("max_gross_exposure", max_gex_min, max_gex_max),
            "max_positions": trial.suggest_int("max_positions", max_positions_min, max_positions_max),
            "min_position_dollars": trial.suggest_float("min_position_dollars", 500.0, 2500.0),
            "min_hold_days": float(trial.suggest_int("min_hold_days", 1, 12)),

            # Market filter
            "market_sma": float(market_sma_override if market_sma_override is not None else trial.suggest_int("market_sma", 80, 220)),
            "market_buffer": float(market_buffer_override if market_buffer_override is not None else trial.suggest_float("market_buffer", 0.0, 0.02)),
            "market_force_exit": float(force_exit_override if force_exit_override is not None else trial.suggest_categorical("market_force_exit", [0, 1])),
            # If not forcing exits, optionally trim exposure during risk-off.
            "market_trim_risk_off": float(trim_override if trim_override is not None else trial.suggest_categorical("market_trim_risk_off", [0, 1])),
            "risk_off_exposure_mult": float(risk_off_exposure_mult_override if risk_off_exposure_mult_override is not None else trial.suggest_float("risk_off_exposure_mult", 0.1, 0.9)),

            # Risk overlays (parameterized)
            "overlay_kill_switch": float(trial.suggest_categorical("overlay_kill_switch", [0, 1])),
            "overlay_kill_dd_pct": trial.suggest_float("overlay_kill_dd_pct", 0.10, 0.35),
            "overlay_kill_cooldown_days": float(trial.suggest_int("overlay_kill_cooldown_days", 5, 20)),
            "overlay_kill_force_exit": float(trial.suggest_categorical("overlay_kill_force_exit", [0, 1])),

            "overlay_vol_enabled": float(trial.suggest_categorical("overlay_vol_enabled", [0, 1])),
            "overlay_vol_target": trial.suggest_float("overlay_vol_target", 0.10, 0.30),
            "overlay_vol_window": float(trial.suggest_int("overlay_vol_window", 10, 40)),
            "overlay_vol_min_mult": trial.suggest_float("overlay_vol_min_mult", 0.25, 1.0),
            "overlay_vol_max_mult": trial.suggest_float("overlay_vol_max_mult", 1.0, 2.0),

            "overlay_gap_enabled": float(trial.suggest_categorical("overlay_gap_enabled", [0, 1])),
            "overlay_gap_max_pct": trial.suggest_float("overlay_gap_max_pct", 0.01, 0.08),

            "overlay_risk_off_adjust": float(trial.suggest_categorical("overlay_risk_off_adjust", [0, 1])),
            "overlay_risk_off_stop_mult": trial.suggest_float("overlay_risk_off_stop_mult", 0.5, 1.0),
            "overlay_risk_off_take_mult": trial.suggest_float("overlay_risk_off_take_mult", 0.5, 1.0),

            # Meta-strategy knobs
            "rsi_buy": trial.suggest_float("rsi_buy", 20.0, 45.0),
            "rsi_sell": trial.suggest_float("rsi_sell", 55.0, 85.0),
            "sma_fast": float(trial.suggest_int("sma_fast", 5, 30)),
            "sma_slow": float(trial.suggest_int("sma_slow", 30, 120)),
            "band_tolerance": trial.suggest_float("band_tolerance", 0.005, 0.03),
            "entry_threshold": trial.suggest_float("entry_threshold", 1.5, 3.5),
            "trend_threshold": trial.suggest_float("trend_threshold", 0.003, 0.03),
            "decision_threshold": trial.suggest_float("decision_threshold", 0.4, 0.9),

            # Weights (sum not forced; optimizer learns scale)
            "w_ensemble": trial.suggest_float("w_ensemble", 0.2, 3.0),
            "w_momentum": trial.suggest_float("w_momentum", 0.0, 3.0),
            "w_meanrev": trial.suggest_float("w_meanrev", 0.0, 3.0),
            "w_statarb": trial.suggest_float("w_statarb", 0.0, 3.0),
        }

        costs = CostModel(
            slippage_bps=float(fixed_slippage_bps if fixed_slippage_bps is not None else trial.suggest_float("slippage_bps", 0.0, 15.0)),
            commission_per_trade=float(fixed_commission if fixed_commission is not None else trial.suggest_float("commission_per_trade", 0.0, 2.0)),
        )

        # Penalize invalid ranges early
        if params["rsi_buy"] >= params["rsi_sell"]:
            return -1e9
        if params["sma_fast"] >= params["sma_slow"]:
            return -1e9

        cagrs: list[float] = []
        sharpes: list[float] = []
        total_returns: list[float] = []
        dds: list[float] = []
        turns: list[float] = []
        trades_list: list[int] = []
        exposures_list: list[float] = []

        market = panel["__MARKET__"]
        trade_panel = panel.drop(columns=["__MARKET__"])

        for (tr_s, tr_e, te_s, te_e) in splits:
            test_panel = slice_panel(trade_panel, te_s, te_e)
            test_market = slice_panel(market.to_frame("__MARKET__"), te_s, te_e)["__MARKET__"]
            test_panel_open = slice_panel(panel_open, te_s, te_e)
            test_market_open = slice_panel(market_open.to_frame("__MARKET_OPEN__"), te_s, te_e)["__MARKET_OPEN__"]
            if len(test_panel) < int(params["warmup"]) + 30:
                continue
            m = run_backtest_panel(
                test_panel,
                test_market,
                params,
                costs,
                initial_capital=initial_capital,
                panel_open=test_panel_open,
                market_open=test_market_open,
            )

            cagrs.append(float(m.cagr_pct))
            sharpes.append(float(m.sharpe))
            total_returns.append(float(m.total_return_pct))
            dds.append(float(m.max_drawdown_pct))
            turns.append(float(m.turnover))
            trades_list.append(int(m.trades))
            exposures_list.append(float(m.avg_gross_exposure))

        if len(cagrs) < 3:
            return -1e9

        cagrs_arr = np.asarray(cagrs, dtype=float)
        sharpes_arr = np.asarray(sharpes, dtype=float)
        total_returns_arr = np.asarray(total_returns, dtype=float)
        dds_arr = np.asarray(dds, dtype=float)
        turns_arr = np.asarray(turns, dtype=float)
        trades_arr = np.asarray(trades_list, dtype=float)
        exposures_arr = np.asarray(exposures_list, dtype=float)

        # Enforce a strict max drawdown cap for Calmar-focused objectives.
        # (Otherwise Calmar can be gamed with a few high-return/high-dd windows.)
        if objective_mode in {"calmar", "calmar_combo"}:
            if float(np.max(dds_arr)) > float(dd_cap_pct):
                return -1e9

        # Tunable guardrails for robustness.
        min_trades_avg_default = 8.0 if high_return_mode else 12.0
        min_trades_window_default = 6.0 if high_return_mode else 8.0
        min_exposure_avg_default = 0.25 if high_return_mode else 0.35
        min_trades_avg = float(os.getenv("OPT_MIN_TRADES_AVG", str(min_trades_avg_default)))
        min_trades_window = float(os.getenv("OPT_MIN_TRADES_WINDOW", str(min_trades_window_default)))
        min_exposure_avg = float(os.getenv("OPT_MIN_EXPOSURE_AVG", str(min_exposure_avg_default)))

        # Robust objective: maximize 25th percentile CAGR (close to worst-case).
        robust_cagr = float(np.percentile(cagrs_arr, 25))
        avg_cagr = float(np.mean(cagrs_arr))

        robust_sharpe = float(np.percentile(sharpes_arr, 25)) if sharpes_arr.size else 0.0
        avg_sharpe = float(np.mean(sharpes_arr)) if sharpes_arr.size else 0.0

        # Calmar ratio is (annualized return %) / (max drawdown %).
        # Use a small floor for DD to avoid blow-ups.
        calmar_arr = cagrs_arr / np.maximum(dds_arr, 0.10)
        robust_calmar = float(np.percentile(calmar_arr, 25))
        avg_calmar = float(np.mean(calmar_arr))

        # Profit-first alternative: maximize 25th percentile total return.
        # (Windows are fixed-length half-years, so total return comparisons are meaningful.)
        robust_total_return = float(np.percentile(total_returns_arr, 25))
        avg_total_return = float(np.mean(total_returns_arr))
        weighted_avg_cagr = avg_cagr
        if recency_weight > 0.0:
            # Emphasize later (more recent) windows slightly.
            n = len(cagrs_arr)
            weights = np.linspace(1.0, 1.0 + 2.0 * recency_weight, n)
            weighted_avg_cagr = float(np.average(cagrs_arr, weights=weights))
        cagr_std = float(np.std(cagrs_arr))

        # Penalties
        dd_over = np.maximum(0.0, dds_arr - dd_cap_pct)
        dd_penalty = float(np.mean(dd_over)) * dd_w

        # Penalize negative windows strongly.
        neg_penalty = float(np.mean(np.maximum(0.0, -cagrs_arr))) * neg_w

        # Reduce churn.
        turn_penalty = float(np.mean(turns_arr)) * turn_w

        # Ensure signal isn't too sparse.
        trade_penalty = 0.0
        mean_trades = float(np.mean(trades_arr))
        min_trades = float(np.min(trades_arr))
        if mean_trades < min_trades_avg:
            trade_penalty += (min_trades_avg - mean_trades) * trade_avg_w
        if min_trades < min_trades_window:
            trade_penalty += (min_trades_window - min_trades) * trade_min_w

        # Avoid "mostly in cash" solutions that are extremely sensitive to a handful of trades.
        mean_exposure = float(np.mean(exposures_arr)) if exposures_arr.size else 0.0
        exposure_penalty = 0.0
        if mean_exposure < min_exposure_avg:
            # Stronger weight because cash-heavy solutions can look great in a few windows.
            exposure_penalty = (min_exposure_avg - mean_exposure) * exposure_w

        # Penalize instability across windows.
        instability_penalty = cagr_std * instab_w

        penalty = dd_penalty + neg_penalty + turn_penalty + trade_penalty + exposure_penalty + instability_penalty

        # Default behavior unchanged (recency_weight=0): optimize robust CAGR.
        # If recency_weight>0, blend robust with a recency-weighted average to adapt to late regimes.
        if objective_mode in {"profit", "profit_only", "robust_total_return", "total_return"}:
            final = robust_total_return - penalty
        elif objective_mode in {"calmar", "calmar_combo"}:
            # Calmar-first scoring with modest Sharpe/CAGR influence.
            # Scale CAGR (% units) to a fraction so weights remain intuitive.
            calmar_score = w_calmar * robust_calmar
            sharpe_score = w_sharpe * robust_sharpe
            cagr_score = w_cagr * (robust_cagr / 100.0)
            final = (calmar_score + sharpe_score + cagr_score) - penalty
        else:
            if recency_weight > 0.0:
                final = (0.7 * robust_cagr + 0.3 * weighted_avg_cagr) - penalty
            else:
                final = robust_cagr - penalty

        trial.set_user_attr("robust_cagr_pct", robust_cagr)
        trial.set_user_attr("avg_cagr_pct", avg_cagr)
        trial.set_user_attr("weighted_avg_cagr_pct", weighted_avg_cagr)
        trial.set_user_attr("robust_sharpe", robust_sharpe)
        trial.set_user_attr("avg_sharpe", avg_sharpe)
        trial.set_user_attr("robust_calmar", robust_calmar)
        trial.set_user_attr("avg_calmar", avg_calmar)
        trial.set_user_attr("robust_total_return_pct", robust_total_return)
        trial.set_user_attr("avg_total_return_pct", avg_total_return)
        trial.set_user_attr("objective_mode", objective_mode)
        trial.set_user_attr("recency_weight", recency_weight)
        trial.set_user_attr("cagr_std", cagr_std)
        trial.set_user_attr("penalty", penalty)
        trial.set_user_attr("mean_trades", mean_trades)
        trial.set_user_attr("min_trades", min_trades)
        trial.set_user_attr("mean_exposure", mean_exposure)
        return final

    return objective


async def main():
    engine_mode = os.getenv("OPT_ENGINE", "research").strip().lower()
    eval_only = os.getenv("OPT_EVAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
    eval_params_path_raw = os.getenv("OPT_EVAL_PARAMS_PATH", "").strip()
    apply_eval_env = os.getenv("OPT_EVAL_APPLY_ENV", "1").strip().lower() in {"1", "true", "yes", "on"}

    eval_cfg: dict[str, object] | None = None
    if eval_only:
        if not eval_params_path_raw:
            raise RuntimeError("OPT_EVAL_ONLY=1 requires OPT_EVAL_PARAMS_PATH pointing to a JSON config")
        cfg_path = Path(eval_params_path_raw)
        if not cfg_path.is_file():
            raise RuntimeError(f"Eval config not found: {cfg_path}")
        eval_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if apply_eval_env and isinstance(eval_cfg.get("env"), dict):
            for k, v in eval_cfg["env"].items():
                if k is None:
                    continue
                os.environ[str(k)] = "" if v is None else str(v)

    symbols_env = os.getenv("OPT_SYMBOLS", "").strip()
    symbols: list[str]
    start: str
    end: str
    if eval_only and isinstance(eval_cfg, dict) and isinstance(eval_cfg.get("symbols"), list):
        symbols = [str(s).strip().upper() for s in eval_cfg["symbols"] if str(s).strip()]
    elif symbols_env:
        symbols = [s.strip().upper() for s in symbols_env.split(",") if s.strip()]
    else:
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

    if eval_only and isinstance(eval_cfg, dict) and isinstance(eval_cfg.get("range"), dict):
        start = str(eval_cfg["range"].get("start", "2023-01-01"))
        end = str(eval_cfg["range"].get("end", "2025-12-31"))
    else:
        start = "2023-01-01"
        end = "2025-12-31"

    dd_cap_pct = float(os.getenv("OPT_DD_CAP_PCT", "25"))
    n_trials = int(os.getenv("OPT_TRIALS", "75"))
    recency_weight = float(os.getenv("OPT_RECENCY_WEIGHT", "0"))
    objective_mode = os.getenv("OPT_OBJECTIVE", "robust_cagr").strip().lower()
    market_buffer_side = os.getenv("OPT_MARKET_BUFFER_SIDE", "below").strip().lower()
    fixed_slippage_bps = os.getenv("OPT_FIXED_SLIPPAGE_BPS")
    fixed_commission = os.getenv("OPT_FIXED_COMMISSION_PER_TRADE")
    market_sma_override = os.getenv("OPT_MARKET_SMA")
    market_buffer_override = os.getenv("OPT_MARKET_BUFFER")
    market_force_exit_override = os.getenv("OPT_MARKET_FORCE_EXIT")
    market_trim_risk_off_override = os.getenv("OPT_MARKET_TRIM_RISK_OFF")
    risk_off_exposure_mult_override = os.getenv("OPT_RISK_OFF_EXPOSURE_MULT")
    holdout_start_raw = os.getenv("OPT_HOLDOUT_START")
    holdout_end_raw = os.getenv("OPT_HOLDOUT_END")

    holdout_override: tuple[pd.Timestamp, pd.Timestamp] | None = None
    if (holdout_start_raw is None) ^ (holdout_end_raw is None):
        raise RuntimeError("Set both OPT_HOLDOUT_START and OPT_HOLDOUT_END (YYYY-MM-DD) or neither")
    if holdout_start_raw is not None and holdout_end_raw is not None:
        try:
            hs = pd.Timestamp(holdout_start_raw.strip()).normalize()
            he = pd.Timestamp(holdout_end_raw.strip()).normalize()
        except Exception as e:
            raise RuntimeError("Invalid OPT_HOLDOUT_START/OPT_HOLDOUT_END; use YYYY-MM-DD") from e
        holdout_override = (hs, he)

    if eval_only and isinstance(eval_cfg, dict) and isinstance(eval_cfg.get("holdout"), dict):
        try:
            hs = pd.Timestamp(str(eval_cfg["holdout"].get("start"))).normalize()
            he = pd.Timestamp(str(eval_cfg["holdout"].get("end"))).normalize()
        except Exception as e:
            raise RuntimeError("Invalid eval config holdout.start/holdout.end; use YYYY-MM-DD") from e
        holdout_override = (hs, he)

    initial_capital = 100_000.0

    print("=" * 80)
    print("OPTUNA META-STRATEGY WALK-FORWARD OPTIMIZER")
    print("=" * 80)
    print(f"Engine: {engine_mode}")
    if eval_only:
        print("MODE: EVAL ONLY (skip Optuna; use OPT_EVAL_PARAMS_PATH)")
        print(f"Eval config: {eval_params_path_raw}")
    high_return_mode = os.getenv("OPT_HIGH_RETURN_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
    allow_leverage_raw = os.getenv("OPT_ALLOW_LEVERAGE")
    allow_leverage = (
        (allow_leverage_raw.strip().lower() in {"1", "true", "yes", "on"})
        if allow_leverage_raw is not None
        else high_return_mode
    )
    print(f"High-return mode: {int(high_return_mode)}")
    print(f"Allow leverage:   {int(allow_leverage)}")
    print(f"Universe: {', '.join(symbols)}")
    print(f"Range: {start} -> {end}")
    print(f"Trials: {n_trials}")
    print(f"DD cap: {dd_cap_pct:.1f}%")
    print(f"Recency weight: {recency_weight}")
    print(f"Objective: {objective_mode}")
    print(f"Market buffer side: {market_buffer_side}")
    if fixed_slippage_bps is not None:
        print(f"Fixed slippage bps: {fixed_slippage_bps}")
    if fixed_commission is not None:
        print(f"Fixed commission/trade: {fixed_commission}")
    if market_sma_override is not None:
        print(f"Market SMA (override): {market_sma_override}")
    if market_buffer_override is not None:
        print(f"Market buffer (override): {market_buffer_override}")
    if market_force_exit_override is not None:
        print(f"Force market exits (override): {market_force_exit_override}")
    if market_trim_risk_off_override is not None:
        print(f"Trim exposure in risk-off (override): {market_trim_risk_off_override}")
    if risk_off_exposure_mult_override is not None:
        print(f"Risk-off exposure mult (override): {risk_off_exposure_mult_override}")
    if holdout_override is not None:
        print(f"Holdout override: {holdout_override[0].date()}..{holdout_override[1].date()}")

    trade_close, trade_open, market_close, market_open = await fetch_price_panel(
        symbols, start=start, end=end, market_symbol="SPY"
    )
    panel = trade_close.join(market_close.rename("__MARKET__"), how="inner")
    splits, holdout = build_walkforward_splits(panel.index, holdout_override=holdout_override)

    print(f"Aligned days: {len(panel)}")
    print("Walk-forward splits:")
    for tr_s, tr_e, te_s, te_e in splits:
        print(f"  train {tr_s.date()}..{tr_e.date()}  -> test {te_s.date()}..{te_e.date()}")
    print(f"Holdout (not optimized): {holdout[0].date()}..{holdout[1].date()}")

    if eval_only:
        if not isinstance(eval_cfg, dict):
            raise RuntimeError("Eval config did not load correctly")
        params_raw = eval_cfg.get("params")
        if not isinstance(params_raw, dict):
            raise RuntimeError("Eval config must contain top-level object 'params'")

        mapped: dict[str, float] = {str(k): float(v) for k, v in params_raw.items()}
        costs_cfg = eval_cfg.get("costs")
        if isinstance(costs_cfg, dict):
            slippage_bps = float(costs_cfg.get("slippage_bps", 0.0))
            commission_per_trade = float(costs_cfg.get("commission_per_trade", 0.0))
        else:
            # Fall back to env overrides for costs.
            fixed_slippage_bps_raw = os.getenv("OPT_FIXED_SLIPPAGE_BPS")
            fixed_commission_raw = os.getenv("OPT_FIXED_COMMISSION_PER_TRADE")
            slippage_bps = float(fixed_slippage_bps_raw) if fixed_slippage_bps_raw else 0.0
            commission_per_trade = float(fixed_commission_raw) if fixed_commission_raw else 0.0

        costs = CostModel(slippage_bps=slippage_bps, commission_per_trade=commission_per_trade)

        # Platform-backed EVAL ONLY: run the holdout via BacktestService for parity with UI/backend.
        if engine_mode == "platform":
            if holdout_override is None:
                raise RuntimeError("OPT_ENGINE=platform requires a holdout window (set in eval config or OPT_HOLDOUT_*)")

            hold = await _platform_holdout_eval(
                name=str(eval_cfg.get("name") or eval_cfg.get("id") or "optuna_eval"),
                symbols=symbols,
                start_date=holdout_override[0].date(),
                end_date=holdout_override[1].date(),
                parameters=mapped,
                costs=costs,
                initial_capital=initial_capital,
            )

            print("\n" + "=" * 80)
            print("HOLDOUT PERFORMANCE (EVAL ONLY, PLATFORM ENGINE)")
            print("=" * 80)
            print(f"Total Return: {hold.total_return_pct:+.2f}%")
            print(f"CAGR:         {hold.cagr_pct:+.2f}%")
            print(f"Sharpe:       {hold.sharpe:+.2f}")
            print(f"Max DD:       {hold.max_drawdown_pct:.2f}%")
            print(f"Trades:       {hold.trades}")
            print(f"Turnover:     {hold.turnover:.2f}x")
            print(f"Avg exposure: {hold.avg_gross_exposure:.2f}x")
            return

        hold_panel_full = slice_panel(panel, holdout[0], holdout[1])
        hold_panel = hold_panel_full.drop(columns=["__MARKET__"])
        hold_market = hold_panel_full["__MARKET__"]
        hold_panel_open = slice_panel(trade_open, holdout[0], holdout[1])
        hold_market_open = slice_panel(market_open.to_frame("__MARKET_OPEN__"), holdout[0], holdout[1])["__MARKET_OPEN__"]
        hold = run_backtest_panel(
            hold_panel,
            hold_market,
            mapped,
            costs,
            initial_capital=initial_capital,
            panel_open=hold_panel_open,
            market_open=hold_market_open,
        )

        print("\n" + "=" * 80)
        print("HOLDOUT PERFORMANCE (EVAL ONLY)")
        print("=" * 80)
        print(f"Total Return: {hold.total_return_pct:+.2f}%")
        print(f"CAGR:         {hold.cagr_pct:+.2f}%")
        print(f"Sharpe:       {hold.sharpe:+.2f}")
        print(f"Max DD:       {hold.max_drawdown_pct:.2f}%")
        print(f"Trades:       {hold.trades}")
        print(f"Turnover:     {hold.turnover:.2f}x")
        print(f"Avg exposure: {hold.avg_gross_exposure:.2f}x")
        return

    import optuna

    study = optuna.create_study(direction="maximize")
    objective = objective_factory(
        panel,
        trade_open,
        market_open,
        splits=splits,
        dd_cap_pct=dd_cap_pct,
        initial_capital=initial_capital,
    )

    study.optimize(objective, n_trials=n_trials)

    best = study.best_trial
    print("\n" + "=" * 80)
    print("BEST PARAMETERS (WALK-FORWARD OPTIMIZED)")
    print("=" * 80)
    print(f"Score: {best.value:.3f}")
    print(f"Robust test CAGR (p25): {best.user_attrs.get('robust_cagr_pct', 0):.2f}%")
    if best.user_attrs.get("robust_calmar") is not None:
        print(f"Robust test Calmar (p25): {best.user_attrs.get('robust_calmar', 0):.3f}")
    if best.user_attrs.get("robust_sharpe") is not None:
        print(f"Robust test Sharpe (p25): {best.user_attrs.get('robust_sharpe', 0):.2f}")
    print(f"Avg test CAGR:          {best.user_attrs.get('avg_cagr_pct', 0):.2f}%")
    if best.user_attrs.get("recency_weight", 0):
        print(f"Weighted avg test CAGR: {best.user_attrs.get('weighted_avg_cagr_pct', 0):.2f}%")
    print(f"CAGR std:              {best.user_attrs.get('cagr_std', 0):.2f}")
    print(f"Penalty: {best.user_attrs.get('penalty', 0):.2f}")
    for k, v in best.params.items():
        if market_sma_override is not None and k == "market_sma":
            continue
        if market_buffer_override is not None and k == "market_buffer":
            continue
        if market_force_exit_override is not None and k == "market_force_exit":
            continue
        if market_trim_risk_off_override is not None and k == "market_trim_risk_off":
            continue
        if risk_off_exposure_mult_override is not None and k == "risk_off_exposure_mult":
            continue
        print(f"  {k}: {v}")

    if market_sma_override is not None:
        print(f"  market_sma: {market_sma_override}  (override)")
    if market_buffer_override is not None:
        print(f"  market_buffer: {market_buffer_override}  (override)")
    if market_force_exit_override is not None:
        print(f"  market_force_exit: {market_force_exit_override}  (override)")
    if market_trim_risk_off_override is not None:
        print(f"  market_trim_risk_off: {market_trim_risk_off_override}  (override)")
    if risk_off_exposure_mult_override is not None:
        print(f"  risk_off_exposure_mult: {risk_off_exposure_mult_override}  (override)")

    # Evaluate on holdout
    hold_panel_full = slice_panel(panel, holdout[0], holdout[1])
    hold_panel = hold_panel_full.drop(columns=["__MARKET__"])
    hold_market = hold_panel_full["__MARKET__"]
    hold_panel_open = slice_panel(trade_open, holdout[0], holdout[1])
    hold_market_open = slice_panel(market_open.to_frame("__MARKET_OPEN__"), holdout[0], holdout[1])["__MARKET_OPEN__"]
    best_params = best.params.copy()

    # Map best params to the runner's expected params
    market_sma_val = float(best_params.get("market_sma", 200))
    if market_sma_override is not None:
        try:
            market_sma_val = float(int(float(market_sma_override.strip())))
        except Exception:
            market_sma_val = float(best_params.get("market_sma", 200))

    market_buffer_val = float(best_params.get("market_buffer", 0.0))
    if market_buffer_override is not None:
        try:
            market_buffer_val = float(market_buffer_override.strip())
        except Exception:
            market_buffer_val = float(best_params.get("market_buffer", 0.0))

    market_force_exit_val = float(best_params.get("market_force_exit", 1.0))
    if market_force_exit_override is not None:
        try:
            market_force_exit_val = float(int(float(market_force_exit_override.strip())))
        except Exception:
            market_force_exit_val = float(best_params.get("market_force_exit", 1.0))

    market_trim_risk_off_val = float(best_params.get("market_trim_risk_off", 0.0))
    if market_trim_risk_off_override is not None:
        try:
            market_trim_risk_off_val = float(int(float(market_trim_risk_off_override.strip())))
        except Exception:
            market_trim_risk_off_val = float(best_params.get("market_trim_risk_off", 0.0))

    risk_off_exposure_mult_val = float(best_params.get("risk_off_exposure_mult", 0.5))
    if risk_off_exposure_mult_override is not None:
        try:
            risk_off_exposure_mult_val = float(risk_off_exposure_mult_override.strip())
        except Exception:
            risk_off_exposure_mult_val = float(best_params.get("risk_off_exposure_mult", 0.5))

    mapped: dict[str, float] = {
        "warmup": float(best_params["warmup"]),
        "stop_loss_pct": float(best_params["stop_loss_pct"]),
        "take_profit_pct": float(best_params["take_profit_pct"]),
        "position_size_pct": float(best_params["position_size_pct"]),
        "risk_per_trade_pct": float(best_params.get("risk_per_trade_pct", 0.0)),
        "max_gross_exposure": float(best_params.get("max_gross_exposure", 1.0)),
        "max_positions": float(best_params["max_positions"]),
        "min_position_dollars": float(best_params["min_position_dollars"]),
        "min_hold_days": float(best_params["min_hold_days"]),
        "market_sma": float(market_sma_val),
        "market_buffer": float(market_buffer_val),
        "market_force_exit": float(market_force_exit_val),
        "market_trim_risk_off": float(market_trim_risk_off_val),
        "risk_off_exposure_mult": float(risk_off_exposure_mult_val),
        "rsi_buy": float(best_params["rsi_buy"]),
        "rsi_sell": float(best_params["rsi_sell"]),
        "sma_fast": float(best_params["sma_fast"]),
        "sma_slow": float(best_params["sma_slow"]),
        "band_tolerance": float(best_params["band_tolerance"]),
        "entry_threshold": float(best_params["entry_threshold"]),
        "trend_threshold": float(best_params["trend_threshold"]),
        "decision_threshold": float(best_params["decision_threshold"]),
        "w_ensemble": float(best_params["w_ensemble"]),
        "w_momentum": float(best_params["w_momentum"]),
        "w_meanrev": float(best_params["w_meanrev"]),
        "w_statarb": float(best_params["w_statarb"]),
        "overlay_kill_switch": float(best_params.get("overlay_kill_switch", 0.0)),
        "overlay_kill_dd_pct": float(best_params.get("overlay_kill_dd_pct", 0.0)),
        "overlay_kill_cooldown_days": float(best_params.get("overlay_kill_cooldown_days", 0.0)),
        "overlay_kill_force_exit": float(best_params.get("overlay_kill_force_exit", 0.0)),
        "overlay_vol_enabled": float(best_params.get("overlay_vol_enabled", 0.0)),
        "overlay_vol_target": float(best_params.get("overlay_vol_target", 0.0)),
        "overlay_vol_window": float(best_params.get("overlay_vol_window", 0.0)),
        "overlay_vol_min_mult": float(best_params.get("overlay_vol_min_mult", 0.0)),
        "overlay_vol_max_mult": float(best_params.get("overlay_vol_max_mult", 0.0)),
        "overlay_gap_enabled": float(best_params.get("overlay_gap_enabled", 0.0)),
        "overlay_gap_max_pct": float(best_params.get("overlay_gap_max_pct", 0.0)),
        "overlay_risk_off_adjust": float(best_params.get("overlay_risk_off_adjust", 0.0)),
        "overlay_risk_off_stop_mult": float(best_params.get("overlay_risk_off_stop_mult", 1.0)),
        "overlay_risk_off_take_mult": float(best_params.get("overlay_risk_off_take_mult", 1.0)),
    }

    fixed_slippage_bps_raw = os.getenv("OPT_FIXED_SLIPPAGE_BPS")
    fixed_commission_raw = os.getenv("OPT_FIXED_COMMISSION_PER_TRADE")

    slippage_bps = best_params.get("slippage_bps")
    commission_per_trade = best_params.get("commission_per_trade")
    if fixed_slippage_bps_raw is not None and fixed_slippage_bps_raw.strip() != "":
        try:
            slippage_bps = float(fixed_slippage_bps_raw.strip())
        except Exception:
            pass
    if fixed_commission_raw is not None and fixed_commission_raw.strip() != "":
        try:
            commission_per_trade = float(fixed_commission_raw.strip())
        except Exception:
            pass

    costs = CostModel(
        slippage_bps=float(0.0 if slippage_bps is None else slippage_bps),
        commission_per_trade=float(0.0 if commission_per_trade is None else commission_per_trade),
    )

    hold = run_backtest_panel(
        hold_panel,
        hold_market,
        mapped,
        costs,
        initial_capital=initial_capital,
        panel_open=hold_panel_open,
        market_open=hold_market_open,
    )

    print("\n" + "=" * 80)
    print("HOLDOUT PERFORMANCE (NOT OPTIMIZED)")
    print("=" * 80)
    print(f"Total Return: {hold.total_return_pct:+.2f}%")
    print(f"CAGR:         {hold.cagr_pct:+.2f}%")
    print(f"Sharpe:       {hold.sharpe:+.2f}")
    print(f"Max DD:       {hold.max_drawdown_pct:.2f}%")
    hold_calmar = float(hold.cagr_pct) / max(0.10, float(hold.max_drawdown_pct))
    print(f"Calmar:       {hold_calmar:+.3f}")
    print(f"Trades:       {hold.trades}")
    print(f"Turnover:     {hold.turnover:.2f}x")
    print(f"Avg exposure: {hold.avg_gross_exposure:.2f}x")


if __name__ == "__main__":
    asyncio.run(main())
