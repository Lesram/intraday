#!/usr/bin/env python3
"""Enhanced concurrent test that properly tests UNIQUE constraint violations"""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

def test_concurrent_daily_ledger_inserts(worker_id: int, num_attempts: int = 10):
    """Test concurrent daily ledger INSERT operations that should trigger UNIQUE constraints"""
    
    account_id = f"shared_account_123"  # Same account for all workers to trigger conflicts
    today = date.today()
    
    results = {
        'worker_id': worker_id,
        'successful_inserts': 0,
        'constraint_violations': 0,
        'other_errors': 0,
    }
    
    try:
        conn = sqlite3.connect('trading_platform.db', timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()
        
        for i in range(num_attempts):
            try:
                # Try to INSERT new daily ledger entry
                # This should fail for all but the first worker due to UNIQUE constraint
                cursor.execute("""
                    INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
                    VALUES (?, ?, ?, ?)
                """, (account_id, today, 1, 100.0))
                
                conn.commit()
                results['successful_inserts'] += 1
                print(f"  ✅ Worker {worker_id} successfully inserted ledger entry")
                
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    results['constraint_violations'] += 1
                    print(f"  🛑 Worker {worker_id} hit UNIQUE constraint (expected)")
                    conn.rollback()
                else:
                    results['other_errors'] += 1
                    conn.rollback()
            except Exception as e:
                results['other_errors'] += 1
                conn.rollback()
                print(f"  ❌ Worker {worker_id} unexpected error: {e}")
            
            # Small delay between attempts
            time.sleep(0.01)
        
        return results
        
    except Exception as e:
        print(f"Worker {worker_id} connection failed: {e}")
        results['connection_error'] = str(e)
        return results
    finally:
        try:
            conn.close()
        except:
            pass

def test_constraint_enforcement():
    """Test that UNIQUE constraints are properly enforced under concurrent load"""
    
    print("🧪 Testing UNIQUE Constraint Enforcement Under Concurrent Load")
    print("=" * 60)
    
    # Clean up any existing test data
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM daily_ledger WHERE account_id LIKE 'shared_account_%'")
        conn.commit()
        conn.close()
        print("✅ Test data cleaned up")
    except Exception as e:
        print(f"❌ Failed to clean test data: {e}")
        return False
    
    num_workers = 5
    attempts_per_worker = 3
    
    print(f"\n📋 Test: {num_workers} workers each trying to INSERT {attempts_per_worker} times")
    print(f"   All workers target the same account_id to trigger UNIQUE constraint")
    
    # Run concurrent INSERT attempts
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(test_concurrent_daily_ledger_inserts, worker_id, attempts_per_worker)
            for worker_id in range(num_workers)
        ]
        
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    # Analyze results
    total_attempts = sum(r['successful_inserts'] + r['constraint_violations'] + r['other_errors'] 
                        for r in results)
    total_success = sum(r['successful_inserts'] for r in results)
    total_violations = sum(r['constraint_violations'] for r in results)
    total_errors = sum(r['other_errors'] for r in results)
    
    print(f"\n📊 Results:")
    print(f"  Total attempts: {total_attempts}")
    print(f"  Successful inserts: {total_success}")
    print(f"  UNIQUE constraint violations: {total_violations}")
    print(f"  Other errors: {total_errors}")
    
    # Verify database state
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM daily_ledger WHERE account_id LIKE 'shared_account_%'")
        actual_rows = cursor.fetchone()[0]
        conn.close()
        
        print(f"  Actual rows in database: {actual_rows}")
        
        # We expect exactly 1 row (only first INSERT should succeed)
        constraint_working = (actual_rows == 1 and total_violations > 0)
        
        if constraint_working:
            print(f"\n✅ UNIQUE constraint working correctly!")
            print(f"   ✓ Only 1 row inserted despite {total_attempts} attempts")
            print(f"   ✓ {total_violations} attempts properly rejected")
            return True
        else:
            print(f"\n❌ UNIQUE constraint issue detected!")
            print(f"   Expected: 1 row, {total_attempts-1} violations")
            print(f"   Actual: {actual_rows} rows, {total_violations} violations")
            return False
            
    except Exception as e:
        print(f"❌ Failed to verify database state: {e}")
        return False

def main():
    """Run enhanced constraint enforcement test"""
    
    print("🚀 Enhanced Database UNIQUE Constraint Test")
    print("=" * 50)
    
    success = test_constraint_enforcement()
    
    # Clean up
    try:
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM daily_ledger WHERE account_id LIKE 'shared_account_%'")
        conn.commit()
        conn.close()
        print("\n🧹 Test data cleaned up")
    except:
        pass
    
    if success:
        print("\n🎉 Enhanced constraint test PASSED!")
        print("   ✅ UNIQUE constraints prevent duplicate entries")
        print("   ✅ Concurrent operations handled properly")
    else:
        print("\n❌ Enhanced constraint test FAILED!")
        print("   Check constraint enforcement and concurrency handling")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)