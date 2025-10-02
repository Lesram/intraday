"""
Quick Start Guide - Launch the Platform
Run this to start the complete algorithmic trading platform
"""
import os
from pathlib import Path
import subprocess
import sys


def check_requirements():
    """Check if required packages are installed"""
    print("🔍 Checking requirements...")

    required_packages = [
        'fastapi', 'uvicorn', 'pydantic', 'pandas', 'numpy',
        'scikit-learn', 'tensorflow', 'xgboost', 'redis',
        'alpaca-trade-api', 'structlog', 'websockets'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        print("💡 Install with: pip install -r requirements.txt")
        return False
    else:
        print("✅ All required packages are installed")
        return True

def setup_environment():
    """Setup environment variables"""
    print("⚙️  Setting up environment...")

    env_file = Path(".env")
    if not env_file.exists():
        print("📝 Creating .env file from template...")

        env_content = """# Algorithmic Trading Platform Configuration
# Copy from env.example and update with your values

# Alpaca API (Get from https://alpaca.markets/)
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Paper trading
# ALPACA_BASE_URL=https://api.alpaca.markets  # Live trading (BE CAREFUL!)

# Database
REDIS_URL=redis://localhost:6379/0

# Risk Management
MAX_POSITION_SIZE=10000
MAX_PORTFOLIO_RISK=0.02
STOP_LOSS_PERCENT=0.05
TAKE_PROFIT_PERCENT=0.10

# Trading
TRADING_ENABLED=false  # Set to true when ready to trade
PAPER_TRADING=true
AUTO_TRADING=false

# API Configuration
API_HOST=localhost
API_PORT=8000
DEBUG=true

# Model Configuration
MODEL_UPDATE_INTERVAL=3600
ENSEMBLE_WEIGHTS_LSTM=0.4
ENSEMBLE_WEIGHTS_XGBOOST=0.35
ENSEMBLE_WEIGHTS_RF=0.25
"""

        with open(".env", "w") as f:
            f.write(env_content)
        print("✅ Created .env file - Please update with your API keys!")
        return False
    else:
        print("✅ Environment file exists")
        return True

def start_platform():
    """Start the platform services"""
    print("🚀 Starting Algorithmic Trading Platform...")
    print("-" * 50)

    # Start the main application
    try:
        print("📡 Starting FastAPI server...")
        print("🌐 Access the API at: http://localhost:8000")
        print("📚 API Documentation: http://localhost:8000/docs")
        print("⚡ Real-time WebSocket: ws://localhost:8000/ws/market-data")
        print()
        print("⏹️  Press Ctrl+C to stop the platform")
        print("-" * 50)

        # Launch the main application
        subprocess.run([sys.executable, "main.py"], check=True)

    except KeyboardInterrupt:
        print("\n⏹️  Platform stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting platform: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def main():
    """Main quick start function"""
    print("🤖 Algorithmic Trading Platform - Quick Start")
    print("=" * 60)
    print("   🏦 Institutional-grade trading platform")
    print("   🧠 AI/ML powered predictions")
    print("   ⚖️  Advanced risk management")
    print("   📊 Multiple trading strategies")
    print("   🔄 MLOps pipeline")
    print("   📡 Real-time market data")
    print("=" * 60)
    print()

    # Check if we're in the right directory
    if not os.path.exists("main.py"):
        print("❌ Please run this from the algotrading_platform directory")
        print("💡 cd algotrading_platform")
        return

    # Check requirements
    if not check_requirements():
        return

    # Setup environment
    env_ready = setup_environment()
    if not env_ready:
        print("\n⚠️  IMPORTANT: Update your .env file with API keys before trading!")
        print("   • Get Alpaca API keys from: https://alpaca.markets/")
        print("   • Set TRADING_ENABLED=true when ready")
        print("   • Keep PAPER_TRADING=true for safety")
        print()

        response = input("Continue with demo mode? (y/N): ")
        if response.lower() != 'y':
            return

    # Start the platform
    start_platform()

if __name__ == "__main__":
    main()
