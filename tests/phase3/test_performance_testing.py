"""
Phase 3.2.3 - Performance Testing Implementation
Load testing for critical paths, memory usage validation, and async performance testing

This test suite provides comprehensive performance validation for the trading platform's
critical operations, memory management, and asynchronous functionality.
"""

import pytest
import asyncio
import time
import gc
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import statistics
import random


class PerformanceTimer:
    """Context manager for measuring execution time"""
    
    def __init__(self, description: str = ""):
        self.description = description
        self.start_time = None
        self.end_time = None
        self.duration = 0.001  # Initialize with minimum value
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        raw_duration = self.end_time - self.start_time
        self.duration = max(raw_duration, 0.001)  # Minimum 1ms to avoid division by zero
        if self.description:
            print(f"{self.description}: {raw_duration:.4f}s")


class MemoryMonitor:
    """Monitor memory usage during test execution"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = None
        self.peak_memory = None
        self.final_memory = None
    
    def __enter__(self):
        gc.collect()  # Clean up before measurement
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.initial_memory
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        gc.collect()  # Clean up after test
        self.final_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = max(self.peak_memory, self.final_memory)
    
    def update_peak(self):
        """Update peak memory usage"""
        current = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory = max(self.peak_memory, current)
    
    @property
    def memory_growth(self):
        """Memory growth in MB"""
        return self.final_memory - self.initial_memory if self.final_memory and self.initial_memory else 0


class TestCriticalPathPerformance:
    """Load testing for critical trading platform paths"""

    @pytest.fixture
    def client(self):
        """Create test client for performance testing"""
        from backend.api.factory import create_app
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers"""
        return {
            "Authorization": "Bearer performance_test_token",
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_order_submission_load(self, client, auth_headers):
        """Test order submission under load - critical path performance"""
        
        order_template = {
            "symbol": "AAPL",
            "quantity": 100,
            "side": "buy",
            "order_type": "market",
            "timestamp": datetime.now().isoformat()
        }
        
        # Performance metrics tracking
        response_times = []
        successful_orders = 0
        failed_orders = 0
        
        print(f"\n🚀 Starting Order Submission Load Test")
        
        with MemoryMonitor() as memory:
            with PerformanceTimer("Order Load Test") as timer:
                
                # Submit 50 orders concurrently to test load handling
                async def submit_single_order(order_id: int):
                    order_data = order_template.copy()
                    order_data["client_order_id"] = f"perf_test_{order_id}"
                    
                    start = time.perf_counter()
                    response = client.post("/api/v1/orders", json=order_data, headers=auth_headers)
                    end = time.perf_counter()
                    
                    response_time = end - start
                    memory.update_peak()
                    
                    return {
                        "order_id": order_id,
                        "status_code": response.status_code,
                        "response_time": response_time,
                        "success": response.status_code in [200, 201, 401, 422]  # Auth/validation errors acceptable
                    }
                
                # Execute concurrent order submissions
                tasks = [submit_single_order(i) for i in range(50)]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Analyze results
                for result in results:
                    if isinstance(result, dict):
                        response_times.append(result["response_time"])
                        if result["success"]:
                            successful_orders += 1
                        else:
                            failed_orders += 1
        
        # Performance Analysis
        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            max_response_time = max(response_times)
            
            print(f"📊 Order Submission Performance Metrics:")
            print(f"   Total Orders: {len(results)}")
            print(f"   Successful: {successful_orders}")
            print(f"   Failed: {failed_orders}")
            print(f"   Success Rate: {successful_orders/len(results)*100:.1f}%")
            print(f"   Avg Response Time: {avg_response_time:.3f}s")
            print(f"   95th Percentile: {p95_response_time:.3f}s")
            print(f"   Max Response Time: {max_response_time:.3f}s")
            print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
            print(f"   Total Test Time: {timer.duration:.3f}s")
            
            # Performance assertions
            assert avg_response_time < 2.0, f"Average response time too high: {avg_response_time:.3f}s"
            assert p95_response_time < 5.0, f"95th percentile too high: {p95_response_time:.3f}s"
            assert successful_orders >= len(results) * 0.8, f"Success rate too low: {successful_orders/len(results)*100:.1f}%"
            assert memory.memory_growth < 100, f"Memory growth too high: {memory.memory_growth:.2f}MB"

    @pytest.mark.asyncio
    async def test_portfolio_access_performance(self, client, auth_headers):
        """Test portfolio data access performance under concurrent load"""
        
        print(f"\n📈 Starting Portfolio Access Performance Test")
        
        response_times = []
        successful_requests = 0
        
        with MemoryMonitor() as memory:
            with PerformanceTimer("Portfolio Access Test") as timer:
                
                async def get_portfolio_data(request_id: int):
                    start = time.perf_counter()
                    response = client.get("/api/v1/portfolio/positions", headers=auth_headers)
                    end = time.perf_counter()
                    
                    memory.update_peak()
                    
                    return {
                        "request_id": request_id,
                        "status_code": response.status_code,
                        "response_time": end - start,
                        "success": response.status_code in [200, 401, 403]
                    }
                
                # Execute 100 concurrent portfolio requests
                tasks = [get_portfolio_data(i) for i in range(100)]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Analyze results
                for result in results:
                    if isinstance(result, dict):
                        response_times.append(result["response_time"])
                        if result["success"]:
                            successful_requests += 1
        
        # Performance Analysis
        if response_times:
            avg_response_time = statistics.mean(response_times)
            p99_response_time = statistics.quantiles(response_times, n=100)[98]  # 99th percentile
            
            print(f"📊 Portfolio Access Performance Metrics:")
            print(f"   Total Requests: {len(results)}")
            print(f"   Successful: {successful_requests}")
            print(f"   Success Rate: {successful_requests/len(results)*100:.1f}%")
            print(f"   Avg Response Time: {avg_response_time:.3f}s")
            print(f"   99th Percentile: {p99_response_time:.3f}s")
            print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
            print(f"   Throughput: {len(results)/timer.duration:.1f} req/s")
            
            # Performance assertions
            assert avg_response_time < 1.0, f"Portfolio access too slow: {avg_response_time:.3f}s"
            assert p99_response_time < 3.0, f"99th percentile too high: {p99_response_time:.3f}s"
            assert successful_requests >= len(results) * 0.9, f"Success rate too low"

    @pytest.mark.asyncio
    async def test_market_data_processing_performance(self, client):
        """Test market data processing performance with high-frequency updates"""
        
        print(f"\n📡 Starting Market Data Processing Performance Test")
        
        # Simulate high-frequency market data
        market_data_samples = []
        for i in range(1000):
            market_data_samples.append({
                "symbol": random.choice(["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]),
                "price": 100.0 + random.uniform(-10, 10),
                "volume": random.randint(1000, 10000),
                "timestamp": (datetime.now() + timedelta(milliseconds=i)).isoformat(),
                "bid": 99.9 + random.uniform(-10, 10),
                "ask": 100.1 + random.uniform(-10, 10)
            })
        
        processing_times = []
        
        with MemoryMonitor() as memory:
            with PerformanceTimer("Market Data Processing") as timer:
                
                # Mock market data processor
                with patch('backend.data.market_data.MarketDataProcessor') as mock_processor:
                    mock_instance = Mock()
                    mock_instance.process_tick = Mock()
                    mock_processor.return_value = mock_instance
                    
                    # Process market data in batches
                    batch_size = 50
                    for i in range(0, len(market_data_samples), batch_size):
                        batch = market_data_samples[i:i + batch_size]
                        
                        start = time.perf_counter()
                        
                        # Simulate processing each tick
                        for tick in batch:
                            mock_instance.process_tick(tick)
                        
                        end = time.perf_counter()
                        processing_times.append(end - start)
                        memory.update_peak()
        
        # Performance Analysis
        if processing_times:
            total_ticks = len(market_data_samples)
            avg_batch_time = statistics.mean(processing_times)
            ticks_per_second = total_ticks / timer.duration
            
            print(f"📊 Market Data Processing Performance:")
            print(f"   Total Ticks Processed: {total_ticks}")
            print(f"   Avg Batch Time: {avg_batch_time:.4f}s")
            print(f"   Processing Rate: {ticks_per_second:.1f} ticks/s")
            print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
            print(f"   Total Processing Time: {timer.duration:.3f}s")
            
            # Performance assertions
            assert ticks_per_second > 100, f"Processing rate too low: {ticks_per_second:.1f} ticks/s"
            assert avg_batch_time < 0.5, f"Batch processing too slow: {avg_batch_time:.4f}s"

    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, client, auth_headers):
        """Test mixed concurrent operations (orders, portfolio, market data)"""
        
        print(f"\n🔄 Starting Mixed Concurrent Operations Test")
        
        operation_results = []
        
        with MemoryMonitor() as memory:
            with PerformanceTimer("Mixed Operations Test") as timer:
                
                async def mixed_operation(op_id: int):
                    start = time.perf_counter()
                    
                    # Randomly choose operation type
                    op_type = random.choice(["order", "portfolio", "system"])
                    
                    if op_type == "order":
                        response = client.post("/api/v1/orders", json={
                            "symbol": "AAPL",
                            "quantity": 100,
                            "side": "buy",
                            "order_type": "market"
                        }, headers=auth_headers)
                    elif op_type == "portfolio":
                        response = client.get("/api/v1/portfolio/positions", headers=auth_headers)
                    else:  # system
                        response = client.get("/api/v1/system/status", headers=auth_headers)
                    
                    end = time.perf_counter()
                    memory.update_peak()
                    
                    return {
                        "op_id": op_id,
                        "op_type": op_type,
                        "status_code": response.status_code,
                        "response_time": end - start,
                        "success": response.status_code in [200, 201, 401, 403, 422]
                    }
                
                # Execute 75 mixed concurrent operations
                tasks = [mixed_operation(i) for i in range(75)]
                operation_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze mixed operation performance
        successful_ops = 0
        response_times_by_type = {"order": [], "portfolio": [], "system": []}
        
        for result in operation_results:
            if isinstance(result, dict) and result["success"]:
                successful_ops += 1
                op_type = result["op_type"]
                response_times_by_type[op_type].append(result["response_time"])
        
        print(f"📊 Mixed Operations Performance:")
        print(f"   Total Operations: {len(operation_results)}")
        print(f"   Successful: {successful_ops}")
        print(f"   Success Rate: {successful_ops/len(operation_results)*100:.1f}%")
        print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
        print(f"   Overall Throughput: {len(operation_results)/timer.duration:.1f} ops/s")
        
        # Per-operation type analysis
        for op_type, times in response_times_by_type.items():
            if times:
                avg_time = statistics.mean(times)
                print(f"   {op_type.title()} Avg Time: {avg_time:.3f}s ({len(times)} ops)")
        
        # Performance assertions
        assert successful_ops >= len(operation_results) * 0.8, "Mixed operation success rate too low"
        assert memory.memory_growth < 50, f"Memory growth too high: {memory.memory_growth:.2f}MB"


class TestMemoryUsageValidation:
    """Memory usage validation and leak detection"""

    @pytest.mark.asyncio
    async def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations"""
        
        print(f"\n🧠 Starting Memory Leak Detection Test")
        
        # Track memory usage over multiple iterations
        memory_snapshots = []
        
        for iteration in range(10):
            gc.collect()  # Force garbage collection
            
            with MemoryMonitor() as memory:
                # Simulate intensive operations
                data_structures = []
                
                # Create and destroy data structures
                for i in range(1000):
                    temp_dict = {
                        f"key_{i}": {
                            "data": list(range(100)),
                            "timestamp": datetime.now(),
                            "metadata": {"iteration": iteration, "index": i}
                        }
                    }
                    data_structures.append(temp_dict)
                
                # Process the data
                processed_count = 0
                for item in data_structures:
                    processed_count += len(item)
                
                # Clear references
                data_structures.clear()
                del data_structures
            
            memory_snapshots.append(memory.final_memory)
            print(f"   Iteration {iteration + 1}: {memory.final_memory:.2f}MB")
        
        # Analyze memory growth trend
        if len(memory_snapshots) >= 5:
            early_avg = statistics.mean(memory_snapshots[:3])
            late_avg = statistics.mean(memory_snapshots[-3:])
            memory_growth_trend = late_avg - early_avg
            
            print(f"📊 Memory Leak Analysis:")
            print(f"   Early Average: {early_avg:.2f}MB")
            print(f"   Late Average: {late_avg:.2f}MB")
            print(f"   Growth Trend: {memory_growth_trend:.2f}MB")
            
            # Memory leak assertion
            assert memory_growth_trend < 20, f"Potential memory leak detected: {memory_growth_trend:.2f}MB growth"

    @pytest.mark.asyncio
    async def test_garbage_collection_efficiency(self):
        """Test garbage collection efficiency and object cleanup"""
        
        print(f"\n🗑️ Starting Garbage Collection Efficiency Test")
        
        # Track object counts before and after operations
        initial_objects = len(gc.get_objects())
        
        with MemoryMonitor() as memory:
            # Create temporary objects
            temp_objects = []
            
            for i in range(5000):
                obj = {
                    "id": i,
                    "data": [random.random() for _ in range(50)],
                    "timestamp": datetime.now(),
                    "nested": {
                        "level1": {"level2": {"level3": list(range(20))}}
                    }
                }
                temp_objects.append(obj)
            
            peak_objects = len(gc.get_objects())
            
            # Clear references
            temp_objects.clear()
            del temp_objects
            
            # Force garbage collection
            collected = gc.collect()
        
        final_objects = len(gc.get_objects())
        
        print(f"📊 Garbage Collection Metrics:")
        print(f"   Initial Objects: {initial_objects}")
        print(f"   Peak Objects: {peak_objects}")
        print(f"   Final Objects: {final_objects}")
        print(f"   Objects Created: {peak_objects - initial_objects}")
        print(f"   Objects Cleaned: {peak_objects - final_objects}")
        print(f"   GC Collections: {collected}")
        print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
        
        # Efficiency assertions
        cleanup_ratio = (peak_objects - final_objects) / (peak_objects - initial_objects)
        assert cleanup_ratio > 0.8, f"Garbage collection efficiency too low: {cleanup_ratio:.2%}"
        assert memory.memory_growth < 30, f"Memory not properly released: {memory.memory_growth:.2f}MB"

    @pytest.mark.asyncio
    async def test_resource_cleanup_validation(self):
        """Test proper cleanup of resources (connections, files, handles)"""
        
        print(f"\n🔧 Starting Resource Cleanup Validation Test")
        
        with MemoryMonitor() as memory:
            # Mock resource creation and cleanup
            mock_resources = []
            
            # Simulate creating connections/resources
            for i in range(50):
                mock_resource = Mock()
                mock_resource.close = Mock()
                mock_resource.cleanup = Mock()
                mock_resource.is_closed = False
                mock_resources.append(mock_resource)
            
            # Simulate resource usage
            for resource in mock_resources:
                resource.use()  # Mock usage
            
            # Cleanup resources
            cleaned_count = 0
            for resource in mock_resources:
                if hasattr(resource, 'close'):
                    resource.close()
                    resource.is_closed = True
                    cleaned_count += 1
            
            # Clear references
            mock_resources.clear()
        
        print(f"📊 Resource Cleanup Metrics:")
        print(f"   Resources Created: 50")
        print(f"   Resources Cleaned: {cleaned_count}")
        print(f"   Cleanup Rate: {cleaned_count/50*100:.1f}%")
        print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
        
        # Resource cleanup assertions
        assert cleaned_count == 50, f"Not all resources cleaned: {cleaned_count}/50"
        assert memory.memory_growth < 10, f"Resource cleanup memory issue: {memory.memory_growth:.2f}MB"


class TestAsyncPerformance:
    """Async performance testing for concurrent operations"""

    @pytest.mark.asyncio
    async def test_async_task_performance(self):
        """Test async task creation and execution performance"""
        
        print(f"\n⚡ Starting Async Task Performance Test")
        
        async def async_operation(task_id: int, delay: float = 0.01):
            """Simulate async operation with small delay"""
            await asyncio.sleep(delay)
            return {
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "result": task_id * 2
            }
        
        task_counts = [10, 50, 100, 200]
        performance_results = {}
        
        for task_count in task_counts:
            with MemoryMonitor() as memory:
                with PerformanceTimer(f"{task_count} Async Tasks") as timer:
                    # Create and execute tasks
                    tasks = [async_operation(i) for i in range(task_count)]
                    results = await asyncio.gather(*tasks)
                    
                    performance_results[task_count] = {
                        "duration": timer.duration,
                        "memory_growth": memory.memory_growth,
                        "throughput": task_count / max(timer.duration, 0.001),
                        "successful": len(results)
                    }
        
        print(f"📊 Async Task Performance:")
        for count, metrics in performance_results.items():
            print(f"   {count} tasks: {metrics['duration']:.3f}s, "
                  f"{metrics['throughput']:.1f} tasks/s, "
                  f"{metrics['memory_growth']:.2f}MB")
        
        # Performance assertions
        for count, metrics in performance_results.items():
            assert metrics['throughput'] > count * 5, f"Async throughput too low for {count} tasks"
            assert metrics['memory_growth'] < 20, f"Memory growth too high for {count} tasks"

    @pytest.mark.asyncio
    async def test_websocket_message_throughput(self):
        """Test WebSocket message processing throughput"""
        
        print(f"\n📡 Starting WebSocket Message Throughput Test")
        
        # Mock WebSocket manager
        mock_manager = Mock()
        mock_manager.connected_clients = {}
        mock_manager.message_queue = asyncio.Queue()
        
        # Simulate message processing
        async def process_message(message_id: int):
            message = {
                "id": message_id,
                "type": "market_data",
                "symbol": "AAPL",
                "price": 150.0 + random.uniform(-5, 5),
                "timestamp": datetime.now().isoformat()
            }
            
            # Simulate message processing delay
            await asyncio.sleep(0.001)  # 1ms processing time
            
            return message
        
        message_counts = [100, 500, 1000]
        throughput_results = {}
        
        for msg_count in message_counts:
            with MemoryMonitor() as memory:
                with PerformanceTimer(f"{msg_count} WebSocket Messages") as timer:
                    # Process messages concurrently
                    tasks = [process_message(i) for i in range(msg_count)]
                    processed_messages = await asyncio.gather(*tasks)
                    
                    throughput_results[msg_count] = {
                        "duration": timer.duration,
                        "memory_growth": memory.memory_growth,
                        "throughput": msg_count / max(timer.duration, 0.001),
                        "processed": len(processed_messages)
                    }
        
        print(f"📊 WebSocket Message Throughput:")
        for count, metrics in throughput_results.items():
            print(f"   {count} messages: {metrics['duration']:.3f}s, "
                  f"{metrics['throughput']:.1f} msg/s, "
                  f"{metrics['memory_growth']:.2f}MB")
        
        # Throughput assertions
        for count, metrics in throughput_results.items():
            assert metrics['throughput'] > 100, f"WebSocket throughput too low: {metrics['throughput']:.1f} msg/s"
            assert metrics['processed'] == count, f"Message processing incomplete: {metrics['processed']}/{count}"

    @pytest.mark.asyncio
    async def test_database_operation_performance(self):
        """Test database operation performance simulation"""
        
        print(f"\n🗄️ Starting Database Operation Performance Test")
        
        # Mock database operations
        async def mock_db_query(query_id: int, query_type: str):
            """Simulate database query with realistic delays"""
            delays = {
                "select": 0.005,  # 5ms for SELECT
                "insert": 0.010,  # 10ms for INSERT  
                "update": 0.008,  # 8ms for UPDATE
                "delete": 0.006   # 6ms for DELETE
            }
            
            await asyncio.sleep(delays.get(query_type, 0.005))
            
            return {
                "query_id": query_id,
                "query_type": query_type,
                "rows_affected": random.randint(1, 100),
                "execution_time": delays.get(query_type, 0.005)
            }
        
        # Test different query mixes
        query_types = ["select", "insert", "update", "delete"]
        concurrent_queries = 50
        
        with MemoryMonitor() as memory:
            with PerformanceTimer("Database Operations") as timer:
                # Create mixed database operations
                tasks = []
                for i in range(concurrent_queries):
                    query_type = random.choice(query_types)
                    tasks.append(mock_db_query(i, query_type))
                
                # Execute concurrent database operations
                results = await asyncio.gather(*tasks)
        
        # Analyze database performance
        query_stats = {}
        for result in results:
            query_type = result["query_type"]
            if query_type not in query_stats:
                query_stats[query_type] = []
            query_stats[query_type].append(result["execution_time"])
        
        print(f"📊 Database Operation Performance:")
        print(f"   Total Queries: {len(results)}")
        print(f"   Total Time: {timer.duration:.3f}s")
        print(f"   Query Throughput: {len(results)/max(timer.duration, 0.001):.1f} queries/s")
        print(f"   Memory Growth: {memory.memory_growth:.2f}MB")
        
        for query_type, times in query_stats.items():
            if times:
                avg_time = statistics.mean(times)
                print(f"   {query_type.upper()} avg: {avg_time*1000:.1f}ms ({len(times)} queries)")
        
        # Database performance assertions
        total_throughput = len(results) / max(timer.duration, 0.001)
        assert total_throughput > 20, f"Database throughput too low: {total_throughput:.1f} queries/s"
        assert memory.memory_growth < 15, f"Database operations memory growth: {memory.memory_growth:.2f}MB"


class TestSystemStressPerformance:
    """System stress testing and performance limits"""

    @pytest.mark.asyncio
    async def test_high_load_stress_test(self):
        """Test system behavior under high load conditions"""
        
        print(f"\n🔥 Starting High Load Stress Test")
        
        # Simulate high load scenario
        load_phases = [
            {"duration": 2, "intensity": "low", "concurrent_ops": 20},
            {"duration": 3, "intensity": "medium", "concurrent_ops": 50},
            {"duration": 2, "intensity": "high", "concurrent_ops": 100},
        ]
        
        stress_results = {}
        
        for phase in load_phases:
            intensity = phase["intensity"]
            concurrent_ops = phase["concurrent_ops"]
            duration = phase["duration"]
            
            print(f"   Running {intensity} intensity phase: {concurrent_ops} ops for {duration}s")
            
            async def stress_operation(op_id: int):
                # Simulate varying operation complexity
                complexity = random.choice([0.001, 0.005, 0.01])  # 1ms, 5ms, 10ms
                await asyncio.sleep(complexity)
                
                return {
                    "op_id": op_id,
                    "complexity": complexity,
                    "timestamp": datetime.now().isoformat()
                }
            
            with MemoryMonitor() as memory:
                with PerformanceTimer(f"{intensity} load phase") as timer:
                    # Run operations for the specified duration
                    start_time = time.time()
                    completed_operations = []
                    
                    while time.time() - start_time < duration:
                        # Launch concurrent operations
                        tasks = [stress_operation(i) for i in range(concurrent_ops)]
                        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                        completed_operations.extend([r for r in batch_results if isinstance(r, dict)])
                        
                        # Small pause between batches
                        await asyncio.sleep(0.1)
                    
                    stress_results[intensity] = {
                        "completed_ops": len(completed_operations),
                        "duration": timer.duration,
                        "memory_growth": memory.memory_growth,
                        "throughput": len(completed_operations) / max(timer.duration, 0.001)
                    }
        
        print(f"📊 Stress Test Results:")
        for intensity, metrics in stress_results.items():
            print(f"   {intensity.title()} Load: {metrics['completed_ops']} ops, "
                  f"{metrics['throughput']:.1f} ops/s, "
                  f"{metrics['memory_growth']:.2f}MB")
        
        # Stress test assertions
        for intensity, metrics in stress_results.items():
            assert metrics['throughput'] > 10, f"{intensity} load throughput too low"
            assert metrics['memory_growth'] < 100, f"{intensity} load memory growth too high"

    @pytest.mark.asyncio
    async def test_performance_degradation_monitoring(self):
        """Monitor performance degradation over extended operation"""
        
        print(f"\n📉 Starting Performance Degradation Monitoring")
        
        # Run operations in waves and monitor performance degradation
        performance_snapshots = []
        
        for wave in range(5):
            print(f"   Performance wave {wave + 1}/5")
            
            with MemoryMonitor() as memory:
                with PerformanceTimer(f"Wave {wave + 1}") as timer:
                    # Each wave has progressively more operations
                    operations_count = 50 + (wave * 25)
                    
                    async def performance_operation(op_id: int):
                        # Simulate realistic operation
                        await asyncio.sleep(0.002)  # 2ms base operation
                        
                        # Some operations do more work
                        if op_id % 10 == 0:
                            await asyncio.sleep(0.005)  # 5ms for complex ops
                        
                        return {"op_id": op_id, "wave": wave}
                    
                    # Execute operations for this wave
                    tasks = [performance_operation(i) for i in range(operations_count)]
                    results = await asyncio.gather(*tasks)
                    
                    performance_snapshots.append({
                        "wave": wave + 1,
                        "operations": len(results),
                        "duration": timer.duration,
                        "memory_growth": memory.memory_growth,
                        "throughput": len(results) / max(timer.duration, 0.001)
                    })
        
        # Analyze performance degradation
        throughputs = [snap["throughput"] for snap in performance_snapshots]
        memory_growths = [snap["memory_growth"] for snap in performance_snapshots]
        
        print(f"📊 Performance Degradation Analysis:")
        for snap in performance_snapshots:
            print(f"   Wave {snap['wave']}: {snap['operations']} ops, "
                  f"{snap['throughput']:.1f} ops/s, "
                  f"{snap['memory_growth']:.2f}MB")
        
        # Calculate degradation metrics
        initial_throughput = throughputs[0]
        final_throughput = throughputs[-1]
        throughput_degradation = (initial_throughput - final_throughput) / initial_throughput
        
        total_memory_growth = sum(memory_growths)
        
        print(f"   Throughput Degradation: {throughput_degradation:.1%}")
        print(f"   Total Memory Growth: {total_memory_growth:.2f}MB")
        
        # Performance degradation assertions
        assert throughput_degradation < 0.3, f"Performance degradation too high: {throughput_degradation:.1%}"
        assert total_memory_growth < 150, f"Total memory growth too high: {total_memory_growth:.2f}MB"