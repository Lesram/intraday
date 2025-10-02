#!/usr/bin/env python3
"""
Database schema fix script.
Recreates the database with the correct schema to fix the missing columns.
"""
import os
import sqlite3
from pathlib import Path

def recreate_database():
    """Recreate the database with the correct schema."""
    
    # Database file path
    db_path = "trading_platform.db"
    
    # Backup existing database if it exists
    if os.path.exists(db_path):
        backup_path = f"{db_path}.backup"
        print(f"Backing up existing database to {backup_path}")
        import shutil
        shutil.copy2(db_path, backup_path)
        
        # Remove old database
        os.remove(db_path)
        print("Removed old database")
    
    # Create new database with correct schema
    print("Creating new database with correct schema...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create orders table with all required columns including fill data
    cursor.execute('''
        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            client_idempotency_key TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty DECIMAL(18,6) NOT NULL,
            order_type TEXT NOT NULL,
            tif TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            filled_qty DECIMAL(18,6) DEFAULT 0,
            avg_fill_price DECIMAL(18,6),
            submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            broker_order_id TEXT,
            attributes TEXT
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX ix_orders_client_idempotency_key ON orders (client_idempotency_key)')
    cursor.execute('CREATE INDEX ix_orders_symbol ON orders (symbol)')
    cursor.execute('CREATE INDEX ix_orders_status ON orders (status)')
    
    # Create users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create positions table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            symbol TEXT NOT NULL,
            qty DECIMAL(18,6) NOT NULL DEFAULT 0,
            avg_cost DECIMAL(18,6),
            market_value DECIMAL(18,6),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create outbox_events table for event sourcing
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbox_events (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            last_error TEXT
        )
    ''')
    
    # Also create the old outbox table for compatibility
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbox (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ Database recreated successfully with correct schema")
    print("✅ All required columns and indexes created")

if __name__ == "__main__":
    recreate_database()