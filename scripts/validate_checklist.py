#!/usr/bin/env python3
"""
Phase 4 Staging Checklist Automation Script

Automates validation of key checklist items for the Go/No-Go gate.
Provides structured output for manual verification of remaining items.
"""

import asyncio
import json
import sys
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StagingChecklistValidator:
    """Validates Phase 4 staging checklist items."""
    
    def __init__(self, base_url="http://localhost:8000", api_token=None):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token or self._get_fresh_token()  # Generate fresh JWT token
        self.results = {}
        # Use session for connection reuse to avoid 2-second connection establishment delays
        self.session = requests.Session()
        # Set reasonable timeout and connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=1,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
    def _get_fresh_token(self):
        """Get a fresh JWT token for testing."""
        try:
            from scripts.get_token import get_jwt_token
            token = get_jwt_token(self.base_url, "admin", "admin123")
            if token:
                logger.info("✅ Generated fresh JWT token for testing")
                return token
            else:
                logger.warning("❌ Failed to generate JWT token, using fallback")
                return "6Av--QEcw6s7O0U7i4nxbNqwSUtL3PfNzC07BIOIzFI"  # Fallback
        except Exception as e:
            logger.warning(f"❌ Error generating JWT token: {e}, using fallback")
            return "6Av--QEcw6s7O0U7i4nxbNqwSUtL3PfNzC07BIOIzFI"  # Fallback
        
    def run_all_checks(self):
        """Run all automated checklist validations."""
        logger.info("Starting Phase 4 Staging Checklist Validation...")
        
        # Authentication & Authorization checks
        self.check_auth_endpoints()
        
        # Route Registry checks
        self.check_route_registry()
        
        # API Health checks
        self.check_api_health()
        
        # Generate report
        self.generate_report()
        
        # Clean up session
        self.session.close()
        
        return self.results

    def check_auth_endpoints(self):
        """Validate authentication requirements."""
        logger.info("🔐 Testing Authentication & Authorization...")
        
        auth_results = {
            'protected_401_without_token': {},
            'protected_200_with_token': {},
            'overall_status': 'PASS'
        }
        
        # Test endpoints that should return 401 without token
        protected_endpoints = [
            '/api/v1/signals',
            '/api/v1/signals/act',
            '/api/v1/orders/test-id',
            '/api/v1/positions'
        ]
        
        for endpoint in protected_endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
                expected_401 = response.status_code == 401
                auth_results['protected_401_without_token'][endpoint] = {
                    'status_code': response.status_code,
                    'expected_401': expected_401,
                    'pass': expected_401
                }
                if not expected_401:
                    auth_results['overall_status'] = 'FAIL'
                    
            except requests.RequestException as e:
                auth_results['protected_401_without_token'][endpoint] = {
                    'error': str(e),
                    'pass': False
                }
                auth_results['overall_status'] = 'FAIL'
        
        # Test endpoints that should return 2xx with valid token
        headers = {'Authorization': f'Bearer {self.api_token}'}
        
        for endpoint in ['/api/v1/signals?symbol=AAPL', '/api/v1/positions']:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", headers=headers, timeout=10)
                is_success = 200 <= response.status_code < 300
                auth_results['protected_200_with_token'][endpoint] = {
                    'status_code': response.status_code,
                    'success': is_success,
                    'pass': is_success
                }
                if not is_success:
                    auth_results['overall_status'] = 'FAIL'
                    
            except requests.RequestException as e:
                auth_results['protected_200_with_token'][endpoint] = {
                    'error': str(e),
                    'pass': False
                }
                auth_results['overall_status'] = 'FAIL'
        
        self.results['authentication'] = auth_results
        logger.info(f"🔐 Authentication check: {auth_results['overall_status']}")

    def check_route_registry(self):
        """Validate route registry and API documentation."""
        logger.info("🛣️ Testing Route Registry & API Health...")
        
        registry_results = {
            'health_check': {},
            'openapi_spec': {},
            'docs_accessible': {},
            'overall_status': 'PASS'
        }
        
        # Health check
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            health_pass = response.status_code == 200
            registry_results['health_check'] = {
                'status_code': response.status_code,
                'response_time_ms': response.elapsed.total_seconds() * 1000,
                'pass': health_pass
            }
            if not health_pass:
                registry_results['overall_status'] = 'FAIL'
                
        except requests.RequestException as e:
            registry_results['health_check'] = {
                'error': str(e),
                'pass': False
            }
            registry_results['overall_status'] = 'FAIL'
        
        # OpenAPI spec
        try:
            response = self.session.get(f"{self.base_url}/openapi.json", timeout=10)
            openapi_pass = response.status_code == 200
            if openapi_pass:
                try:
                    openapi_data = response.json()
                    has_version = 'info' in openapi_data and 'version' in openapi_data['info']
                    has_paths = 'paths' in openapi_data and len(openapi_data['paths']) > 0
                    openapi_pass = has_version and has_paths
                except json.JSONDecodeError:
                    openapi_pass = False
            
            registry_results['openapi_spec'] = {
                'status_code': response.status_code,
                'valid_json': openapi_pass,
                'pass': openapi_pass
            }
            if not openapi_pass:
                registry_results['overall_status'] = 'FAIL'
                
        except requests.RequestException as e:
            registry_results['openapi_spec'] = {
                'error': str(e),
                'pass': False
            }
            registry_results['overall_status'] = 'FAIL'
        
        # Documentation accessibility
        try:
            response = self.session.get(f"{self.base_url}/docs", timeout=10)
            docs_pass = response.status_code == 200
            registry_results['docs_accessible'] = {
                'status_code': response.status_code,
                'pass': docs_pass
            }
            if not docs_pass:
                registry_results['overall_status'] = 'FAIL'
                
        except requests.RequestException as e:
            registry_results['docs_accessible'] = {
                'error': str(e),
                'pass': False
            }
            registry_results['overall_status'] = 'FAIL'
        
        self.results['route_registry'] = registry_results
        logger.info(f"🛣️ Route registry check: {registry_results['overall_status']}")

    def check_api_health(self):
        """Check basic API responsiveness."""
        logger.info("⚡ Testing API Responsiveness...")
        
        health_results = {
            'response_times': {},
            'error_rates': {},
            'overall_status': 'PASS'
        }
        
        # Test a few key endpoints for basic responsiveness
        test_endpoints = [
            ('GET', '/health', None),
            ('GET', '/api/v1/signals?symbol=AAPL', {'Authorization': f'Bearer {self.api_token}'}),
        ]
        
        for method, endpoint, headers in test_endpoints:
            times = []
            errors = 0
            
            # Make 5 requests to get average response time
            for _ in range(5):
                try:
                    start_time = time.time()
                    if method == 'GET':
                        response = self.session.get(f"{self.base_url}{endpoint}", headers=headers, timeout=10)
                    
                    response_time = (time.time() - start_time) * 1000  # Convert to ms
                    times.append(response_time)
                    
                    if response.status_code >= 500:
                        errors += 1
                        
                except requests.RequestException:
                    errors += 1
            
            if times:
                avg_time = sum(times) / len(times)
                p95_time = sorted(times)[int(0.95 * len(times))] if len(times) > 1 else times[0]
            else:
                avg_time = p95_time = float('inf')
            
            error_rate = errors / 5 * 100
            
            health_results['response_times'][endpoint] = {
                'avg_ms': round(avg_time, 1),
                'p95_ms': round(p95_time, 1),
                'samples': len(times)
            }
            
            health_results['error_rates'][endpoint] = {
                'error_rate_percent': error_rate,
                'errors': errors,
                'total_requests': 5
            }
            
            # Simple health check - if too slow or too many errors, fail
            if p95_time > 2000 or error_rate > 20:  # Lenient thresholds for basic check
                health_results['overall_status'] = 'FAIL'
        
        self.results['api_health'] = health_results
        logger.info(f"⚡ API health check: {health_results['overall_status']}")

    def generate_report(self):
        """Generate a comprehensive validation report."""
        logger.info("📊 Generating Checklist Validation Report...")
        
        # Calculate overall status
        overall_pass = all(
            result.get('overall_status') == 'PASS' 
            for result in self.results.values()
        )
        
        # Print summary
        print("\n" + "="*80)
        print("PHASE 4 STAGING CHECKLIST VALIDATION REPORT")
        print("="*80)
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print(f"Base URL: {self.base_url}")
        print(f"Overall Status: {'✅ PASS' if overall_pass else '❌ FAIL'}")
        print()
        
        # Authentication summary
        auth = self.results.get('authentication', {})
        print(f"🔐 Authentication & Authorization: {auth.get('overall_status', 'UNKNOWN')}")
        if auth.get('protected_401_without_token'):
            for endpoint, result in auth['protected_401_without_token'].items():
                status = "✅" if result.get('pass') else "❌"
                print(f"   {status} {endpoint} → {result.get('status_code', 'ERROR')}")
        
        if auth.get('protected_200_with_token'):
            for endpoint, result in auth['protected_200_with_token'].items():
                status = "✅" if result.get('pass') else "❌"
                print(f"   {status} {endpoint} → {result.get('status_code', 'ERROR')}")
        print()
        
        # Route registry summary
        registry = self.results.get('route_registry', {})
        print(f"🛣️ Route Registry & API Health: {registry.get('overall_status', 'UNKNOWN')}")
        for check_name, result in registry.items():
            if check_name != 'overall_status' and isinstance(result, dict):
                status = "✅" if result.get('pass') else "❌"
                print(f"   {status} {check_name}")
        print()
        
        # API health summary
        health = self.results.get('api_health', {})
        print(f"⚡ API Health & Responsiveness: {health.get('overall_status', 'UNKNOWN')}")
        if health.get('response_times'):
            for endpoint, times in health['response_times'].items():
                print(f"   📈 {endpoint}: {times['avg_ms']}ms avg, {times['p95_ms']}ms p95")
        print()
        
        # Manual checks reminder
        print("📋 MANUAL CHECKS REQUIRED:")
        print("   ⏳ Performance benchmarks (K6 smoke test)")
        print("   📦 Order outbox processing")
        print("   🚨 Error monitoring & log analysis")
        print("   💾 Backup/restore validation")
        print("   🛡️ Risk management gates")
        print()
        
        print("💡 Next Steps:")
        if overall_pass:
            print("   ✅ Automated checks PASSED")
            print("   🔄 Complete manual checks in PHASE4_STAGING_CHECKLIST.md")
            print("   📝 Document results and make Go/No-Go decision")
        else:
            print("   ❌ Automated checks FAILED")
            print("   🔧 Fix issues identified above")
            print("   🔄 Re-run validation after fixes")
        
        print("="*80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 4 Staging Checklist Validator")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the staging API"
    )
    parser.add_argument(
        "--api-token",
        help="API token for authenticated requests"
    )
    parser.add_argument(
        "--output",
        help="Output JSON results to file"
    )
    
    args = parser.parse_args()
    
    # Create validator and run checks
    validator = StagingChecklistValidator(
        base_url=args.base_url,
        api_token=args.api_token
    )
    
    try:
        results = validator.run_all_checks()
        
        # Save results to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'base_url': args.base_url,
                    'results': results
                }, f, indent=2)
            logger.info(f"Results saved to {args.output}")
        
        # Exit with appropriate code
        overall_pass = all(
            result.get('overall_status') == 'PASS' 
            for result in results.values()
        )
        
        sys.exit(0 if overall_pass else 1)
        
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()