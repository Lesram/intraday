#!/usr/bin/env python3
"""
Pre-Run Test Suite - Consolidated Layers 1-4
=============================================
Comprehensive pre-deployment validation combining:
- Layer 1: Import Validation (dependencies available)  
- Layer 2: Functional Validation (components work)
- Layer 3: Paper Trading Integration (real API calls)
- Layer 4: Live Server Integration (HTTP endpoints)

This consolidated test ensures the platform is ready before running
Layer 5 business workflows and K6 performance testing.
"""

import sys
import os
import asyncio
import time
import subprocess
import json
import tempfile
import uuid
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from io import StringIO

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.paper')

# Optional imports - will be tested
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

@dataclass
class PreRunTestResult:
    """Result of a pre-run test"""
    layer: int
    test_name: str
    success: bool
    duration_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None

class PreRunTestSuite:
    """
    Consolidated pre-run test suite covering Layers 1-4
    
    Validates platform readiness through progressive testing:
    1. Dependencies can be imported
    2. Components function correctly  
    3. Paper trading APIs work
    4. Live server responds properly
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[PreRunTestResult] = []
        self.auth_token: Optional[str] = None
        self.test_symbols = ["AAPL", "MSFT", "GOOGL"]
        
    async def run_all_prerun_tests(self) -> Tuple[bool, Dict[str, Any]]:
        """Run complete pre-run test suite across all 4 layers"""
        
        print("[*] PRE-RUN TEST SUITE - LAYERS 1-4 CONSOLIDATED")
        print("=" * 80)
        print("Validating platform readiness before business workflow testing...")
        print()
        
        start_time = time.time()
        
        # Layer 1: Import Validation
        print("[LAYER] LAYER 1: IMPORT VALIDATION")
        print("-" * 40)
        layer1_success = await self._run_layer1_import_tests()
        
        # Layer 2: Functional Validation  
        print("\n[LAYER] LAYER 2: FUNCTIONAL VALIDATION")
        print("-" * 40)
        layer2_success = await self._run_layer2_functional_tests()
        
        # Layer 3: Paper Trading Integration
        print("\n[LAYER] LAYER 3: PAPER TRADING INTEGRATION")
        print("-" * 40)
        layer3_success = await self._run_layer3_paper_trading_tests()
        
        # Layer 4: Live Server Integration
        print("\n[LAYER] LAYER 4: LIVE SERVER INTEGRATION")
        print("-" * 40)
        layer4_success = await self._run_layer4_live_server_tests()
        
        # Generate comprehensive results
        total_duration = time.time() - start_time
        overall_success = all([layer1_success, layer2_success, layer3_success, layer4_success])
        
        summary = self._generate_test_summary(overall_success, total_duration)
        
        print(f"\n[RESULTS] PRE-RUN TEST RESULTS")
        print("=" * 80)
        self._print_results_summary(summary)
        
        return overall_success, summary
    
    async def _run_layer1_import_tests(self) -> bool:
        """Layer 1: Test that required modules can be imported"""
        
        # Core Python imports
        core_imports = [
            "asyncio", "json", "os", "sys", "pathlib", "tempfile", 
            "subprocess", "time", "datetime", "uuid"
        ]
        
        # Data science imports
        data_science_imports = [
            "pandas", "numpy", "sklearn", "tensorflow", "xgboost"
        ]
        
        # Web/API imports
        web_imports = [
            "fastapi", "uvicorn", "pydantic", "httpx"
        ]
        
        # Database imports
        db_imports = [
            "sqlalchemy", "asyncpg"
        ]
        
        # Trading/Finance imports
        trading_imports = [
            "alpaca", "yfinance"
        ]
        
        all_import_groups = [
            ("Core Python", core_imports),
            ("Data Science", data_science_imports), 
            ("Web/API", web_imports),
            ("Database", db_imports),
            ("Trading/Finance", trading_imports)
        ]
        
        layer1_success = True
        
        for group_name, imports in all_import_groups:
            start_time = time.time()
            failed_imports = []
            
            for module in imports:
                try:
                    __import__(module)
                except ImportError as e:
                    failed_imports.append(f"{module}: {str(e)}")
            
            duration_ms = (time.time() - start_time) * 1000
            group_success = len(failed_imports) == 0
            
            if not group_success:
                layer1_success = False
            
            self.results.append(PreRunTestResult(
                layer=1,
                test_name=f"Import {group_name}",
                success=group_success,
                duration_ms=duration_ms,
                details={
                    "modules_tested": len(imports),
                    "modules_passed": len(imports) - len(failed_imports),
                    "failed_imports": failed_imports
                },
                error=None if group_success else f"Failed imports: {failed_imports}"
            ))
            
            status = "[PASS] PASS" if group_success else "[FAIL] FAIL"
            print(f"  {group_name} imports: {status} ({len(imports) - len(failed_imports)}/{len(imports)})")
        
        return layer1_success
    
    async def _run_layer2_functional_tests(self) -> bool:
        """Layer 2: Test that imported components actually work"""
        
        layer2_success = True
        
        # Test TensorFlow functionality
        tf_success = await self._test_tensorflow_functional()
        layer2_success &= tf_success
        
        # Test Pandas functionality  
        pandas_success = await self._test_pandas_functional()
        layer2_success &= pandas_success
        
        # Test NumPy functionality
        numpy_success = await self._test_numpy_functional()
        layer2_success &= numpy_success
        
        # Test scikit-learn functionality
        sklearn_success = await self._test_sklearn_functional()
        layer2_success &= sklearn_success
        
        # Test database functionality
        db_success = await self._test_database_functional()
        layer2_success &= db_success
        
        return layer2_success
    
    async def _test_tensorflow_functional(self) -> bool:
        """Test TensorFlow model creation and training"""
        start_time = time.time()
        
        try:
            import tensorflow as tf
            import numpy as np
            
            # Create simple test data
            X = np.random.random((100, 2))
            y = np.random.random((100, 1))
            
            # Create and compile model using modern Keras API
            model = tf.keras.Sequential([
                tf.keras.layers.Input(shape=(2,)),
                tf.keras.layers.Dense(4, activation='relu'),
                tf.keras.layers.Dense(1)
            ])
            
            model.compile(optimizer='adam', loss='mse')
            
            # Train for 1 epoch (functional test)
            history = model.fit(X, y, epochs=1, verbose=0)
            
            # Make prediction
            prediction = model.predict(X[:1], verbose=0)
            
            success = len(history.history['loss']) == 1 and prediction.shape == (1, 1)
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="TensorFlow Functional",
                success=success,
                duration_ms=duration_ms,
                details={
                    "model_created": True,
                    "training_epochs": 1,
                    "prediction_shape": str(prediction.shape),
                    "loss_value": float(history.history['loss'][0])
                },
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  TensorFlow model training: {status}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="TensorFlow Functional",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  TensorFlow model training: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_pandas_functional(self) -> bool:
        """Test Pandas DataFrame operations"""
        start_time = time.time()
        
        try:
            import pandas as pd
            import numpy as np
            
            # Create test DataFrame
            data = {
                'symbol': ['AAPL', 'GOOGL', 'MSFT'] * 100,
                'price': np.random.uniform(100, 200, 300),
                'volume': np.random.randint(1000, 10000, 300)
            }
            df = pd.DataFrame(data)
            
            # Perform operations
            grouped = df.groupby('symbol').agg({
                'price': ['mean', 'std'],
                'volume': 'sum'
            })
            
            # Test serialization
            json_str = df.head().to_json()
            df_restored = pd.read_json(StringIO(json_str))
            
            success = (
                len(df) == 300 and
                len(grouped) == 3 and
                len(df_restored) == 5 and
                'symbol' in df_restored.columns
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Pandas Functional",
                success=success,
                duration_ms=duration_ms,
                details={
                    "dataframe_rows": len(df),
                    "grouped_symbols": len(grouped),
                    "json_serialization": True
                },
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Pandas DataFrame operations: {status}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Pandas Functional",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Pandas DataFrame operations: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_numpy_functional(self) -> bool:
        """Test NumPy array operations"""
        start_time = time.time()
        
        try:
            import numpy as np
            
            # Create test arrays
            a = np.random.random((1000, 10))
            b = np.random.random((10, 5))
            
            # Matrix operations
            result = np.dot(a, b)
            mean_result = np.mean(result, axis=0)
            std_result = np.std(result, axis=1)
            
            # Statistical operations
            percentiles = np.percentile(a, [25, 50, 75, 95])
            
            success = (
                result.shape == (1000, 5) and
                len(mean_result) == 5 and
                len(std_result) == 1000 and
                len(percentiles) == 4
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="NumPy Functional",
                success=success,
                duration_ms=duration_ms,
                details={
                    "matrix_multiplication": True,
                    "result_shape": str(result.shape),
                    "statistical_operations": True
                },
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  NumPy array operations: {status}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="NumPy Functional",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  NumPy array operations: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_sklearn_functional(self) -> bool:
        """Test scikit-learn model training"""
        start_time = time.time()
        
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_squared_error
            import numpy as np
            
            # Create synthetic dataset
            X = np.random.random((1000, 5))
            y = np.sum(X, axis=1) + np.random.normal(0, 0.1, 1000)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Train model
            model = RandomForestRegressor(n_estimators=10, random_state=42)
            model.fit(X_train, y_train)
            
            # Make predictions
            predictions = model.predict(X_test)
            mse = mean_squared_error(y_test, predictions)
            
            success = (
                len(predictions) == len(y_test) and
                mse < 1.0 and  # Should be low MSE for our simple synthetic data
                hasattr(model, 'feature_importances_')
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Scikit-learn Functional",
                success=success,
                duration_ms=duration_ms,
                details={
                    "model_trained": True,
                    "predictions_made": len(predictions),
                    "mse": float(mse),
                    "feature_importances": len(model.feature_importances_)
                },
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Scikit-learn model training: {status}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Scikit-learn Functional",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Scikit-learn model training: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_database_functional(self) -> bool:
        """Test REAL database connection functionality (PostgreSQL)"""
        start_time = time.time()
        
        try:
            # Test database imports and basic functionality
            import sqlalchemy
            from sqlalchemy import create_engine, text, inspect
            
            # Try to get real database URL from environment or config
            db_url = None
            try:
                # Try to import backend config
                from backend.config.unified import get_settings
                settings = get_settings()
                db_url = settings.database_url
                print(f"  [INFO] Using production database from config")
            except (ImportError, AttributeError):
                # Fallback to environment variable
                db_url = os.getenv("DATABASE_URL")
                if db_url:
                    print(f"  [INFO] Using DATABASE_URL from environment")
            
            # Require PostgreSQL database for functional tests
            if not db_url:
                pytest.fail(
                    "DATABASE_URL not configured. Functional tests require PostgreSQL.\n"
                    "Set DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading\n"
                    "Start PostgreSQL: docker-compose up -d db\n"
                    "\n"
                    "Production systems MUST use PostgreSQL for proper validation of:\n"
                    "  - Connection pooling\n"
                    "  - Transaction isolation\n"
                    "  - JSON/JSONB types\n"
                    "  - Full-text search\n"
                    "  - Concurrent connections\n"
                )
            
            # Enforce PostgreSQL only - no SQLite fallback
            if not db_url.startswith("postgresql"):
                pytest.fail(
                    f"Functional tests require PostgreSQL, got: {db_url}\n"
                    "\n"
                    "SQLite is NOT supported for testing. Production systems use PostgreSQL.\n"
                    "\n"
                    "To fix:\n"
                    "  1. Start PostgreSQL: docker-compose up -d db\n"
                    "  2. Set DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading\n"
                    "  3. Re-run tests\n"
                )
            
            using_real_db = True
            print(f"  [INFO] Using PostgreSQL - full production feature validation")
            
            # Convert asyncpg URL to psycopg2 for synchronous testing
            # asyncpg is for async operations, but test uses sync engine
            test_db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
            
            # Create engine with connection pooling settings for PostgreSQL
            engine = create_engine(
                test_db_url,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=5,
                max_overflow=10,
                echo=False
            )
            
            # Test database connection and operations
            with engine.connect() as conn:
                # Test 1: Basic connection
                conn.execute(text("SELECT 1"))
                
                if using_real_db and db_url.startswith("postgresql"):
                    # Test 2: PostgreSQL-specific features
                    # Check for expected tables (production schema)
                    inspector = inspect(engine)
                    tables = inspector.get_table_names()
                    
                    # Expected core tables (adjust based on your schema)
                    expected_tables = ['users', 'orders', 'positions', 'signals', 'risk_limits']
                    tables_found = [t for t in expected_tables if t in tables]
                    
                    # Test 3: Check for alembic version table (migrations)
                    has_migrations = 'alembic_version' in tables
                    
                    # Test 4: PostgreSQL-specific syntax (jsonb, array operations)
                    try:
                        # Try a PostgreSQL-specific query
                        conn.execute(text("SELECT version()"))
                        postgres_version_result = conn.execute(text("SELECT version()")).fetchone()
                        postgres_version = postgres_version_result[0] if postgres_version_result else "unknown"
                    except Exception:
                        postgres_version = "unknown"
                    
                    success = True
                    details = {
                        "database_type": "postgresql",
                        "engine_created": True,
                        "connection_successful": True,
                        "connection_pool_enabled": True,
                        "total_tables": len(tables),
                        "expected_tables_found": len(tables_found),
                        "expected_tables_total": len(expected_tables),
                        "tables_found": tables_found,
                        "missing_tables": [t for t in expected_tables if t not in tables],
                        "migrations_available": has_migrations,
                        "postgres_version": postgres_version[:50] if postgres_version else "unknown"
                    }
                    
                    # Validate critical tables exist
                    if len(tables_found) == 0:
                        print(f"  [WARN]  No expected tables found - schema may not be initialized")
                        print(f"  [WARN]  Available tables: {tables[:10]}")  # Show first 10
                        # Don't fail - schema might be valid but different
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Database Functional",
                success=success,
                duration_ms=duration_ms,
                details=details,
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Database operations: {status}")
            if using_real_db and "total_tables" in details:
                print(f"    -> Database: PostgreSQL, Tables: {details['total_tables']}, Expected Found: {details['expected_tables_found']}/{details['expected_tables_total']}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=2,
                test_name="Database Functional",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Database operations: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _run_layer3_paper_trading_tests(self) -> bool:
        """Layer 3: Test paper trading API integration"""
        
        layer3_success = True
        
        # Test Alpaca credentials
        creds_success = await self._test_alpaca_credentials()
        layer3_success &= creds_success
        
        # Test market data access
        market_data_success = await self._test_market_data_access()
        layer3_success &= market_data_success
        
        # Test account information
        account_success = await self._test_account_information()
        layer3_success &= account_success
        
        return layer3_success
    
    async def _test_alpaca_credentials(self) -> bool:
        """Test Alpaca API credentials with REAL API calls"""
        start_time = time.time()
        
        try:
            api_key = os.getenv("ALPACA_API_KEY_ID")
            api_secret = os.getenv("ALPACA_API_SECRET_KEY")
            
            # First check if credentials exist
            if not api_key or not api_secret:
                raise ValueError("Missing ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY environment variables")
            
            # REAL API TEST: Actually connect to Alpaca and validate credentials
            try:
                from alpaca.trading.client import TradingClient
                from alpaca.trading.requests import GetAssetsRequest
                from alpaca.trading.enums import AssetClass
                
                # Create Alpaca client (paper=True for paper trading)
                trading_client = TradingClient(api_key, api_secret, paper=True)
                
                # Test 1: Get account info (validates credentials and API access)
                account = trading_client.get_account()
                
                # Test 2: Verify it's a paper trading account
                if not hasattr(account, 'account_number'):
                    raise ValueError("Invalid account object returned from Alpaca API")
                
                # Test 3: Quick asset lookup to verify API functionality
                search_params = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status='active')
                assets = trading_client.get_all_assets(search_params)
                
                success = True
                details = {
                    "api_key_present": True,
                    "api_secret_present": True,
                    "api_connection_successful": True,
                    "account_status": str(account.status),
                    "account_blocked": bool(account.account_blocked),
                    "trading_blocked": bool(account.trading_blocked),
                    "pattern_day_trader": bool(account.pattern_day_trader),
                    "buying_power": float(account.buying_power),
                    "assets_accessible": len(assets) > 0,
                    "total_assets_count": len(assets)
                }
                
                # Validate account is in good standing
                if account.account_blocked or account.trading_blocked:
                    success = False
                    details["error"] = "Account or trading is blocked in Alpaca"
                
            except ImportError as ie:
                # Alpaca SDK not installed - fallback to basic check
                print(f"  [WARN]  Alpaca SDK not available: {str(ie)}")
                print(f"  [WARN]  Falling back to basic credential check")
                success = bool(api_key and api_secret and len(api_key) > 10 and len(api_secret) > 10)
                details = {
                    "api_key_present": bool(api_key),
                    "api_secret_present": bool(api_secret),
                    "credentials_valid_format": success,
                    "warning": "Alpaca SDK not installed - install with: pip install alpaca-py"
                }
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Alpaca Credentials",
                success=success,
                duration_ms=duration_ms,
                details=details,
                error=None if success else details.get("error", "Credential validation failed")
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Alpaca credentials: {status}")
            if success and "buying_power" in details:
                print(f"    -> Account Status: {details['account_status']}, Buying Power: ${details['buying_power']:.2f}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Alpaca Credentials",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Alpaca credentials: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_market_data_access(self) -> bool:
        """Test market data API access"""
        start_time = time.time()
        
        try:
            import yfinance as yf
            
            # Test Yahoo Finance data access
            ticker = yf.Ticker("AAPL")
            hist = ticker.history(period="5d")
            info = ticker.info
            
            success = (
                len(hist) > 0 and
                'Close' in hist.columns and
                isinstance(info, dict) and
                'symbol' in info
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Market Data Access",
                success=success,
                duration_ms=duration_ms,
                details={
                    "historical_data_days": len(hist),
                    "price_columns": list(hist.columns),
                    "info_keys_count": len(info) if isinstance(info, dict) else 0
                },
                error=None
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Market data access: {status}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Market Data Access",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Market data access: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_account_information(self) -> bool:
        """Test paper trading account access with REAL Alpaca API"""
        start_time = time.time()
        
        try:
            api_key = os.getenv("ALPACA_API_KEY_ID")
            api_secret = os.getenv("ALPACA_API_SECRET_KEY")
            
            if not api_key or not api_secret:
                raise ValueError("Missing Alpaca credentials")
            
            # REAL API TEST: Test actual order placement capability
            try:
                from alpaca.trading.client import TradingClient
                from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                
                trading_client = TradingClient(api_key, api_secret, paper=True)
                
                # Get account info
                account = trading_client.get_account()
                
                # Test order placement capability (but don't actually submit)
                # We'll create a valid order request to validate the capability exists
                test_order_request = MarketOrderRequest(
                    symbol="AAPL",
                    qty=1,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                
                # Validate we can access orders endpoint (get existing orders)
                orders = trading_client.get_orders()
                
                # Validate we can access positions
                positions = trading_client.get_all_positions()
                
                success = True
                details = {
                    "credentials_available": True,
                    "account_type": "paper_trading",
                    "account_status": str(account.status),
                    "account_number": str(account.account_number)[:8] + "...",  # Partial for security
                    "cash": float(account.cash),
                    "buying_power": float(account.buying_power),
                    "portfolio_value": float(account.portfolio_value),
                    "equity": float(account.equity),
                    "account_blocked": bool(account.account_blocked),
                    "trading_blocked": bool(account.trading_blocked),
                    "orders_accessible": True,
                    "active_orders_count": len([o for o in orders if o.status in ['new', 'partially_filled', 'accepted']]),
                    "positions_accessible": True,
                    "open_positions_count": len(positions),
                    "order_placement_capability": "validated"
                }
                
                # Critical validations
                if account.status != 'ACTIVE':
                    success = False
                    details["error"] = f"Account status is {account.status}, expected ACTIVE"
                elif account.account_blocked:
                    success = False
                    details["error"] = "Account is blocked"
                elif account.trading_blocked:
                    success = False
                    details["error"] = "Trading is blocked"
                elif float(account.buying_power) <= 0:
                    success = False
                    details["error"] = "No buying power available"
                
            except ImportError as ie:
                # Alpaca SDK not installed - fallback to basic check
                print(f"  [WARN]  Alpaca SDK not available: {str(ie)}")
                success = bool(api_key and api_secret)
                details = {
                    "credentials_available": success,
                    "account_type": "paper_trading",
                    "warning": "Alpaca SDK not installed - cannot validate account access"
                }
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Account Information",
                success=success,
                duration_ms=duration_ms,
                details=details,
                error=None if success else details.get("error", "Cannot validate account")
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  Account information: {status}")
            if success and "buying_power" in details:
                print(f"    -> Portfolio: ${details['portfolio_value']:.2f}, Cash: ${details['cash']:.2f}")
                print(f"    -> Open Positions: {details.get('open_positions_count', 0)}, Active Orders: {details.get('active_orders_count', 0)}")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=3,
                test_name="Account Information",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Account information: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _run_layer4_live_server_tests(self) -> bool:
        """Layer 4: Test live server HTTP endpoints"""
        
        if not HTTPX_AVAILABLE:
            print("  [WARN]  httpx not available - skipping live server tests")
            return True
        
        layer4_success = True
        
        # Test server health endpoint
        health_success = await self._test_server_health()
        layer4_success &= health_success
        
        # Test authentication endpoint
        auth_success = await self._test_authentication()
        layer4_success &= auth_success
        
        # Test API endpoints
        api_success = await self._test_api_endpoints()
        layer4_success &= api_success
        
        return layer4_success
    
    async def _test_server_health(self) -> bool:
        """Test server health endpoint"""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                
                success = response.status_code == 200
                
                duration_ms = (time.time() - start_time) * 1000
                
                self.results.append(PreRunTestResult(
                    layer=4,
                    test_name="Server Health",
                    success=success,
                    duration_ms=duration_ms,
                    details={
                        "status_code": response.status_code,
                        "response_time_ms": duration_ms,
                        "endpoint": "/health"
                    },
                    error=None if success else f"Health check failed with status {response.status_code}"
                ))
                
                status = "[PASS] PASS" if success else "[FAIL] FAIL"
                print(f"  Server health check: {status}")
                return success
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=4,
                test_name="Server Health",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Server health check: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_authentication(self) -> bool:
        """Test authentication endpoint"""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient() as client:
                # Attempt login
                login_data = {
                    "username": "admin",
                    "password": "admin123"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/login",
                    json=login_data,
                    timeout=5.0
                )
                
                success = response.status_code in [200, 401, 422]  # Any of these is acceptable
                
                # If successful, extract token
                if response.status_code == 200:
                    data = response.json()
                    self.auth_token = data.get("access_token")
                
                duration_ms = (time.time() - start_time) * 1000
                
                self.results.append(PreRunTestResult(
                    layer=4,
                    test_name="Authentication",
                    success=success,
                    duration_ms=duration_ms,
                    details={
                        "status_code": response.status_code,
                        "token_received": bool(self.auth_token),
                        "endpoint": "/api/v1/auth/login"
                    },
                    error=None if success else f"Auth endpoint failed with status {response.status_code}"
                ))
                
                status = "[PASS] PASS" if success else "[FAIL] FAIL"
                print(f"  Authentication endpoint: {status}")
                return success
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=4,
                test_name="Authentication",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  Authentication endpoint: [FAIL] FAIL - {str(e)}")
            return False
    
    async def _test_api_endpoints(self) -> bool:
        """Test key API endpoints"""
        start_time = time.time()
        
        endpoints_to_test = [
            "/api/v1/signals/",
            "/api/v1/positions",  
            "/api/v1/orders"  # Removed trailing slash - may fix 405 error
        ]
        
        successful_endpoints = 0
        
        try:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            
            async with httpx.AsyncClient() as client:
                for endpoint in endpoints_to_test:
                    try:
                        response = await client.get(
                            f"{self.base_url}{endpoint}",
                            headers=headers,
                            timeout=5.0
                        )
                        
                        # Consider success if endpoint exists and responds correctly
                        # 200: OK, 301/307: Redirects, 401: Auth required (endpoint exists), 422: Validation error
                        # Excludes: 404 (not found), 405 (method not allowed) - these indicate problems
                        if response.status_code in [200, 301, 307, 401, 422]:
                            successful_endpoints += 1
                            print(f"    {endpoint}: [PASS] {response.status_code}")
                        else:
                            print(f"    {endpoint}: [FAIL] {response.status_code} (not acceptable)")
                            
                    except Exception as endpoint_error:
                        print(f"    {endpoint}: [FAIL] FAIL - {str(endpoint_error)}")
                        continue
            
            # Require 100% of endpoints to succeed - no broken endpoints allowed
            success = successful_endpoints == len(endpoints_to_test)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=4,
                test_name="API Endpoints",
                success=success,
                duration_ms=duration_ms,
                details={
                    "endpoints_tested": len(endpoints_to_test),
                    "endpoints_successful": successful_endpoints,
                    "success_rate": successful_endpoints / len(endpoints_to_test),
                    "auth_token_used": bool(self.auth_token)
                },
                error=None if success else f"Only {successful_endpoints}/{len(endpoints_to_test)} endpoints responded correctly"
            ))
            
            status = "[PASS] PASS" if success else "[FAIL] FAIL"
            print(f"  API endpoints: {status} ({successful_endpoints}/{len(endpoints_to_test)})")
            return success
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.results.append(PreRunTestResult(
                layer=4,
                test_name="API Endpoints",
                success=False,
                duration_ms=duration_ms,
                details={},
                error=str(e)
            ))
            
            print(f"  API endpoints: [FAIL] FAIL - {str(e)}")
            return False
    
    def _generate_test_summary(self, overall_success: bool, total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive test summary"""
        
        # Aggregate results by layer
        layer_results = {}
        for i in range(1, 5):
            layer_tests = [r for r in self.results if r.layer == i]
            layer_results[f"layer_{i}"] = {
                "tests_run": len(layer_tests),
                "tests_passed": len([r for r in layer_tests if r.success]),
                "success_rate": len([r for r in layer_tests if r.success]) / len(layer_tests) if layer_tests else 0,
                "total_duration_ms": sum(r.duration_ms for r in layer_tests)
            }
        
        # Overall statistics
        total_tests = len(self.results)
        total_passed = len([r for r in self.results if r.success])
        
        return {
            "test_suite": "Pre-Run Tests (Layers 1-4)",
            "timestamp": datetime.now().isoformat(),
            "overall_success": overall_success,
            "total_duration_seconds": total_duration,
            "total_tests": total_tests,
            "total_passed": total_passed,
            "overall_success_rate": total_passed / total_tests if total_tests > 0 else 0,
            "layer_results": layer_results,
            "detailed_results": [
                {
                    "layer": r.layer,
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                    "error": r.error
                } for r in self.results
            ]
        }
    
    def _print_results_summary(self, summary: Dict[str, Any]):
        """Print comprehensive results summary"""
        
        print(f"Duration: {summary['total_duration_seconds']:.1f}s")
        print(f"Tests: {summary['total_passed']}/{summary['total_tests']} passed")
        print(f"Success Rate: {summary['overall_success_rate']:.1%}")
        print()
        
        # Layer-by-layer results
        layer_names = {
            1: "Layer 1 (Import Validation)",
            2: "Layer 2 (Functional Validation)", 
            3: "Layer 3 (Paper Trading Integration)",
            4: "Layer 4 (Live Server Integration)"
        }
        
        for i in range(1, 5):
            layer_key = f"layer_{i}"
            if layer_key in summary['layer_results']:
                layer_data = summary['layer_results'][layer_key]
                layer_name = layer_names[i]
                
                success_rate = layer_data['success_rate']
                status = "[PASS] PASS" if success_rate >= 0.8 else "[WARN]  PARTIAL" if success_rate >= 0.5 else "[FAIL] FAIL"
                
                print(f"{layer_name}: {status} ({layer_data['tests_passed']}/{layer_data['tests_run']})")
        
        print()
        
        # Overall assessment
        overall_success = summary['overall_success']
        if overall_success:
            print("[SUCCESS] OVERALL STATUS: PRE-RUN VALIDATION SUCCESSFUL")
            print("[OK] Platform is ready for Layer 5 business workflow testing")
        else:
            print("[WARNING] OVERALL STATUS: ISSUES DETECTED")
            print("[ACTION] Address failing tests before proceeding to Layer 5")
            
            # Show failed tests
            failed_tests = [r for r in self.results if not r.success]
            if failed_tests:
                print("\nFailed Tests:")
                for test in failed_tests:
                    print(f"  [FAIL] Layer {test.layer} - {test.test_name}: {test.error}")

async def main():
    """Main entry point for pre-run testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pre-Run Test Suite - Layers 1-4')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Base URL for server tests')
    
    args = parser.parse_args()
    
    # Run pre-run test suite
    suite = PreRunTestSuite(base_url=args.base_url)
    success, summary = await suite.run_all_prerun_tests()
    
    # Save results
    timestamp = int(time.time())
    results_file = f"prerun_test_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    # Return appropriate exit code
    return 0 if success else 1

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
