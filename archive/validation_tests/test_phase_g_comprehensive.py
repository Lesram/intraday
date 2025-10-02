#!/usr/bin/env python3
"""
Comprehensive Phase G Testing Suite
Tests all aspects of database-backed order flow implementation
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"
TEST_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "TSLA"]


class PhaseGTester:
    """Comprehensive Phase G test runner"""
    
    def __init__(self):
        self.results = {}
        self.token = None
        self.headers = {}
        
    async def setup(self):
        """Initialize test environment"""
        print("🚀 Phase G Comprehensive Test Suite")
        print("=" * 50)
        
        # Authenticate
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{BASE_URL}/auth/login",
                    json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
                )
                if response.status_code == 200:
                    self.token = response.json()["access_token"]
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    print("✅ Authentication successful")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    async def test_health_check(self):
        """Test basic health endpoint"""
        print("\n📊 Testing Health Check...")
        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{BASE_URL}/health")
                duration = (time.time() - start_time) * 1000
                
                if response.status_code == 200 and duration < 100:
                    print(f"✅ Health check: {response.status_code} in {duration:.1f}ms")
                    self.results["health_check"] = True
                else:
                    print(f"❌ Health check failed: {response.status_code}, {duration:.1f}ms")
                    self.results["health_check"] = False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            self.results["health_check"] = False
    
    async def test_positions_endpoint(self):
        """Test positions endpoint"""
        print("\n📈 Testing Positions Endpoint...")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{BASE_URL}/positions", headers=self.headers)
                
                if response.status_code == 200:
                    print("✅ Positions endpoint accessible")
                    self.results["positions"] = True
                else:
                    print(f"❌ Positions endpoint failed: {response.status_code}")
                    self.results["positions"] = False
        except Exception as e:
            print(f"❌ Positions error: {e}")
            self.results["positions"] = False
    
    async def test_database_persistence(self):
        """Test database-backed order persistence"""
        print("\n💾 Testing Database Persistence...")
        try:
            from backend.infra.db import init_db
            from backend.services.order_service import OrderService
            
            # Initialize database
            database_url = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./test_phase_g.db')
            engine, sessionmaker = init_db(database_url)
            
            # Create service and submit order
            service = OrderService(sessionmaker=sessionmaker)
            test_signal = {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 10,
                "signal_id": f"test-{uuid.uuid4()}",
                "timestamp": datetime.now().isoformat()
            }
            
            result = await service.submit_order_async(test_signal)
            
            if result and hasattr(result, 'order_id') and result.order_id:
                order_id = str(result.order_id)
                print(f"✅ Order created: {order_id}")
                
                # Test immediate lookup
                status = await service.get_order_status(order_id)
                if status:
                    print("✅ Immediate database lookup successful")
                    
                    # Test with new service instance (simulating restart)
                    service2 = OrderService(sessionmaker=sessionmaker)
                    status2 = await service2.get_order_status(order_id)
                    
                    if status2:
                        print("✅ Database persistence after restart successful")
                        self.results["database_persistence"] = True
                    else:
                        print("❌ Database persistence after restart failed")
                        self.results["database_persistence"] = False
                else:
                    print("❌ Database lookup failed")
                    self.results["database_persistence"] = False
            else:
                print("❌ Order creation failed")
                self.results["database_persistence"] = False
                
        except Exception as e:
            print(f"❌ Database persistence error: {e}")
            self.results["database_persistence"] = False
    
    async def test_order_flow_integration(self):
        """Test complete order flow via API"""
        print("\n🔄 Testing Complete Order Flow Integration...")
        order_ids = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for symbol in TEST_SYMBOLS[:2]:  # Test with 2 symbols
                    print(f"  Testing {symbol}...")
                    
                    # Submit signal (creates order)
                    signal_data = {
                        "symbol": symbol,
                        "signal_strength": 0.8,
                        "timestamp": datetime.now().isoformat(),
                        "features": {"test": True},
                        "metadata": {"source": "phase_g_test"}
                    }
                    
                    response = await client.post(
                        f"{BASE_URL}/signals/act",
                        json=signal_data,
                        headers=self.headers
                    )
                    
                    if response.status_code == 200:
                        act_data = response.json()
                        order_info = act_data.get("order", {})
                        order_id = order_info.get("order_id")
                        
                        if order_id:
                            order_ids.append(order_id)
                            print(f"    ✅ Order created: {order_id}")
                            
                            # Test status lookup immediately
                            status_response = await client.get(
                                f"{BASE_URL}/orders/{order_id}",
                                headers=self.headers
                            )
                            
                            if status_response.status_code == 200:
                                print(f"    ✅ Status lookup successful")
                            else:
                                print(f"    ❌ Status lookup failed: {status_response.status_code}")
                        else:
                            print(f"    ❌ No order_id in response")
                    else:
                        print(f"    ❌ Signal submission failed: {response.status_code}")
                        if response.status_code != 200:
                            print(f"    Response: {response.text[:200]}")
            
            success_rate = len(order_ids) / len(TEST_SYMBOLS[:2])
            if success_rate >= 1.0:
                print(f"✅ Order flow integration: {len(order_ids)}/{len(TEST_SYMBOLS[:2])} successful")
                self.results["order_flow_integration"] = True
            else:
                print(f"❌ Order flow integration: {len(order_ids)}/{len(TEST_SYMBOLS[:2])} successful ({success_rate:.1%})")
                self.results["order_flow_integration"] = False
                
        except Exception as e:
            print(f"❌ Order flow integration error: {e}")
            self.results["order_flow_integration"] = False
    
    async def test_error_handling(self):
        """Test error handling for edge cases"""
        print("\n🚨 Testing Error Handling...")
        error_tests = []
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test invalid UUID format
                response = await client.get(
                    f"{BASE_URL}/orders/invalid-uuid",
                    headers=self.headers
                )
                error_tests.append(("Invalid UUID", response.status_code in [400, 422, 404]))
                
                # Test non-existent UUID
                fake_uuid = str(uuid.uuid4())
                response = await client.get(
                    f"{BASE_URL}/orders/{fake_uuid}",
                    headers=self.headers
                )
                error_tests.append(("Non-existent UUID", response.status_code == 404))
                
                # Test unauthorized access
                response = await client.get(f"{BASE_URL}/orders/{fake_uuid}")
                error_tests.append(("Unauthorized access", response.status_code == 401))
            
            success_count = sum(1 for _, success in error_tests if success)
            if success_count == len(error_tests):
                print("✅ All error handling tests passed")
                self.results["error_handling"] = True
            else:
                print(f"❌ Error handling: {success_count}/{len(error_tests)} passed")
                for test_name, success in error_tests:
                    status = "✅" if success else "❌"
                    print(f"  {status} {test_name}")
                self.results["error_handling"] = False
                
        except Exception as e:
            print(f"❌ Error handling test error: {e}")
            self.results["error_handling"] = False
    
    def run_k6_test(self, duration="30s", vus=5):
        """Run K6 performance test"""
        print(f"\n⚡ Running K6 Performance Test ({duration}, {vus} VUs)...")
        
        try:
            cmd = [
                "k6", "run",
                f"--duration={duration}",
                f"--vus={vus}",
                "-e", f"USERNAME={TEST_USERNAME}",
                "-e", f"PASSWORD={TEST_PASSWORD}",
                "perf/k6_order_flow.js"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Parse K6 output for key metrics
                output = result.stdout
                if "checks_succeeded...: 100.00%" in output and "rate=0.00%" in output:
                    print("✅ K6 test passed: 100% success rate, 0% errors")
                    self.results["k6_performance"] = True
                else:
                    print("❌ K6 test failed: Performance thresholds not met")
                    self.results["k6_performance"] = False
                    
                # Show key metrics
                for line in output.split('\n'):
                    if any(metric in line for metric in ['checks_succeeded', 'errors', 'http_req_duration']):
                        print(f"  📊 {line.strip()}")
            else:
                print(f"❌ K6 test failed: Exit code {result.returncode}")
                print(f"Error: {result.stderr[:200]}")
                self.results["k6_performance"] = False
                
        except subprocess.TimeoutExpired:
            print("❌ K6 test timed out")
            self.results["k6_performance"] = False
        except FileNotFoundError:
            print("❌ K6 not found - install K6 to run performance tests")
            self.results["k6_performance"] = False
        except Exception as e:
            print(f"❌ K6 test error: {e}")
            self.results["k6_performance"] = False
    
    def run_syntax_check(self):
        """Check Python syntax of key files"""
        print("\n🔍 Running Syntax Checks...")
        
        key_files = [
            "backend/services/order_service.py",
            "backend/api/routes/signals.py", 
            "backend/api/routes/orders.py",
            "backend/infra/repositories/orders.py",
            "backend/api/factory.py"
        ]
        
        syntax_errors = []
        
        for file_path in key_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), file_path, 'exec')
                print(f"  ✅ {file_path}")
            except SyntaxError as e:
                syntax_errors.append(f"{file_path}: {e}")
                print(f"  ❌ {file_path}: {e}")
            except FileNotFoundError:
                print(f"  ⚠️  {file_path}: File not found")
        
        if not syntax_errors:
            print("✅ All syntax checks passed")
            self.results["syntax_check"] = True
        else:
            print(f"❌ {len(syntax_errors)} syntax errors found")
            self.results["syntax_check"] = False
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*50)
        print("🎯 PHASE G TEST RESULTS SUMMARY")
        print("="*50)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result)
        
        for test_name, result in self.results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name.replace('_', ' ').title()}")
        
        print("-" * 50)
        print(f"📊 Overall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests:.1%})")
        
        if passed_tests == total_tests:
            print("🎉 ALL PHASE G TESTS PASSED! 🚀")
            return True
        else:
            print("⚠️  Some tests failed - review and fix issues")
            return False


async def main():
    """Main test runner"""
    tester = PhaseGTester()
    
    # Setup
    if not await tester.setup():
        print("❌ Setup failed - ensure server is running")
        sys.exit(1)
    
    # Run all tests
    await tester.test_health_check()
    await tester.test_positions_endpoint()
    await tester.test_database_persistence()
    await tester.test_order_flow_integration()
    await tester.test_error_handling()
    
    tester.run_syntax_check()
    tester.run_k6_test(duration="30s", vus=5)
    
    # Print summary
    success = tester.print_summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())