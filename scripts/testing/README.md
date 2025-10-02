# Platform Testing Framework

This directory contains dedicated testing scripts with correct import paths and syntax "set in stone" to avoid recurring issues with path errors and method name mistakes.

## 🎯 Testing Philosophy

Instead of ad-hoc terminal commands that are prone to:
- ❌ Wrong import paths (`backend.models.order` vs `backend.risk.types`)
- ❌ Wrong method names (`create_order()` vs `submit_order()`, `fit()` vs `train()`) 
- ❌ Syntax errors (backslash escaping issues)
- ❌ Inconsistent testing approaches

We use **dedicated test scripts** with:
- ✅ Correct import paths hardcoded
- ✅ Proper method names verified
- ✅ Clean syntax without escaping issues
- ✅ Consistent functional testing approach

## 📁 Test Scripts

### `test_environment.py`
Tests core Python packages and system dependencies:
- **Python Package Dependencies**: All required packages (pandas, sklearn, fastapi, etc.)
- **Scikit-learn**: ML training/prediction operations (not just imports)
- **Pandas**: DataFrame manipulation and analysis
- **NumPy**: Mathematical operations and array processing  
- **Docker**: Runtime availability, daemon connectivity
- **K6**: Load testing tool availability and functionality

### `test_core_platform.py`  
Tests core platform components:
- **Database**: Async operations and health checks (SQLite StaticPool compatible)
- **Unified Settings**: Configuration system loading
- **Alpaca Configuration**: API keys and broker settings
- **JWT Configuration**: Authentication token settings
- **Database Configuration**: Connection and pool settings
- **OrderService**: Uses `submit_order()` method (not `create_order()`)
- **RiskManager**: Returns `dict` with `'allowed'` key (not `bool`)
- **PositionsService**: Basic service functionality

### `test_ml_strategy.py`
Tests AI/ML pipeline and strategy components:
- **EnsembleModel**: From `backend.models` (not `backend.ml`), uses `train()` method
- **ModelRegistry**: ML model management 
- **StrategyEngine Import**: Component import capability
- **StrategyEngine Factory Creation**: `create_default()` factory method
- **Strategy Signal Processing**: `process_signals()` method (plural)
- **TradingSignal Creation**: Signal object creation and validation
- **Data Processing**: ML data pipeline components
- **Feature Engineering**: Feature creation and management

### `test_api_integration.py`
Tests API layer and external integrations:
- **FastAPI Application**: Web framework setup and configuration
- **API Routes Import**: Order, signal, and position endpoints
- **Alpaca Broker Integration**: Trading broker connectivity
- **Alpaca Data Client**: Market data integration
- **WebSocket Integration**: Real-time data streaming
- **Authentication System**: JWT token creation and verification
- **Middleware Components**: CORS, rate limiting, security layers

### `test_security_performance.py`
Tests security features and performance characteristics:
- **Environment Security**: Secure configuration and secrets
- **Password Security**: Hashing and verification
- **JWT Token Security**: Token generation, validation, expiry
- **Rate Limiting**: API request throttling
- **Input Validation**: XSS and injection prevention
- **Database Performance**: Connection and query performance
- **ML Model Performance**: Training and prediction speed
- **K6 Performance Setup**: Load testing infrastructure

### `run_all_tests.py`
Comprehensive test runner:
- Executes all 5 test categories in sequence
- Provides real-time output and final summary
- Generates `test_results_summary.txt` report
- Returns appropriate exit codes for CI/CD

## 🚀 Usage

### Run Individual Test Categories
```powershell
# Test environment and dependencies
python scripts\testing\test_environment.py

# Test core platform components  
python scripts\testing\test_core_platform.py

# Test ML pipeline and strategy engine
python scripts\testing\test_ml_strategy.py
```

### Run Complete Test Suite
```powershell
# Run all tests with comprehensive reporting
python scripts\testing\run_all_tests.py
```

## 📊 Output Format

Each script provides:
- **Real-time progress**: Shows each test as it runs
- **Detailed results**: Success/failure with error details
- **Summary statistics**: Pass/fail counts and percentages
- **Clear verdicts**: FUNCTIONAL, NEEDS_IMPROVEMENT, etc.

## 🔧 Maintenance

When platform components change:
1. **Update import paths** in relevant test scripts
2. **Verify method names** are still correct
3. **Test the test scripts** before relying on results
4. **Version control** all changes to maintain reliability

## 🎯 Benefits

- **Consistency**: Same tests run the same way every time
- **Reliability**: No more path/syntax errors disrupting testing
- **Maintainability**: Easy to update when platform changes
- **Automation**: Can be integrated into CI/CD pipelines
- **Documentation**: Tests serve as executable documentation

This framework eliminates the "downspiraling problems" caused by incorrect paths and ensures reliable, repeatable testing.