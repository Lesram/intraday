#!/usr/bin/env python3
"""Check database tables and schema"""

import sqlite3
import sys

def check_database_schema():
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("🔍 Existing database tables:")
        for table in tables:
            print(f"  ✅ {table[0]}")
        
        # Check if order_events exists
        if ('order_events',) in tables:
            print("\n⚠️  order_events table already exists!")
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='order_events'")
            schema = cursor.fetchone()
            print(f"Schema: {schema[0] if schema else 'Not found'}")
        
        # Check if daily_ledger exists  
        if ('daily_ledger',) in tables:
            print("\n⚠️  daily_ledger table already exists!")
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='daily_ledger'")
            schema = cursor.fetchone()
            print(f"Schema: {schema[0] if schema else 'Not found'}")
            
        # Check orders table schema
        cursor.execute("PRAGMA table_info(orders)")
        columns = cursor.fetchall()
        print("\n📋 Orders table columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

if __name__ == "__main__":
    check_database_schema()