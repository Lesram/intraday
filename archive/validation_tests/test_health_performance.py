#!/usr/bin/env python3
"""
Test health endpoint performance improvements.
"""

import asyncio
import time
import requests
from statistics import mean, stdev


async def test_health_performance():
    """Test health endpoint performance to verify <5ms target."""
    print("Testing Health Endpoint Performance...")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test 1: Health endpoint performance (should be <5ms)
    print("1. Testing /health performance (target: <5ms)...")
    
    health_times = []
    for i in range(10):
        try:
            start_time = time.perf_counter()
            response = requests.get(f"{base_url}/health", timeout=1)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 200:
                health_times.append(elapsed_ms)
                print(f"   Request {i+1}: {elapsed_ms:.2f}ms")
            else:
                print(f"   Request {i+1}: Failed ({response.status_code})")
        except Exception as e:
            print(f"   Request {i+1}: Error - {e}")
    
    if health_times:
        avg_health = mean(health_times)
        p95_health = sorted(health_times)[int(0.95 * len(health_times))]
        print(f"   Average: {avg_health:.2f}ms")
        print(f"   P95: {p95_health:.2f}ms")
        print(f"   Target achieved: {'✅' if p95_health < 5 else '❌'} (target: <5ms)")
    
    # Test 2: Readiness endpoint caching
    print("\n2. Testing /readyz caching behavior...")
    
    readyz_times = []
    for i in range(5):
        try:
            start_time = time.perf_counter()
            response = requests.get(f"{base_url}/readyz", timeout=2)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            if response.status_code in [200, 503]:
                readyz_times.append(elapsed_ms)
                data = response.json()
                cached = data.get('cached', False)
                status = data.get('status', 'unknown')
                print(f"   Request {i+1}: {elapsed_ms:.2f}ms, Status: {status}, Cached: {cached}")
            else:
                print(f"   Request {i+1}: Failed ({response.status_code})")
                
            # Small delay to test caching
            if i < 4:
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"   Request {i+1}: Error - {e}")
    
    if readyz_times and len(readyz_times) >= 2:
        first_call = readyz_times[0]
        subsequent_avg = mean(readyz_times[1:])
        print(f"   First call: {first_call:.2f}ms (uncached)")
        print(f"   Subsequent avg: {subsequent_avg:.2f}ms (should be cached)")
        print(f"   Cache working: {'✅' if subsequent_avg < first_call else '❌'}")
    
    # Test 3: Compare health vs readyz performance
    print(f"\n3. Performance comparison:")
    if health_times and readyz_times:
        health_avg = mean(health_times)
        readyz_first = readyz_times[0]
        speedup = readyz_first / health_avg
        print(f"   /health avg: {health_avg:.2f}ms")
        print(f"   /readyz first call: {readyz_first:.2f}ms") 
        print(f"   Health is {speedup:.1f}x faster than deep checks")


def test_health_endpoints_sync():
    """Synchronous wrapper for testing."""
    asyncio.run(test_health_performance())


if __name__ == "__main__":
    test_health_endpoints_sync()