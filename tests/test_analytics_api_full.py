"""
Test the full Analytics API endpoint with authentication to see exact error.
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.api.routes.trades import get_trade_analytics, TradeAnalytics
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"


# Mock user for authentication
class MockUser:
    email = "admin@example.com"
    roles = ["admin", "trader"]


async def test_analytics_api():
    """Test the full Analytics API endpoint with Pydantic validation"""
    
    print("=" * 80)
    print("TESTING ANALYTICS API ENDPOINT WITH PYDANTIC VALIDATION")
    print("=" * 80)
    
    # Create database connection
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        try:
            print("\n✓ Database connection established")
            
            # Call the actual API endpoint function
            print("\n📊 Calling API endpoint: get_trade_analytics()...")
            
            response = await get_trade_analytics(
                start_date=None,
                end_date=None,
                symbol=None,
                strategy_id=None,
                db=session,
                user=MockUser()
            )
            
            print(f"\n✅ SUCCESS - API endpoint returned valid response")
            print(f"   Type: {type(response).__name__}")
            print(f"\n📈 Analytics Data:")
            print(f"   Total Trades: {response.totalTrades}")
            print(f"   Total Volume: ${response.totalVolume:,.2f}")
            print(f"   Buy Trades: {response.buyTrades}")
            print(f"   Sell Trades: {response.sellTrades}")
            print(f"   Avg Trade Value: ${response.avgTradeValue:,.2f}")
            print(f"   Total Realized P&L: ${response.totalRealizedPnL:,.2f}")
            print(f"   Winning Trades: {response.winningTrades}")
            print(f"   Losing Trades: {response.losingTrades}")
            print(f"   Win Rate: {response.winRate:.1f}%")
            
            # Try to convert to dict (as FastAPI would for JSON response)
            print(f"\n🔄 Converting to JSON dict...")
            json_dict = response.model_dump()
            print(f"   ✓ Successfully converted to JSON")
            print(f"   Keys: {list(json_dict.keys())}")
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERROR OCCURRED:")
            print(f"   Type: {type(e).__name__}")
            print(f"   Message: {str(e)}")
            
            # Show full traceback
            import traceback
            print(f"\n📋 Full Traceback:")
            traceback.print_exc()
            
            return False
        
        finally:
            await engine.dispose()
            print("\n✓ Database connection closed")


if __name__ == "__main__":
    print("\n🚀 Starting Analytics API Endpoint Test\n")
    
    success = asyncio.run(test_analytics_api())
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - Analytics API endpoint works correctly")
        print("   If frontend still shows 0, check browser console for errors")
    else:
        print("❌ TEST FAILED - Analytics API endpoint has errors")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
