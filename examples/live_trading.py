"""
Example: Live Market Data Streaming
Demonstrates real-time market data processing and signal generation
"""
import asyncio
from datetime import datetime

from backend.config import get_settings
from backend.data.alpaca_client import AlpacaDataClient
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import RiskManager
from backend.strategies.trading_strategies import StrategyManager
from backend.utils.logger import audit_logger


class LiveTradingExample:
    """Example of live trading with real-time data"""

    def __init__(self):
        self.settings = get_settings()
        self.data_client = AlpacaDataClient()
        self.risk_manager = RiskManager()
        self.ensemble_model = EnsembleModel()
        self.strategy_manager = StrategyManager(
            self.risk_manager,
            self.ensemble_model
        )

        self.symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN']
        self.price_buffers = {symbol: [] for symbol in self.symbols}

    async def handle_market_data(self, symbol: str, data: dict):
        """Process incoming market data"""
        try:
            price = data.get('price', 0)
            volume = data.get('volume', 0)
            timestamp = datetime.now()

            # Add to price buffer
            self.price_buffers[symbol].append({
                'timestamp': timestamp,
                'price': price,
                'volume': volume
            })

            # Keep only last 100 data points
            if len(self.price_buffers[symbol]) > 100:
                self.price_buffers[symbol].pop(0)

            # Only process if we have enough data
            if len(self.price_buffers[symbol]) >= 20:
                await self.process_signal(symbol)

        except Exception as e:
            audit_logger.error(
                "market_data_error",
                symbol=symbol,
                error=str(e)
            )

    async def process_signal(self, symbol: str):
        """Generate and process trading signals"""
        try:
            # Get historical data for context
            historical_data = await self.data_client.get_historical_data(
                symbol, '1Day', limit=100
            )

            if historical_data is not None and not historical_data.empty:
                # Generate features and signal
                features = self.strategy_manager.feature_engineer.compute_all_features(
                    historical_data
                )

                signal = await self.strategy_manager.generate_combined_signal(
                    symbol, historical_data, features
                )

                if signal.confidence > 0.7:  # High confidence signals only
                    print(f"\n🚨 HIGH CONFIDENCE SIGNAL: {symbol}")
                    print(f"   Signal: {signal.signal_type.value}")
                    print(f"   Confidence: {signal.confidence:.2%}")
                    print(f"   Position Size: {signal.position_size}")
                    print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")

                    # Risk check
                    side = 'buy' if 'BUY' in signal.signal_type.value else 'sell'
                    risk_result = await self.risk_manager.assess_position_risk(
                        symbol, signal.position_size, side
                    )

                    if risk_result['approved']:
                        print("   ✅ Risk Approved - Ready to Execute")

                        audit_logger.info(
                            "high_confidence_signal",
                            symbol=symbol,
                            signal=signal.signal_type.value,
                            confidence=signal.confidence,
                            position_size=signal.position_size,
                            risk_approved=True
                        )
                    else:
                        print(f"   ❌ Risk Rejected: {risk_result['reason']}")

        except Exception as e:
            audit_logger.error(
                "signal_processing_error",
                symbol=symbol,
                error=str(e)
            )

    async def simulate_live_data(self):
        """Simulate live market data (replace with real WebSocket in production)"""
        import random

        print("📡 Starting Live Data Simulation")
        print("   (In production, connect to real market data feeds)")
        print("-" * 50)

        base_prices = {
            'AAPL': 150.0,
            'GOOGL': 2500.0,
            'MSFT': 300.0,
            'TSLA': 800.0,
            'AMZN': 3000.0
        }

        current_prices = base_prices.copy()

        for _ in range(200):  # Simulate 200 ticks
            for symbol in self.symbols:
                # Random price movement
                change_pct = random.uniform(-0.02, 0.02)  # ±2%
                current_prices[symbol] *= (1 + change_pct)

                # Simulate market data
                market_data = {
                    'price': current_prices[symbol],
                    'volume': random.randint(1000, 10000),
                    'timestamp': datetime.now().isoformat()
                }

                await self.handle_market_data(symbol, market_data)

            await asyncio.sleep(1)  # 1 second between ticks

            # Print progress every 10 ticks
            if _ % 10 == 0:
                print(f"📊 Processed {_ + 1} market ticks...")

    async def run(self):
        """Run the live trading example"""
        try:
            await self.simulate_live_data()

            print("\n📈 Live Trading Example Complete!")
            print("   Summary:")
            for symbol in self.symbols:
                buffer_size = len(self.price_buffers[symbol])
                print(f"   • {symbol}: Processed {buffer_size} data points")

        except KeyboardInterrupt:
            print("\n⏹️  Trading stopped by user")
        except Exception as e:
            print(f"❌ Error: {e}")
            audit_logger.error("live_trading_error", error=str(e))

async def main():
    """Main function"""
    print("🔴 LIVE Trading Example")
    print("=" * 50)
    print("⚠️  This is a SIMULATION - No real trades executed")
    print("   In production, connect to real Alpaca WebSocket feeds")
    print()

    trading_bot = LiveTradingExample()
    await trading_bot.run()

if __name__ == "__main__":
    asyncio.run(main())
