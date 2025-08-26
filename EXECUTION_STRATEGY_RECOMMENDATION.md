# RECOMMENDED TEST EXECUTION STRATEGY

## SUMMARY OF OPTIONS

Based on the complete inventory of 400+ tests across Phases 1-7B.6, I recommend **Option 1: Complete All-Phase Execution** for the following reasons:

### **Why Run All Together (Recommended)**:

1. **Historical Success**: Your documented 60%+ coverage was achieved through comprehensive execution
2. **Efficiency**: Single execution provides complete coverage report in one run  
3. **Integration Testing**: Reveals cross-phase dependencies and interactions
4. **Matching Documented Methodology**: Replicates the successful approach from your historical reports

### **When to Run Phase-by-Phase**:

1. **Debugging Failures**: If the comprehensive run reveals failures, then isolate by phase
2. **Development**: When working on specific components
3. **Performance Issues**: If memory/timeout constraints require smaller batches

---

## IMMEDIATE EXECUTION COMMAND

Here's the complete command to restore your documented 60%+ coverage:

```bash
# Activate virtual environment first
& C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/Activate.ps1

# Execute all historical phases
python -m pytest \
  tests/core/test_app_lifespan_and_di.py \
  tests/unit/test_risk_manager_current.py \
  tests/unit/test_alpaca_client_core.py \
  tests/unit/test_alpaca_client_comprehensive.py \
  tests/test_api_factory_comprehensive.py \
  tests/test_websocket_comprehensive.py \
  tests/test_websocket_manager_phase7b6.py \
  tests/test_feature_engineering_part1.py \
  tests/test_feature_engineering_part2.py \
  tests/test_model_manager_part1.py \
  tests/test_model_manager_part2_fixed.py \
  tests/test_model_manager_part3.py \
  tests/test_model_manager_part4.py \
  tests/test_ensemble_model_phase7a1.py \
  tests/test_ensemble_model_phase7a1_extended.py \
  tests/test_market_data_phase7b1.py \
  tests/test_market_data_phase7b1_extended.py \
  tests/test_market_data_phase7b1_final.py \
  tests/test_social_sentiment_phase7b2_final.py \
  tests/test_order_service_phase7b3_final.py \
  tests/test_ensemble_model_phase7b4_final.py \
  tests/test_trading_strategies_core.py \
  tests/test_trading_strategies_phase7b5.py \
  --cov=backend \
  --cov-report=html \
  --cov-report=term-missing \
  --maxfail=50 \
  --timeout=300 \
  -v
```

---

## QUICK PHASE-BY-PHASE ALTERNATIVE

If you prefer to run systematically by phase (useful for debugging):

```bash
# Phase 1: Foundation (41 tests) - Expected: 100% pass
pytest tests/core/test_app_lifespan_and_di.py tests/unit/test_risk_manager_current.py --cov=backend --cov-report=term-missing -v

# Phase 2: AlpacaClient (36 tests) - Expected: 89% pass  
pytest tests/unit/test_alpaca_client_core.py tests/unit/test_alpaca_client_comprehensive.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 3: API Factory (37 tests) - Expected: 100% pass
pytest tests/test_api_factory_comprehensive.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 4: WebSocket (35+ tests) - Expected: 100% pass
pytest tests/test_websocket_comprehensive.py tests/test_websocket_manager_phase7b6.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 5: Feature Engineering (54 tests) - Expected: 100% pass
pytest tests/test_feature_engineering_part1.py tests/test_feature_engineering_part2.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 6: ModelManager (67 tests) - Expected: 85% pass
pytest tests/test_model_manager_part1.py tests/test_model_manager_part2_fixed.py tests/test_model_manager_part3.py tests/test_model_manager_part4.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 7A: Ensemble (59 tests) - Expected: 66% pass
pytest tests/test_ensemble_model_phase7a1.py tests/test_ensemble_model_phase7a1_extended.py tests/test_ensemble_model_phase7b4_final.py --cov=backend --cov-append --cov-report=term-missing -v

# Phase 7B: Final Components - Expected: 90%+ pass
pytest tests/test_market_data_phase7b1.py tests/test_market_data_phase7b1_extended.py tests/test_market_data_phase7b1_final.py tests/test_social_sentiment_phase7b2_final.py tests/test_order_service_phase7b3_final.py tests/test_trading_strategies_core.py tests/test_trading_strategies_phase7b5.py --cov=backend --cov-append --cov-report=html --cov-report=term-missing -v
```

**Note**: Using `--cov-append` builds cumulative coverage across phases.

---

## MY RECOMMENDATION

**Execute the complete all-phases command first** - this matches your historical methodology and should restore the documented 60%+ coverage baseline. If any phase shows unexpected failures, we can then drill down with phase-specific execution for debugging.

This approach:
- ✅ Matches your documented successful methodology  
- ✅ Provides complete integration testing
- ✅ Generates comprehensive AI agent review report
- ✅ Efficiently achieves maximum coverage in single run
- ✅ Replicates the systematic approach that achieved 400+ test success

Would you like me to execute the complete all-phases command now?
