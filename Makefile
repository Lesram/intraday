# =====================================
# AlgoTrading Platform Development Makefile
# =====================================

.PHONY: help install test-fast test-deep auto format lint typecheck coverage coverage-quality-gate coverage-full coverage-diff clean

# Configuration
PYTHON := python
TEST_TIMEOUT := 60
COVERAGE_THRESHOLD := 40
DIFF_COVERAGE_THRESHOLD := 85

# Color codes for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
RED := \033[0;31m
NC := \033[0m # No Color

# Default target
help: ## Show available commands
	@echo "🚀 AlgoTrading Platform Development Commands"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

install: ## Install dependencies
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

# =====================================
# Testing Targets
# =====================================

test-fast: ## Run fast working tests with coverage
	@echo "$(BLUE)🏃‍♂️ Running fast test suite with coverage...$(NC)"
	@echo "$(YELLOW)Including: working unit tests, core functionality$(NC)"
	$(PYTHON) -m pytest tests/test_coverage_boost.py \
		tests/services/test_order_service_working.py \
		tests/services/test_order_service_contract.py \
		tests/services/test_positions_and_safety.py \
		tests/test_config_working.py \
		tests/security/test_jwt_simple.py \
		tests/security/test_security_functions.py \
		tests/security/test_jwt_and_cors.py \
		tests/api/test_ws_backpressure.py \
		tests/api/test_ws_manager_unit.py \
		tests/api/test_main_routes_registered.py \
		tests/config/test_config_coverage.py \
		tests/strategies/test_types_coverage.py \
		tests/risk/test_risk_types_coverage.py \
		tests/risk/test_risk_block_reasons.py \
		tests/mlops/test_model_manager_paths.py \
		tests/mlops/test_model_manager_smoke.py \
		tests/utils/test_logger_coverage.py \
		-v --tb=short --durations=10 \
		--cov=backend --cov-report=term-missing --cov-report=xml --cov-report=html \
		--timeout=$(TEST_TIMEOUT) -x --disable-warnings
	@echo "$(GREEN)✅ Fast tests completed$(NC)"

test-deep: ## Run comprehensive test suite with all tests
	@echo "$(BLUE)🔬 Running comprehensive test suite...$(NC)"
	@echo "$(YELLOW)Including: all tests, comprehensive coverage analysis$(NC)"
	$(PYTHON) -m pytest tests/ \
		--tb=short --durations=20 \
		--cov=backend --cov-report=term-missing --cov-report=xml --cov-report=html \
		--timeout=$(TEST_TIMEOUT) \
		-v -m "not slow"
	@echo "$(GREEN)✅ Deep tests completed$(NC)"

# =====================================
# Code Quality Targets  
# =====================================

format: ## Format code with black and ruff
	@echo "$(BLUE)🎨 Formatting code...$(NC)"
	black backend/ tests/
	ruff format backend/ tests/
	@echo "$(GREEN)✅ Code formatted$(NC)"

lint: ## Run linting with ruff
	@echo "$(BLUE)🔍 Running linting...$(NC)"
	ruff check backend/ tests/ --fix
	@echo "$(GREEN)✅ Linting completed$(NC)"

typecheck: ## Run type checking with mypy
	@echo "$(BLUE)📝 Running type checks...$(NC)"
	mypy --strict backend/ tests/ --ignore-missing-imports --show-error-codes
	@echo "$(GREEN)✅ Type checking completed$(NC)"

# =====================================
# =====================================
# Coverage Targets
# =====================================

coverage: ## Run tests with coverage analysis
	@echo "$(BLUE)📊 Running coverage analysis...$(NC)"
	pytest tests/unit/ tests/contract/ tests/integration/ \
		--cov=backend --cov-report=html --cov-report=xml --cov-report=term-missing \
		--cov-fail-under=40 \
		-n auto --tb=short --disable-warnings
	@echo "$(GREEN)✅ Coverage analysis completed$(NC)"
	@echo "$(YELLOW)📄 HTML report: htmlcov/index.html$(NC)"

coverage-quality-gate: ## Check per-package coverage requirements
	@echo "$(BLUE)🎯 Checking per-package coverage requirements...$(NC)"
	$(PYTHON) scripts/check_coverage.py --coverage-file coverage.xml
	@echo "$(GREEN)✅ Coverage quality gate completed$(NC)"

coverage-full: coverage coverage-quality-gate ## Run full coverage analysis with quality gates
	@echo "$(GREEN)✅ Full coverage analysis with quality gates completed$(NC)"

coverage-diff: ## Check diff coverage for PR (85% threshold)
	@echo "$(BLUE)📊 Checking differential coverage...$(NC)"
	diff-cover coverage.xml --compare-branch=origin/main --fail-under=$(DIFF_COVERAGE_THRESHOLD)
	@echo "$(GREEN)✅ Diff coverage check completed$(NC)"

# =====================================
# Automation Targets
# =====================================

auto: ## Auto-fix code issues and run tests
	@echo "$(BLUE)🤖 Running autofix and test cycle...$(NC)"
	@if [ ! -f scripts/autofix_and_test.sh ]; then \
		echo "$(RED)❌ autofix_and_test.sh not found$(NC)"; \
		echo "$(YELLOW)💡 Run 'make create-autofix-script' to create it$(NC)"; \
		exit 1; \
	fi
	@chmod +x scripts/autofix_and_test.sh
	@./scripts/autofix_and_test.sh
	@echo "$(GREEN)✅ Auto-fix and test cycle completed$(NC)"

create-autofix-script: ## Create the autofix_and_test.sh script
	@echo "$(BLUE)📝 Creating autofix_and_test.sh script...$(NC)"
	@mkdir -p scripts
	create-autofix-script: ## Create the autofix_and_test.sh script
	@echo "$(BLUE)📝 Creating autofix_and_test.sh script...$(NC)"
	@mkdir -p scripts
	@echo '#!/bin/bash' > scripts/autofix_and_test.sh
	@echo '# Auto-fix and test script for AlgoTrading Platform' >> scripts/autofix_and_test.sh
	@echo 'set -e' >> scripts/autofix_and_test.sh
	@echo 'echo "🤖 Starting auto-fix and test cycle..."' >> scripts/autofix_and_test.sh
	@echo 'echo "🎨 Step 1: Auto-formatting code..."' >> scripts/autofix_and_test.sh
	@echo 'black backend/ tests/ || { echo "❌ Black formatting failed"; exit 1; }' >> scripts/autofix_and_test.sh
	@echo 'echo "✅ Formatting completed"' >> scripts/autofix_and_test.sh
	@chmod +x scripts/autofix_and_test.sh
	@echo "$(GREEN)✅ Created scripts/autofix_and_test.sh$(NC)"

# =====================================
# Utility Targets
# =====================================

clean: ## Clean up temporary files and caches
	@echo "$(BLUE)🧹 Cleaning up...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf dist/
	rm -rf build/
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

# =====================================
# Development Workflow
# =====================================

dev-setup: install ## Set up development environment
	@echo "$(BLUE)🔧 Setting up development environment...$(NC)"
	pre-commit install || echo "⚠️ pre-commit not available"
	@echo "$(GREEN)✅ Development environment ready$(NC)"
	@echo "$(YELLOW)💡 Try: make auto$(NC)"

quick-check: ## Quick development check (format + lint + fast tests)
	@echo "$(BLUE)⚡ Running quick development check...$(NC)"
	@$(MAKE) format
	@$(MAKE) lint  
	@$(MAKE) test-fast
	@echo "$(GREEN)✅ Quick check completed$(NC)"

full-check: ## Full check before commit (all quality + deep tests)
	@echo "$(BLUE)🔍 Running full pre-commit check...$(NC)"
	@$(MAKE) format
	@$(MAKE) lint
	@$(MAKE) typecheck
	@$(MAKE) coverage
	@$(MAKE) test-deep
	@echo "$(GREEN)✅ Full check completed - ready to commit!$(NC)"

# Show configuration
show-config: ## Show current configuration
	@echo "$(BLUE)⚙️  Current Configuration$(NC)"
	@echo "Python: $(PYTHON)"
	@echo "Test timeout: $(TEST_TIMEOUT)s"
	@echo "Coverage threshold: $(COVERAGE_THRESHOLD)%"
	@echo "Diff coverage threshold: $(DIFF_COVERAGE_THRESHOLD)%"
