# Makefile for Algorithmic Trading Platform
# Comprehensive test execution with performance and chaos testing

.PHONY: help test test-unit test-integration test-perf test-chaos test-all
.PHONY: lint format type-check security-check
.PHONY: dev-setup clean docker-build docker-run

# Default target
help:
	@echo "Algorithmic Trading Platform - Test Harness"
	@echo ""
	@echo "Available targets:"
	@echo "  test           - Run all unit and integration tests"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests"
	@echo "  test-perf      - Run performance tests (requires infrastructure)"
	@echo "  test-chaos     - Run chaos engineering tests (fault injection)"
	@echo "  test-all       - Run ALL tests including perf and chaos"
	@echo ""
	@echo "Quality targets:"
	@echo "  lint           - Run code linting (ruff)"
	@echo "  format         - Format code (ruff format)"
	@echo "  type-check     - Run type checking (mypy)"
	@echo "  security-check - Run security scanning (bandit)"
	@echo ""
	@echo "Development:"
	@echo "  dev-setup      - Install development dependencies"
	@echo "  clean          - Clean build artifacts and cache"

# Test targets
test:
	@echo "🧪 Running unit and integration tests..."
	pytest -v --tb=short tests/unit/ tests/integration/ \
		--cov=backend --cov-report=term-missing --cov-report=xml \
		--maxfail=5

test-unit:
	@echo "🔬 Running unit tests..."
	pytest -v -m "not integration and not perf and not chaos" tests/unit/ \
		--cov=backend --cov-report=term-missing \
		--maxfail=3

test-integration:
	@echo "🔗 Running integration tests..."
	pytest -v -m integration tests/integration/ \
		--tb=short --maxfail=2

test-perf:
	@echo "⚡ Running performance tests..."
	@echo "⚠️  Performance tests require infrastructure setup"
	pytest -v -m perf tests/perf/ \
		--tb=short --maxfail=1 \
		--durations=10

test-chaos:
	@echo "💥 Running chaos engineering tests..."
	@echo "⚠️  Chaos tests intentionally inject faults"
	pytest -v -m chaos tests/chaos/ \
		--tb=short --maxfail=1 \
		--durations=10

test-all:
	@echo "🚀 Running ALL tests (unit + integration + perf + chaos)..."
	pytest -v tests/ \
		--cov=backend --cov-report=term-missing --cov-report=xml \
		--tb=short --maxfail=5 \
		--durations=20

# Quality targets
lint:
	@echo "🔍 Running code linting..."
	ruff check . --no-fix
	ruff format --check .

format:
	@echo "🎨 Formatting code..."
	ruff format .
	ruff check . --fix

type-check:
	@echo "🔍 Running type checking..."
	mypy backend/ tests/ --strict

security-check:
	@echo "🔒 Running security checks..."
	bandit -r backend/ -lll
	pip-audit

# Development targets
dev-setup:
	@echo "📦 Setting up development environment..."
	pip install -e .
	pip install -r requirements-dev.txt
	pre-commit install

clean:
	@echo "🧹 Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info

# Docker targets (for containerized testing)
docker-build:
	@echo "🐳 Building Docker image..."
	docker build -t algotrading-platform:latest .

docker-run:
	@echo "🐳 Running Docker container..."
	docker run --rm -p 8000:8000 \
		-e DATABASE_URL=postgresql://user:pass@host.docker.internal:5432/testdb \
		algotrading-platform:latest

# CI/CD helper targets
ci-test:
	@echo "🤖 Running CI test suite..."
	pytest -v tests/unit/ tests/integration/ \
		--cov=backend --cov-report=xml --cov-fail-under=85 \
		--tb=short --maxfail=1 --disable-warnings

ci-quality:
	@echo "🤖 Running CI quality checks..."
	ruff check . --no-fix
	ruff format --check .
	mypy backend/ tests/ --strict
	bandit -r backend/ -lll
	pip-audit

# Environment variables for different test modes
export TESTING=true
export LOG_LEVEL=WARNING
export DATABASE_URL?=postgresql://test:test@localhost:5432/test_db
export BROKER_API_BASE_URL?=https://paper-api.alpaca.markets
export BROKER_API_KEY_ID?=test_key
export BROKER_API_SECRET_KEY?=test_secret

# Performance test environment
test-perf-env:
	export TESTING=true
	export PERFORMANCE_TESTING=true
	export LOG_LEVEL=ERROR
	export DATABASE_URL=postgresql://perf:perf@localhost:5432/perf_db

# Chaos test environment  
test-chaos-env:
	export TESTING=true
	export CHAOS_TESTING=true
	export LOG_LEVEL=ERROR
	export BROKER_FAULT_INJECTION=true
