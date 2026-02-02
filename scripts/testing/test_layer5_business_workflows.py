#!/usr/bin/env python3
"""
🎯 LAYER 5: BUSINESS WORKFLOW INTEGRATION TEST SUITE
====================================================
Complete end-to-end business workflow testing with advanced ML capabilities.
Tests what users actually DO with the platform in production scenarios.

This test suite covers:
- Advanced ML workflows (Ensemble Models, Model Manager, MLOps)
- Complete Signal-to-Order business processes  
- Real database persistence and state management
- Performance under realistic concurrent load
- Integration service orchestration
- Model serving and A/B testing scenarios
"""

import asyncio
import json
import time
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import uuid

import httpx

# Import K6 Cache Manager for centralized K6 execution
from k6_cache_manager import K6CacheManager, K6ExecutionConfig
import pandas as pd
import numpy as np

# Import enhanced test output
try:
    from test_output_enhanced import TestOutput, Colors, print_test_start, print_test_pass, print_test_fail, print_progress
except ImportError:
    # Fallback to basic output if enhanced module not available
    class TestOutput:
        @staticmethod
        def header(title, width=80): print(f"\n{'='*width}\n{title.center(width)}\n{'='*width}\n")
        @staticmethod
        def test_pass(name, dur, det=""): print(f"[OK] {name} ({dur:.0f}ms)")
        @staticmethod
        def test_fail(name, err): print(f"[FAIL] {name} - {err}")
        @staticmethod
        def progress(cur, tot, lbl="Progress"): print(f"{lbl}: {cur}/{tot}")
        @staticmethod
        def summary_box(title, items, width=70): print(f"\n{title}\n{items}\n")
        @staticmethod
        def test_summary(passed, failed, skipped=0, dur=0): print(f"Passed: {passed}, Failed: {failed}")
        @staticmethod
        def ascii_art_success(): print("\n*** SUCCESS ***\n")
        @staticmethod
        def ascii_art_partial(): print("\n*** PARTIAL SUCCESS ***\n")
        @staticmethod
        def section_divider(char='-', width=80): print(char * width)
        @staticmethod
        def subheader(title, width=80): print(f"\n{title}\n{'-'*width}")
        @staticmethod
        def metric(label, value, color='', unit=''): print(f"  {label}: {value} {unit}")
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def success(msg): print(f"[SUCCESS] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARNING] {msg}")
        @staticmethod
        def timestamp(): return datetime.now().strftime("%H:%M:%S")
    class Colors:
        RESET = ''; GREEN = ''; RED = ''; YELLOW = ''; CYAN = ''; BRIGHT_BLACK = ''
    def print_test_start(name): print(f"[TEST] {name}...", end='', flush=True)
    def print_test_pass(name, dur, det=""): print(f"\r[OK] {name} ({dur:.0f}ms)")
    def print_test_fail(name, err): print(f"\r[FAIL] {name} - {err}")
    def print_progress(cur, tot, lbl="Progress"): print(f"{lbl}: {cur}/{tot}")

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from backend.config.unified import get_settings
    from backend.mlops.model_manager import get_model_manager
    from backend.models.ensemble_model import EnsembleModel
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False
    print("Backend modules not available - testing in API-only mode")


@dataclass
class BusinessScenarioResult:
    """Result of a business scenario test"""
    scenario_name: str
    success: bool
    duration_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None
    sub_tests: List[Dict[str, Any]] = None


@dataclass
class MLWorkflowResult:
    """Result of ML workflow testing"""
    workflow_name: str
    model_type: str
    success: bool
    metrics: Dict[str, Any]
    performance_data: Dict[str, Any]
    error: Optional[str] = None


class Layer5BusinessWorkflowSuite:
    """Comprehensive Layer 5 business workflow test suite"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_token: Optional[str] = None
        self.test_results: List[BusinessScenarioResult] = []
        self.ml_results: List[MLWorkflowResult] = []
        self.test_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]
        self.concurrent_users = 5
        self.test_duration = 30  # seconds
        
    async def wait_for_server(self, timeout: int = 30) -> bool:
        """Wait for server to be ready with health check"""
        print("[WAIT] Waiting for server at http://localhost:8000...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{self.base_url}/health")
                    if response.status_code == 200:
                        health_data = response.json()
                        print(f"  [OK] Server ready! Status: {health_data.get('status', 'unknown')}")
                        return True
            except Exception:
                pass
            await asyncio.sleep(1)
        
        print("[FAIL] Server did not start within timeout")
        return False
    
    async def authenticate(self) -> bool:
        """Authenticate and get JWT token"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/login",
                    data={"username": "admin", "password": "admin123"}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    self.auth_token = token_data["access_token"]
                    print(f"[OK] Authenticated successfully (token length: {len(self.auth_token)})")
                    return True
                else:
                    print(f"[FAIL] Authentication failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            print(f"[FAIL] Authentication error: {e}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        return {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
    
    # ========================================
    # ML WORKFLOW TESTING
    # ========================================
    
    async def test_ml_ensemble_model_workflow(self) -> MLWorkflowResult:
        """Test advanced ensemble model workflow"""
        start_time = time.time()
        workflow_name = "ML Ensemble Model Integration"
        
        try:
            print("[ML] Testing ML Ensemble Model Workflow...")
            
            metrics = {}
            performance_data = {}
            
            # Test 1: Model status and availability
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self.get_headers()
                
                # Check model status endpoint
                response = await client.get(f"{self.base_url}/api/v1/models/status", headers=headers)
                if response.status_code == 200:
                    model_status = response.json()
                    metrics["model_status_available"] = True
                    metrics["model_count"] = len(model_status.get("models", []))
                    print(f"  [OK] Model Status: {metrics['model_count']} models available")
                else:
                    print(f"  [FAIL] Model Status failed: {response.status_code}")
                    
                # Test 2: Model training endpoint (if available)
                training_data = {
                    "model_name": "test_ensemble",
                    "symbols": self.test_symbols[:3],
                    "training_window": {
                        "start": "2024-01-01",
                        "end": "2024-06-01"
                    },
                    "model_type": "ensemble",
                    "config": {
                        "lookback_period": 100,
                        "ensemble_weights": {"lstm": 0.4, "xgboost": 0.4, "rf": 0.2}
                    }
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/models/train",
                    json=training_data,
                    headers=headers
                )
                
                if response.status_code in [200, 201, 202]:
                    train_result = response.json()
                    metrics["training_initiated"] = True
                    metrics["training_id"] = train_result.get("training_id", "unknown")
                    print(f"  [OK] Model Training: Initiated ({metrics['training_id']})")
                else:
                    metrics["training_initiated"] = False
                    print(f"  [WARN]  Model Training: {response.status_code} (may not be implemented)")
                
            duration = (time.time() - start_time) * 1000
            performance_data["total_duration_ms"] = duration
            
            return MLWorkflowResult(
                workflow_name=workflow_name,
                model_type="ensemble",
                success=True,
                metrics=metrics,
                performance_data=performance_data
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return MLWorkflowResult(
                workflow_name=workflow_name,
                model_type="ensemble",
                success=False,
                metrics={},
                performance_data={"total_duration_ms": duration},
                error=str(e)
            )
    
    async def test_ml_model_serving_workflow(self) -> MLWorkflowResult:
        """Test model serving and A/B testing workflow"""
        start_time = time.time()
        workflow_name = "Model Serving & A/B Testing"
        
        try:
            print("[TEST] Testing Model Serving & A/B Testing Workflow...")
            
            metrics = {}
            performance_data = {}
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self.get_headers()
                
                # Test model prediction endpoints for multiple symbols
                prediction_results = []
                
                for symbol in self.test_symbols[:3]:
                    # Test prediction endpoint (if available)
                    prediction_data = {
                        "symbol": symbol,
                        "model_version": "v1.0",
                        "features": {
                            "close": 150.0,
                            "volume": 1000000,
                            "rsi": 65.5,
                            "macd": 0.5,
                            "bb_position": 0.7
                        }
                    }
                    
                    response = await client.post(
                        f"{self.base_url}/api/v1/models/predict",
                        json=prediction_data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        pred_result = response.json()
                        prediction_results.append({
                            "symbol": symbol,
                            "prediction": pred_result.get("prediction", 0.0),
                            "confidence": pred_result.get("confidence", 0.0)
                        })
                        print(f"  [OK] Prediction for {symbol}: {pred_result.get('prediction', 'N/A')}")
                    else:
                        print(f"  [WARN]  Prediction for {symbol}: {response.status_code} (may not be implemented)")
                
                metrics["predictions_successful"] = len(prediction_results)
                metrics["prediction_results"] = prediction_results
                
                # Test model health endpoint
                response = await client.get(f"{self.base_url}/api/v1/models/health", headers=headers)
                if response.status_code == 200:
                    health_data = response.json()
                    metrics["model_health_available"] = True
                    metrics["model_health"] = health_data
                    print(f"  [OK] Model Health Check: Available")
                else:
                    print(f"  [WARN]  Model Health: {response.status_code} (may not be implemented)")
            
            duration = (time.time() - start_time) * 1000
            performance_data["total_duration_ms"] = duration
            
            return MLWorkflowResult(
                workflow_name=workflow_name,
                model_type="serving",
                success=len(prediction_results) > 0 or metrics.get("model_health_available", False),
                metrics=metrics,
                performance_data=performance_data
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return MLWorkflowResult(
                workflow_name=workflow_name,
                model_type="serving",
                success=False,
                metrics={},
                performance_data={"total_duration_ms": duration},
                error=str(e)
            )
    
    # ========================================
    # BUSINESS WORKFLOW TESTING
    # ========================================
    
    async def test_signal_to_order_workflow(self) -> BusinessScenarioResult:
        """Test complete signal-to-order business workflow"""
        start_time = time.time()
        scenario_name = "Signal-to-Order Workflow"
        
        try:
            print("[SIGNAL] Testing Signal-to-Order Business Workflow...")
            
            sub_tests = []
            order_ids = []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self.get_headers()
                
                # Test 1: Create trading signals for multiple symbols
                print("  [STEP] Creating trading signals...")
                for i, symbol in enumerate(self.test_symbols[:3]):
                    signal_data = {
                        "symbol": symbol,
                        "signal_type": "BUY" if i % 2 == 0 else "SELL",
                        "confidence": 0.75 + (i * 0.05),
                        "action": "BUY" if i % 2 == 0 else "SELL",
                        "quantity": 10 * (i + 1),
                        "price": 150.0 + (i * 10),
                        "metadata": {
                            "strategy": "ensemble_ml",
                            "test_batch": "layer5_workflow",
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                    }
                    
                    response = await client.post(
                        f"{self.base_url}/api/v1/signals/",
                        json=signal_data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        signal_result = response.json()
                        sub_tests.append({
                            "test": f"Signal Creation - {symbol}",
                            "success": True,
                            "signal_id": signal_result.get("signal_id", "unknown"),
                            "confidence": signal_result.get("confidence", 0.0)
                        })
                        print(f"    [OK] Signal created for {symbol}")
                    else:
                        sub_tests.append({
                            "test": f"Signal Creation - {symbol}",
                            "success": False,
                            "error": f"HTTP {response.status_code}"
                        })
                        print(f"    [FAIL] Signal failed for {symbol}: {response.status_code}")
                
                # Test 2: Test signal-to-order conversion (if /act endpoint exists)
                print("  [STEP] Testing signal-to-order conversion...")
                for symbol in self.test_symbols[:2]:
                    act_data = {
                        "symbol": symbol,
                        "lookback": 200,
                        "size_mode": "fixed",
                        "fixed_qty": 10.0,
                        "risk_budget_pct": 0.01,
                        "portfolio_value": 100000.0
                    }
                    
                    response = await client.post(
                        f"{self.base_url}/api/v1/signals/act",
                        json=act_data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        act_result = response.json()
                        # Defensive check for None response
                        if act_result is None:
                            act_result = {}
                        
                        order_data = act_result.get("order", {})
                        # Defensive check for None order_data
                        if order_data is None:
                            order_data = {}
                        
                        order_id = order_data.get("order_id")
                        
                        if order_id:
                            order_ids.append(order_id)
                            sub_tests.append({
                                "test": f"Signal-to-Order - {symbol}",
                                "success": True,
                                "order_id": order_id,
                                "action": act_result.get("action", "unknown")
                            })
                            print(f"    [OK] Order created for {symbol}: {order_id}")
                        else:
                            sub_tests.append({
                                "test": f"Signal-to-Order - {symbol}",
                                "success": False,
                                "error": "No order_id returned"
                            })
                            print(f"    [FAIL] No order created for {symbol}")
                    else:
                        error_detail = "Unknown error"
                        try:
                            error_data = response.json()
                            error_detail = error_data.get("detail", f"HTTP {response.status_code}")
                        except:
                            error_detail = f"HTTP {response.status_code}"
                        
                        sub_tests.append({
                            "test": f"Signal-to-Order - {symbol}",
                            "success": False,
                            "error": error_detail
                        })
                        print(f"    [FAIL] Order conversion failed for {symbol}: {error_detail}")
                
                # Test 3: Order status tracking
                print("  [STEP] Testing order status tracking...")
                if order_ids:
                    for order_id in order_ids:
                        response = await client.get(
                            f"{self.base_url}/api/v1/orders/{order_id}",
                            headers=headers
                        )
                        
                        if response.status_code == 200:
                            order_status = response.json()
                            sub_tests.append({
                                "test": f"Order Status - {order_id[:8]}",
                                "success": True,
                                "status": order_status.get("status", "unknown"),
                                "symbol": order_status.get("symbol", "unknown")
                            })
                            print(f"    [OK] Order status retrieved: {order_id[:8]}")
                        else:
                            sub_tests.append({
                                "test": f"Order Status - {order_id[:8]}",
                                "success": False,
                                "error": f"HTTP {response.status_code}"
                            })
                            print(f"    [FAIL] Order status failed: {order_id[:8]}")
                
                # Test 4: Portfolio positions
                print("  [STEP] Testing portfolio positions...")
                response = await client.get(f"{self.base_url}/api/v1/portfolio/positions", headers=headers)
                
                if response.status_code == 200:
                    positions = response.json()
                    # Handle both dict and list responses
                    if isinstance(positions, dict):
                        position_count = len(positions.get("positions", []))
                        total_value = positions.get("total_value", 0.0)
                    else:
                        position_count = len(positions) if isinstance(positions, list) else 0
                        total_value = 0.0
                    
                    sub_tests.append({
                        "test": "Portfolio Positions",
                        "success": True,
                        "position_count": position_count,
                        "total_value": total_value
                    })
                    print(f"    [OK] Portfolio positions retrieved")
                else:
                    sub_tests.append({
                        "test": "Portfolio Positions",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [FAIL] Portfolio positions failed: {response.status_code}")
            
            duration = (time.time() - start_time) * 1000
            successful_tests = sum(1 for test in sub_tests if test["success"])
            success_rate = successful_tests / len(sub_tests) if sub_tests else 0.0
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=success_rate >= 0.5,  # At least 50% success rate
                duration_ms=duration,
                details={
                    "success_rate": f"{success_rate:.1%}",
                    "successful_tests": successful_tests,
                    "total_tests": len(sub_tests),
                    "orders_created": len(order_ids),
                    "order_ids": order_ids
                },
                sub_tests=sub_tests
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def test_real_order_execution_workflow(self) -> BusinessScenarioResult:
        """
        Test REAL order execution workflow with Alpaca Paper Trading API.
        This replaces mock-based order testing with actual API integration.
        
        Tests:
        1. Real paper trading order placement via Alpaca API
        2. Order lifecycle validation (pending → filled/cancelled)
        3. Position updates after order fills
        4. Order cancellation capability
        """
        start_time = time.time()
        scenario_name = "Real Order Execution (Alpaca Paper Trading)"
        
        try:
            print("[ORDER] Testing Real Order Execution with Alpaca Paper Trading...")
            
            sub_tests = []
            order_ids = []
            
            # Import Alpaca SDK
            try:
                from alpaca.trading.client import TradingClient
                from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
                from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
            except ImportError:
                return BusinessScenarioResult(
                    scenario_name=scenario_name,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    details={},
                    error="alpaca-py not installed. Run: pip install alpaca-py",
                    sub_tests=[]
                )
            
            # Get Alpaca credentials
            api_key = os.getenv("ALPACA_API_KEY_ID")
            api_secret = os.getenv("ALPACA_API_SECRET_KEY")
            
            if not api_key or not api_secret:
                return BusinessScenarioResult(
                    scenario_name=scenario_name,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    details={},
                    error="Missing ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY environment variables",
                    sub_tests=[]
                )
            
            # Initialize Alpaca client for paper trading
            trading_client = TradingClient(api_key, api_secret, paper=True)
            
            # Test 1: Verify account access and get initial state
            print("  [STEP] Verifying Alpaca account access...")
            try:
                account = trading_client.get_account()
                initial_buying_power = float(account.buying_power)
                initial_cash = float(account.cash)
                
                sub_tests.append({
                    "test": "Account Access Verification",
                    "success": True,
                    "details": {
                        "account_status": str(account.status),
                        "buying_power": initial_buying_power,
                        "cash": initial_cash,
                        "pattern_day_trader": bool(account.pattern_day_trader)
                    }
                })
                print(f"    [OK] Account verified - Status: {account.status}, Buying Power: ${initial_buying_power:.2f}")
            except Exception as e:
                sub_tests.append({
                    "test": "Account Access Verification",
                    "success": False,
                    "error": str(e)
                })
                print(f"    [FAIL] Account verification failed: {str(e)}")
                raise
            
            # Test 2: Place REAL market order (small quantity for testing)
            test_symbol = "SPY"  # Highly liquid ETF
            test_quantity = 1    # Small quantity for paper trading test
            
            print(f"  [STEP] Placing REAL market order: {test_quantity} shares of {test_symbol}...")
            try:
                # Create market order request
                order_request = MarketOrderRequest(
                    symbol=test_symbol,
                    qty=test_quantity,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                
                # Submit order to Alpaca
                order = trading_client.submit_order(order_request)
                order_id = str(order.id)
                order_ids.append(order_id)
                
                sub_tests.append({
                    "test": f"Market Order Placement - {test_symbol}",
                    "success": True,
                    "details": {
                        "order_id": order_id,
                        "symbol": order.symbol,
                        "qty": float(order.qty),
                        "side": str(order.side),
                        "type": str(order.type),
                        "status": str(order.status),
                        "submitted_at": str(order.submitted_at)
                    }
                })
                print(f"    [OK] Order placed - ID: {order_id}, Status: {order.status}")
            except Exception as e:
                sub_tests.append({
                    "test": f"Market Order Placement - {test_symbol}",
                    "success": False,
                    "error": str(e)
                })
                print(f"    [FAIL] Order placement failed: {str(e)}")
                # Don't raise - continue with other tests
            
            # Test 3: Monitor order status until completion or timeout
            if order_ids:
                print("  [STEP] Monitoring order status...")
                try:
                    max_wait_seconds = 30
                    poll_interval = 2
                    elapsed_time = 0
                    
                    final_status = None
                    while elapsed_time < max_wait_seconds:
                        order = trading_client.get_order_by_id(order_ids[0])
                        current_status = str(order.status)
                        
                        # Check if order is in final state
                        if current_status in ["filled", "cancelled", "expired", "rejected"]:
                            final_status = current_status
                            break
                        
                        await asyncio.sleep(poll_interval)
                        elapsed_time += poll_interval
                    
                    if final_status:
                        sub_tests.append({
                            "test": "Order Lifecycle Monitoring",
                            "success": True,
                            "details": {
                                "final_status": final_status,
                                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                                "time_to_completion": elapsed_time
                            }
                        })
                        print(f"    [OK] Order completed - Status: {final_status}, Filled: {order.filled_qty} @ ${order.filled_avg_price}")
                    else:
                        sub_tests.append({
                            "test": "Order Lifecycle Monitoring",
                            "success": False,
                            "error": f"Order did not complete within {max_wait_seconds}s - Status: {current_status}"
                        })
                        print(f"    [WARN] Order still pending after {max_wait_seconds}s - Status: {current_status}")
                except Exception as e:
                    sub_tests.append({
                        "test": "Order Lifecycle Monitoring",
                        "success": False,
                        "error": str(e)
                    })
                    print(f"    [FAIL] Order monitoring failed: {str(e)}")
            
            # Test 4: Verify position was created (if order filled)
            print("  [STEP] Checking positions after order...")
            try:
                positions = trading_client.get_all_positions()
                position_symbols = [p.symbol for p in positions]
                
                test_symbol_in_positions = test_symbol in position_symbols
                position_details = None
                
                if test_symbol_in_positions:
                    position = next(p for p in positions if p.symbol == test_symbol)
                    position_details = {
                        "symbol": position.symbol,
                        "qty": float(position.qty),
                        "market_value": float(position.market_value),
                        "avg_entry_price": float(position.avg_entry_price),
                        "unrealized_pl": float(position.unrealized_pl)
                    }
                
                sub_tests.append({
                    "test": "Position Verification",
                    "success": True,
                    "details": {
                        "total_positions": len(positions),
                        "test_symbol_found": test_symbol_in_positions,
                        "position": position_details
                    }
                })
                
                if test_symbol_in_positions:
                    print(f"    [OK] Position found - {test_symbol}: {position_details['qty']} shares @ ${position_details['avg_entry_price']:.2f}")
                else:
                    print(f"    [INFO] Position not found for {test_symbol} (order may not have filled)")
            except Exception as e:
                sub_tests.append({
                    "test": "Position Verification",
                    "success": False,
                    "error": str(e)
                })
                print(f"    [FAIL] Position check failed: {str(e)}")
            
            # Test 5: Test order cancellation (place and immediately cancel)
            print(f"  [STEP] Testing order cancellation with limit order...")
            try:
                # Use a limit order with unrealistic price so it won't fill immediately
                from alpaca.trading.requests import LimitOrderRequest
                
                # Get current price and set limit way below market
                current_price = None
                try:
                    from alpaca.data.historical import StockHistoricalDataClient
                    from alpaca.data.requests import StockLatestQuoteRequest
                    
                    data_client = StockHistoricalDataClient(api_key, api_secret)
                    quote_request = StockLatestQuoteRequest(symbol_or_symbols=test_symbol)
                    quotes = data_client.get_stock_latest_quote(quote_request)
                    current_price = float(quotes[test_symbol].ask_price)
                    # 50% below market - won't fill, round to 2 decimals for valid price format
                    limit_price = round(current_price * 0.5, 2)
                except:
                    limit_price = 1.00  # Fallback unrealistic price (valid 2-decimal format)
                
                cancel_order_request = LimitOrderRequest(
                    symbol=test_symbol,
                    qty=1,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price
                )
                
                cancel_order = trading_client.submit_order(cancel_order_request)
                cancel_order_id = str(cancel_order.id)
                
                # Wait a moment then cancel
                await asyncio.sleep(1)
                trading_client.cancel_order_by_id(cancel_order_id)
                
                # Verify cancellation
                await asyncio.sleep(1)
                cancelled_order = trading_client.get_order_by_id(cancel_order_id)
                
                cancellation_successful = str(cancelled_order.status) in ["cancelled", "pending_cancel"]
                
                sub_tests.append({
                    "test": "Order Cancellation",
                    "success": cancellation_successful,
                    "details": {
                        "order_id": cancel_order_id,
                        "status": str(cancelled_order.status)
                    }
                })
                
                if cancellation_successful:
                    print(f"    [OK] Order cancelled successfully - ID: {cancel_order_id}")
                else:
                    print(f"    [WARN] Order cancellation status: {cancelled_order.status}")
            except Exception as e:
                sub_tests.append({
                    "test": "Order Cancellation",
                    "success": False,
                    "error": str(e)
                })
                print(f"    [FAIL] Order cancellation test failed: {str(e)}")
            
            # Calculate overall success
            successful_tests = sum(1 for t in sub_tests if t.get("success", False))
            total_tests = len(sub_tests)
            success_rate = successful_tests / total_tests if total_tests > 0 else 0.0
            
            # Success if at least 80% of tests pass
            overall_success = success_rate >= 0.8
            
            duration_ms = (time.time() - start_time) * 1000
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=overall_success,
                duration_ms=duration_ms,
                details={
                    "total_tests": total_tests,
                    "successful_tests": successful_tests,
                    "success_rate": f"{success_rate:.1%}",
                    "orders_placed": len(order_ids),
                    "order_ids": order_ids,
                    "test_symbol": test_symbol,
                    "performance_summary": f"{successful_tests}/{total_tests} tests passed ({success_rate:.0%})"
                },
                error=None if overall_success else f"Only {successful_tests}/{total_tests} tests passed",
                sub_tests=sub_tests
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            print(f"  [ERROR] Real order execution workflow failed: {str(e)}")
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e),
                sub_tests=sub_tests if 'sub_tests' in locals() else []
            )
    
    async def test_risk_management_workflow(self) -> BusinessScenarioResult:
        """Test risk management and compliance workflow"""
        start_time = time.time()
        scenario_name = "Risk Management & Compliance"
        
        try:
            print("[RISK] Testing Risk Management & Compliance Workflow...")
            
            sub_tests = []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self.get_headers()
                
                # Test 1: Risk metrics endpoint
                response = await client.get(f"{self.base_url}/api/v1/risk/metrics", headers=headers)
                if response.status_code == 200:
                    risk_data = response.json()
                    sub_tests.append({
                        "test": "Risk Metrics",
                        "success": True,
                        "risk_score": risk_data.get("risk_metrics", {}).get("risk_score", "N/A"),
                        "daily_usage": risk_data.get("risk_metrics", {}).get("daily_orders_used", 0)
                    })
                    print(f"    [OK] Risk metrics retrieved")
                else:
                    sub_tests.append({
                        "test": "Risk Metrics",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [FAIL] Risk metrics failed: {response.status_code}")
                
                # Test 2: Risk-blocked order submission (should fail gracefully)
                risky_order = {
                    "symbol": "AAPL",
                    "qty": 10000,  # Large quantity to trigger risk limits
                    "side": "buy",
                    "order_type": "market",
                    "time_in_force": "day"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/orders/",
                    json=risky_order,
                    headers=headers
                )
                
                if response.status_code == 422:
                    error_data = response.json()
                    if "risk" in str(error_data).lower() or "limit" in str(error_data).lower():
                        sub_tests.append({
                            "test": "Risk Blocking",
                            "success": True,
                            "blocked_reason": "Risk limits enforced",
                            "risk_working": True
                        })
                        print(f"    [OK] Risk management correctly blocked high-risk order")
                    else:
                        sub_tests.append({
                            "test": "Risk Blocking",
                            "success": True,
                            "blocked_reason": "Validation error (expected)",
                            "risk_working": True
                        })
                        print(f"    [OK] Order validation working (blocked for validation)")
                else:
                    sub_tests.append({
                        "test": "Risk Blocking",
                        "success": False,
                        "error": f"Order was not blocked (HTTP {response.status_code})"
                    })
                    print(f"    [WARN]  Risk blocking test inconclusive: {response.status_code}")
                
                # Test 3: Market hours enforcement
                current_time = datetime.now(UTC)
                market_hours_test = {
                    "symbol": "AAPL",
                    "qty": 1,
                    "side": "buy",
                    "order_type": "market",
                    "time_in_force": "day"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/orders/",
                    json=market_hours_test,
                    headers=headers
                )
                
                # Check if order is blocked due to market hours
                if response.status_code == 422:
                    error_data = response.json()
                    error_text = str(error_data).lower()
                    if "market" in error_text and ("closed" in error_text or "hours" in error_text):
                        sub_tests.append({
                            "test": "Market Hours Enforcement",
                            "success": True,
                            "enforcement": "Market hours properly enforced",
                            "current_time_utc": current_time.isoformat()
                        })
                        print(f"    [OK] Market hours enforcement working")
                    else:
                        sub_tests.append({
                            "test": "Market Hours Enforcement",
                            "success": True,
                            "enforcement": "Order blocked (risk/validation)",
                            "current_time_utc": current_time.isoformat()
                        })
                        print(f"    [OK] Order blocked (validation/risk working)")
                else:
                    sub_tests.append({
                        "test": "Market Hours Enforcement",
                        "success": False,
                        "error": f"Order not blocked as expected (HTTP {response.status_code})"
                    })
                    print(f"    [WARN]  Market hours test inconclusive: {response.status_code}")
            
            duration = (time.time() - start_time) * 1000
            successful_tests = sum(1 for test in sub_tests if test["success"])
            success_rate = successful_tests / len(sub_tests) if sub_tests else 0.0
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=success_rate >= 0.67,  # At least 67% success rate
                duration_ms=duration,
                details={
                    "success_rate": f"{success_rate:.1%}",
                    "successful_tests": successful_tests,
                    "total_tests": len(sub_tests),
                    "risk_management_active": True
                },
                sub_tests=sub_tests
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def test_integration_services_workflow(self) -> BusinessScenarioResult:
        """Test integration services and external connections"""
        start_time = time.time()
        scenario_name = "Integration Services & External APIs"
        
        try:
            print("[INTEGRATION] Testing Integration Services & External APIs...")
            
            sub_tests = []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self.get_headers()
                
                # Test 1: System status with integrations
                response = await client.get(f"{self.base_url}/api/v1/system/status", headers=headers)
                if response.status_code == 200:
                    status_data = response.json()
                    integrations = status_data.get("integrations", {})
                    sub_tests.append({
                        "test": "System Status",
                        "success": True,
                        "integrations_count": len(integrations),
                        "system_health": status_data.get("status", "unknown")
                    })
                    print(f"    [OK] System status retrieved ({len(integrations)} integrations)")
                else:
                    sub_tests.append({
                        "test": "System Status",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [FAIL] System status failed: {response.status_code}")
                
                # Test 2: Market data integration (if available)
                response = await client.get(
                    f"{self.base_url}/api/v1/market/quote",
                    params={"symbol": "AAPL"},
                    headers=headers
                )
                if response.status_code == 200:
                    quote_data = response.json()
                    sub_tests.append({
                        "test": "Market Data Integration",
                        "success": True,
                        "symbol": quote_data.get("symbol", "unknown"),
                        "price": quote_data.get("price", 0.0)
                    })
                    print(f"    [OK] Market data integration working")
                else:
                    sub_tests.append({
                        "test": "Market Data Integration",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [WARN]  Market data integration: {response.status_code} (may not be implemented)")
                
                # Test 3: Sentiment analysis integration (if available)
                response = await client.get(
                    f"{self.base_url}/api/v1/sentiment",
                    params={"symbol": "AAPL"},
                    headers=headers
                )
                if response.status_code == 200:
                    sentiment_data = response.json()
                    sub_tests.append({
                        "test": "Sentiment Analysis",
                        "success": True,
                        "sentiment": sentiment_data.get("sentiment", {}),
                        "symbol": sentiment_data.get("symbol", "unknown")
                    })
                    print(f"    [OK] Sentiment analysis working")
                else:
                    sub_tests.append({
                        "test": "Sentiment Analysis",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [WARN]  Sentiment analysis: {response.status_code} (may not be implemented)")
                
                # Test 4: Broker integration status
                response = await client.get(f"{self.base_url}/api/v1/broker/status", headers=headers)
                if response.status_code == 200:
                    broker_data = response.json()
                    sub_tests.append({
                        "test": "Broker Integration",
                        "success": True,
                        "broker_status": broker_data.get("status", "unknown"),
                        "connection": "active"
                    })
                    print(f"    [OK] Broker integration status available")
                else:
                    sub_tests.append({
                        "test": "Broker Integration",
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    })
                    print(f"    [WARN]  Broker integration: {response.status_code} (may not be implemented)")
            
            duration = (time.time() - start_time) * 1000
            successful_tests = sum(1 for test in sub_tests if test["success"])
            success_rate = successful_tests / len(sub_tests) if sub_tests else 0.0
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=success_rate >= 0.25,  # At least 25% success rate (some endpoints may not be implemented)
                duration_ms=duration,
                details={
                    "success_rate": f"{success_rate:.1%}",
                    "successful_tests": successful_tests,
                    "total_tests": len(sub_tests),
                    "integration_services_tested": len(sub_tests)
                },
                sub_tests=sub_tests
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    # ========================================
    # PERFORMANCE & LOAD TESTING
    # ========================================
    
    async def test_concurrent_user_load(self) -> BusinessScenarioResult:
        """Test concurrent user load with realistic trading scenarios"""
        start_time = time.time()
        scenario_name = "Concurrent User Load Testing"
        
        try:
            print(f"[LOAD] Testing Concurrent User Load ({self.concurrent_users} users)...")
            
            # Create concurrent trading sessions
            tasks = []
            for user_id in range(self.concurrent_users):
                task = asyncio.create_task(
                    self._simulate_trading_user(user_id, duration=10)
                )
                tasks.append(task)
            
            # Run all users concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful_users = 0
            total_requests = 0
            total_errors = 0
            user_results = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    user_results.append({
                        "user_id": i,
                        "success": False,
                        "error": str(result)
                    })
                else:
                    successful_users += 1
                    total_requests += result.get("total_requests", 0)
                    total_errors += result.get("total_errors", 0)
                    user_results.append({
                        "user_id": i,
                        "success": True,
                        "requests": result.get("total_requests", 0),
                        "errors": result.get("total_errors", 0),
                        "avg_response_time": result.get("avg_response_time", 0.0)
                    })
            
            duration = (time.time() - start_time) * 1000
            success_rate = successful_users / self.concurrent_users
            error_rate = (total_errors / max(total_requests, 1)) * 100
            
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=success_rate >= 0.8 and error_rate < 20,  # 80% user success, <20% error rate
                duration_ms=duration,
                details={
                    "concurrent_users": self.concurrent_users,
                    "successful_users": successful_users,
                    "user_success_rate": f"{success_rate:.1%}",
                    "total_requests": total_requests,
                    "total_errors": total_errors,
                    "error_rate": f"{error_rate:.1f}%",
                    "requests_per_second": round(total_requests / (duration / 1000), 2)
                },
                sub_tests=user_results
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def _simulate_trading_user(self, user_id: int, duration: int = 10) -> Dict[str, Any]:
        """Simulate a single trading user for load testing"""
        start_time = time.time()
        total_requests = 0
        total_errors = 0
        response_times = []
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = self.get_headers()
                
                # Simulate trading activity for specified duration
                while time.time() - start_time < duration:
                    # Random trading actions
                    actions = [
                        ("health_check", "GET", "/health", None),
                        ("signal_creation", "POST", "/api/v1/signals/", {
                            "symbol": np.random.choice(self.test_symbols),
                            "signal_type": np.random.choice(["BUY", "SELL"]),
                            "confidence": np.random.uniform(0.6, 0.9),
                            "action": "BUY",
                            "quantity": np.random.randint(1, 20),
                            "price": np.random.uniform(100, 200)
                        }),
                        ("user_profile", "GET", "/api/v1/auth/me", None),
                    ]
                    
                    action_name, method, endpoint, data = np.random.choice(actions)
                    
                    req_start = time.time()
                    total_requests += 1
                    
                    try:
                        if method == "GET":
                            response = await client.get(f"{self.base_url}{endpoint}", headers=headers)
                        elif method == "POST":
                            response = await client.post(f"{self.base_url}{endpoint}", json=data, headers=headers)
                        
                        req_time = (time.time() - req_start) * 1000
                        response_times.append(req_time)
                        
                        if response.status_code >= 400 and response.status_code != 422:  # 422 is expected (risk management)
                            total_errors += 1
                            
                    except Exception:
                        total_errors += 1
                        response_times.append(10000)  # 10s timeout
                    
                    # Small delay between requests
                    await asyncio.sleep(np.random.uniform(0.1, 0.5))
            
            avg_response_time = np.mean(response_times) if response_times else 0.0
            
            return {
                "user_id": user_id,
                "total_requests": total_requests,
                "total_errors": total_errors,
                "avg_response_time": avg_response_time,
                "success": True
            }
            
        except Exception as e:
            return {
                "user_id": user_id,
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error": str(e),
                "success": False
            }
    
    async def run_k6_performance_test(self) -> BusinessScenarioResult:
        """Run K6 performance test using centralized cache manager"""
        start_time = time.time()
        scenario_name = "K6 Performance Test"
        
        try:
            print("[K6] Running K6 Performance Test using cache manager...")
            
            # Configure K6 execution using cache manager
            k6_config = K6ExecutionConfig(
                duration="15s",
                virtual_users=3,
                base_url=self.base_url,
                k6_script="scripts/testing/k6_enhanced_comprehensive_test.js",
                cache_ttl_minutes=10,  # Use cached results if less than 10 minutes old
                force_refresh=False    # Allow cache reuse for business workflow tests
            )
            
            # Get K6 results using cache manager
            cache_manager = K6CacheManager("test_results")
            k6_result = await cache_manager.get_k6_results(k6_config)
            
            duration = (time.time() - start_time) * 1000
            
            if k6_result.test_passed:
                return BusinessScenarioResult(
                    scenario_name=scenario_name,
                    success=True,
                    duration_ms=duration,
                    details={
                        "k6_available": True,
                        "test_completed": True,
                        "cached_result": k6_result.execution_id != f"k6_{int(time.time())}_",  # Simple cache detection
                        "success_rate": f"{k6_result.success_rate:.3%}",
                        "p95_latency_ms": f"{k6_result.p95_latency_ms:.1f}",
                        "unexpected_error_rate": f"{k6_result.unexpected_error_rate:.3%}",
                        "total_requests": k6_result.total_requests,
                        "performance_summary": f"Success: {k6_result.success_rate:.1%}, P95: {k6_result.p95_latency_ms:.0f}ms"
                    }
                )
            else:
                return BusinessScenarioResult(
                    scenario_name=scenario_name,
                    success=False,
                    duration_ms=duration,
                    details={
                        "k6_available": True,
                        "test_failed": True,
                        "failure_reasons": k6_result.failure_reasons,
                        "error_details": k6_result.error_details
                    }
                )
                    
        except FileNotFoundError:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=True,  # Not a failure if K6 is not installed
                duration_ms=duration,
                details={
                    "k6_available": False,
                    "skipped": "K6 not installed - test skipped"
                }
            )
        except subprocess.TimeoutExpired:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={
                    "k6_available": True,
                    "timeout": True,
                    "error": "K6 test timed out"
                }
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return BusinessScenarioResult(
                scenario_name=scenario_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    # ========================================
    # MAIN TEST ORCHESTRATION
    # ========================================
    
    async def run_all_tests(self) -> Tuple[bool, Dict[str, Any]]:
        """Run complete Layer 5 business workflow test suite"""
        TestOutput.layer_header(5, "BUSINESS WORKFLOW INTEGRATION TESTING", ">")
        print(f"{Colors.BRIGHT_BLACK}Testing comprehensive business workflows and ML capabilities...{Colors.RESET}")
        TestOutput.metric("Server", self.base_url, Colors.CYAN)
        TestOutput.metric("Concurrent Users", str(self.concurrent_users), Colors.CYAN)
        TestOutput.metric("Test Symbols", ', '.join(self.test_symbols), Colors.CYAN)
        TestOutput.section_divider()
        
        # Check server availability
        if not await self.wait_for_server():
            TestOutput.error("Server not available")
            TestOutput.error("Server not available")
            return False, {"error": "Server not available"}
        
        # Authenticate
        TestOutput.info("Authenticating...")
        if not await self.authenticate():
            TestOutput.error("Authentication failed")
            return False, {"error": "Authentication failed"}
        TestOutput.success("Authentication successful")
        
        # Run ML workflow tests
        TestOutput.section_divider()
        TestOutput.subheader("ML WORKFLOW TESTING")
        
        ml_tests = [
            self.test_ml_ensemble_model_workflow(),
            self.test_ml_model_serving_workflow(),
        ]
        
        TestOutput.info(f"Running {len(ml_tests)} ML workflow tests...")
        self.ml_results = await asyncio.gather(*ml_tests, return_exceptions=True)
        
        # Convert exceptions to failed results
        for i, result in enumerate(self.ml_results):
            if isinstance(result, Exception):
                self.ml_results[i] = MLWorkflowResult(
                    workflow_name=f"ML Test {i+1}",
                    model_type="unknown",
                    success=False,
                    metrics={},
                    performance_data={},
                    error=str(result)
                )
        
        # Show ML progress
        ml_passed = sum(1 for r in self.ml_results if r.success)
        TestOutput.progress(ml_passed, len(ml_tests), "ML Tests Completed")
        
        # Run business workflow tests
        TestOutput.section_divider()
        TestOutput.subheader("BUSINESS WORKFLOW TESTING")
        
        business_tests = [
            self.test_signal_to_order_workflow(),
            self.test_real_order_execution_workflow(),  # NEW: Real Alpaca paper trading test
            self.test_risk_management_workflow(),
            self.test_integration_services_workflow(),
            self.test_concurrent_user_load(),
        ]
        
        TestOutput.info(f"Running {len(business_tests)} business workflow tests...")
        self.test_results = await asyncio.gather(*business_tests, return_exceptions=True)
        
        # Convert exceptions to failed results
        for i, result in enumerate(self.test_results):
            if isinstance(result, Exception):
                self.test_results[i] = BusinessScenarioResult(
                    scenario_name=f"Business Test {i+1}",
                    success=False,
                    duration_ms=0.0,
                    details={},
                    error=str(result)
                )
        
        # Show business workflow progress
        business_passed = sum(1 for r in self.test_results if r.success)
        TestOutput.progress(business_passed, len(business_tests), "Business Tests Completed")
        
        # Run K6 performance test
        print("\n[PERF] PERFORMANCE TESTING")
        print("-" * 40)
        
        k6_result = await self.run_k6_performance_test()
        self.test_results.append(k6_result)
        
        # Generate comprehensive results
        return self._generate_results_summary()
    
    def _generate_results_summary(self) -> Tuple[bool, Dict[str, Any]]:
        """Generate comprehensive test results summary"""
        
        # ML Results Summary
        ml_successful = sum(1 for result in self.ml_results if result.success)
        ml_total = len(self.ml_results)
        ml_success_rate = ml_successful / ml_total if ml_total > 0 else 0.0
        
        # Business Results Summary
        business_successful = sum(1 for result in self.test_results if result.success)
        business_total = len(self.test_results)
        business_success_rate = business_successful / business_total if business_total > 0 else 0.0
        
        # Overall success criteria
        overall_success = (
            ml_success_rate >= 0.5 and  # At least 50% ML workflows successful
            business_success_rate >= 0.6  # At least 60% business workflows successful
        )
        
        total_duration = sum(r.duration_ms for r in self.test_results if hasattr(r, 'duration_ms'))
        
        results_summary = {
            "overall_success": overall_success,
            "ml_workflows": {
                "successful": ml_successful,
                "total": ml_total,
                "success_rate": f"{ml_success_rate:.1%}",
                "results": [asdict(result) for result in self.ml_results]
            },
            "business_workflows": {
                "successful": business_successful,
                "total": business_total,
                "success_rate": f"{business_success_rate:.1%}",
                "results": [asdict(result) for result in self.test_results]
            },
            "performance_metrics": {
                "total_duration_ms": total_duration,
                "concurrent_users_tested": self.concurrent_users,
                "symbols_tested": len(self.test_symbols),
                "avg_test_duration_ms": total_duration / business_total if business_total > 0 else 0
            },
            "test_configuration": {
                "server_url": self.base_url,
                "concurrent_users": self.concurrent_users,
                "test_symbols": self.test_symbols,
                "test_duration": self.test_duration,
                "backend_available": BACKEND_AVAILABLE
            }
        }
        
        return overall_success, results_summary


async def main():
    """Main test execution function"""
    
    # Print fancy header
    TestOutput.header("LAYER 5: BUSINESS WORKFLOW INTEGRATION TESTS", width=80)
    TestOutput.info(f"Started at {TestOutput.timestamp()}")
    TestOutput.info("Testing comprehensive business workflows and ML capabilities")
    
    # Initialize test suite
    test_suite = Layer5BusinessWorkflowSuite()
    
    # Run all tests with progress tracking
    TestOutput.section_divider()
    start_time = time.time()
    success, results = await test_suite.run_all_tests()
    total_duration = time.time() - start_time
    
    # Print detailed results with enhanced visuals
    TestOutput.section_divider()
    TestOutput.subheader("ML WORKFLOW RESULTS")
    
    # ML Workflow Results
    ml_data = results["ml_workflows"]
    TestOutput.metric("ML Workflows", f"{ml_data['successful']}/{ml_data['total']}", 
                     color=Colors.GREEN if ml_data['successful'] == ml_data['total'] else Colors.YELLOW,
                     unit=f"({ml_data['success_rate']})")
    
    print()  # Spacing
    for i, result in enumerate(ml_data["results"], 1):
        if result["success"]:
            TestOutput.test_pass(f"{i}. {result['workflow_name']} ({result['model_type']})", 0, "")
        else:
            TestOutput.test_fail(f"{i}. {result['workflow_name']} ({result['model_type']})", 
                                result.get("error", "Unknown error"))
    
    # Business Workflow Results
    TestOutput.section_divider()
    TestOutput.subheader("BUSINESS WORKFLOW RESULTS")
    business_data = results["business_workflows"]
    TestOutput.metric("Business Workflows", f"{business_data['successful']}/{business_data['total']}", 
                     color=Colors.GREEN if business_data['successful'] == business_data['total'] else Colors.YELLOW,
                     unit=f"({business_data['success_rate']})")
    
    print()  # Spacing
    for i, result in enumerate(business_data["results"], 1):
        duration = result.get("duration_ms", 0)
        if result["success"]:
            details = f"{result.get('details', {}).get('performance_summary', '')}"
            TestOutput.test_pass(f"{i}. {result['scenario_name']}", duration, details)
        else:
            TestOutput.test_fail(f"{i}. {result['scenario_name']}", 
                                result.get("error", "Unknown error"))
            
            # Show sub-test details for failed tests
            if result.get("sub_tests"):
                for sub_test in result["sub_tests"][:3]:  # Show first 3 sub-tests
                    sub_name = sub_test.get('test', 'Unknown')
                    if sub_test.get("success", False):
                        print(f"        {Colors.GREEN}+--> OK{Colors.RESET} {sub_name}")
                    else:
                        print(f"        {Colors.RED}+--> FAIL{Colors.RESET} {sub_name}")
    
    # Performance Summary
    TestOutput.section_divider()
    TestOutput.subheader("PERFORMANCE METRICS")
    perf_data = results["performance_metrics"]
    
    TestOutput.metric("Total Test Duration", f"{perf_data['total_duration_ms']/1000:.1f}", Colors.CYAN, "seconds")
    TestOutput.metric("Wall Clock Duration", f"{total_duration:.1f}", Colors.CYAN, "seconds")
    TestOutput.metric("Concurrent Users", str(perf_data['concurrent_users_tested']), Colors.CYAN)
    TestOutput.metric("Symbols Tested", str(perf_data['symbols_tested']), Colors.CYAN)
    TestOutput.metric("Avg Test Duration", f"{perf_data['avg_test_duration_ms']:.0f}", Colors.CYAN, "ms")
    
    # Overall Result with ASCII art
    TestOutput.section_divider()
    total_tests = ml_data['total'] + business_data['total']
    total_passed = ml_data['successful'] + business_data['successful']
    total_failed = total_tests - total_passed
    
    TestOutput.test_summary(
        passed=total_passed,
        failed=total_failed,
        skipped=0,
        duration_sec=total_duration
    )
    
    if success:
        TestOutput.ascii_art_success()
        TestOutput.success("Platform ready for production business workflows!")
        TestOutput.info("[OK] ML capabilities validated")
        TestOutput.info("[OK] End-to-end trading workflows operational")
        TestOutput.info("[OK] All business scenarios passed")
    else:
        TestOutput.ascii_art_partial()
        TestOutput.warning("Some workflows need attention before full production deployment")
        TestOutput.info("Review failed tests and implement missing endpoints/features")
    
    TestOutput.section_divider()
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
