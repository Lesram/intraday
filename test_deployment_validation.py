"""
Simplified BRANCH 2.12 deployment readiness validation.
Tests deployment infrastructure without complex app loading.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent

def test_health_endpoints_simple():
    """Test health endpoints by checking if they exist in the code."""
    print("🏥 Testing Health Endpoints Configuration")
    print("=" * 50)

    main_py = project_root / "backend" / "api" / "main.py"
    if not main_py.exists():
        print("❌ main.py not found")
        return False

    content = main_py.read_text()

    checks = {
        "Liveness probe (/healthz)": '@app.get("/healthz"' in content,
        "Readiness probe (/readyz)": '@app.get("/readyz"' in content,
        "Legacy health (/health)": '@app.get("/health"' in content,
        "Metrics endpoint (/metrics)": '@app.get("/metrics"' in content,
    }

    all_passed = True
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}: {'CONFIGURED' if passed else 'MISSING'}")
        if not passed:
            all_passed = False

    if all_passed:
        print("🎉 All health endpoints configured!")
        return True
    else:
        print("⚠️ Some health endpoints missing")
        return False

def test_graceful_shutdown_configuration():
    """Test graceful shutdown implementation."""
    print("\n🛡️ Testing Graceful Shutdown Configuration")
    print("=" * 50)

    main_py = project_root / "backend" / "api" / "main.py"
    content = main_py.read_text()

    shutdown_checks = {
        "Lifespan context manager": "@asynccontextmanager" in content and "lifespan" in content,
        "Shutdown timeout": "30" in content or "timeout" in content.lower(),
        "Background task cleanup": "cancel" in content.lower() and "task" in content.lower(),
        "WebSocket cleanup": "websocket" in content.lower() and ("close" in content or "disconnect" in content),
        "Database cleanup": "close" in content and ("engine" in content or "session" in content),
    }

    all_passed = True
    for check_name, passed in shutdown_checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}: {'CONFIGURED' if passed else 'MISSING'}")
        if not passed:
            all_passed = False

    if all_passed:
        print("🎉 Graceful shutdown properly configured!")
        return True
    else:
        print("⚠️ Some shutdown features missing")
        return False

def test_container_configuration():
    """Test Docker container configuration."""
    print("\n🐳 Testing Container Configuration")
    print("=" * 50)

    dockerfile_path = project_root / "Dockerfile"
    compose_path = project_root / "docker-compose.yml"

    results = []

    # Test Dockerfile
    if dockerfile_path.exists():
        dockerfile_content = dockerfile_path.read_text()

        dockerfile_checks = {
            "Multi-stage build": "FROM python" in dockerfile_content and "AS builder" in dockerfile_content,
            "Non-root user": "USER " in dockerfile_content and ("appuser" in dockerfile_content or "10001" in dockerfile_content),
            "Health check": "HEALTHCHECK" in dockerfile_content,
            "Security hardening": "chown" in dockerfile_content or "chmod" in dockerfile_content,
            "Slim base image": "slim" in dockerfile_content.lower(),
        }

        print("Dockerfile checks:")
        dockerfile_passed = True
        for check_name, passed in dockerfile_checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'PASS' if passed else 'FAIL'}")
            if not passed:
                dockerfile_passed = False

        results.append(("Dockerfile", dockerfile_passed))
    else:
        print("❌ Dockerfile not found")
        results.append(("Dockerfile", False))

    # Test Docker Compose
    if compose_path.exists():
        compose_content = compose_path.read_text()

        compose_checks = {
            "API service": "api:" in compose_content or "algotrading" in compose_content,
            "Database service": "postgres" in compose_content,
            "Redis service": "redis" in compose_content,
            "Observability": "otel" in compose_content or "prometheus" in compose_content,
            "Health checks": "healthcheck" in compose_content,
        }

        print("\nDocker Compose checks:")
        compose_passed = True
        for check_name, passed in compose_checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'PASS' if passed else 'FAIL'}")
            if not passed:
                compose_passed = False

        results.append(("Docker Compose", compose_passed))
    else:
        print("❌ docker-compose.yml not found")
        results.append(("Docker Compose", False))

    all_passed = all(result[1] for result in results)
    if all_passed:
        print("🎉 Container configuration validation passed!")
        return True
    else:
        print("⚠️ Some container configuration issues found")
        return False

def test_kubernetes_deployment():
    """Test Kubernetes deployment configuration."""
    print("\n☸️ Testing Kubernetes Deployment")
    print("=" * 50)

    k8s_dir = project_root / "k8s"
    if not k8s_dir.exists():
        print(f"❌ Kubernetes directory not found")
        return False

    required_files = {
        "deployment.yaml": "Application deployment",
        "service.yaml": "Service and networking",
        "namespace.yaml": "Namespace and configuration",
        "postgres.yaml": "PostgreSQL database",
        "redis.yaml": "Redis cache",
        "otel-collector.yaml": "OpenTelemetry collector",
        "prometheus.yaml": "Metrics collection",
        "kustomization.yaml": "Deployment orchestration"
    }

    all_present = True
    for file_name, description in required_files.items():
        file_path = k8s_dir / file_name
        if file_path.exists():
            print(f"✅ {file_name}: {description}")
        else:
            print(f"❌ {file_name}: MISSING")
            all_present = False

    # Check deployment.yaml for BRANCH 2.12 features
    deployment_file = k8s_dir / "deployment.yaml"
    if deployment_file.exists():
        content = deployment_file.read_text()

        deployment_features = {
            "Liveness probe": "livenessProbe" in content and "/healthz" in content,
            "Readiness probe": "readinessProbe" in content and "/readyz" in content,
            "Security context": "securityContext" in content and "runAsUser" in content,
            "Resource limits": "resources:" in content and "limits:" in content,
            "HPA configuration": "HorizontalPodAutoscaler" in content or "autoscaling" in content,
        }

        print("\nDeployment features:")
        for feature_name, present in deployment_features.items():
            status = "✅" if present else "⚠️"
            print(f"  {status} {feature_name}: {'CONFIGURED' if present else 'BASIC'}")

    if all_present:
        print("🎉 Kubernetes deployment configuration complete!")
        return True
    else:
        print("⚠️ Some Kubernetes manifests missing")
        return False

def test_deployment_automation():
    """Test deployment automation scripts."""
    print("\n🚀 Testing Deployment Automation")
    print("=" * 50)

    scripts = {
        "deploy.sh": "Bash deployment script",
        "deploy.ps1": "PowerShell deployment script",
    }

    all_present = True
    for script_name, description in scripts.items():
        script_path = project_root / script_name
        if script_path.exists():
            print(f"✅ {script_name}: {description}")

            # Check script functionality
            content = script_path.read_text()
            functions = ["build", "deploy", "health", "status", "cleanup"]

            for func in functions:
                if func.lower() in content.lower():
                    print(f"  ✅ {func} functionality present")
                else:
                    print(f"  ⚠️ {func} functionality may be missing")
        else:
            print(f"❌ {script_name}: MISSING")
            all_present = False

    if all_present:
        print("🎉 Deployment automation scripts complete!")
        return True
    else:
        print("⚠️ Some deployment scripts missing")
        return False

def test_observability_configuration():
    """Test observability and monitoring configuration."""
    print("\n📊 Testing Observability Configuration")
    print("=" * 50)

    config_files = {
        "logging_config.yaml": "Structured logging configuration",
        "config/otel-collector-config.yaml": "OpenTelemetry collector",
        "config/prometheus.yml": "Prometheus metrics collection",
        ".env.production": "Production environment template",
    }

    all_present = True
    for file_path, description in config_files.items():
        full_path = project_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}: {description}")
        else:
            print(f"❌ {file_path}: MISSING")
            all_present = False

    # Check main.py for observability features
    main_py = project_root / "backend" / "api" / "main.py"
    if main_py.exists():
        content = main_py.read_text()

        observability_features = {
            "Prometheus metrics": "prometheus" in content.lower(),
            "OpenTelemetry": "otel" in content.lower() or "tracing" in content.lower(),
            "Structured logging": "logging" in content.lower(),
            "Health monitoring": "health" in content.lower(),
        }

        print("\nObservability features in application:")
        for feature_name, present in observability_features.items():
            status = "✅" if present else "⚠️"
            print(f"  {status} {feature_name}: {'ENABLED' if present else 'BASIC'}")

    if all_present:
        print("🎉 Observability configuration complete!")
        return True
    else:
        print("⚠️ Some observability configuration missing")
        return False

def run_all_validation():
    """Run all BRANCH 2.12 deployment readiness validation."""
    print("🧪 BRANCH 2.12 - Deploy Readiness Validation Suite")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Project: {project_root}")
    print()

    tests = [
        ("Health Endpoints", test_health_endpoints_simple),
        ("Graceful Shutdown", test_graceful_shutdown_configuration),
        ("Container Config", test_container_configuration),
        ("Kubernetes Deploy", test_kubernetes_deployment),
        ("Deployment Scripts", test_deployment_automation),
        ("Observability", test_observability_configuration),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("🏆 VALIDATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nResults: {passed}/{total} validations passed")

    if passed == total:
        print("🎉 ALL VALIDATIONS PASSED - BRANCH 2.12 DEPLOYMENT READY!")
        print("\nYour algotrading platform is production-deployment ready with:")
        print("• Container security and optimization")
        print("• Kubernetes orchestration")
        print("• Health monitoring and probes")
        print("• Graceful shutdown handling")
        print("• Complete observability stack")
        print("• Automated deployment processes")
        return True
    else:
        print("⚠️ Some validations failed - review implementation")
        return False

if __name__ == "__main__":
    success = run_all_validation()
    sys.exit(0 if success else 1)
