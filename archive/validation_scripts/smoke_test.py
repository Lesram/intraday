#!/usr/bin/env python3
"""Quick smoke test for Phase 4 fixes"""

print("🚀 Phase 4 Quick Smoke Test")
print("=" * 40)

# Test 1: SignalResponse
try:
    from backend.api.schemas.signals import SignalResponse
    signal = SignalResponse(action='buy', confidence=0.75, timestamp='2025-09-28T00:00:00Z')
    print(f"✅ SignalResponse: confidence={signal.confidence}, signal_strength={signal.signal_strength}")
except Exception as e:
    print(f"❌ SignalResponse: {e}")

# Test 2: PositionLimits 
try:
    from backend.risk.position_limits import PositionLimits
    limits = PositionLimits(circuit_breaker_pct=0.05)
    print(f"✅ PositionLimits: circuit_breaker_pct={limits.circuit_breaker_pct}")
except Exception as e:
    print(f"❌ PositionLimits: {e}")

# Test 3: BasicStrategy
try:
    from backend.strategies.basic import BasicStrategy
    strategy = BasicStrategy()
    decision = strategy.decide(closes=[100, 101, 102, 99, 98])
    print(f"✅ BasicStrategy: action={decision.get('action')}, confidence={decision.get('confidence')}")
except Exception as e:
    print(f"❌ BasicStrategy: {e}")

print("=" * 40)