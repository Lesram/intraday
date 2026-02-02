"""
Test the full API endpoint including Pydantic validation.
This simulates what happens when the frontend calls the endpoint.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.api.routes.trades import get_trade_history, TradeHistoryResponse
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"


# Mock user for authentication
class MockUser:
    email = "admin@example.com"
    roles = ["admin", "trader"]


async def test_api_endpoint():
    """Test the full API endpoint with Pydantic validation"""
    
    print("=" * 80)
    print("TESTING FULL API ENDPOINT WITH PYDANTIC VALIDATION")
    print("=" * 80)
    
    # Create database connection
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        try:
            print("\n✓ Database connection established")
            
            # Call the actual API endpoint function
            print("\n📊 Calling API endpoint: get_trade_history()...")
            
            response = await get_trade_history(
                start_date=None,
                end_date=None,
                symbol=None,
                strategy_id=None,
                side=None,
                limit=100,
                offset=0,
                db=session,
                user=MockUser()
            )
            
            print(f"\n✅ SUCCESS - API endpoint returned valid response")
            print(f"   Type: {type(response).__name__}")
            print(f"   Total trades: {response.total}")
            print(f"   Trades returned: {len(response.trades)}")
            
            # Validate response structure
            if response.trades:
                first_trade = response.trades[0]
                print(f"\n📝 First Trade Validation:")
                print(f"   orderId: {first_trade.orderId}")
                print(f"   symbol: {first_trade.symbol}")
                print(f"   avgFillPrice: {first_trade.avgFillPrice}")
                print(f"   filledQty: {first_trade.filledQty}")
                print(f"   orderType: {first_trade.orderType}")
                print(f"   submittedAt: {first_trade.submittedAt}")
                
                # Try to convert to dict (as FastAPI would)
                print(f"\n🔄 Converting to JSON dict...")
                json_dict = response.model_dump()
                print(f"   ✓ Successfully converted to JSON")
                print(f"   Keys: {list(json_dict.keys())}")
                if json_dict['trades']:
                    print(f"   First trade keys: {list(json_dict['trades'][0].keys())}")
            
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
    print("\n🚀 Starting Full API Endpoint Test\n")
    
    success = asyncio.run(test_api_endpoint())
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - API endpoint works with Pydantic validation")
        print("   The frontend should now be able to fetch trade history successfully!")
    else:
        print("❌ TEST FAILED - API endpoint has validation errors")
    print("=" * 80)
