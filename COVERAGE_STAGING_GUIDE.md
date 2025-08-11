# Coverage Staging Strategy

## Overview

This project uses a **staged coverage ratcheting system** to gradually improve test coverage while maintaining CI stability. Instead of jumping from ~28% to 85% coverage (which would break CI), we implement incremental gates that ratchet upward as new tests are added.

## Staging Plan

### 🟢 Stage 1: Foundation (30% minimum)
**Status**: ✅ **ACTIVE**
**Target**: ≥30% line coverage
**Timeline**: Immediate (current baseline)

```bash
# Current pytest.ini setting
--cov-fail-under=30
```

**Purpose**: Establish realistic baseline that doesn't break existing CI while preventing coverage regressions.

### 🟡 Stage 2: Core Logic (40% target)
**Status**: 🔄 **PENDING** (after unit test batch lands)
**Target**: ≥40% line coverage
**Timeline**: After landing comprehensive unit tests for:
- Risk mathematics edge cases
- Feature validator error branches
- Security JWT failure modes
- Order service idempotency/retry logic
- WebSocket manager backpressure

**Activation**:
```bash
# Update pytest.ini
sed -i 's/--cov-fail-under=30/--cov-fail-under=40/' pytest.ini

# Update CI workflow
sed -i 's/--cov-fail-under=30/--cov-fail-under=40/' .github/workflows/ci.yml
```

### 🎯 Stage 3: Comprehensive (50% target)
**Status**: ⏳ **FUTURE** (after integration test expansion)
**Target**: ≥50% line coverage
**Timeline**: After adding integration tests for:
- Database layer edge cases
- Broker API failure scenarios
- WebSocket connection management
- Strategy execution paths
- Risk limit enforcement

### 🏆 Long-term: Production Ready (85% target)
**Status**: 📋 **ROADMAP**
**Target**: ≥85% line coverage
**Timeline**: Future milestone after core platform stabilization

## Ratchet Mechanism

### 1. **Never Decrease Policy**
- PRs cannot reduce coverage vs main branch (within 1% tolerance)
- Implemented via `scripts/ci/check_coverage_ratchet.py`
- Automatically fails CI if coverage drops

### 2. **Baseline Comparison**
```bash
# CI automatically compares PR coverage to main branch
python scripts/ci/check_coverage_ratchet.py \
  --current coverage.xml \
  --baseline baseline-coverage.xml \
  --min-coverage 30.0 \
  --tolerance 1.0
```

### 3. **Stage Gate Enforcement**
- Current stage gate is enforced in both pytest.ini and CI workflow
- Cannot merge PRs that fail current coverage threshold
- Manual promotion to next stage after validation

## Usage

### Running Tests with Coverage

```bash
# Current stage (30%)
make coverage-stage1

# Test readiness for next stage
make coverage-stage2  # Will fail until we hit 40%

# Generate detailed report
make coverage-report
```

### Updating Coverage Gates

```bash
# Check current coverage and next steps
make coverage-update

# Manual stage promotion (after tests land)
# Stage 1 → Stage 2
sed -i 's/--cov-fail-under=30/--cov-fail-under=40/' pytest.ini
sed -i 's/--cov-fail-under=30/--cov-fail-under=40/' .github/workflows/ci.yml

# Stage 2 → Stage 3
sed -i 's/--cov-fail-under=40/--cov-fail-under=50/' pytest.ini
sed -i 's/--cov-fail-under=40/--cov-fail-under=50/' .github/workflows/ci.yml
```

## Coverage Report Interpretation

### CI Status Indicators
- 🔴 Below minimum (< 30%): **Blocks PR**
- 🟢 Stage 1 (30-39%): **Current target met**
- 🟡 Stage 2 (40-49%): **Ready for next stage**
- 🎯 Stage 3 (50%+): **Comprehensive coverage**

### Per-Module Targets
Based on our analysis, the high-ROI modules for coverage improvement:

| Module | Coverage Impact | Difficulty | Priority |
|--------|-----------------|------------|----------|
| Risk Mathematics | +8-12% | Low | 🟢 High |
| Feature Validators | +6-10% | Low | 🟢 High |
| Security (JWT/Auth) | +4-6% | Medium | 🟡 High |
| Order Services | +5-8% | Medium | 🟡 High |
| WebSocket Manager | +4-6% | Medium | 🟡 Medium |

## Expected Timeline

```
Current State: ~28% coverage (Stage 1: 30% gate active)
    ↓
After Unit Tests: ~38-45% coverage
    ↓ (promote to Stage 2: 40% gate)
After Integration: ~45-55% coverage
    ↓ (promote to Stage 3: 50% gate)
Future Expansion: 50%+ coverage
```

## Benefits

✅ **CI Stability**: No sudden jumps that break builds
✅ **Progressive Improvement**: Continuous coverage growth
✅ **Regression Prevention**: Ratchet mechanism prevents backsliding
✅ **Developer Confidence**: Realistic gates that developers can meet
✅ **Quality Visibility**: Clear progress tracking and goals

## Configuration Files

- **pytest.ini**: Current coverage gate setting
- **.coveragerc**: Staging configuration and paths
- **.github/workflows/ci.yml**: CI enforcement logic
- **scripts/ci/check_coverage_ratchet.py**: Ratchet comparison tool
- **Makefile**: Convenience targets for each stage

## Monitoring

The CI system automatically:
1. Runs coverage analysis on every PR
2. Compares against main branch baseline
3. Enforces current stage minimum
4. Reports coverage status with stage indicators
5. Blocks PRs that decrease coverage (within tolerance)

This ensures steady progress toward comprehensive coverage without disrupting development velocity.
