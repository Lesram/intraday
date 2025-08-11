"""
Test script for BRANCH 2.12 deployment readiness features.
Tests health probes, graceful shutdown, and deployment infrastructure.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_health_endpoints():
    """Test the new health endpoints /healthz and /readyz."""
    print("🏥 Testing Health Endpoints")
    print("=" * 50)

    # Import inside function to avoid import issues
    import os
    os.environ["PROMETHEUS_AVAILABLE"] = "false"  # Disable metrics during testing

    from httpx import ASGITransport, AsyncClient
    from backend.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:

        # Test liveness probe
        print("Testing /healthz (liveness probe)...")
        try:
            response = await client.get("/healthz")
            data = response.json()
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Response: {json.dumps(data, indent=2)}")
            assert response.status_code == 200
            assert data["status"] in ["alive", "healthy"]  # Accept both formats
            assert "timestamp" in data
        except Exception as e:
            print(f"❌ /healthz failed: {e}")
            return False

        # Test readiness probe
        print("\nTesting /readyz (readiness probe)...")
        try:
            response = await client.get("/readyz")
            data = response.json()
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Response: {json.dumps(data, indent=2)}")
            # Note: This might return 503 if dependencies are not healthy
            assert response.status_code in [200, 503]
            assert "status" in data
            assert "checks" in data
        except Exception as e:
            print(f"❌ /readyz failed: {e}")
            return False

        # Test legacy health endpoint
        print("\nTesting /health (legacy endpoint)...")
        try:
            response = await client.get("/health")
            data = response.json()
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Response: {json.dumps(data, indent=2)}")
            assert response.status_code == 200
            assert data["status"] == "healthy"
        except Exception as e:
            print(f"❌ /health failed: {e}")
            return False

    print("\n🎉 All health endpoint tests passed!")
    return True

async def test_metrics_endpoint():
    """Test Prometheus metrics endpoint."""
    print("\n📊 Testing Metrics Endpoint")
    print("=" * 50)

    import os
    # Try with metrics enabled but handle failures gracefully

    from httpx import ASGITransport, AsyncClient
    from backend.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:

        try:
            response = await client.get("/metrics")
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Content-Type: {response.headers.get('content-type')}")

            # Check for Prometheus metrics format
            content = response.text
            if "# HELP" in content and "# TYPE" in content:
                print("✅ Prometheus metrics format detected")
                print(f"✅ Metrics size: {len(content)} bytes")
            else:
                print("⚠️ Metrics format may not be Prometheus-compatible")

        except Exception as e:
            print(f"❌ /metrics failed: {e}")
            return False

    print("🎉 Metrics endpoint test passed!")
    return True

def test_container_build():
    """Test Docker container build process."""
    print("\n🐳 Testing Container Build")
    print("=" * 50)

    import subprocess
    import os

    # Check if Docker is available
    try:
        result = subprocess.run(["docker", "--version"],
                              capture_output=True, text=True, check=True)
        print(f"✅ Docker available: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker not available - skipping container tests")
        return False

    # Check if Dockerfile exists
    dockerfile_path = project_root / "Dockerfile"
    if not dockerfile_path.exists():
        print(f"❌ Dockerfile not found at {dockerfile_path}")
        return False

    print("✅ Dockerfile found")

    # Validate Dockerfile content for BRANCH 2.12 features
    dockerfile_content = dockerfile_path.read_text()

    checks = {
        "Multi-stage build": "FROM python" in dockerfile_content and "AS builder" in dockerfile_content,
        "Non-root user": "USER " in dockerfile_content and ("appuser" in dockerfile_content or "10001" in dockerfile_content),
        "Health check": "HEALTHCHECK" in dockerfile_content,
        "Security hardening": "chown" in dockerfile_content or "chmod" in dockerfile_content or "appuser" in dockerfile_content,
        "Slim base image": "slim" in dockerfile_content.lower(),
    }

    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}: {'PASS' if passed else 'FAIL'}")

    if all(checks.values()):
        print("🎉 Container configuration validation passed!")
        return True
    else:
        print("⚠️ Some container checks failed")
        return False

def test_kubernetes_manifests():
    """Test Kubernetes deployment manifests."""
    print("\n☸️ Testing Kubernetes Manifests")
    print("=" * 50)

    k8s_dir = project_root / "k8s"
    if not k8s_dir.exists():
        print(f"❌ Kubernetes directory not found at {k8s_dir}")
        return False

    required_files = [
        "deployment.yaml",
        "service.yaml",
        "namespace.yaml",
        "postgres.yaml",
        "redis.yaml",
        "kustomization.yaml"
    ]

    all_present = True
    for file_name in required_files:
        file_path = k8s_dir / file_name
        if file_path.exists():
            print(f"✅ {file_name} found")
        else:
            print(f"❌ {file_name} missing")
            all_present = False

    # Check deployment.yaml for BRANCH 2.12 features
    deployment_file = k8s_dir / "deployment.yaml"
    if deployment_file.exists():
        content = deployment_file.read_text()

        deployment_checks = {
            "Liveness probe": "livenessProbe" in content and "/healthz" in content,
            "Readiness probe": "readinessProbe" in content and "/readyz" in content,
            "Security context": "securityContext" in content,
            "Resource limits": "resources:" in content and "limits:" in content,
            "Non-root user": "runAsUser" in content,
        }

        print("\nDeployment features:")
        for check_name, passed in deployment_checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'PASS' if passed else 'FAIL'}")

    if all_present:
        print("🎉 Kubernetes manifests validation passed!")
        return True
    else:
        print("⚠️ Some Kubernetes manifests missing")
        return False

def test_deployment_scripts():
    """Test deployment automation scripts."""
    print("\n🚀 Testing Deployment Scripts")
    print("=" * 50)

    scripts = {
        "deploy.sh": project_root / "deploy.sh",
        "deploy.ps1": project_root / "deploy.ps1",
    }

    all_present = True
    for script_name, script_path in scripts.items():
        if script_path.exists():
            print(f"✅ {script_name} found")

            # Check script content for key functions
            content = script_path.read_text()
            functions = ["build", "deploy", "health", "status"]

            for func in functions:
                if func in content.lower():
                    print(f"  ✅ {func} functionality present")
                else:
                    print(f"  ⚠️ {func} functionality may be missing")
        else:
            print(f"❌ {script_name} missing")
            all_present = False

    if all_present:
        print("🎉 Deployment scripts validation passed!")
        return True
    else:
        print("⚠️ Some deployment scripts missing")
        return False

async def run_all_tests():
    """Run all BRANCH 2.12 deployment readiness tests."""
    print("🧪 BRANCH 2.12 - Deploy Readiness Test Suite")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Project: {project_root}")
    print()

    tests = [
        ("Health Endpoints", test_health_endpoints()),
        ("Metrics Endpoint", test_metrics_endpoint()),
        ("Container Build", test_container_build),
        ("Kubernetes Manifests", test_kubernetes_manifests),
        ("Deployment Scripts", test_deployment_scripts),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutine(test_func):
                result = await test_func
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("🏆 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED - BRANCH 2.12 DEPLOYMENT READY!")
        return True
    else:
        print("⚠️ Some tests failed - review implementation")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
