"""
Example: Model Training and Backtesting
Demonstrates AI model training and strategy backtesting
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

from backend.models.ensemble_model import EnsembleModel
from backend.strategies.trading_strategies import StrategyManager
from backend.risk.risk_manager import RiskManager
from backend.features.feature_engineering import FeatureEngineer
from backend.utils.logger import audit_logger

class BacktestingExample:
    """Example of model training and backtesting"""
    
    def __init__(self):
        self.ensemble_model = EnsembleModel()
        self.risk_manager = RiskManager()
        self.strategy_manager = StrategyManager(
            self.risk_manager, 
            self.ensemble_model
        )
        self.feature_engineer = FeatureEngineer()
        
    def generate_sample_data(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Generate realistic sample market data"""
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=days),
            end=datetime.now(),
            freq='D'
        )
        
        # Use random walk with drift for realistic price movement
        np.random.seed(42)
        returns = np.random.normal(0.0008, 0.02, len(dates))  # 20% daily volatility
        
        # Add some trend and mean reversion
        for i in range(1, len(returns)):
            returns[i] += 0.1 * returns[i-1]  # Some momentum
            returns[i] -= 0.05 * (returns[i-1] - 0.0008)  # Mean reversion
        
        prices = [100.0]  # Starting price
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        # Generate OHLCV data
        data = []
        for i, (date, close_price) in enumerate(zip(dates, prices)):
            volatility = abs(returns[i])
            
            open_price = close_price * np.random.uniform(0.995, 1.005)
            high_price = max(open_price, close_price) * (1 + volatility * np.random.uniform(0, 2))
            low_price = min(open_price, close_price) * (1 - volatility * np.random.uniform(0, 2))
            volume = np.random.randint(500000, 2000000)
            
            data.append({
                'timestamp': date,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        df = pd.DataFrame(data).set_index('timestamp')
        return df
    
    async def train_models(self, symbol: str, data: pd.DataFrame):
        """Train AI models"""
        print(f"🧠 Training AI Models for {symbol}")
        print("-" * 40)
        
        # Generate features
        features = self.feature_engineer.compute_all_features(data)
        print(f"   ✅ Generated {len(features.columns)} features")
        
        # Split data for training
        split_idx = int(len(data) * 0.8)
        train_data = data.iloc[:split_idx]
        train_features = features.iloc[:split_idx]
        
        # Train models
        print("   🔄 Training LSTM model...")
        await self.ensemble_model.lstm_model.train(train_data, train_features, symbol)
        
        print("   🔄 Training XGBoost model...")
        await self.ensemble_model.xgboost_model.train(train_data, train_features, symbol)
        
        print("   🔄 Training Random Forest model...")
        await self.ensemble_model.random_forest_model.train(train_data, train_features, symbol)
        
        print("   ✅ All models trained successfully!")
        
        # Test predictions
        test_data = data.iloc[split_idx:]
        test_features = features.iloc[split_idx:]
        
        if len(test_data) > 0:
            prediction = self.ensemble_model.predict(
                test_data.tail(1), 
                test_features.tail(1), 
                symbol
            )
            print(f"   📊 Test Prediction: ${prediction.ensemble_prediction:.2f}")
            print(f"   📈 Confidence: {prediction.ensemble_confidence:.2%}")
    
    async def backtest_strategy(self, symbol: str, data: pd.DataFrame):
        """Backtest trading strategies"""
        print(f"\n📊 Backtesting Strategies for {symbol}")
        print("-" * 40)
        
        features = self.feature_engineer.compute_all_features(data)
        
        # Simulation parameters
        initial_capital = 100000
        current_capital = initial_capital
        position = 0
        trades = []
        portfolio_values = []
        
        # Walk through data for backtesting
        lookback_window = 50
        
        for i in range(lookback_window, len(data)):
            current_date = data.index[i]
            current_price = data.iloc[i]['close']
            
            # Get historical window for signal generation
            hist_data = data.iloc[i-lookback_window:i]
            hist_features = features.iloc[i-lookback_window:i]
            
            # Generate signal
            try:
                signal = await self.strategy_manager.generate_combined_signal(
                    symbol, hist_data, hist_features
                )
                
                # Execute trades based on signal
                if signal.confidence > 0.6:  # Only trade on confident signals
                    if signal.signal_type.value in ['BUY', 'STRONG_BUY'] and position <= 0:
                        # Buy signal
                        shares_to_buy = min(signal.position_size, current_capital // current_price)
                        if shares_to_buy > 0:
                            cost = shares_to_buy * current_price
                            current_capital -= cost
                            position += shares_to_buy
                            
                            trades.append({
                                'date': current_date,
                                'action': 'BUY',
                                'shares': shares_to_buy,
                                'price': current_price,
                                'confidence': signal.confidence
                            })
                    
                    elif signal.signal_type.value in ['SELL', 'STRONG_SELL'] and position > 0:
                        # Sell signal
                        shares_to_sell = min(position, signal.position_size)
                        if shares_to_sell > 0:
                            proceeds = shares_to_sell * current_price
                            current_capital += proceeds
                            position -= shares_to_sell
                            
                            trades.append({
                                'date': current_date,
                                'action': 'SELL',
                                'shares': shares_to_sell,
                                'price': current_price,
                                'confidence': signal.confidence
                            })
                
                # Calculate portfolio value
                portfolio_value = current_capital + (position * current_price)
                portfolio_values.append({
                    'date': current_date,
                    'value': portfolio_value,
                    'cash': current_capital,
                    'position': position,
                    'price': current_price
                })
                
            except Exception as e:
                audit_logger.error("backtest_error", symbol=symbol, error=str(e))
        
        # Calculate performance metrics
        final_value = portfolio_values[-1]['value'] if portfolio_values else initial_capital
        total_return = (final_value - initial_capital) / initial_capital
        
        # Calculate daily returns for Sharpe ratio
        if len(portfolio_values) > 1:
            values = [pv['value'] for pv in portfolio_values]
            daily_returns = pd.Series(values).pct_change().dropna()
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Print results
        print(f"   💰 Initial Capital: ${initial_capital:,.2f}")
        print(f"   💰 Final Value: ${final_value:,.2f}")
        print(f"   📈 Total Return: {total_return:.2%}")
        print(f"   📊 Number of Trades: {len(trades)}")
        print(f"   ⚡ Sharpe Ratio: {sharpe_ratio:.2f}")
        
        if trades:
            avg_confidence = np.mean([t['confidence'] for t in trades])
            print(f"   🎯 Avg Trade Confidence: {avg_confidence:.2%}")
            
            buy_trades = [t for t in trades if t['action'] == 'BUY']
            sell_trades = [t for t in trades if t['action'] == 'SELL']
            print(f"   📊 Buy Trades: {len(buy_trades)}, Sell Trades: {len(sell_trades)}")
        
        return {
            'initial_capital': initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'trades': trades,
            'portfolio_values': portfolio_values,
            'sharpe_ratio': sharpe_ratio
        }
    
    async def run_example(self):
        """Run the complete example"""
        symbols = ['AAPL', 'GOOGL']
        results = {}
        
        for symbol in symbols:
            print(f"\n{'='*60}")
            print(f"🚀 Processing {symbol}")
            print(f"{'='*60}")
            
            # Generate sample data
            print(f"📊 Generating sample data for {symbol}")
            data = self.generate_sample_data(symbol, days=500)
            print(f"   ✅ Generated {len(data)} days of market data")
            
            # Train models
            await self.train_models(symbol, data)
            
            # Run backtest
            backtest_results = await self.backtest_strategy(symbol, data)
            results[symbol] = backtest_results
        
        # Summary
        print(f"\n{'='*60}")
        print("📈 BACKTEST SUMMARY")
        print(f"{'='*60}")
        
        for symbol, result in results.items():
            print(f"\n{symbol}:")
            print(f"   Return: {result['total_return']:.2%}")
            print(f"   Sharpe: {result['sharpe_ratio']:.2f}")
            print(f"   Trades: {len(result['trades'])}")
        
        print(f"\n✅ Backtesting Example Complete!")
        audit_logger.info("backtest_completed", symbols=list(symbols), results=results)

async def main():
    """Main function"""
    print("🔬 Model Training & Backtesting Example")
    print("=" * 60)
    print("   • Train AI/ML models on historical data")
    print("   • Backtest trading strategies")
    print("   • Calculate performance metrics")
    print("   • Generate trading signals")
    print()
    
    backtester = BacktestingExample()
    await backtester.run_example()

if __name__ == "__main__":
    asyncio.run(main())
