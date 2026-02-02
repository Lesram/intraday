"""
Test Position Reconciliation Service
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from backend.infra.schemas import Order
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.services.position_reconciliation_service import PositionReconciliationService

DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"

async def main():
    print("\n" + "="*80)
    print("TESTING POSITION RECONCILIATION SERVICE")
    print("="*80)
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        # Create services
        alpaca_client = AlpacaBrokerClient()
        reconciliation_service = PositionReconciliationService(session, alpaca_client)
        
        # Get all filled orders
        query = select(Order).where(Order.status == 'filled').order_by(Order.submitted_at)
        result = await session.execute(query)
        orders = list(result.scalars().all())
        
        print(f"\n📝 Found {len(orders)} filled orders\n")
        
        # Get position status for all orders
        order_ids = [str(order.id) for order in orders]
        status_map = await reconciliation_service.get_position_status_for_orders(order_ids)
        
        print("📊 POSITION STATUS BY ORDER:\n")
        print("-" * 80)
        
        for order in orders:
            order_id_str = str(order.id)
            status_info = status_map.get(order_id_str, {})
            
            is_imported = order.attributes and order.attributes.get('imported') == True
            source = "📥 Imported" if is_imported else "🔸 Local"
            
            position_status = status_info.get('position_status', 'unknown')
            note = status_info.get('note', 'No info')
            
            # Status icon
            if position_status == 'open':
                status_icon = "✅ OPEN"
                status_color = "green"
            elif position_status in ['closed', 'partially_closed']:
                status_icon = "⚠️ CLOSED"
                status_color = "yellow"
            elif position_status == 'closed_by_sell':
                status_icon = "✓ SOLD"
                status_color = "gray"
            else:
                status_icon = "❓ UNKNOWN"
                status_color = "gray"
            
            print(f"{order.submitted_at.date()} | {order.symbol:6} | {order.side.upper():4} | {source:12} | {status_icon:10} | {float(order.filled_qty):6.2f} @ ${float(order.avg_fill_price or 0):8.2f}")
            print(f"   └─ {note}")
            print()
        
        print("-" * 80)
        
        # Get summary
        print("\n📈 RECONCILIATION SUMMARY:\n")
        summary = await reconciliation_service.get_reconciliation_summary()
        
        print(f"  Total Filled Buy Orders: {summary['total_filled_buys']}")
        print(f"  Open Positions: {summary['open_positions']} ✅")
        print(f"  Closed Positions: {summary['closed_positions']} ⚠️")
        print(f"  Unknown Status: {summary.get('unknown', 0)} ❓")
        
        if summary['discrepancies']:
            print(f"\n  ⚠️ DISCREPANCIES FOUND: {summary['discrepancy_count']}")
            print("\n  Orders that are closed but have no sell order in database:")
            for disc in summary['discrepancies']:
                print(f"    • {disc['symbol']}: {disc['qty']} shares on {disc['submitted_at'][:10]}")
                print(f"      Reason: {disc['reason']}")
        else:
            print("\n  ✅ No discrepancies - all positions accounted for")
        
        print("\n" + "="*80)
        print("✅ POSITION RECONCILIATION TEST COMPLETE")
        print("="*80)
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
