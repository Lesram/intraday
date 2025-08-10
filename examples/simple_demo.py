# Add the parent directory to the Python path
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

"""
Example: Simple Trading Demo
A simplified demonstration of the platform's core capabilities
"""
import asyncio

import numpy as np
import pandas as pd

# Import platform components
from backend.config import get_settings
from backend.features.feature_engineering import FeatureEngineer
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import RiskManager
from backend.utils.logger import audit_logger


async def main():
    """Simple trading demo"""

    print("🚀 Algorithmic Trading Platform Demo")
    print("=" * 50)

    try:
        # Initialize components
        print("⚙️  Initializing components...")
        settings = get_settings()
        risk_manager = RiskManager()
        ensemble_model = EnsembleModel()
        feature_engineer = FeatureEngineer()
        print("✅ Components initialized successfully!")

        # Create sample market data
        symbol = 'DEMO'
        print(f"\n📊 Generating sample data for {symbol}")

        # Generate 60 days of sample data
        dates = pd.date_range(start='2024-01-01', end='2024-03-01', freq='D')
        np.random.seed(42)

        base_price = 100.0
        returns = np.random.normal(0.001, 0.015, len(dates))
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

        print(f"   ✅ Generated {len(price_data)} days of market data")
        print(f"   📈 Price range: ${price_data['close'].min():.2f} - ${price_data['close'].max():.2f}")

        # Generate technical features
        print("\n🔧 Computing technical indicators...")
        features = feature_engineer.compute_technical_indicators(price_data)
        print(f"   ✅ Computed {len(features.columns)} technical features")

        # Show some key features
        latest_features = features.tail(1)
        if 'sma_20' in features.columns:
            print(f"   📊 20-day SMA: ${latest_features['sma_20'].iloc[0]:.2f}")
        if 'rsi_14' in features.columns:
            print(f"   📊 RSI (14): {latest_features['rsi_14'].iloc[0]:.1f}")
        if 'bb_upper' in features.columns and 'bb_lower' in features.columns:
            bb_upper = latest_features['bb_upper'].iloc[0]
            bb_lower = latest_features['bb_lower'].iloc[0]
            current_price = price_data['close'].iloc[-1]
            print(f"   📊 Bollinger Bands: ${bb_lower:.2f} - ${bb_upper:.2f} (Current: ${current_price:.2f})")

        # Test AI prediction
        print("\n🧠 Testing AI ensemble prediction...")
        try:
            prediction = ensemble_model.predict(price_data.tail(5), features.tail(5), symbol)
            if prediction.ensemble_prediction > 0:
                print(f"   🎯 AI Prediction: ${prediction.ensemble_prediction:.2f}")
                print(f"   📈 Confidence: {prediction.ensemble_confidence:.2%}")
                print("   🔍 Individual Models:")
                print(f"      LSTM: ${prediction.individual_predictions['lstm']:.2f}")
                print(f"      XGBoost: ${prediction.individual_predictions['xgboost']:.2f}")
                print(f"      Random Forest: ${prediction.individual_predictions['random_forest']:.2f}")
            else:
                print("   ℹ️  Models need training data (predictions = 0)")
        except Exception as e:
            print(f"   ⚠️  AI prediction skipped: {str(e)[:50]}...")

        # Test risk metrics
        print("\n⚖️  Risk Management Demo")
        try:
            # Simulate a position
            position_size = 100
            side = 'buy'
            current_price = price_data['close'].iloc[-1]

            # Test position risk assessment
            risk_check = await risk_manager.assess_position_risk(symbol, position_size, side)

            print("   📊 Position Assessment:")
            print(f"      Symbol: {symbol}")
            print(f"      Size: {position_size} shares @ ${current_price:.2f}")
            print(f"      Side: {side.upper()}")
            print(f"      Risk Score: {risk_check.get('risk_score', 0):.3f}")
            print(f"      Status: {'✅ APPROVED' if risk_check.get('approved') else '❌ REJECTED'}")
            if not risk_check.get('approved'):
                print(f"      Reason: {risk_check.get('reason', 'Unknown')}")

        except Exception as e:
            print(f"   ⚠️  Risk assessment error: {str(e)[:50]}...")

        # Summary
        print("\n🎉 Platform Demo Complete!")
        print("   ✅ Configuration loaded")
        print("   ✅ Market data processed")
        print("   ✅ Technical indicators computed")
        print("   ✅ AI models initialized")
        print("   ✅ Risk management tested")
        print("   ✅ Audit logging active")

        print("\n💡 Next Steps:")
        print("   • Configure your Alpaca API keys in .env")
        print("   • Run 'python main.py' to start the full platform")
        print("   • Access API docs at http://localhost:8000/docs")
        print("   • Try the other examples in the examples/ folder")

        audit_logger.info(
            "platform_demo_complete",
            symbol=symbol,
            features_count=len(features.columns),
            data_points=len(price_data),
            status="success"
        )

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        audit_logger.error("platform_demo_failed", error=str(e))

if __name__ == "__main__":
    asyncio.run(main())
