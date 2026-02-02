"""Backtest sanity check script."""
import asyncio
from datetime import date


async def run_backtest():
    from backend.services.backtest_service import BacktestService
    from backend.models.backtest import EquityPoint, Trade
    from backend.data.alpaca_client import MarketData
    from backend.services.backtest_service import PortfolioState

    class MockSession:
        async def execute(self, q):
            class R:
                def scalar_one_or_none(self):
                    return None

                def scalars(self):
                    class S:
                        def all(self):
                            return []

                    return S()

            return R()

        async def add(self, o):
            pass

        async def commit(self):
            pass

        async def refresh(self, o):
            pass

    service = BacktestService(MockSession())

    print("=" * 60)
    print("BACKTEST SANITY CHECK")
    print("=" * 60)
    print()

    # Test 1: Signal generation with mock data (downtrend = oversold)
    price_history = {"AAPL": [150 - i * 0.3 for i in range(100)]}
    market_data = {
        "AAPL": MarketData(
            symbol="AAPL",
            timestamp="2024-06-01",
            open=105,
            high=107,
            low=103,
            close=105,
            volume=1000000,
        )
    }
    portfolio = PortfolioState(100000)

    signals = service._generate_signals_with_history(
        strategy_type="mean_reversion",
        parameters={"rsi_buy": 35, "rsi_sell": 65, "sma_fast": 20, "sma_slow": 50},
        market_data=market_data,
        price_history=price_history,
        portfolio=portfolio,
        current_date=date(2024, 6, 1),
    )

    print("Test 1: Signal Generation (Mean Reversion)")
    print(f"  Signals generated: {len(signals)}")
    if signals:
        sig = signals[0]
        print(f"  Action: {sig['action']}")
        print(f"  Symbol: {sig['symbol']}")
        print(f"  Confidence: {sig['confidence']}")
        print(f"  RSI: {sig['indicators']['rsi']:.2f}")
        print(f"  Trend: {sig['indicators']['trend']}")
    print()

    # Test 2: Momentum strategy
    price_history_up = {"TSLA": [100 + i * 0.5 for i in range(100)]}
    market_data_up = {
        "TSLA": MarketData(
            symbol="TSLA",
            timestamp="2024-06-01",
            open=148,
            high=152,
            low=147,
            close=150,
            volume=2000000,
        )
    }

    signals_mom = service._generate_signals_with_history(
        strategy_type="momentum",
        parameters={"rsi_buy": 50, "rsi_sell": 70, "sma_fast": 10, "sma_slow": 30},
        market_data=market_data_up,
        price_history=price_history_up,
        portfolio=portfolio,
        current_date=date(2024, 6, 1),
    )

    print("Test 2: Signal Generation (Momentum)")
    print(f"  Signals generated: {len(signals_mom)}")
    if signals_mom:
        sig = signals_mom[0]
        print(f"  Action: {sig['action']}")
        print(f"  Symbol: {sig['symbol']}")
    print()

    # Test 3: Metrics with correctly shaped Trade model
    equity_curve = [
        EquityPoint(
            date=date(2024, 1, i + 1),
            value=100000 + i * 100,
            cash=50000,
            positions_value=50000 + i * 100,
        )
        for i in range(30)
    ]

    trades = [
        Trade(
            symbol="AAPL",
            side="long",
            quantity=10,
            entry_date=date(2024, 1, 5),
            entry_price=150.0,
            exit_date=date(2024, 1, 15),
            exit_price=160.0,
            pnl=100.0,
            pnl_percent=6.67,
            duration_days=10,
        ),
        Trade(
            symbol="MSFT",
            side="long",
            quantity=5,
            entry_date=date(2024, 1, 10),
            entry_price=300.0,
            exit_date=date(2024, 1, 20),
            exit_price=290.0,
            pnl=-50.0,
            pnl_percent=-3.33,
            duration_days=10,
        ),
        Trade(
            symbol="GOOGL",
            side="long",
            quantity=8,
            entry_date=date(2024, 1, 12),
            entry_price=140.0,
            exit_date=date(2024, 1, 22),
            exit_price=155.0,
            pnl=120.0,
            pnl_percent=10.71,
            duration_days=10,
        ),
    ]

    metrics = service.calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=100000,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 30),
    )

    print("Test 3: Metrics Calculation")
    print(f"  Total Return: {metrics.total_return:.2f}%")
    print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics.max_drawdown:.2f}%")
    print(f"  Win Rate: {metrics.win_rate:.1f}%")
    print(f"  Total Trades: {metrics.total_trades}")
    print(f"  Profit Factor: {metrics.profit_factor:.2f}")
    print(f"  Avg Trade PnL: ${metrics.avg_trade_pnl:.2f}")
    print()

    # Validate metrics sanity
    all_ok = True
    issues = []

    if metrics.win_rate < 0 or metrics.win_rate > 100:
        issues.append(f"Win rate out of range: {metrics.win_rate}")
        all_ok = False

    if metrics.total_trades != len(trades):
        issues.append(f"Trade count mismatch: {metrics.total_trades} vs {len(trades)}")
        all_ok = False

    if metrics.profit_factor < 0:
        issues.append(f"Negative profit factor: {metrics.profit_factor}")
        all_ok = False

    # Expected: 2 wins, 1 loss = 66.7% win rate
    expected_win_rate = 66.67
    if abs(metrics.win_rate - expected_win_rate) > 1:
        issues.append(f"Win rate mismatch: {metrics.win_rate:.2f} vs expected {expected_win_rate:.2f}")
        all_ok = False

    print("=" * 60)
    if all_ok:
        print("BACKTEST SANITY CHECK: PASSED ✓")
    else:
        print("BACKTEST SANITY CHECK: ISSUES FOUND")
        for issue in issues:
            print(f"  ⚠ {issue}")
    print("=" * 60)
    print()

    if all_ok:
        print("✅ Ready for algorithm training phase!")
    else:
        print("⚠ Address issues before proceeding")


if __name__ == "__main__":
    asyncio.run(run_backtest())
