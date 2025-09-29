#!/usr/bin/env python3
"""
Simple Python Performance Test Script
Equivalent to K6 smoke test for Phase G validation
"""

import asyncio
import aiohttp
import statistics
import time
from datetime import datetime
from typing import Dict, List, Tuple

BASE_URL = "http://localhost:8000"
API_TOKEN = "6Av--QEcw6s7O0U7i4nxbNqwSUtL3PfNzC07BIOIzFI"  # From seeding

class PerformanceTest:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.results: Dict[str, List[float]] = {}
        self.errors: List[str] = []
        
    async def make_request(self, session: aiohttp.ClientSession, method: str, path: str, 
                          headers: Dict = None, json_data: Dict = None) -> Tuple[float, int, str]:
        """Make HTTP request and return (latency_ms, status_code, response_text)"""
        start_time = time.time()
        try:
            url = f"{self.base_url}{path}"
            async with session.request(method, url, headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response_text = await response.text()
                latency_ms = (time.time() - start_time) * 1000
                return latency_ms, response.status, response_text
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return latency_ms, 0, str(e)
    
    async def test_endpoint(self, session: aiohttp.ClientSession, name: str, method: str, 
                           path: str, headers: Dict = None, expected_status: int = 200) -> Dict:
        """Test single endpoint and record metrics"""
        latency, status, response = await self.make_request(session, method, path, headers)
        
        if name not in self.results:
            self.results[name] = []
        self.results[name].append(latency)
        
        success = status == expected_status
        if not success:
            error_msg = f"{name}: Expected {expected_status}, got {status} - {response[:100]}"
            self.errors.append(error_msg)
        
        return {
            "name": name,
            "latency_ms": latency,
            "status": status,
            "success": success,
            "expected_status": expected_status
        }
    
    async def run_smoke_test(self, num_requests: int = 10):
        """Run smoke test with authentication and basic endpoints"""
        print(f"🚀 Starting Performance Smoke Test - {num_requests} requests per endpoint")
        print(f"📡 Target: {self.base_url}")
        print("=" * 60)
        
        headers_with_auth = {"Authorization": f"Bearer {API_TOKEN}"}
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Health endpoint (no auth required)
            print("📊 Testing /health endpoint...")
            for i in range(num_requests):
                await self.test_endpoint(session, "health", "GET", "/health", expected_status=200)
            
            # Test 2: OpenAPI spec
            print("📊 Testing /openapi.json endpoint...")
            for i in range(num_requests):
                await self.test_endpoint(session, "openapi", "GET", "/openapi.json", expected_status=200)
            
            # Test 3: Protected endpoints without auth (should return 401)
            print("📊 Testing protected endpoints without auth...")
            for i in range(3):  # Fewer tests for expected failures
                await self.test_endpoint(session, "signals_unauth", "GET", "/api/v1/signals?symbol=AAPL", expected_status=401)
                await self.test_endpoint(session, "orders_unauth", "GET", "/api/v1/orders/test-id", expected_status=401)
            
            # Test 4: Protected endpoints with auth
            print("📊 Testing protected endpoints with auth...")
            for i in range(num_requests):
                await self.test_endpoint(session, "signals_auth", "GET", "/api/v1/signals?symbol=AAPL", headers_with_auth, expected_status=200)
                await asyncio.sleep(0.1)  # Small delay to avoid overwhelming
                
            # Test 5: Positions endpoint
            print("📊 Testing positions endpoint...")
            for i in range(5):  # Fewer requests for this endpoint
                await self.test_endpoint(session, "positions", "GET", "/api/v1/positions", headers_with_auth, expected_status=200)
        
        self.generate_report()
    
    def calculate_stats(self, data: List[float]) -> Dict:
        """Calculate performance statistics"""
        if not data:
            return {"count": 0, "avg": 0, "p95": 0, "min": 0, "max": 0}
        
        return {
            "count": len(data),
            "avg": round(statistics.mean(data), 1),
            "p95": round(statistics.quantiles(data, n=20)[-1], 1) if len(data) > 1 else data[0],
            "min": round(min(data), 1),
            "max": round(max(data), 1)
        }
    
    def generate_report(self):
        """Generate performance test report"""
        print("\n" + "=" * 80)
        print("📊 PERFORMANCE TEST RESULTS")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Base URL: {self.base_url}")
        
        # Overall status
        total_errors = len(self.errors)
        total_requests = sum(len(data) for data in self.results.values())
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        print(f"Total Requests: {total_requests}")
        print(f"Total Errors: {total_errors}")
        print(f"Error Rate: {error_rate:.1f}%")
        
        # Determine overall status
        if error_rate < 5:
            status_icon = "✅ PASS"
        elif error_rate < 20:
            status_icon = "⚠️  WARN"
        else:
            status_icon = "❌ FAIL"
        
        print(f"Overall Status: {status_icon}")
        print()
        
        # Performance targets from Phase 4 checklist
        auth_target = 200  # ms
        read_target = 300  # ms
        write_target = 500  # ms
        
        print("🎯 PERFORMANCE TARGETS VS ACTUAL:")
        print(f"   Auth endpoints: <{auth_target}ms P95")
        print(f"   Read endpoints: <{read_target}ms P95") 
        print(f"   Write endpoints: <{write_target}ms P95")
        print()
        
        # Detailed results by endpoint
        print("📈 DETAILED RESULTS BY ENDPOINT:")
        print("-" * 80)
        
        for endpoint_name, latencies in self.results.items():
            stats = self.calculate_stats(latencies)
            
            # Categorize endpoint type for target comparison
            if "health" in endpoint_name or "openapi" in endpoint_name:
                target = read_target
                category = "READ"
            elif "unauth" in endpoint_name:
                target = auth_target  
                category = "AUTH"
            elif "signals" in endpoint_name or "positions" in endpoint_name:
                target = read_target
                category = "READ"
            else:
                target = write_target
                category = "WRITE"
            
            # Check if meets target
            meets_target = stats["p95"] <= target
            status = "✅" if meets_target else "❌"
            
            print(f"{status} {endpoint_name:20} [{category:5}] | "
                  f"Avg: {stats['avg']:6.1f}ms | "
                  f"P95: {stats['p95']:6.1f}ms | "
                  f"Target: <{target}ms | "
                  f"Count: {stats['count']:2d}")
        
        # Error details
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            print("-" * 80)
            for error in self.errors[:10]:  # Show first 10 errors
                print(f"   • {error}")
            if len(self.errors) > 10:
                print(f"   ... and {len(self.errors) - 10} more errors")
        
        # Summary recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print("-" * 80)
        
        # Check specific performance targets
        failed_endpoints = []
        for endpoint_name, latencies in self.results.items():
            stats = self.calculate_stats(latencies)
            if "health" in endpoint_name or "openapi" in endpoint_name:
                target = read_target
            elif "unauth" in endpoint_name:
                target = auth_target
            elif "signals" in endpoint_name or "positions" in endpoint_name:
                target = read_target
            else:
                target = write_target
                
            if stats["p95"] > target:
                failed_endpoints.append(f"{endpoint_name} ({stats['p95']:.1f}ms > {target}ms)")
        
        if failed_endpoints:
            print("❌ Performance targets NOT MET:")
            for failed in failed_endpoints:
                print(f"   • {failed}")
        else:
            print("✅ All performance targets MET!")
        
        if error_rate > 5:
            print(f"❌ Error rate ({error_rate:.1f}%) exceeds 5% threshold")
        else:
            print("✅ Error rate within acceptable limits")
        
        print("=" * 80)

async def main():
    """Run the performance test"""
    test = PerformanceTest()
    await test.run_smoke_test(num_requests=10)

if __name__ == "__main__":
    asyncio.run(main())