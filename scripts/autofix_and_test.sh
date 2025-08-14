#!/bin/bash
# Auto-fix and test script for AlgoTrading Platform
# This script attempts to automatically fix common code issues and run tests

set -e  # Exit on any error

echo "🤖 Starting auto-fix and test cycle..."

# Step 1: Auto-format code
echo "🎨 Step 1: Auto-formatting code..."
black backend/ tests/ || { echo "❌ Black formatting failed"; exit 1; }
ruff format backend/ tests/ || { echo "❌ Ruff formatting failed"; exit 1; }
echo "✅ Formatting completed"

# Step 2: Auto-fix linting issues
echo "🔧 Step 2: Auto-fixing linting issues..."
ruff check backend/ tests/ --fix || { echo "❌ Some linting issues could not be auto-fixed"; }
echo "✅ Linting auto-fix completed"

# Step 3: Run type checking (informational)
echo "📝 Step 3: Running type checking..."
if ! mypy --strict backend/ tests/ --ignore-missing-imports --show-error-codes; then
    echo "⚠️  Type checking found issues - manual review needed"
    echo "🔄 Continuing with tests anyway..."
fi

# Step 4: Run fast test suite 
echo "🏃‍♂️ Step 4: Running fast test suite..."
if pytest tests/unit/ tests/contract/ \
    tests/integration/test_core_trading_flow.py \
    tests/integration/test_authentication.py \
    tests/e2e/test_golden_path.py \
    -n auto --tb=short --durations=10 --strict-markers \
    --disable-warnings --maxfail=3 --timeout=300; then
    echo "✅ Fast tests passed!"
else
    echo "❌ Fast tests failed - check output above"
    exit 1
fi

# Step 5: Run coverage check
echo "📊 Step 5: Running coverage check..."
if pytest tests/unit/ tests/contract/ tests/integration/ \
    --cov=backend --cov-report=term-missing --cov-report=xml \
    --cov-fail-under=80 \
    -n auto --tb=short --disable-warnings --quiet; then
    echo "✅ Coverage check passed!"
else
    echo "❌ Coverage check failed"
    exit 1
fi

echo ""
echo "🎉 Auto-fix and test cycle completed successfully!"
echo "📊 Coverage report generated: coverage.xml"
echo "💡 Tip: Run 'make test-deep' for comprehensive testing"
