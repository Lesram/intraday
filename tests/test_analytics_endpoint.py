"""
Test the Analytics endpoint to diagnose why it shows 0 activity.
"""

import asyncio
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.services.trade_service import TradeService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"


async def test_analytics():
    """Test the analytics calculation"""
    
    print("=" * 80)
    print("TESTING ANALYTICS ENDPOINT")
    print("=" * 80)
    
    # Create database connection
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        try:
            print("\n✓ Database connection established")
            
            # Create TradeService instance
            trade_service = TradeService(session)
            print("✓ TradeService instance created")
            
            # Call calculate_analytics - same as API endpoint
            print("\n📊 Calculating analytics (no filters)...")
            analytics = await trade_service.calculate_analytics(
                start_date=None,
                end_date=None,
                symbol=None,
                strategy_id=None
            )
            
            print(f"\n✅ SUCCESS - Analytics calculated")
            print(f"\n📈 Analytics Results:")
            print(f"   Total Trades: {analytics['total_trades']}")
            print(f"   Total Volume: ${analytics['total_volume']:,.2f}")
            print(f"   Buy Trades: {analytics['buy_trades']}")
            print(f"   Sell Trades: {analytics['sell_trades']}")
            print(f"   Avg Trade Value: ${analytics['avg_trade_value']:,.2f}")
            print(f"   Total Realized P&L: ${analytics['total_realized_pnl']:,.2f}")
            print(f"   Winning Trades: {analytics['winning_trades']}")
            print(f"   Losing Trades: {analytics['losing_trades']}")
            print(f"   Win Rate: {analytics['win_rate']:.1f}%")
            print(f"   Avg Winning Trade: ${analytics['avg_winning_trade']:,.2f}")
            print(f"   Avg Losing Trade: ${analytics['avg_losing_trade']:,.2f}")
            
            if analytics['best_trade']:
                print(f"\n🏆 Best Trade:")
                print(f"   Symbol: {analytics['best_trade']['symbol']}")
                print(f"   P&L: ${analytics['best_trade']['pnl']:,.2f}")
                print(f"   Date: {analytics['best_trade']['date']}")
            
            if analytics['worst_trade']:
                print(f"\n📉 Worst Trade:")
                print(f"   Symbol: {analytics['worst_trade']['symbol']}")
                print(f"   P&L: ${analytics['worst_trade']['pnl']:,.2f}")
                print(f"   Date: {analytics['worst_trade']['date']}")
            
            print(f"\n📅 P&L by Day: {len(analytics['pnl_by_day'])} day(s)")
            for day in analytics['pnl_by_day'][:5]:  # Show first 5 days
                print(f"   {day['date']}: ${day['pnl']:,.2f} ({day['trades']} trades)")
            
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
    print("\n🚀 Starting Analytics Endpoint Test\n")
    
    success = asyncio.run(test_analytics())
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - Analytics endpoint working correctly")
    else:
        print("❌ TEST FAILED - Analytics endpoint has errors")
    print("=" * 80)
