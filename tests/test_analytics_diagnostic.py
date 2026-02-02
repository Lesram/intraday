"""
Diagnostic script to test the analytics endpoint
Run this to see the exact error
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.services.trade_service import TradeService
from backend.config.settings import get_settings

async def test_analytics():
    settings = get_settings()
    
    # Create database connection using the correct attribute
    db_url = settings.database.url
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("🔍 Testing TradeService.calculate_analytics()...")
            
            service = TradeService(session)
            analytics = await service.calculate_analytics()
            
            print("\n✅ SUCCESS! Analytics data:")
            print(f"  Total Trades: {analytics.get('totalTrades', 0)}")
            print(f"  Win Rate: {analytics.get('winRate', 0)}%")
            print(f"  Total P&L: ${analytics.get('totalRealizedPnL', 0)}")
            print(f"  Best Trade: {analytics.get('bestTrade')}")
            print(f"  Worst Trade: {analytics.get('worstTrade')}")
            print(f"\n📊 Full response keys: {list(analytics.keys())}")
            
        except Exception as e:
            print(f"\n❌ ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_analytics())
