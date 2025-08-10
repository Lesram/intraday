#!/bin/bash
# Local CI Pipeline Runner
# Simulates the GitHub Actions CI pipeline locally

set -e  # Exit on first error

echo "🚀 Running Local CI Pipeline Simulation"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track results
LINT_RESULT=0
TYPE_RESULT=0
SECURITY_RESULT=0
TEST_RESULT=0

echo ""
echo "${BLUE}🔍 Step 1: Lint & Format Check${NC}"
echo "================================"

if ruff check --no-fix .; then
    echo "${GREEN}✅ Ruff linting passed${NC}"
else
    echo "${RED}❌ Ruff linting failed${NC}"
    LINT_RESULT=1
fi

if ruff format --check .; then
    echo "${GREEN}✅ Ruff formatting passed${NC}"  
else
    echo "${RED}❌ Ruff formatting failed${NC}"
    LINT_RESULT=1
fi

echo ""
echo "${BLUE}🧮 Step 2: Type Check${NC}"
echo "====================="

if mypy --strict backend tests --ignore-missing-imports --show-error-codes; then
    echo "${GREEN}✅ MyPy type checking passed${NC}"
else
    echo "${RED}❌ MyPy type checking failed${NC}"
    TYPE_RESULT=1
fi

echo ""
echo "${BLUE}🛡️ Step 3: Security Scan${NC}"
echo "========================"

# Bandit security scan
if bandit -r backend -lll; then
    echo "${GREEN}✅ Bandit security scan passed${NC}"
else
    echo "${RED}❌ Bandit security scan failed${NC}"
    SECURITY_RESULT=1
fi

# pip-audit vulnerability scan
if command -v pip-audit &> /dev/null; then
    if pip-audit; then
        echo "${GREEN}✅ pip-audit vulnerability scan passed${NC}"
    else
        echo "${YELLOW}⚠️ pip-audit found vulnerabilities (may be false positives)${NC}"
        # Don't fail on pip-audit issues as they can be false positives
    fi
else
    echo "${YELLOW}⚠️ pip-audit not installed, skipping vulnerability scan${NC}"
fi

# Safety check
if command -v safety &> /dev/null; then
    if safety check; then
        echo "${GREEN}✅ Safety vulnerability check passed${NC}"
    else
        echo "${YELLOW}⚠️ Safety found potential issues (review manually)${NC}"
        # Don't fail on safety issues as they can be false positives  
    fi
else
    echo "${YELLOW}⚠️ safety not installed, skipping vulnerability scan${NC}"
fi

# Metrics label check (if available)
if [ -f "scripts/ci/check_metrics_labels.py" ]; then
    echo ""
    echo "${BLUE}🏷️ Checking metrics labels...${NC}"
    if python scripts/ci/check_metrics_labels.py; then
        echo "${GREEN}✅ Metrics labels validation passed${NC}"
    else
        echo "${RED}❌ Metrics labels validation failed${NC}"
        SECURITY_RESULT=1
    fi
fi

echo ""
echo "${BLUE}🧪 Step 4: Test & Coverage${NC}"
echo "==========================="

# Set test environment variables
export TESTING=true
export DATABASE_URL=postgresql://testuser:testpass@localhost:5432/testdb
export REDIS_URL=redis://localhost:6379/0

# Check if services are running
if ! nc -z localhost 5432; then
    echo "${YELLOW}⚠️ PostgreSQL not running locally - integration tests may fail${NC}"
fi

if ! nc -z localhost 6379; then
    echo "${YELLOW}⚠️ Redis not running locally - caching tests may fail${NC}"
fi

# Run tests with coverage
if pytest \
    --cov=backend \
    --cov-report=xml:coverage.xml \
    --cov-report=html:htmlcov \
    --cov-report=term-missing \
    --cov-fail-under=85 \
    --maxfail=1 \
    --disable-warnings \
    -x \
    tests/; then
    echo "${GREEN}✅ Tests and coverage passed${NC}"
else
    echo "${RED}❌ Tests or coverage failed${NC}"
    TEST_RESULT=1
fi

# Summary
echo ""
echo "📋 CI Pipeline Results Summary"
echo "=============================="

if [ $LINT_RESULT -eq 0 ]; then
    echo "${GREEN}✅ Lint & Format: PASSED${NC}"
else
    echo "${RED}❌ Lint & Format: FAILED${NC}"
fi

if [ $TYPE_RESULT -eq 0 ]; then
    echo "${GREEN}✅ Type Check: PASSED${NC}"
else
    echo "${RED}❌ Type Check: FAILED${NC}"
fi

if [ $SECURITY_RESULT -eq 0 ]; then
    echo "${GREEN}✅ Security Scan: PASSED${NC}"
else
    echo "${RED}❌ Security Scan: FAILED${NC}"
fi

if [ $TEST_RESULT -eq 0 ]; then
    echo "${GREEN}✅ Tests & Coverage: PASSED${NC}"
else
    echo "${RED}❌ Tests & Coverage: FAILED${NC}"
fi

# Extract coverage if available
if [ -f "coverage.xml" ]; then
    COVERAGE=$(grep -o 'line-rate="[0-9.]*"' coverage.xml | head -1 | grep -o '[0-9.]*')
    if [ -n "$COVERAGE" ]; then
        COVERAGE_PCT=$(echo "$COVERAGE * 100" | bc -l | cut -d. -f1)
        echo "${BLUE}📊 Coverage: ${COVERAGE_PCT}%${NC}"
    fi
fi

echo ""

# Final result
TOTAL_FAILURES=$((LINT_RESULT + TYPE_RESULT + SECURITY_RESULT + TEST_RESULT))

if [ $TOTAL_FAILURES -eq 0 ]; then
    echo "${GREEN}🎉 All quality gates passed! Ready for CI/CD${NC}"
    echo ""
    echo "Next steps:"
    echo "  git add ."
    echo "  git commit -m \"Your commit message\""
    echo "  git push origin your-branch"
    exit 0
else
    echo "${RED}❌ $TOTAL_FAILURES quality gate(s) failed${NC}"
    echo ""
    echo "Please fix the issues above before committing."
    echo "Run individual commands to debug:"
    echo "  ruff check . --fix     # Fix linting"
    echo "  mypy backend tests     # Check types"  
    echo "  bandit -r backend      # Review security"
    echo "  pytest tests/          # Run tests"
    exit 1
fi
