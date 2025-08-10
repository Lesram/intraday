# Add the parent directory to the Python path
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

"""
Example: Basic Trading Bot
Demonstrates how to use the algorithmic trading platform components
"""
import asyncio

import numpy as np
import pandas as pd

# Import platform components
from backend.config import get_settings
from backend.features.feature_engineering import FeatureEngineer
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import RiskManager
from backend.strategies.trading_strategies import StrategyManager
from backend.utils.logger import audit_logger


async def main():
    """Main trading bot example"""

    print("🤖 Starting Basic Trading Bot Example")
    print("=" * 50)

    # Initialize components
    settings = get_settings()
    risk_manager = RiskManager()
    ensemble_model = EnsembleModel()
    strategy_manager = StrategyManager(risk_manager, ensemble_model)
    feature_engineer = FeatureEngineer()

    # Create sample market data (normally from Alpaca API)
    symbols = ['AAPL', 'GOOGL', 'MSFT']

    for symbol in symbols:
        print(f"\n📊 Processing {symbol}")
        print("-" * 30)

        # Generate sample price data
        dates = pd.date_range(start='2024-01-01', end='2024-01-31', freq='D')
        np.random.seed(42)

        base_price = 150.0
        returns = np.random.normal(0.001, 0.02, len(dates))
        prices = [base_price]

        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))

        price_data = pd.DataFrame({
            'timestamp': dates,
            'open': [p * np.random.uniform(0.99, 1.01) for p in prices],
            'high': [p * np.random.uniform(1.005, 1.02) for p in prices],
            'low': [p * np.random.uniform(0.98, 0.995) for p in prices],
            'close': prices,
            'volume': np.random.randint(100000, 1000000, len(dates))
        }).set_index('timestamp')

        # Generate technical features
        features = feature_engineer.compute_technical_indicators(price_data)
        print(f"   ✅ Generated {len(features.columns)} technical features")

        # Get AI prediction
        prediction = ensemble_model.predict(price_data, features, symbol)
        print(f"   🧠 AI Prediction: ${prediction.ensemble_prediction:.2f}")
        print(f"   📈 Confidence: {prediction.ensemble_confidence:.2%}")

        # Generate trading signal
        signal = await strategy_manager.generate_combined_signal(
            symbol, price_data, features
        )
        print(f"   🎯 Trading Signal: {signal.signal_type.value}")
        print(f"   💪 Signal Confidence: {signal.confidence:.2%}")

        if signal.position_size > 0:
            print(f"   📦 Position Size: {signal.position_size:.0f} shares")
            print(f"   🎯 Target Price: ${signal.target_price:.2f}")

            # Risk assessment
            side = 'buy' if signal.signal_type.value in ['BUY', 'STRONG_BUY'] else 'sell'
            risk_check = await risk_manager.assess_position_risk(
                symbol, signal.position_size, side
            )

            if risk_check['approved']:
                print("   ✅ Risk Check: APPROVED")
                print(f"      Risk Score: {risk_check['risk_score']:.3f}")

                # In a real implementation, would execute trade here
                print("   💼 Trade Execution: SIMULATED")

                audit_logger.info(
                    "trade_simulation",
                    symbol=symbol,
                    signal=signal.signal_type.value,
                    position_size=signal.position_size,
                    confidence=signal.confidence,
                    risk_approved=True
                )
            else:
                print("   ❌ Risk Check: REJECTED")
                print(f"      Reason: {risk_check['reason']}")
        else:
            print("   ⏸️  No position recommended")

    # Get portfolio risk metrics
    print("\n⚖️  Portfolio Risk Analysis")
    print("-" * 30)

    risk_metrics = risk_manager.get_risk_metrics()
    print(f"   VaR (95%): {risk_metrics.get('var_95', 0):.3f}")
    print(f"   CVaR (95%): {risk_metrics.get('cvar_95', 0):.3f}")
    print(f"   Portfolio Beta: {risk_metrics.get('portfolio_beta', 0):.2f}")
    print(f"   Sharpe Ratio: {risk_metrics.get('sharpe_ratio', 0):.2f}")

    print("\n🎉 Trading Bot Example Complete!")
    print("   • Analyzed multiple symbols")
    print("   • Generated AI predictions")
    print("   • Created trading signals")
    print("   • Performed risk assessments")
    print("   • Logged all activities")

if __name__ == "__main__":
    asyncio.run(main())
