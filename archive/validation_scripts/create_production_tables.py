#!/usr/bin/env python3
"""Manually create production tables for Phase 5"""

import sqlite3
import sys
from datetime import datetime

def create_production_tables():
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        
        print("🚀 Creating production tables for Phase 5...")
        
        # Create order_events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                broker_order_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_time DATETIME NOT NULL,
                event_data JSON,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id),
                UNIQUE (broker_order_id, event_type, event_time)
            )
        """)
        print("✅ Created order_events table")
        
        # Create daily_ledger table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                day_utc DATE NOT NULL,
                orders_count INTEGER DEFAULT 0,
                submitted_notional_usd DECIMAL(15, 2) DEFAULT 0.00,
                filled_notional_usd DECIMAL(15, 2) DEFAULT 0.00,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (account_id, day_utc)
            )
        """)
        print("✅ Created daily_ledger table")
        
        # Add account_id column to orders if it doesn't exist
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN account_id TEXT")
            print("✅ Added account_id column to orders table")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                print("⚠️ account_id column already exists in orders table")
            else:
                raise
        
        # Create indexes
        indexes = [
            ("idx_orders_created_at", "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at)"),
            ("idx_orders_status", "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)"),
            ("idx_orders_broker_order_id", "CREATE INDEX IF NOT EXISTS idx_orders_broker_order_id ON orders (broker_order_id)"),
            ("idx_orders_symbol_created", "CREATE INDEX IF NOT EXISTS idx_orders_symbol_created ON orders (symbol, created_at)"),
            ("idx_events_broker_order", "CREATE INDEX IF NOT EXISTS idx_events_broker_order ON order_events (broker_order_id)"),
            ("idx_events_order_time", "CREATE INDEX IF NOT EXISTS idx_events_order_time ON order_events (order_id, event_time)"),
            ("idx_events_type_time", "CREATE INDEX IF NOT EXISTS idx_events_type_time ON order_events (event_type, event_time)"),
            ("idx_daily_ledger_account_day", "CREATE INDEX IF NOT EXISTS idx_daily_ledger_account_day ON daily_ledger (account_id, day_utc)")
        ]
        
        for idx_name, idx_sql in indexes:
            cursor.execute(idx_sql)
            print(f"✅ Created index {idx_name}")
        
        # Commit all changes
        conn.commit()
        
        # Verify tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📋 Final database schema ({len(tables)} tables):")
        for table in tables:
            print(f"  ✅ {table}")
            
        if 'order_events' in tables and 'daily_ledger' in tables:
            print("\n🎉 Production database schema ready!")
            return True
        else:
            print("\n❌ Missing required tables")
            return False
            
    except Exception as e:
        print(f"❌ Error creating production tables: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = create_production_tables()
    sys.exit(0 if success else 1)