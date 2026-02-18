"""Optuna meta-strategy *research* backtest engine.

This module hosts the research harness execution logic so it can be reused by:
- the Optuna script (research/optimizer workflows)
- the backend API when users explicitly select the research engine

It is intentionally separate from the platform backtest engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    slippage_bps: float
    commission_per_trade: float


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    trades: int
    turnover: float
    avg_gross_exposure: float


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    qty: int
    entry_dt: pd.Timestamp
    entry_price: float
    exit_dt: pd.Timestamp
    exit_price: float
    commission: float
    exit_reason: str | None = None


@dataclass(frozen=True)
class ResearchBacktestOutput:
    metrics: BacktestMetrics
    equity_curve: list[tuple[pd.Timestamp, float, float, float]]  # (dt, equity, cash, positions_value)
    closed_trades: list[ClosedTrade]


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
    signal = macd * 0.9
    return float(macd), float(signal)


def _trend_regime(series: np.ndarray, sma_fast: int, sma_slow: int, trend_threshold: float) -> bool:
    if series.size < max(sma_fast, sma_slow):
        return False
    fast = _sma(series, sma_fast)
    slow = _sma(series, sma_slow)
    if slow == 0:
        return False
    spread = abs(fast - slow) / abs(slow)
    return spread >= trend_threshold


def _meta_signal(prices: np.ndarray, params: dict[str, float]) -> tuple[str, float]:
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

    in_trend = _trend_regime(prices, sma_fast=sma_fast, sma_slow=sma_slow, trend_threshold=trend_threshold)

    rsi = _rsi(prices, 14)
    macd, macd_sig = _macd(prices)
    sma_f = _sma(prices, sma_fast)
    sma_s = _sma(prices, sma_slow)
    bb_u, _bb_m, bb_l = _bollinger(prices, 20)

    lookback = 60
    window = prices[-lookback:]
    mean = float(np.mean(window))
    std = float(np.std(window))
    z = (current - mean) / std if std > 0 else 0.0

    buy_votes = 0.0
    sell_votes = 0.0

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

    mr_buy = 0.0
    mr_sell = 0.0
    if current < bb_l * (1.0 + band_tol) and rsi < rsi_buy:
        mr_buy = min(0.9, (rsi_buy - rsi) / 20.0)
    elif current > bb_u * (1.0 - band_tol) and rsi > rsi_sell:
        mr_sell = min(0.9, (rsi - rsi_sell) / 20.0)

    mom_buy = 0.0
    mom_sell = 0.0
    if macd > macd_sig and current > sma_f > sma_s:
        mom_buy = min(0.85, abs(macd - macd_sig) * 10.0)
    elif macd < macd_sig and current < sma_f < sma_s:
        mom_sell = min(0.85, abs(macd - macd_sig) * 10.0)

    sa_buy = 0.0
    sa_sell = 0.0
    if z < -entry_z:
        sa_buy = min(0.9, abs(z) / 5.0)
    elif z > entry_z:
        sa_sell = min(0.9, abs(z) / 5.0)

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

    if in_trend:
        buy_votes += w_ens * ens_buy + w_mom * mom_buy + 0.25 * w_mr * mr_buy + 0.25 * w_sa * sa_buy
        sell_votes += w_ens * ens_sell + w_mom * mom_sell + 0.25 * w_mr * mr_sell + 0.25 * w_sa * sa_sell
    else:
        buy_votes += w_ens * ens_buy + w_mr * mr_buy + w_sa * sa_buy + 0.25 * w_mom * mom_buy
        sell_votes += w_ens * ens_sell + w_mr * mr_sell + w_sa * sa_sell + 0.25 * w_mom * mom_sell

    threshold = params["decision_threshold"]
    if buy_votes >= threshold and buy_votes > sell_votes:
        return "buy", min(1.0, buy_votes)
    if sell_votes >= threshold and sell_votes > buy_votes:
        return "sell", min(1.0, sell_votes)
    return "hold", 0.0


def run_backtest_panel_detailed(
    panel: pd.DataFrame,
    market: pd.Series,
    params: dict[str, float],
    costs: CostModel,
    initial_capital: float,
    *,
    panel_open: pd.DataFrame | None = None,
    market_open: pd.Series | None = None,
    execution_mode: str = "close",
    market_buffer_side: str = "below",
    allow_leverage: bool = False,
) -> ResearchBacktestOutput:
    """Research backtest.

    This keeps the original research semantics, but is packaged so the backend/UI can run it.

    execution_mode:
      - "close": signal + execute on same close
      - "next_open": signal on prior close, execute on next open
    """

    warmup = int(params["warmup"])
    stop_loss = float(params["stop_loss_pct"])
    take_profit = float(params["take_profit_pct"])
    position_size_pct = float(params["position_size_pct"])
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

    # Parameterized overlays (optional; defaults keep legacy behavior)
    overlay_kill_switch = bool(int(params.get("overlay_kill_switch", 0)))
    overlay_kill_dd_pct = float(params.get("overlay_kill_dd_pct", 0.0))
    overlay_kill_cooldown_days = int(params.get("overlay_kill_cooldown_days", 0))
    overlay_kill_force_exit = bool(int(params.get("overlay_kill_force_exit", 0)))

    overlay_vol_enabled = bool(int(params.get("overlay_vol_enabled", 0)))
    overlay_vol_target = float(params.get("overlay_vol_target", 0.0))
    overlay_vol_window = int(params.get("overlay_vol_window", 20))
    overlay_vol_min_mult = float(params.get("overlay_vol_min_mult", 0.5))
    overlay_vol_max_mult = float(params.get("overlay_vol_max_mult", 1.5))

    overlay_gap_enabled = bool(int(params.get("overlay_gap_enabled", 0)))
    overlay_gap_max_pct = float(params.get("overlay_gap_max_pct", 0.0))

    overlay_risk_off_adjust = bool(int(params.get("overlay_risk_off_adjust", 0)))
    overlay_risk_off_stop_mult = float(params.get("overlay_risk_off_stop_mult", 1.0))
    overlay_risk_off_take_mult = float(params.get("overlay_risk_off_take_mult", 1.0))

    market_buffer_side = (market_buffer_side or "below").strip().lower()

    next_open_mode = execution_mode.strip().lower() in {"next_open", "nextopen", "open"}
    if next_open_mode:
        if panel_open is None or market_open is None:
            raise RuntimeError("execution_mode=next_open requires panel_open and market_open")
        if not panel_open.index.equals(panel.index):
            raise RuntimeError("panel_open index must match panel index")
        if not market_open.index.equals(market.index):
            raise RuntimeError("market_open index must match market index")

    cash = float(initial_capital)
    positions: dict[str, dict[str, float]] = {}

    equity_curve: list[tuple[pd.Timestamp, float, float, float]] = []
    gross_exposures: list[float] = []
    turnover_notional = 0.0
    fills = 0

    closed_trades: list[ClosedTrade] = []

    symbols = list(panel.columns)
    closes = panel.to_numpy(dtype=float)
    market_prices = market.to_numpy(dtype=float)
    opens = panel_open.to_numpy(dtype=float) if panel_open is not None else None

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

    idx_to_dt = list(panel.index)

    kill_cooldown_remaining = 0
    kill_peak_equity = float(initial_capital)

    def _update_kill_state(equity_now: float) -> bool:
        nonlocal kill_peak_equity, kill_cooldown_remaining
        if equity_now > kill_peak_equity:
            kill_peak_equity = equity_now
        dd = (kill_peak_equity - equity_now) / kill_peak_equity if kill_peak_equity > 0 else 0.0
        if overlay_kill_switch and overlay_kill_dd_pct > 0 and dd >= overlay_kill_dd_pct:
            if kill_cooldown_remaining <= 0:
                kill_cooldown_remaining = max(1, overlay_kill_cooldown_days)
        return kill_cooldown_remaining > 0

    def _vol_size_mult(idx: int) -> float:
        if not overlay_vol_enabled or overlay_vol_target <= 0 or overlay_vol_window < 2:
            return 1.0
        start = max(1, idx - overlay_vol_window)
        window = market_prices[start : idx + 1]
        if window.size < 3:
            return 1.0
        rets = np.diff(window) / np.where(window[:-1] == 0, 1, window[:-1])
        realized = float(np.std(rets)) * np.sqrt(252.0)
        if realized <= 0:
            return 1.0
        mult = overlay_vol_target / realized
        return float(np.clip(mult, overlay_vol_min_mult, overlay_vol_max_mult))

    def _exit_position(*, i_exec: int, symbol: str, exec_price: float, reason: str | None = None) -> None:
        nonlocal cash, turnover_notional, fills
        pos = positions.get(symbol)
        if pos is None:
            return
        qty = float(pos["qty"])
        notional = exec_price * qty
        cash += notional
        cash -= float(costs.commission_per_trade)
        turnover_notional += abs(notional)
        fills += 1

        entry_i = int(pos.get("entry_i", i_exec))
        entry_dt = pd.Timestamp(idx_to_dt[entry_i])
        exit_dt = pd.Timestamp(idx_to_dt[i_exec])
        closed_trades.append(
            ClosedTrade(
                symbol=symbol,
                qty=int(qty),
                entry_dt=entry_dt,
                entry_price=float(pos["entry_price"]),
                exit_dt=exit_dt,
                exit_price=float(exec_price),
                commission=float(costs.commission_per_trade) * 2.0,
                exit_reason=reason,
            )
        )
        del positions[symbol]

    if next_open_mode:
        for i in range(warmup + 1, closes.shape[0]):
            decision_i = i - 1
            positions_value_close = 0.0
            for sym, pos in positions.items():
                jj = symbols.index(sym)
                positions_value_close += float(closes[decision_i, jj]) * float(pos["qty"])
            equity_close = cash + positions_value_close
            kill_active = _update_kill_state(equity_close)

            risk_on = market_on(decision_i)
            kill_force_exit = kill_active and overlay_kill_force_exit

            stop_loss_adj = stop_loss
            take_profit_adj = take_profit
            if (not risk_on) and overlay_risk_off_adjust:
                stop_loss_adj = stop_loss * overlay_risk_off_stop_mult
                take_profit_adj = take_profit * overlay_risk_off_take_mult

            # exits (decided on close, executed next open)
            for symbol in list(positions.keys()):
                j = symbols.index(symbol)
                price_close = float(closes[decision_i, j])
                price_open = float(opens[i, j])
                pos = positions[symbol]
                entry = float(pos["entry_price"])
                pnl_pct = (price_close - entry) / entry if entry else 0.0

                held_days = int(decision_i - int(pos.get("entry_i", decision_i)))
                action, _conf = _meta_signal(closes[: decision_i + 1, j], params)
                should_exit = (pnl_pct <= -stop_loss_adj) or (pnl_pct >= take_profit_adj) or (
                    action == "sell" and held_days >= min_hold_days
                )
                exit_reason = None
                if market_force_exit and (not risk_on):
                    should_exit = True
                    exit_reason = "market_force_exit"
                if kill_force_exit:
                    should_exit = True
                    exit_reason = "overlay_kill_switch"
                if should_exit and exit_reason is None:
                    if pnl_pct <= -stop_loss_adj:
                        exit_reason = "stop_loss"
                    elif pnl_pct >= take_profit_adj:
                        exit_reason = "take_profit"
                    elif action == "sell" and held_days >= min_hold_days:
                        exit_reason = "optuna_meta_sell"
                if should_exit:
                    exec_price = price_open * (1.0 - costs.slippage_bps / 10000.0)
                    _exit_position(i_exec=i, symbol=symbol, exec_price=exec_price, reason=exit_reason)

            # risk-off trimming (decided on close, executed next open)
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
                        bucket = 0 if action == "sell" else (1 if action == "hold" else 2)
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
                        exec_price = price_open * (1.0 - costs.slippage_bps / 10000.0)
                        _exit_position(i_exec=i, symbol=sym, exec_price=exec_price, reason="market_trim_risk_off")
                        positions_value_for_trim = 0.0
                        for _s2, _p2 in positions.items():
                            kk = symbols.index(_s2)
                            positions_value_for_trim += float(closes[decision_i, kk]) * float(_p2["qty"])

            # entries (decided on close, executed next open)
            open_slots = max_positions - len(positions)
            if open_slots > 0 and risk_on and (not kill_active):
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

                size_mult = _vol_size_mult(decision_i)
                for symbol, _conf, price_open in candidates[:open_slots]:
                    if overlay_gap_enabled and overlay_gap_max_pct > 0:
                        prev_close = float(closes[decision_i, symbols.index(symbol)])
                        if prev_close > 0:
                            gap = abs(price_open - prev_close) / prev_close
                            if gap > overlay_gap_max_pct:
                                continue
                    exec_price = price_open * (1.0 + costs.slippage_bps / 10000.0)

                    gross_notional_open = 0.0
                    for sym, pos in positions.items():
                        jj = symbols.index(sym)
                        gross_notional_open += float(opens[i, jj]) * float(pos["qty"])

                    gross_room = max(0.0, equity_now_open * max_gross_exposure - gross_notional_open)
                    notional_cap = equity_now_open * position_size_pct * size_mult

                    if risk_per_trade_pct > 0 and stop_loss > 0:
                        risk_budget_dollars = equity_now_open * risk_per_trade_pct
                        risk_based_notional = risk_budget_dollars / max(stop_loss_adj, 1e-9)
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
                    cash -= float(costs.commission_per_trade)
                    turnover_notional += abs(notional)
                    fills += 1

                    positions[symbol] = {"entry_price": float(exec_price), "qty": float(qty), "entry_i": float(i)}

            # equity mark-to-market on close
            positions_value = 0.0
            for symbol, pos in positions.items():
                j = symbols.index(symbol)
                positions_value += float(closes[i, j]) * float(pos["qty"])

            equity_now = cash + positions_value
            equity_curve.append((pd.Timestamp(idx_to_dt[i]), float(equity_now), float(cash), float(positions_value)))
            gross_exposures.append(positions_value / equity_now if equity_now > 0 else 0.0)
            if kill_cooldown_remaining > 0:
                kill_cooldown_remaining -= 1

    else:
        for i in range(warmup, closes.shape[0]):
            positions_value_close = 0.0
            for sym, pos in positions.items():
                jj = symbols.index(sym)
                positions_value_close += float(closes[i, jj]) * float(pos["qty"])
            equity_close = cash + positions_value_close
            kill_active = _update_kill_state(equity_close)

            risk_on = market_on(i)
            kill_force_exit = kill_active and overlay_kill_force_exit

            stop_loss_adj = stop_loss
            take_profit_adj = take_profit
            if (not risk_on) and overlay_risk_off_adjust:
                stop_loss_adj = stop_loss * overlay_risk_off_stop_mult
                take_profit_adj = take_profit * overlay_risk_off_take_mult

            # exits
            for symbol in list(positions.keys()):
                j = symbols.index(symbol)
                price = float(closes[i, j])
                pos = positions[symbol]
                entry = float(pos["entry_price"])
                pnl_pct = (price - entry) / entry if entry else 0.0

                held_days = int(i - int(pos.get("entry_i", i)))
                action, _conf = _meta_signal(closes[: i + 1, j], params)
                should_exit = (pnl_pct <= -stop_loss_adj) or (pnl_pct >= take_profit_adj) or (
                    action == "sell" and held_days >= min_hold_days
                )
                exit_reason = None
                if market_force_exit and (not risk_on):
                    should_exit = True
                    exit_reason = "market_force_exit"
                if kill_force_exit:
                    should_exit = True
                    exit_reason = "overlay_kill_switch"

                if should_exit and exit_reason is None:
                    if pnl_pct <= -stop_loss_adj:
                        exit_reason = "stop_loss"
                    elif pnl_pct >= take_profit_adj:
                        exit_reason = "take_profit"
                    elif action == "sell" and held_days >= min_hold_days:
                        exit_reason = "optuna_meta_sell"

                if should_exit:
                    exec_price = price * (1.0 - costs.slippage_bps / 10000.0)
                    _exit_position(i_exec=i, symbol=symbol, exec_price=exec_price, reason=exit_reason)

            # risk-off trimming
            open_slots = max_positions - len(positions)
            if (not risk_on) and (not market_force_exit) and market_trim_risk_off and positions:
                positions_value_for_trim = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_for_trim += float(closes[i, jj]) * float(pos["qty"])
                equity_now = cash + positions_value_for_trim

                risk_off_cap = max(0.0, max_gross_exposure * risk_off_exposure_mult)
                target_positions_value = equity_now * risk_off_cap

                if positions_value_for_trim > target_positions_value and equity_now > 0:
                    ranked: list[tuple[int, float, str]] = []
                    for sym in positions.keys():
                        jj = symbols.index(sym)
                        action, conf = _meta_signal(closes[: i + 1, jj], params)
                        bucket = 0 if action == "sell" else (1 if action == "hold" else 2)
                        ranked.append((bucket, float(conf), sym))
                    ranked.sort(key=lambda x: (x[0], x[1]))

                    for _bucket, _conf, sym in ranked:
                        if positions_value_for_trim <= target_positions_value:
                            break
                        jj = symbols.index(sym)
                        price = float(closes[i, jj])
                        exec_price = price * (1.0 - costs.slippage_bps / 10000.0)
                        _exit_position(i_exec=i, symbol=sym, exec_price=exec_price, reason="market_trim_risk_off")
                        positions_value_for_trim = 0.0
                        for _s2, _p2 in positions.items():
                            kk = symbols.index(_s2)
                            positions_value_for_trim += float(closes[i, kk]) * float(_p2["qty"])

            if open_slots > 0 and risk_on and (not kill_active):
                positions_value_for_sizing = 0.0
                for sym, pos in positions.items():
                    jj = symbols.index(sym)
                    positions_value_for_sizing += float(closes[i, jj]) * float(pos["qty"])
                equity_now = cash + positions_value_for_sizing

                candidates: list[tuple[str, float, float]] = []
                for symbol in symbols:
                    if symbol in positions:
                        continue
                    j = symbols.index(symbol)
                    action, conf = _meta_signal(closes[: i + 1, j], params)
                    if action == "buy" and conf > 0:
                        candidates.append((symbol, float(conf), float(closes[i, j])))

                candidates.sort(key=lambda x: x[1], reverse=True)

                size_mult = _vol_size_mult(i)
                for symbol, _conf, price in candidates[:open_slots]:
                    if overlay_gap_enabled and overlay_gap_max_pct > 0 and i > 0:
                        prev_close = float(closes[i - 1, symbols.index(symbol)])
                        if prev_close > 0:
                            gap = abs(price - prev_close) / prev_close
                            if gap > overlay_gap_max_pct:
                                continue
                    exec_price = price * (1.0 + costs.slippage_bps / 10000.0)
                    gross_notional = 0.0
                    for sym, pos in positions.items():
                        jj = symbols.index(sym)
                        gross_notional += float(closes[i, jj]) * float(pos["qty"])

                    gross_room = max(0.0, equity_now * max_gross_exposure - gross_notional)
                    notional_cap = equity_now * position_size_pct * size_mult

                    if risk_per_trade_pct > 0 and stop_loss > 0:
                        risk_budget_dollars = equity_now * risk_per_trade_pct
                        risk_based_notional = risk_budget_dollars / max(stop_loss_adj, 1e-9)
                        desired_notional = min(risk_based_notional, notional_cap)
                    else:
                        desired_notional = notional_cap

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
                    cash -= float(costs.commission_per_trade)
                    turnover_notional += abs(notional)
                    fills += 1

                    positions[symbol] = {"entry_price": float(exec_price), "qty": float(qty), "entry_i": float(i)}

            positions_value = 0.0
            for symbol, pos in positions.items():
                j = symbols.index(symbol)
                positions_value += float(closes[i, j]) * float(pos["qty"])

            equity_now = cash + positions_value
            equity_curve.append((pd.Timestamp(idx_to_dt[i]), float(equity_now), float(cash), float(positions_value)))
            gross_exposures.append(positions_value / equity_now if equity_now > 0 else 0.0)

    if not equity_curve:
        metrics = BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0)
        return ResearchBacktestOutput(metrics=metrics, equity_curve=[], closed_trades=[])

    equity_arr = np.asarray([p[1] for p in equity_curve], dtype=float)
    daily_returns = np.diff(equity_arr) / np.where(equity_arr[:-1] == 0, 1, equity_arr[:-1])

    final_value = float(equity_arr[-1])
    total_return_pct = (final_value / initial_capital - 1.0) * 100.0
    cagr_pct = _cagr(final_value, initial_capital, trading_days=len(equity_arr)) * 100.0
    sharpe = _sharpe(daily_returns)
    max_dd_pct = _max_drawdown(equity_arr) * 100.0

    turnover = turnover_notional / initial_capital if initial_capital > 0 else 0.0
    avg_gross_exposure = float(np.mean(gross_exposures)) if gross_exposures else 0.0

    metrics = BacktestMetrics(
        total_return_pct=float(total_return_pct),
        cagr_pct=float(cagr_pct),
        sharpe=float(sharpe),
        max_drawdown_pct=float(max_dd_pct),
        trades=int(fills),
        turnover=float(turnover),
        avg_gross_exposure=float(avg_gross_exposure),
    )

    return ResearchBacktestOutput(metrics=metrics, equity_curve=equity_curve, closed_trades=closed_trades)


def run_backtest_panel(
    panel: pd.DataFrame,
    market: pd.Series,
    params: dict[str, float],
    costs: CostModel,
    initial_capital: float,
    *,
    panel_open: pd.DataFrame | None = None,
    market_open: pd.Series | None = None,
    execution_mode: str = "close",
    market_buffer_side: str = "below",
    allow_leverage: bool = False,
) -> BacktestMetrics:
    out = run_backtest_panel_detailed(
        panel,
        market,
        params,
        costs,
        initial_capital,
        panel_open=panel_open,
        market_open=market_open,
        execution_mode=execution_mode,
        market_buffer_side=market_buffer_side,
        allow_leverage=allow_leverage,
    )
    return out.metrics
