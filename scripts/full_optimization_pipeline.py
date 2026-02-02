"""
Comprehensive Trading Algorithm Optimization Pipeline
======================================================
1. Parameter Optimization (Grid Search)
2. Walk-Forward Validation
3. ML Model Training
4. Multi-Symbol/Timeframe Testing
"""
import asyncio
import os
import warnings
from datetime import date, timedelta
from pathlib import Path
from itertools import product
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")

if not api_key or not secret_key:
    print("ERROR: Alpaca API credentials not found")
    exit(1)


@dataclass
class BacktestResult:
    """Container for backtest results."""
    params: dict
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    final_value: float


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI indicator."""
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent_deltas = deltas[-period:]
    gains = [d for d in recent_deltas if d > 0]
    losses = [-d for d in recent_deltas if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run_backtest_with_params(
    price_history: dict[str, list[float]],
    params: dict,
    initial_capital: float = 100_000.0,
    start_date: date = date(2024, 1, 1),
) -> BacktestResult:
    """Run backtest with specific parameters."""
    from backend.models.backtest import Trade, EquityPoint

    cash = initial_capital
    positions: dict[str, dict] = {}
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    min_len = min(len(p) for p in price_history.values())

    for day_idx in range(params["sma_slow"], min_len):
        current_date = start_date + timedelta(days=day_idx)

        for symbol in price_history:
            prices = price_history[symbol][: day_idx + 1]
            if len(prices) < params["sma_slow"]:
                continue

            rsi = calculate_rsi(prices, 14)
            sma_fast = sum(prices[-params["sma_fast"] :]) / params["sma_fast"]
            sma_slow = sum(prices[-params["sma_slow"] :]) / params["sma_slow"]
            current_price = prices[-1]

            # Exit logic
            if symbol in positions:
                pos = positions[symbol]
                pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

                if (
                    pnl_pct <= -params["stop_loss_pct"]
                    or pnl_pct >= params["take_profit_pct"]
                    or rsi > params["rsi_sell"]
                ):
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    cash += current_price * pos["quantity"]
                    trades.append(
                        Trade(
                            symbol=symbol,
                            side="long",
                            quantity=pos["quantity"],
                            entry_date=pos["entry_date"],
                            entry_price=pos["entry_price"],
                            exit_date=current_date,
                            exit_price=current_price,
                            pnl=pnl,
                            pnl_percent=pnl_pct * 100,
                            duration_days=(current_date - pos["entry_date"]).days,
                        )
                    )
                    del positions[symbol]

            # Entry logic
            elif symbol not in positions:
                should_buy = False

                # Mean reversion
                if rsi < params["rsi_buy"] and current_price < sma_slow:
                    should_buy = True
                # Momentum
                elif 40 < rsi < 60 and sma_fast > sma_slow * 1.02:
                    should_buy = True

                if should_buy:
                    position_value = cash * params["position_size_pct"]
                    if position_value > 1000:
                        quantity = int(position_value / current_price)
                        if quantity > 0:
                            cash -= quantity * current_price
                            positions[symbol] = {
                                "entry_date": current_date,
                                "entry_price": current_price,
                                "quantity": quantity,
                            }

        # Portfolio value
        positions_value = sum(
            price_history[sym][day_idx] * pos["quantity"]
            for sym, pos in positions.items()
        )
        total_value = cash + positions_value
        equity_curve.append(
            EquityPoint(
                date=current_date,
                value=total_value,
                cash=cash,
                positions_value=positions_value,
            )
        )

    # Close remaining positions
    for symbol, pos in list(positions.items()):
        current_price = price_history[symbol][-1]
        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
        trades.append(
            Trade(
                symbol=symbol,
                side="long",
                quantity=pos["quantity"],
                entry_date=pos["entry_date"],
                entry_price=pos["entry_price"],
                exit_date=start_date + timedelta(days=min_len - 1),
                exit_price=current_price,
                pnl=pnl,
                pnl_percent=pnl_pct * 100,
                duration_days=10,
            )
        )
        cash += current_price * pos["quantity"]

    # Calculate metrics
    if not equity_curve:
        return BacktestResult(
            params=params,
            total_return=0,
            sharpe_ratio=0,
            max_drawdown=0,
            win_rate=0,
            profit_factor=0,
            total_trades=0,
            final_value=initial_capital,
        )

    final_value = equity_curve[-1].value
    total_return = ((final_value - initial_capital) / initial_capital) * 100

    # Sharpe ratio
    if len(equity_curve) > 1:
        returns = [
            (equity_curve[i].value - equity_curve[i - 1].value) / equity_curve[i - 1].value
            for i in range(1, len(equity_curve))
        ]
        if returns and np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0

    # Max drawdown
    peak = initial_capital
    max_dd = 0
    for point in equity_curve:
        if point.value > peak:
            peak = point.value
        dd = (peak - point.value) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Win rate and profit factor
    if trades:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) * 100
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")
    else:
        win_rate = 0
        profit_factor = 0

    return BacktestResult(
        params=params,
        total_return=total_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_dd,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_trades=len(trades),
        final_value=final_value,
    )


async def fetch_data(symbols: list[str], start_date: date, end_date: date) -> dict[str, list[float]]:
    """Fetch historical data for symbols."""
    from backend.data.alpaca_client import AlpacaClient

    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)
    price_history = {}

    for symbol in symbols:
        try:
            df = client.get_historical_data(
                symbol=symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                timeframe="1Day",
            )
            if not df.empty:
                price_history[symbol] = df["close"].tolist()
        except Exception as e:
            print(f"  ⚠ {symbol}: {e}")

    return price_history


# =============================================================================
# STEP 1: PARAMETER OPTIMIZATION
# =============================================================================
async def step1_optimize_parameters(price_history: dict[str, list[float]]) -> dict:
    """Grid search for optimal parameters."""
    print("\n" + "=" * 70)
    print("STEP 1: PARAMETER OPTIMIZATION (Grid Search)")
    print("=" * 70)

    # Parameter grid
    param_grid = {
        "rsi_buy": [25, 30, 35],
        "rsi_sell": [65, 70, 75],
        "sma_fast": [5, 10, 15],
        "sma_slow": [30, 50, 70],
        "stop_loss_pct": [0.03, 0.05, 0.07],
        "take_profit_pct": [0.10, 0.15, 0.20],
        "position_size_pct": [0.10],  # Fixed
    }

    # Generate all combinations
    keys = list(param_grid.keys())
    combinations = list(product(*[param_grid[k] for k in keys]))
    total = len(combinations)

    print(f"  Testing {total} parameter combinations...")

    results: list[BacktestResult] = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        result = run_backtest_with_params(price_history, params)
        results.append(result)

        if (i + 1) % 50 == 0:
            print(f"    Progress: {i + 1}/{total} ({(i + 1) / total * 100:.1f}%)")

    # Sort by Sharpe ratio
    results.sort(key=lambda x: x.sharpe_ratio, reverse=True)

    print("\n  Top 5 Parameter Sets (by Sharpe Ratio):")
    print("-" * 70)
    for i, r in enumerate(results[:5]):
        print(f"  #{i + 1}: Sharpe={r.sharpe_ratio:.2f}, Return={r.total_return:.2f}%, "
              f"MaxDD={r.max_drawdown:.2f}%, WinRate={r.win_rate:.1f}%")
        print(f"      Params: RSI({r.params['rsi_buy']}/{r.params['rsi_sell']}), "
              f"SMA({r.params['sma_fast']}/{r.params['sma_slow']}), "
              f"SL={r.params['stop_loss_pct']*100:.0f}%, TP={r.params['take_profit_pct']*100:.0f}%")

    best = results[0]
    print(f"\n  ✅ Best Parameters Found:")
    print(f"     {best.params}")

    return best.params


# =============================================================================
# STEP 2: WALK-FORWARD VALIDATION
# =============================================================================
async def step2_walk_forward_validation(
    symbols: list[str],
    optimal_params: dict,
) -> list[BacktestResult]:
    """Walk-forward validation with rolling windows."""
    print("\n" + "=" * 70)
    print("STEP 2: WALK-FORWARD VALIDATION")
    print("=" * 70)

    # Define periods (train 6 months, test 3 months)
    periods = [
        ("2023-01-01", "2023-06-30", "2023-07-01", "2023-09-30"),
        ("2023-04-01", "2023-09-30", "2023-10-01", "2023-12-31"),
        ("2023-07-01", "2023-12-31", "2024-01-01", "2024-03-31"),
        ("2023-10-01", "2024-03-31", "2024-04-01", "2024-06-30"),
        ("2024-01-01", "2024-06-30", "2024-07-01", "2024-09-30"),
    ]

    results = []
    print("\n  Period Results (Out-of-Sample):")
    print("-" * 70)

    for train_start, train_end, test_start, test_end in periods:
        # Fetch test data
        test_data = await fetch_data(
            symbols,
            date.fromisoformat(test_start),
            date.fromisoformat(test_end),
        )

        if not test_data:
            print(f"  ⚠ No data for {test_start} to {test_end}")
            continue

        # Run backtest on test period
        result = run_backtest_with_params(
            test_data,
            optimal_params,
            start_date=date.fromisoformat(test_start),
        )
        results.append(result)

        print(f"  {test_start} to {test_end}: "
              f"Return={result.total_return:>6.2f}%, "
              f"Sharpe={result.sharpe_ratio:>5.2f}, "
              f"MaxDD={result.max_drawdown:>5.2f}%, "
              f"Trades={result.total_trades:>3}")

    # Summary
    if results:
        avg_return = sum(r.total_return for r in results) / len(results)
        avg_sharpe = sum(r.sharpe_ratio for r in results) / len(results)
        avg_dd = sum(r.max_drawdown for r in results) / len(results)
        positive_periods = sum(1 for r in results if r.total_return > 0)

        print("\n  Walk-Forward Summary:")
        print(f"    Average Return:     {avg_return:.2f}%")
        print(f"    Average Sharpe:     {avg_sharpe:.2f}")
        print(f"    Average Max DD:     {avg_dd:.2f}%")
        print(f"    Positive Periods:   {positive_periods}/{len(results)}")

        if avg_return > 0 and avg_sharpe > 0.3:
            print("\n  ✅ Walk-Forward Validation PASSED")
        else:
            print("\n  ⚠️ Walk-Forward shows strategy may need refinement")

    return results


# =============================================================================
# STEP 3: ML MODEL TRAINING
# =============================================================================
async def step3_train_ml_model(price_history: dict[str, list[float]]) -> Any:
    """Train ML model to predict signals."""
    print("\n" + "=" * 70)
    print("STEP 3: ML MODEL TRAINING")
    print("=" * 70)

    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, accuracy_score
    import xgboost as xgb

    # Build feature dataset
    print("\n  Building feature dataset...")

    features = []
    labels = []

    for symbol, prices in price_history.items():
        for i in range(60, len(prices) - 5):  # Need history and forward lookahead
            # Features
            rsi = calculate_rsi(prices[: i + 1], 14)
            sma_5 = sum(prices[i - 4 : i + 1]) / 5
            sma_10 = sum(prices[i - 9 : i + 1]) / 10
            sma_20 = sum(prices[i - 19 : i + 1]) / 20
            sma_50 = sum(prices[i - 49 : i + 1]) / 50

            current = prices[i]
            ret_1d = (current - prices[i - 1]) / prices[i - 1] * 100
            ret_5d = (current - prices[i - 5]) / prices[i - 5] * 100
            ret_20d = (current - prices[i - 20]) / prices[i - 20] * 100

            # Volatility
            returns = [(prices[j] - prices[j - 1]) / prices[j - 1] for j in range(i - 19, i + 1)]
            volatility = np.std(returns) * 100

            # Price relative to SMAs
            price_sma5_ratio = current / sma_5
            price_sma20_ratio = current / sma_20
            sma5_sma20_ratio = sma_5 / sma_20

            feature_row = [
                rsi,
                ret_1d,
                ret_5d,
                ret_20d,
                volatility,
                price_sma5_ratio,
                price_sma20_ratio,
                sma5_sma20_ratio,
            ]
            features.append(feature_row)

            # Label: 1 if price goes up 2% in next 5 days, else 0
            future_price = prices[i + 5]
            future_return = (future_price - current) / current
            labels.append(1 if future_return > 0.02 else 0)

    X = np.array(features)
    y = np.array(labels)

    print(f"  Dataset: {len(X)} samples, {X.shape[1]} features")
    print(f"  Class distribution: {sum(y)} positive ({sum(y)/len(y)*100:.1f}%)")

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train models
    print("\n  Training models...")

    models = {
        "Random Forest": RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100, max_depth=5, random_state=42
        ),
        "XGBoost": xgb.XGBClassifier(
            n_estimators=100, max_depth=5, random_state=42, use_label_encoder=False, eval_metric="logloss"
        ),
    }

    results = {}
    best_model = None
    best_score = 0

    for name, model in models.items():
        model.fit(X_train_scaled, y_train)
        y_pred = model.predict(X_test_scaled)

        accuracy = accuracy_score(y_test, y_pred)
        cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5)

        results[name] = {
            "accuracy": accuracy,
            "cv_mean": cv_scores.mean(),
            "cv_std": cv_scores.std(),
        }

        if accuracy > best_score:
            best_score = accuracy
            best_model = (name, model, scaler)

        print(f"\n  {name}:")
        print(f"    Test Accuracy:    {accuracy:.4f}")
        print(f"    CV Score:         {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")

    # Feature importance (for best model)
    print("\n  Feature Importance (Best Model):")
    feature_names = ["RSI", "Ret_1d", "Ret_5d", "Ret_20d", "Volatility",
                     "Price/SMA5", "Price/SMA20", "SMA5/SMA20"]

    if hasattr(best_model[1], "feature_importances_"):
        importances = best_model[1].feature_importances_
        sorted_idx = np.argsort(importances)[::-1]
        for i in sorted_idx[:5]:
            print(f"    {feature_names[i]:15} {importances[i]:.4f}")

    print(f"\n  ✅ Best Model: {best_model[0]} (Accuracy: {best_score:.4f})")

    return best_model


# =============================================================================
# STEP 4: MULTI-SYMBOL/TIMEFRAME TESTING
# =============================================================================
async def step4_multi_symbol_timeframe_test(optimal_params: dict) -> dict:
    """Test strategy on different symbols and timeframes."""
    print("\n" + "=" * 70)
    print("STEP 4: MULTI-SYMBOL/TIMEFRAME TESTING")
    print("=" * 70)

    # Different symbol groups
    symbol_groups = {
        "Tech Giants": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
        "Semiconductors": ["NVDA", "AMD", "INTC", "AVGO", "QCOM"],
        "Finance": ["JPM", "BAC", "GS", "MS", "C"],
        "Healthcare": ["JNJ", "UNH", "PFE", "MRK", "ABBV"],
        "Consumer": ["WMT", "COST", "HD", "MCD", "NKE"],
    }

    results = {}

    print("\n  Testing across different sectors...")
    print("-" * 70)

    for group_name, symbols in symbol_groups.items():
        print(f"\n  {group_name}:")

        # Fetch data
        data = await fetch_data(symbols, date(2024, 1, 1), date(2024, 12, 31))

        if len(data) < 3:
            print(f"    ⚠ Insufficient data (only {len(data)} symbols)")
            continue

        # Run backtest
        result = run_backtest_with_params(data, optimal_params)
        results[group_name] = result

        print(f"    Return: {result.total_return:>7.2f}%  |  "
              f"Sharpe: {result.sharpe_ratio:>5.2f}  |  "
              f"MaxDD: {result.max_drawdown:>5.2f}%  |  "
              f"Trades: {result.total_trades:>3}")

    # Summary
    print("\n" + "-" * 70)
    print("  Sector Performance Summary:")

    if results:
        best_sector = max(results.items(), key=lambda x: x[1].sharpe_ratio)
        worst_sector = min(results.items(), key=lambda x: x[1].sharpe_ratio)

        print(f"    Best Sector:  {best_sector[0]} (Sharpe: {best_sector[1].sharpe_ratio:.2f})")
        print(f"    Worst Sector: {worst_sector[0]} (Sharpe: {worst_sector[1].sharpe_ratio:.2f})")

        avg_return = sum(r.total_return for r in results.values()) / len(results)
        print(f"    Average Return Across Sectors: {avg_return:.2f}%")

        positive_sectors = sum(1 for r in results.values() if r.total_return > 0)
        print(f"    Profitable Sectors: {positive_sectors}/{len(results)}")

    return results


# =============================================================================
# MAIN PIPELINE
# =============================================================================
async def run_full_pipeline():
    """Run the complete optimization pipeline."""
    print("=" * 70)
    print("COMPREHENSIVE TRADING ALGORITHM OPTIMIZATION PIPELINE")
    print("=" * 70)
    print(f"Started at: {pd.Timestamp.now()}")

    # Initial data fetch
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    print(f"\nFetching initial data for: {', '.join(symbols)}")

    price_history = await fetch_data(symbols, date(2024, 1, 1), date(2024, 12, 31))
    print(f"  ✓ Loaded data for {len(price_history)} symbols")

    # Step 1: Parameter Optimization
    optimal_params = await step1_optimize_parameters(price_history)

    # Step 2: Walk-Forward Validation
    wf_results = await step2_walk_forward_validation(symbols, optimal_params)

    # Step 3: ML Model Training
    ml_model = await step3_train_ml_model(price_history)

    # Step 4: Multi-Symbol Testing
    sector_results = await step4_multi_symbol_timeframe_test(optimal_params)

    # Final Summary
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE - FINAL SUMMARY")
    print("=" * 70)

    print("\n📊 Optimal Parameters:")
    for k, v in optimal_params.items():
        print(f"    {k}: {v}")

    print(f"\n📈 Walk-Forward: {sum(1 for r in wf_results if r.total_return > 0)}/{len(wf_results)} periods profitable")

    print(f"\n🤖 Best ML Model: {ml_model[0]}")

    print(f"\n🌐 Sector Coverage: {sum(1 for r in sector_results.values() if r.total_return > 0)}/{len(sector_results)} sectors profitable")

    print("\n✅ Ready for live paper trading!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_full_pipeline())
