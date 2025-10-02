#!/usr/bin/env python3
import sqlite3
import os

# Check the database that the server is actually using
db_path = "trading_platform.db"
print(f"=== CHECKING SERVER DATABASE: {db_path} ===")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check orders table
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders';")
    result = cursor.fetchone()
    if result:
        print("✅ ORDERS TABLE FOUND")
        cursor.execute("PRAGMA table_info(orders);")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        print(f"client_idempotency_key: {'✅ EXISTS' if 'client_idempotency_key' in column_names else '❌ MISSING'}")
        print(f"filled_qty: {'✅ EXISTS' if 'filled_qty' in column_names else '❌ MISSING'}")
        print(f"avg_fill_price: {'✅ EXISTS' if 'avg_fill_price' in column_names else '❌ MISSING'}")
    else:
        print("❌ ORDERS TABLE NOT FOUND")
    
    # Check outbox_events table
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='outbox_events';")
    result = cursor.fetchone()
    if result:
        print("✅ OUTBOX_EVENTS TABLE EXISTS")
    else:
        print("❌ OUTBOX_EVENTS TABLE MISSING")
    
    conn.close()
else:
    print("❌ DATABASE FILE DOES NOT EXIST!")