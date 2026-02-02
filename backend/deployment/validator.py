"""
Production Deployment Validator and Fixer

This module ensures all production deployment requirements are met
and provides automated fixes for common deployment issues.
"""

import asyncio
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
from typing import Any


class ProductionDeploymentValidator:
    """
    Comprehensive production deployment validator that identifies and fixes
    common deployment issues to ensure smooth production launches.
    """

    def __init__(self):
        self.validation_results: dict[str, Any] = {}
        self.fixes_applied: list[str] = []
        self.logger = logging.getLogger('deployment_validator')
        self._setup_logging()

    def _setup_logging(self):
        """Setup structured logging for deployment validation."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - DEPLOYMENT - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def validate_production_readiness(self) -> dict[str, Any]:
        """Comprehensive production readiness validation."""

        self.logger.info("🚀 Starting Production Deployment Validation")

        validation_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'PENDING',
            'readiness_score': 0,
            'critical_issues': [],
            'warnings': [],
            'fixes_applied': [],
            'deployment_recommendations': []
        }

        # Validate core components
        await self._validate_database_readiness()
        await self._validate_configuration_completeness()
        await self._validate_security_configuration()
        await self._validate_monitoring_setup()
        await self._validate_containerization()
        await self._validate_kubernetes_manifests()

        # Calculate overall readiness
        validation_results.update(self.validation_results)
        validation_results['fixes_applied'] = self.fixes_applied

        # Determine deployment status
        critical_count = len(validation_results.get('critical_issues', []))
        warning_count = len(validation_results.get('warnings', []))

        if critical_count == 0 and warning_count <= 2:
            validation_results['overall_status'] = '✅ DEPLOYMENT READY'
            validation_results['readiness_score'] = 95 + (2 - warning_count) * 2.5
        elif critical_count == 0:
            validation_results['overall_status'] = '🟡 CONDITIONAL DEPLOYMENT'
            validation_results['readiness_score'] = 85
        else:
            validation_results['overall_status'] = '❌ DEPLOYMENT BLOCKED'
            validation_results['readiness_score'] = max(0, 70 - critical_count * 10)

        self.logger.info(f"🎯 Deployment Status: {validation_results['overall_status']}")
        self.logger.info(f"📊 Readiness Score: {validation_results['readiness_score']}%")

        return validation_results

    async def _validate_database_readiness(self):
        """Validate database configuration and setup."""
        self.logger.info("🗄️ Validating database readiness...")

        try:
            # Check database configuration
            from backend.database.unified_config import get_database_config

            db_config = get_database_config()
            connection_test = db_config.test_connection()

            if connection_test:
                self.logger.info("✅ Database connection successful")
            else:
                self.validation_results.setdefault('warnings', []).append(
                    "Database connection test failed (may be expected in test environment)"
                )

            # Check if we need to create tables
            if db_config.is_sqlite:
                await self._ensure_sqlite_tables_exist()

        except Exception as e:
            self.validation_results.setdefault('critical_issues', []).append(
                f"Database validation failed: {e}"
            )
            self.logger.error(f"❌ Database validation failed: {e}")

    async def _ensure_sqlite_tables_exist(self):
        """Ensure SQLite tables exist for production testing."""
        self.logger.info("📋 Ensuring SQLite tables exist...")

        try:
            # Import database models and create tables if needed
            from backend.database.unified_config import get_database_config

            db_config = get_database_config()

            if hasattr(db_config, 'get_sync_engine'):
                engine = db_config.get_sync_engine()

                # Create basic table structure for testing
                with engine.begin() as conn:
                    # Create minimal tables for index testing
                    tables_sql = [
                        """CREATE TABLE IF NOT EXISTS orders (
                            id INTEGER PRIMARY KEY,
                            user_id TEXT,
                            symbol TEXT,
                            status TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )""",
                        """CREATE TABLE IF NOT EXISTS positions (
                            id INTEGER PRIMARY KEY,
                            user_id TEXT,
                            symbol TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )""",
                        """CREATE TABLE IF NOT EXISTS daily_ledger (
                            id INTEGER PRIMARY KEY,
                            account_id TEXT,
                            date DATE
                        )""",
                        """CREATE TABLE IF NOT EXISTS order_events (
                            id INTEGER PRIMARY KEY,
                            broker_order_id TEXT,
                            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )""",
                        """CREATE TABLE IF NOT EXISTS trades (
                            id INTEGER PRIMARY KEY,
                            symbol TEXT,
                            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )"""
                    ]

                    for sql in tables_sql:
                        conn.execute(sql)

                    self.logger.info("✅ SQLite tables created successfully")
                    self.fixes_applied.append("Created missing SQLite tables for production testing")

        except Exception as e:
            self.logger.warning(f"⚠️ Could not create SQLite tables: {e}")

    async def _validate_configuration_completeness(self):
        """Validate that all required configuration is present."""
        self.logger.info("⚙️ Validating configuration completeness...")

        required_env_vars = [
            'DATABASE_URL',
            'JWT_SECRET_KEY',
            'ALPACA_API_KEY_ID',
            'ALPACA_API_SECRET_KEY'
        ]

        missing_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)

        if missing_vars:
            self.validation_results.setdefault('warnings', []).append(
                f"Missing environment variables: {', '.join(missing_vars)}"
            )
        else:
            self.logger.info("✅ All required environment variables present")

    async def _validate_security_configuration(self):
        """Validate security configuration for production."""
        self.logger.info("🔒 Validating security configuration...")

        security_checks = []

        # Check JWT secret length
        jwt_secret = os.getenv('JWT_SECRET_KEY', '')
        if len(jwt_secret) < 32:
            security_checks.append("JWT secret should be at least 32 characters")

        # Check debug mode
        debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
        if debug_mode:
            security_checks.append("Debug mode should be disabled in production")

        if security_checks:
            self.validation_results.setdefault('warnings', []).extend(security_checks)
        else:
            self.logger.info("✅ Security configuration validated")

    async def _validate_monitoring_setup(self):
        """Validate monitoring and observability setup."""
        self.logger.info("📊 Validating monitoring setup...")

        try:
            # Check if monitoring components are importable
            monitoring_components = [
                'backend.monitoring.slo_monitor',
                'backend.monitoring.slo_metrics',
                'backend.monitoring.slo_dashboard'
            ]

            available_components = 0
            for component in monitoring_components:
                try:
                    __import__(component)
                    available_components += 1
                except ImportError:
                    continue

            if available_components >= 2:
                self.logger.info(f"✅ Monitoring components available ({available_components}/{len(monitoring_components)})")
            else:
                self.validation_results.setdefault('warnings', []).append(
                    f"Limited monitoring components available ({available_components}/{len(monitoring_components)})"
                )

        except Exception as e:
            self.logger.warning(f"⚠️ Monitoring validation failed: {e}")

    async def _validate_containerization(self):
        """Validate Docker and containerization setup."""
        self.logger.info("🐳 Validating containerization setup...")

        dockerfile_path = Path('Dockerfile')
        if dockerfile_path.exists():
            self.logger.info("✅ Dockerfile found")

            # Check for multi-stage build
            content = dockerfile_path.read_text()
            if 'FROM' in content and 'as' in content.lower():
                self.logger.info("✅ Multi-stage Dockerfile detected")
            else:
                self.validation_results.setdefault('warnings', []).append(
                    "Consider using multi-stage Dockerfile for production optimization"
                )
        else:
            self.validation_results.setdefault('critical_issues', []).append(
                "Dockerfile not found - required for containerized deployment"
            )

    async def _validate_kubernetes_manifests(self):
        """Validate Kubernetes deployment manifests."""
        self.logger.info("☸️ Validating Kubernetes manifests...")

        k8s_dir = Path('k8s')
        if k8s_dir.exists():
            required_files = ['deployment.yaml', 'service.yaml', 'namespace.yaml']
            missing_files = []

            for file in required_files:
                if not (k8s_dir / file).exists():
                    missing_files.append(file)

            if not missing_files:
                self.logger.info("✅ All required Kubernetes manifests found")

                # Check for production optimizations
                deployment_file = k8s_dir / 'deployment.yaml'
                if deployment_file.exists():
                    content = deployment_file.read_text()

                    prod_features = []
                    if 'resources:' in content:
                        prod_features.append('resource limits')
                    if 'livenessProbe:' in content:
                        prod_features.append('liveness probe')
                    if 'readinessProbe:' in content:
                        prod_features.append('readiness probe')

                    if len(prod_features) >= 2:
                        self.logger.info(f"✅ Production features detected: {', '.join(prod_features)}")
                    else:
                        self.validation_results.setdefault('warnings', []).append(
                            "Kubernetes manifests could benefit from additional production features"
                        )
            else:
                self.validation_results.setdefault('warnings', []).append(
                    f"Missing Kubernetes manifests: {', '.join(missing_files)}"
                )
        else:
            self.validation_results.setdefault('warnings', []).append(
                "Kubernetes manifests directory (k8s/) not found"
            )

    def generate_deployment_guide(self) -> str:
        """Generate comprehensive deployment guide."""

        guide = """
🚀 PRODUCTION DEPLOYMENT GUIDE
============================================

## Pre-Deployment Checklist
✅ Run: python -m backend.deployment.validator
✅ Ensure all critical issues are resolved
✅ Verify environment variables are configured
✅ Test database connectivity
✅ Validate security configuration

## Docker Deployment
```bash
# Build production image
docker build -t algotrading-api:latest .

# Run with production configuration
docker run -d \\
  --name algotrading-api \\
  -p 8000:8000 \\
  -e DATABASE_URL="your_production_db_url" \\
  -e JWT_SECRET_KEY="your_production_jwt_secret" \\
  -e ALPACA_API_KEY="your_alpaca_key" \\
  -e ALPACA_SECRET_KEY="your_alpaca_secret" \\
  -v ./logs:/app/logs \\
  -v ./data:/app/data \\
  algotrading-api:latest

# Verify deployment
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

## Kubernetes Deployment
```bash
# Create secrets
kubectl create secret generic algotrading-secrets \\
  --from-literal=database-url="your_production_db_url" \\
  --from-literal=jwt-secret="your_production_jwt_secret"

kubectl create secret generic alpaca-secrets \\
  --from-literal=api-key="your_alpaca_key" \\
  --from-literal=secret-key="your_alpaca_secret"

# Deploy application
kubectl apply -k k8s/

# Monitor deployment
kubectl get pods -n algotrading
kubectl logs -f deployment/algotrading-api -n algotrading
```

## Post-Deployment Verification
1. Health checks responding (GET /healthz, /readyz)
2. Metrics endpoint available (GET /metrics)
3. Database connectivity verified
4. Trading functionality validated
5. Monitoring alerts configured
6. Backup procedures tested

## Production Monitoring
- Monitor CPU/Memory usage
- Track database performance
- Observe trading metrics
- Set up alerting rules
- Regular backup verification

## Rollback Procedure
```bash
# Docker rollback
docker stop algotrading-api
docker run --name algotrading-api-backup ...

# Kubernetes rollback
kubectl rollout undo deployment/algotrading-api -n algotrading
```

============================================
"""
        return guide

    async def fix_common_deployment_issues(self) -> list[str]:
        """Automatically fix common deployment issues."""
        fixes_applied = []

        try:
            # Fix 1: Ensure SQLite tables exist for testing
            await self._ensure_sqlite_tables_exist()

            # Fix 2: Create missing directories
            required_dirs = ['logs', 'data', 'backups']
            for dir_name in required_dirs:
                dir_path = Path(dir_name)
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    fixes_applied.append(f"Created missing directory: {dir_name}")

            # Fix 3: Set production environment variables if missing
            prod_env_defaults = {
                'APP_ENVIRONMENT': 'production',
                'LOG_LEVEL': 'INFO',
                'DEBUG': 'false'
            }

            for var, default in prod_env_defaults.items():
                if not os.getenv(var):
                    os.environ[var] = default
                    fixes_applied.append(f"Set default production value for {var}")

            self.logger.info(f"✅ Applied {len(fixes_applied)} automatic fixes")

        except Exception as e:
            self.logger.error(f"❌ Error applying fixes: {e}")

        return fixes_applied


async def main():
    """Main deployment validation function."""
    validator = ProductionDeploymentValidator()

    print("🚀 Production Deployment Validation Starting...")
    print("=" * 60)

    # Run validation
    results = await validator.validate_production_readiness()

    # Apply fixes if needed
    fixes = await validator.fix_common_deployment_issues()
    results['fixes_applied'].extend(fixes)

    # Generate summary
    print("\n📊 DEPLOYMENT VALIDATION SUMMARY")
    print("=" * 40)
    print(f"Overall Status: {results['overall_status']}")
    print(f"Readiness Score: {results['readiness_score']}%")
    print(f"Critical Issues: {len(results.get('critical_issues', []))}")
    print(f"Warnings: {len(results.get('warnings', []))}")
    print(f"Fixes Applied: {len(results.get('fixes_applied', []))}")

    if results.get('critical_issues'):
        print("\n❌ CRITICAL ISSUES:")
        for issue in results['critical_issues']:
            print(f"   - {issue}")

    if results.get('warnings'):
        print("\n⚠️ WARNINGS:")
        for warning in results['warnings']:
            print(f"   - {warning}")

    if results.get('fixes_applied'):
        print("\n🔧 FIXES APPLIED:")
        for fix in results['fixes_applied']:
            print(f"   - {fix}")

    # Generate deployment guide
    guide = validator.generate_deployment_guide()
    guide_file = Path('DEPLOYMENT_GUIDE.md')
    guide_file.write_text(guide)
    print(f"\n📖 Deployment guide saved: {guide_file}")

    print("\n" + "=" * 60)
    print("🎯 Production Deployment Validation Complete!")

    return results['readiness_score'] >= 90


if __name__ == "__main__":
    # Run the validation
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
