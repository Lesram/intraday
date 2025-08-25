import asyncio
import pandas as pd
import numpy as np
import pytest

from backend.strategies.trading_strategies import BaseStrategy, TradingSignal, SignalType


class DummyRiskManager:
	async def assess_position_risk(self, symbol: str, quantity: float, side: str):
		return {"approved": True}

	def get_portfolio_value(self) -> float:
		return 100000.0


class TinyStrategy(BaseStrategy):
	def __init__(self, risk_manager):
		super().__init__("TinyStrategy", risk_manager)

	async def generate_signal(self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame) -> TradingSignal:
		# Simple rule: if last close > first close, BUY else HOLD
		last_close = float(price_data["close"].iloc[-1])
		first_close = float(price_data["close"].iloc[0])
		sig = SignalType.BUY if last_close >= first_close else SignalType.HOLD
		return TradingSignal(symbol=symbol, signal_type=sig, confidence=0.7, target_price=last_close)

	def get_required_features(self) -> list[str]:
		return ["feat"]


def test_strategy_runs_on_tiny_slice_without_lookahead():
	risk = DummyRiskManager()
	strat = TinyStrategy(risk)

	# Minimal OHLCV data (no look-ahead; strictly increasing index)
	df = pd.DataFrame({
		"open": [10, 10.5, 10.7],
		"high": [10.6, 10.8, 11.0],
		"low": [9.9, 10.4, 10.6],
		"close": [10.2, 10.6, 10.9],
		"volume": [1000, 1200, 1300],
	})
	feats = pd.DataFrame({"feat": [0.1, 0.2, 0.3]})

	sig = asyncio.get_event_loop().run_until_complete(strat.generate_signal("ABC", df, feats))

	assert sig.symbol == "ABC"
	assert sig.signal_type in (SignalType.BUY, SignalType.HOLD)
	assert sig.target_price == float(df["close"].iloc[-1])
