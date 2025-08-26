# PHASE MAPPING FOR READY EXECUTION COMMAND

## TESTS READY FOR EXECUTION - PHASE BREAKDOWN

### **PHASE 1: Foundation & Risk Management** (41 historical tests)
```bash
tests/core/test_app_lifespan_and_di.py        # 20 tests - App lifecycle, DI, components
tests/unit/test_risk_manager_current.py       # 21 tests - Risk calculations, limits, decisions
```
**Coverage**: Core infrastructure, dependency injection, risk management foundation

---

### **PHASE 2: AlpacaClient Integration** (36 historical tests)
```bash
tests/unit/test_alpaca_client_core.py          # 19 tests - Basic client functionality
tests/unit/test_alpaca_client_comprehensive.py # 17 tests - Advanced client operations
```
**Coverage**: External API integration, trading operations, data retrieval

---

### **PHASE 3: API Factory Testing** (37 historical tests)
```bash
tests/test_api_factory_comprehensive.py       # 37 tests - FastAPI bootstrap, middleware
```
**Coverage**: Application factory, FastAPI integration, health endpoints, middleware

---

### **PHASE 4: WebSocket Manager Testing** (35 historical tests)
```bash
tests/test_websocket_comprehensive.py         # 35 tests - Real-time communication
```
**Coverage**: WebSocket connections, broadcasting, backpressure, heartbeat

---

### **PHASE 5: Feature Engineering Testing** (54 historical tests)
```bash
tests/test_feature_engineering_part1.py       # 24 tests - Core features, indicators
tests/test_feature_engineering_part2.py       # 30 tests - Validation, scaling, utilities
```
**Coverage**: ML feature pipeline, technical indicators, data validation

---

### **PHASE 6: ModelManager Testing** (67 historical tests)
```bash
tests/test_model_manager_part1.py             # 15 tests - Registry operations
tests/test_model_manager_part2_fixed.py       # 19 tests - Lifecycle management
tests/test_model_manager_part3.py             # 15 tests - Drift detection
tests/test_model_manager_part4.py             # 18 tests - Persistence & integration
```
**Coverage**: MLOps infrastructure, model lifecycle, drift detection, persistence

---

## **MISSING FROM CURRENT EXECUTION (PHASE 7A/7B FILES)**

Based on historical reports, these Phase 7A/7B files exist but need verification:

### **PHASE 7A: Ensemble Model Testing** (59 historical tests)
```bash
# NOT YET VERIFIED - May exist:
tests/test_ensemble_model_phase7a1.py         # 32 tests - Ensemble system
tests/test_ensemble_model_phase7a1_extended.py # 27 tests - Advanced ensemble
```

### **PHASE 7B: Advanced Components** (100+ historical tests)  
```bash
# NOT YET VERIFIED - May exist:
tests/test_market_data_phase7b1.py            # 22 tests - Market data processing
tests/test_market_data_phase7b1_extended.py   # 21 tests - Extended validation
tests/test_market_data_phase7b1_final.py      # 13 tests - Final scenarios
tests/test_social_sentiment_phase7b2_final.py # Social sentiment analysis
tests/test_order_service_phase7b3_final.py    # Order processing service
tests/test_ensemble_model_phase7b4_final.py   # Final ensemble testing
tests/test_trading_strategies_core.py         # Core strategy logic
tests/test_trading_strategies_phase7b5.py     # Advanced strategies
tests/test_websocket_manager_phase7b6.py      # Extended WebSocket tests
```

---

## **CURRENT EXECUTION SCOPE**

### **Ready to Execute: Phases 1-6** (270 tests)
- ✅ All files verified and exist
- ✅ Framework validated and ready  
- ✅ Expected ~85-95% success rate based on historical data
- ✅ Should achieve ~45-50% coverage (Phases 1-6 baseline)

### **Missing: Phase 7A/7B** (~130 additional tests)
- ⚠️ Files need verification
- ⚠️ Would complete the full 60%+ coverage target
- ⚠️ Represents the advanced ML/trading components

---

## **RECOMMENDATION**

1. **Execute Phases 1-6 now** (ready and verified)
2. **Then locate and add Phase 7A/7B files** for complete coverage
3. **This matches the systematic approach** from historical documentation

**Current command covers Phases 1-6 comprehensively - the foundation through ModelManager testing.**
