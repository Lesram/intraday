#!/usr/bin/env python3
"""
Python-based K6 Alternative for Phase G Performance Testing

This script provides K6-style load testing using Python's asyncio and aiohttp
libraries to validate concurrent performance against authenticated endpoints.

Usage:
    python perf/python_k6_alternative.py

Expected behavior:
- Tests concurrent load (5 VUs for 2 minutes)  
- Authenticates via JWT login
- Validates performance thresholds:
  - Health: < 100ms p95
  - Signals: < 300ms p95
  - Positions: < 300ms p95
"""

import asyncio
import json
import statistics
import time
from typing import Dict, List, Optional
import aiohttp
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PerformanceMetrics:
    """Collects and analyzes performance metrics"""
    
    def __init__(self):
        self.response_times: Dict[str, List[float]] = {}
        self.status_codes: Dict[str, List[int]] = {}
        self.errors: List[str] = []
        
    def record_response(self, endpoint: str, response_time: float, status_code: int, error: Optional[str] = None):
        """Record a response for analysis"""
        if endpoint not in self.response_times:
            self.response_times[endpoint] = []
            self.status_codes[endpoint] = []
            
        self.response_times[endpoint].append(response_time)
        self.status_codes[endpoint].append(status_code)
        
        if error:
            self.errors.append(f"{endpoint}: {error}")
            
    def get_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = k - int(k)
        return sorted_values[int(k)] + f * (sorted_values[int(k) + 1] - sorted_values[int(k)])
        
    def get_success_rate(self, endpoint: str) -> float:
        """Get success rate for an endpoint"""
        if endpoint not in self.status_codes:
            return 0.0
        codes = self.status_codes[endpoint]
        successful = sum(1 for code in codes if 200 <= code < 300)
        return (successful / len(codes)) * 100 if codes else 0.0
        
    def print_results(self):
        """Print detailed performance results"""
        print("\n" + "="*60)
        print("🚀 PYTHON K6 ALTERNATIVE - PERFORMANCE RESULTS")
        print("="*60)
        
        # Overall summary
        total_requests = sum(len(times) for times in self.response_times.values())
        total_errors = len(self.errors)
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total Requests: {total_requests}")
        print(f"   Total Errors: {total_errors}")
        print(f"   Error Rate: {(total_errors/total_requests)*100:.2f}%" if total_requests > 0 else "   Error Rate: N/A")
        
        # Per-endpoint analysis
        print(f"\n⏱️  ENDPOINT PERFORMANCE:")
        
        thresholds_passed = True
        
        for endpoint, times in self.response_times.items():
            if not times:
                continue
                
            avg_time = statistics.mean(times) * 1000  # Convert to ms
            p95_time = self.get_percentile(times, 95) * 1000
            min_time = min(times) * 1000
            max_time = max(times) * 1000
            success_rate = self.get_success_rate(endpoint)
            
            print(f"\n   📈 {endpoint}:")
            print(f"      Requests: {len(times)}")
            print(f"      Success Rate: {success_rate:.1f}%")
            print(f"      Avg: {avg_time:.1f}ms")
            print(f"      Min: {min_time:.1f}ms") 
            print(f"      Max: {max_time:.1f}ms")
            print(f"      P95: {p95_time:.1f}ms")
            
            # Check thresholds
            if endpoint == "health":
                threshold = 100
                passed = p95_time < threshold
                print(f"      Threshold: P95 < {threshold}ms {'✅ PASS' if passed else '❌ FAIL'}")
                if not passed:
                    thresholds_passed = False
            elif endpoint in ["signals", "positions"]:
                threshold = 300
                passed = p95_time < threshold
                print(f"      Threshold: P95 < {threshold}ms {'✅ PASS' if passed else '❌ FAIL'}")
                if not passed:
                    thresholds_passed = False
                    
        # Error details
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors[:10]:  # Show first 10 errors
                print(f"   • {error}")
            if len(self.errors) > 10:
                print(f"   ... and {len(self.errors) - 10} more errors")
                
        # Final result
        print(f"\n🎯 FINAL RESULT:")
        if thresholds_passed and total_errors < (total_requests * 0.05):  # Less than 5% error rate
            print("   ✅ PERFORMANCE TEST PASSED")
            return True
        else:
            print("   ❌ PERFORMANCE TEST FAILED")
            return False

class K6Alternative:
    """Python-based K6 alternative for load testing"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.metrics = PerformanceMetrics()
        self.auth_token: Optional[str] = None
        
    async def get_auth_token(self, session: aiohttp.ClientSession) -> bool:
        """Obtain JWT authentication token"""
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        try:
            start_time = time.time()
            async with session.post(
                f"{self.base_url}/api/v1/auth/login",
                json=login_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get("access_token")
                    logger.info(f"✅ Authentication successful ({response_time*1000:.1f}ms)")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Authentication failed: {response.status} - {error_text}")
                    self.metrics.record_response("login", response_time, response.status, f"Status {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            return False
            
    async def test_health_endpoint(self, session: aiohttp.ClientSession) -> bool:
        """Test unauthenticated health endpoint"""
        try:
            start_time = time.time()
            async with session.get(
                f"{self.base_url}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    success = data.get("status") == "ok"
                    self.metrics.record_response("health", response_time, response.status)
                    return success
                else:
                    self.metrics.record_response("health", response_time, response.status, f"Status {response.status}")
                    return False
                    
        except Exception as e:
            self.metrics.record_response("health", 0, 0, str(e))
            return False
            
    async def test_authenticated_endpoint(self, session: aiohttp.ClientSession, endpoint: str, path: str) -> bool:
        """Test authenticated endpoint"""
        if not self.auth_token:
            self.metrics.record_response(endpoint, 0, 0, "No auth token")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            start_time = time.time()
            
            async with session.get(
                f"{self.base_url}{path}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    self.metrics.record_response(endpoint, response_time, response.status)
                    return True
                else:
                    error_text = await response.text()
                    self.metrics.record_response(endpoint, response_time, response.status, f"Status {response.status}")
                    return False
                    
        except Exception as e:
            self.metrics.record_response(endpoint, 0, 0, str(e))
            return False
            
    async def worker_iteration(self, session: aiohttp.ClientSession, worker_id: int):
        """Single iteration of load test worker"""
        # Test health endpoint (unauthenticated)
        await self.test_health_endpoint(session)
        await asyncio.sleep(0.1)  # Small delay between requests
        
        # Test signals endpoint (authenticated)
        await self.test_authenticated_endpoint(session, "signals", "/api/v1/signals?symbol=AAPL")
        await asyncio.sleep(0.1)
        
        # Test positions endpoint (authenticated)  
        await self.test_authenticated_endpoint(session, "positions", "/api/v1/positions")
        await asyncio.sleep(1)  # Delay between iterations to simulate realistic user behavior
        
    async def worker(self, worker_id: int, duration_seconds: int):
        """Load test worker coroutine"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
        
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        ) as session:
            
            # Get authentication token once per worker
            if not await self.get_auth_token(session):
                logger.error(f"Worker {worker_id}: Failed to authenticate, exiting")
                return
                
            logger.info(f"Worker {worker_id}: Starting load test for {duration_seconds}s")
            
            start_time = time.time()
            iterations = 0
            
            while time.time() - start_time < duration_seconds:
                await self.worker_iteration(session, worker_id)
                iterations += 1
                
                # Log progress every 30 seconds
                elapsed = time.time() - start_time
                if iterations % 30 == 0:
                    logger.info(f"Worker {worker_id}: {iterations} iterations in {elapsed:.1f}s")
                    
            logger.info(f"Worker {worker_id}: Completed {iterations} iterations")
            
    async def run_load_test(self, num_workers: int = 5, duration_seconds: int = 120):
        """Run the main load test"""
        logger.info(f"🚀 Starting Python K6 Alternative")
        logger.info(f"   Base URL: {self.base_url}")
        logger.info(f"   Workers: {num_workers}")
        logger.info(f"   Duration: {duration_seconds}s")
        logger.info(f"   Expected Requests: ~{num_workers * duration_seconds / 1.3:.0f}")
        
        # Test connectivity first
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status != 200:
                        logger.error(f"❌ Server not responding: {response.status}")
                        return False
                    logger.info("✅ Server connectivity confirmed")
        except Exception as e:
            logger.error(f"❌ Cannot connect to server: {e}")
            return False
            
        # Run load test workers
        start_time = time.time()
        
        tasks = []
        for i in range(num_workers):
            task = asyncio.create_task(self.worker(i + 1, duration_seconds))
            tasks.append(task)
            await asyncio.sleep(0.5)  # Stagger worker startup
            
        logger.info(f"📊 Load test running with {num_workers} workers...")
        
        # Wait for all workers to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        logger.info(f"🏁 Load test completed in {total_time:.1f}s")
        
        # Print results and return success status
        return self.metrics.print_results()

async def main():
    """Main entry point"""
    # Check if server is running on default port
    k6_alt = K6Alternative("http://localhost:8000")
    
    # Run 2-minute load test with 5 concurrent workers
    success = await k6_alt.run_load_test(num_workers=5, duration_seconds=120)
    
    if success:
        logger.info("🎉 Performance test PASSED - Phase G requirements met!")
        exit(0)
    else:
        logger.error("💥 Performance test FAILED - Check results above")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())