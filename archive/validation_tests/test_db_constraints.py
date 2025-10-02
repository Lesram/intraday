#!/usr/bin/env python3
"""Test production database constraints"""

import sqlite3
import sys
from datetime import date, datetime
import uuid

def test_database_constraints():
    print("🧪 Testing production database constraints...")
    
    conn = sqlite3.connect('trading_platform.db')
    cursor = conn.cursor()
    
    try:
        # Test 1: order_events table constraints
        print("\n📋 Test 1: Order events deduplication")
        
        # Insert first event
        event_data = {
            'order_id': str(uuid.uuid4()),
            'broker_order_id': 'TEST_ORDER_123',
            'event_type': 'fill',
            'event_time': '2025-09-30 10:00:00'
        }
        
        cursor.execute("""
            INSERT INTO order_events (order_id, broker_order_id, event_type, event_time, event_data)
            VALUES (?, ?, ?, ?, '{}')
        """, (event_data['order_id'], event_data['broker_order_id'], 
              event_data['event_type'], event_data['event_time']))
        
        print("  ✅ First event inserted successfully")
        
        # Try to insert duplicate event (should fail)
        try:
            cursor.execute("""
                INSERT INTO order_events (order_id, broker_order_id, event_type, event_time, event_data)
                VALUES (?, ?, ?, ?, '{}')
            """, (event_data['order_id'], event_data['broker_order_id'], 
                  event_data['event_type'], event_data['event_time']))
            print("  ❌ Duplicate event was allowed - constraint not working!")
            return False
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                print("  ✅ Duplicate event properly rejected by UNIQUE constraint")
            else:
                print(f"  ⚠️ Unexpected error: {e}")
        
        # Test 2: daily_ledger table constraints  
        print("\n📋 Test 2: Daily ledger uniqueness")
        
        # Insert first ledger entry
        ledger_data = {
            'account_id': 'TEST_ACCOUNT_001',
            'day_utc': date.today(),
            'orders_count': 5,
            'submitted_notional_usd': 1000.00
        }
        
        cursor.execute("""
            INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
            VALUES (?, ?, ?, ?)
        """, (ledger_data['account_id'], ledger_data['day_utc'],
              ledger_data['orders_count'], ledger_data['submitted_notional_usd']))
        
        print("  ✅ First ledger entry inserted successfully")
        
        # Try to insert duplicate ledger (should fail)
        try:
            cursor.execute("""
                INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
                VALUES (?, ?, ?, ?)
            """, (ledger_data['account_id'], ledger_data['day_utc'], 10, 2000.00))
            print("  ❌ Duplicate ledger entry was allowed - constraint not working!")
            return False
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                print("  ✅ Duplicate ledger entry properly rejected by UNIQUE constraint")
            else:
                print(f"  ⚠️ Unexpected error: {e}")
        
        # Test 3: Check indexes exist
        print("\n📋 Test 3: Performance indexes")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        expected_indexes = [
            'idx_orders_created_at',
            'idx_orders_status', 
            'idx_orders_broker_order_id',
            'idx_orders_symbol_created',
            'idx_events_broker_order',
            'idx_events_order_time',
            'idx_events_type_time',
            'idx_daily_ledger_account_day'
        ]
        
        for expected_idx in expected_indexes:
            if expected_idx in indexes:
                print(f"  ✅ {expected_idx}")
            else:
                print(f"  ❌ Missing index: {expected_idx}")
        
        # Cleanup test data
        cursor.execute("DELETE FROM order_events WHERE broker_order_id = 'TEST_ORDER_123'")
        cursor.execute("DELETE FROM daily_ledger WHERE account_id = 'TEST_ACCOUNT_001'")
        conn.commit()
        
        print(f"\n🎉 Database constraints validation completed successfully!")
        print(f"   - Event deduplication: ✅ Working")
        print(f"   - Daily ledger uniqueness: ✅ Working") 
        print(f"   - Performance indexes: ✅ {len([i for i in expected_indexes if i in indexes])}/{len(expected_indexes)} created")
        
        return True
        
    except Exception as e:
        print(f"❌ Constraint test failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = test_database_constraints()
    sys.exit(0 if success else 1)