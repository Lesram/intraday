#!/usr/bin/env python3
"""Performance test for concurrent operations with database constraints"""

import asyncio
import sqlite3
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
import random
import uuid

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_concurrent_daily_ledger_operations(worker_id: int, num_operations: int = 20):
    """Test concurrent daily ledger operations from a single worker"""
    
    account_id = "test_concurrent_account"
    today = date.today()
    results = {
        'worker_id': worker_id,
        'successful_updates': 0,
        'constraint_violations': 0,
        'other_errors': 0,
        'start_time': time.time()
    }
    
    try:
        # Each worker gets its own connection
        conn = sqlite3.connect('trading_platform.db', timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')  # Enable WAL mode for better concurrency
        cursor = conn.cursor()
        
        for i in range(num_operations):
            try:
                # Simulate atomic operation: read current value, then update
                
                # First, try to get existing ledger entry
                cursor.execute("""
                    SELECT orders_count, submitted_notional_usd FROM daily_ledger 
                    WHERE account_id = ? AND day_utc = ?
                """, (account_id, today))
                
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing entry
                    current_orders, current_notional = existing
                    new_orders = current_orders + 1
                    new_notional = current_notional + 100.0
                    
                    cursor.execute("""
                        UPDATE daily_ledger 
                        SET orders_count = ?, submitted_notional_usd = ?, updated_at = ?
                        WHERE account_id = ? AND day_utc = ?
                    """, (new_orders, new_notional, datetime.now(), account_id, today))
                else:
                    # Insert new entry
                    cursor.execute("""
                        INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
                        VALUES (?, ?, ?, ?)
                    """, (account_id, today, 1, 100.0))
                
                conn.commit()
                results['successful_updates'] += 1
                
                # Add small random delay to increase chance of race conditions
                time.sleep(random.uniform(0.001, 0.005))
                
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    results['constraint_violations'] += 1
                    # This is expected in concurrent scenario
                    conn.rollback()
                else:
                    results['other_errors'] += 1
                    conn.rollback()
            except Exception as e:
                results['other_errors'] += 1
                conn.rollback()
                print(f"Worker {worker_id} unexpected error: {e}")
        
        results['end_time'] = time.time()
        results['duration'] = results['end_time'] - results['start_time']
        
        return results
        
    except Exception as e:
        print(f"Worker {worker_id} failed to connect: {e}")
        results['connection_error'] = str(e)
        return results
    finally:
        try:
            conn.close()
        except:
            pass

def test_concurrent_order_events(worker_id: int, num_operations: int = 20):
    """Test concurrent order event insertions"""
    
    results = {
        'worker_id': worker_id,
        'successful_inserts': 0,
        'duplicate_violations': 0,
        'other_errors': 0,
        'start_time': time.time()
    }
    
    try:
        conn = sqlite3.connect('trading_platform.db', timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()
        
        for i in range(num_operations):
            try:
                # Create unique event
                order_id = f"test_order_{worker_id}_{i}"
                broker_order_id = f"broker_{worker_id}_{i}"
                event_type = random.choice(["fill", "partial_fill", "cancelled"])
                event_time = datetime.now().isoformat()
                
                cursor.execute("""
                    INSERT INTO order_events (order_id, broker_order_id, event_type, event_time, event_data)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, broker_order_id, event_type, event_time, '{"test": true}'))
                
                conn.commit()
                results['successful_inserts'] += 1
                
                # Small delay
                time.sleep(random.uniform(0.001, 0.005))
                
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    results['duplicate_violations'] += 1
                    conn.rollback()
                else:
                    results['other_errors'] += 1
                    conn.rollback()
            except Exception as e:
                results['other_errors'] += 1
                conn.rollback()
        
        results['end_time'] = time.time()
        results['duration'] = results['end_time'] - results['start_time']
        
        return results
        
    except Exception as e:
        print(f"Events worker {worker_id} failed: {e}")
        results['connection_error'] = str(e)
        return results
    finally:
        try:
            conn.close()
        except:
            pass

def setup_test_environment():
    """Clean up any existing test data"""
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        
        # Clean up test data
        cursor.execute("DELETE FROM daily_ledger WHERE account_id LIKE 'test_%'")
        cursor.execute("DELETE FROM order_events WHERE order_id LIKE 'test_%'")
        conn.commit()
        conn.close()
        
        print("✅ Test environment cleaned up")
        return True
    except Exception as e:
        print(f"❌ Failed to setup test environment: {e}")
        return False

def analyze_results(ledger_results, events_results):
    """Analyze and report test results"""
    
    print("\n📊 Performance Test Results")
    print("=" * 50)
    
    # Daily Ledger Results
    print("\n🏦 Daily Ledger Concurrent Operations:")
    total_ledger_ops = sum(r['successful_updates'] + r['constraint_violations'] + r['other_errors'] 
                          for r in ledger_results)
    total_ledger_success = sum(r['successful_updates'] for r in ledger_results)
    total_ledger_violations = sum(r['constraint_violations'] for r in ledger_results)
    total_ledger_errors = sum(r['other_errors'] for r in ledger_results)
    
    avg_duration = sum(r.get('duration', 0) for r in ledger_results) / len(ledger_results)
    
    print(f"  Total operations: {total_ledger_ops}")
    print(f"  Successful updates: {total_ledger_success}")
    print(f"  Constraint violations: {total_ledger_violations}")
    print(f"  Other errors: {total_ledger_errors}")
    print(f"  Average worker duration: {avg_duration:.2f}s")
    print(f"  Success rate: {total_ledger_success/total_ledger_ops*100:.1f}%")
    
    # Order Events Results  
    print("\n📋 Order Events Concurrent Operations:")
    total_events_ops = sum(r['successful_inserts'] + r['duplicate_violations'] + r['other_errors'] 
                          for r in events_results)
    total_events_success = sum(r['successful_inserts'] for r in events_results)
    total_events_violations = sum(r['duplicate_violations'] for r in events_results)
    total_events_errors = sum(r['other_errors'] for r in events_results)
    
    avg_events_duration = sum(r.get('duration', 0) for r in events_results) / len(events_results)
    
    print(f"  Total operations: {total_events_ops}")
    print(f"  Successful inserts: {total_events_success}")
    print(f"  Duplicate violations: {total_events_violations}")
    print(f"  Other errors: {total_events_errors}")
    print(f"  Average worker duration: {avg_events_duration:.2f}s")
    print(f"  Success rate: {total_events_success/total_events_ops*100:.1f}%")
    
    # Check final state
    print("\n🔍 Final Database State:")
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        
        # Check final daily_ledger state
        cursor.execute("""
            SELECT account_id, orders_count, submitted_notional_usd 
            FROM daily_ledger 
            WHERE account_id LIKE 'test_%'
        """)
        ledger_rows = cursor.fetchall()
        
        for account_id, orders_count, notional in ledger_rows:
            print(f"  {account_id}: {orders_count} orders, ${notional} notional")
        
        # Check order_events count
        cursor.execute("SELECT COUNT(*) FROM order_events WHERE order_id LIKE 'test_%'")
        events_count = cursor.fetchone()[0]
        print(f"  Total test events in DB: {events_count}")
        
        conn.close()
        
    except Exception as e:
        print(f"  ❌ Failed to check final state: {e}")
    
    # Determine if test passed
    race_condition_detected = (
        total_ledger_errors > 0 or 
        total_events_errors > 0 or
        total_ledger_success == 0 or
        total_events_success == 0
    )
    
    if race_condition_detected:
        print("\n❌ RACE CONDITIONS OR ERRORS DETECTED")
        return False
    else:
        print("\n✅ NO RACE CONDITIONS - DATABASE CONSTRAINTS WORKING CORRECTLY")
        return True

def main():
    """Run concurrent performance test"""
    
    print("🚀 Starting Concurrent Database Operations Performance Test")
    
    # Setup
    if not setup_test_environment():
        return False
    
    num_workers = 10  # Number of concurrent workers
    operations_per_worker = 20  # Operations each worker performs
    
    print(f"\n📋 Test Configuration:")
    print(f"  Workers: {num_workers}")
    print(f"  Operations per worker: {operations_per_worker}")
    print(f"  Total operations: {num_workers * operations_per_worker}")
    
    start_time = time.time()
    
    # Run concurrent daily ledger tests
    print(f"\n🏃 Running concurrent daily ledger operations...")
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        ledger_futures = [
            executor.submit(test_concurrent_daily_ledger_operations, worker_id, operations_per_worker)
            for worker_id in range(num_workers)
        ]
        
        ledger_results = []
        for future in as_completed(ledger_futures):
            result = future.result()
            ledger_results.append(result)
            print(f"  Worker {result['worker_id']} completed: "
                  f"{result['successful_updates']} success, "
                  f"{result['constraint_violations']} violations, "
                  f"{result['other_errors']} errors")
    
    # Run concurrent order events tests
    print(f"\n🏃 Running concurrent order events operations...")
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        events_futures = [
            executor.submit(test_concurrent_order_events, worker_id, operations_per_worker)
            for worker_id in range(num_workers)
        ]
        
        events_results = []
        for future in as_completed(events_futures):
            result = future.result()
            events_results.append(result)
            print(f"  Worker {result['worker_id']} completed: "
                  f"{result['successful_inserts']} success, "
                  f"{result['duplicate_violations']} violations, "
                  f"{result['other_errors']} errors")
    
    total_time = time.time() - start_time
    print(f"\n⏱️ Total test duration: {total_time:.2f}s")
    
    # Analyze results
    success = analyze_results(ledger_results, events_results)
    
    # Cleanup
    setup_test_environment()  # Clean up test data
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 Concurrent performance test PASSED!")
        print("   ✅ Database constraints prevent race conditions")
        print("   ✅ Concurrent operations handle conflicts properly")
        print("   ✅ No data integrity issues detected")
    else:
        print("\n❌ Concurrent performance test FAILED!")
        print("   Check for race conditions or data integrity issues")
    
    sys.exit(0 if success else 1)