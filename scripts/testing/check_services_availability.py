#!/usr/bin/env python3
"""
Service Availability Diagnostic Script
Checks if all required endpoints are responding correctly
Used to diagnose promotion gate "Services Availability" requirement
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any, Tuple
from datetime import datetime


class ServiceAvailabilityChecker:
    """Check availability of required services for promotion gates"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.required_endpoints = [
            "/api/v1/signals",
            "/api/v1/orders",
            "/api/v1/risk/metrics"
        ]
        
    async def get_auth_token(self) -> str:
        """Get authentication token for testing"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try form-urlencoded format (as per K6 fix)
                data = "username=admin&password=admin123"
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                
                async with session.post(
                    f"{self.base_url}/api/v1/auth/login",
                    data=data,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("access_token", "")
                    else:
                        print(f"⚠️  Authentication failed: {resp.status}")
                        text = await resp.text()
                        print(f"    Response: {text[:200]}")
                        return ""
        except Exception as e:
            print(f"⚠️  Authentication error: {str(e)}")
            return ""
    
    async def check_endpoint(self, endpoint: str, token: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if an endpoint is available and responding
        Returns: (is_available, details)
        """
        details = {
            "endpoint": endpoint,
            "status": None,
            "response_time_ms": None,
            "error": None,
            "requires_auth": False,
            "available": False
        }
        
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            start_time = asyncio.get_event_loop().time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    end_time = asyncio.get_event_loop().time()
                    response_time_ms = (end_time - start_time) * 1000
                    
                    details["status"] = resp.status
                    details["response_time_ms"] = round(response_time_ms, 2)
                    
                    # Endpoints are considered available if they return:
                    # - 200 (success)
                    # - 401 (unauthorized - endpoint exists but needs auth)
                    # - 422 (unprocessable - endpoint exists but needs valid params)
                    # - 405 (method not allowed - endpoint exists but wrong HTTP method)
                    # - 307 (redirect - endpoint exists but redirecting to correct path)
                    if resp.status in [200, 401, 422, 405, 307]:
                        details["available"] = True
                        if resp.status == 401:
                            details["requires_auth"] = True
                        elif resp.status == 405:
                            details["note"] = "Endpoint exists but GET method not allowed (acceptable)"
                        elif resp.status == 307:
                            details["note"] = "Endpoint redirecting (likely trailing slash)"
                    
                    # Get response body for diagnostics
                    try:
                        body = await resp.text()
                        if body and len(body) < 500:
                            details["response_sample"] = body
                    except:
                        pass
                    
                    return details["available"], details
                    
        except asyncio.TimeoutError:
            details["error"] = "Timeout (>10s)"
            return False, details
        except aiohttp.ClientConnectorError as e:
            details["error"] = f"Connection failed: {str(e)}"
            return False, details
        except Exception as e:
            details["error"] = f"Unexpected error: {str(e)}"
            return False, details
    
    async def check_all_services(self) -> Dict[str, Any]:
        """Check all required services and generate report"""
        print("=" * 70)
        print("🔍 SERVICE AVAILABILITY DIAGNOSTIC")
        print("=" * 70)
        print(f"Base URL: {self.base_url}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print()
        
        # Get authentication token
        print("🔐 Authenticating...")
        token = await self.get_auth_token()
        if token:
            print(f"✅ Authentication successful (token: {token[:20]}...)")
        else:
            print("⚠️  Authentication failed - testing without token")
        print()
        
        # Check each endpoint
        print("📊 Checking Required Endpoints:")
        print("-" * 70)
        
        results = []
        available_count = 0
        
        for endpoint in self.required_endpoints:
            is_available, details = await self.check_endpoint(endpoint, token)
            results.append(details)
            
            # Display result
            status_icon = "✅" if is_available else "❌"
            status_code = details.get("status", "N/A")
            response_time = details.get("response_time_ms", "N/A")
            error = details.get("error", "")
            
            print(f"{status_icon} {endpoint}")
            print(f"   Status: {status_code}")
            if response_time != "N/A":
                print(f"   Response Time: {response_time}ms")
            if error:
                print(f"   Error: {error}")
            if details.get("requires_auth"):
                print(f"   ℹ️  Requires authentication (401) - endpoint exists")
            if "response_sample" in details:
                print(f"   Response: {details['response_sample'][:100]}")
            print()
            
            if is_available:
                available_count += 1
        
        # Summary
        print("=" * 70)
        print("📈 SUMMARY")
        print("=" * 70)
        total = len(self.required_endpoints)
        percentage = (available_count / total) * 100
        
        print(f"Available Services: {available_count}/{total} ({percentage:.1f}%)")
        print(f"Required for Promotion Gate: {int(total * 0.8)}/{total} (80%)")
        print()
        
        if available_count >= total * 0.8:
            print("✅ PASS: Services availability meets promotion gate requirement")
        else:
            print("❌ FAIL: Services availability below promotion gate threshold")
            print()
            print("Missing Services:")
            for details in results:
                if not details["available"]:
                    endpoint = details["endpoint"]
                    error = details.get("error", details.get("status", "Unknown"))
                    print(f"  - {endpoint}: {error}")
        
        print("=" * 70)
        
        return {
            "total_services": total,
            "available_services": available_count,
            "percentage": percentage,
            "meets_requirement": available_count >= total * 0.8,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    
    async def export_report(self, output_file: str = "service_availability_report.json"):
        """Generate and export detailed report"""
        report = await self.check_all_services()
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print()
        print(f"📄 Detailed report saved to: {output_file}")
        
        return report


async def main():
    """Main entry point"""
    import sys
    
    # Allow custom base URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    checker = ServiceAvailabilityChecker(base_url)
    report = await checker.export_report()
    
    # Exit with appropriate code
    sys.exit(0 if report["meets_requirement"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
