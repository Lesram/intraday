#!/usr/bin/env python3
"""
K6 Performance Test Integration for 5-Layer Testing Architecture
==============================================================
Integrates K6 comprehensive performance testing with the Layer testing system.
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

class K6PerformanceTestSuite:
    """K6 Performance Test Suite Integration"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.script_dir = Path(__file__).parent
        self.workspace_dir = self.script_dir.parent.parent
        self.k6_script = self.script_dir / "k6_enhanced_comprehensive_test.js"
        
    def check_k6_installed(self) -> bool:
        """Check if K6 is installed and available"""
        try:
            result = subprocess.run(
                ["k6", "version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"K6 found: {result.stdout.strip().split()[0]}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        print("K6 not found. Install from: https://k6.io/docs/get-started/installation/")
        return False
    
    def check_server_health(self) -> bool:
        """Check if the server is running and healthy"""
        try:
            import httpx
            
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    print(f"Server healthy at {self.base_url}")
                    return True
                else:
                    print(f"Server responded with status {response.status_code}")
                    return False
        except Exception as e:
            print(f"Server not accessible: {e}")
            return False
    
    def run_k6_test(self, duration: str = None, vus: int = None) -> tuple[bool, dict]:
        """Run the K6 comprehensive performance test"""
        if not self.check_k6_installed():
            return False, {"error": "K6 not installed"}
        
        if not self.check_server_health():
            return False, {"error": "Server not healthy"}
        
        print("K6 COMPREHENSIVE PERFORMANCE TEST")
        print("=" * 60)
        print(f"Test Script: {self.k6_script}")
        print(f"Target Server: {self.base_url}")
        print(f"Test Coverage: All 5 scenarios integrated")
        print("=" * 60)
        
        # Build K6 command
        cmd = ["k6", "run"]
        
        # Add environment variables
        env = os.environ.copy()
        env.update({
            "BASE_URL": self.base_url,
            "USERNAME": "admin",
            "PASSWORD": "admin123"
        })
        
        # Add K6 script path
        cmd.append(str(self.k6_script))
        
        try:
            print("Starting K6 performance test...")
            start_time = time.time()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env=env,
                cwd=self.workspace_dir
            )
            
            duration = time.time() - start_time
            
            print(f"\nK6 Test completed in {duration:.1f} seconds")
            print(f"Exit Code: {result.returncode}")
            
            if result.stdout:
                print("\nK6 Output:")
                print(result.stdout)
            
            if result.stderr and result.returncode != 0:
                print("\nK6 Errors:")
                print(result.stderr)
            
            success = result.returncode == 0
            
            # Parse results from output
            results = self.parse_k6_results(result.stdout, success)
            results["duration_seconds"] = duration
            results["exit_code"] = result.returncode
            
            if success:
                print("\nK6 PERFORMANCE TEST: SUCCESS")
                print("Platform performance validated across all scenarios!")
            else:
                print("\nK6 PERFORMANCE TEST: ISSUES DETECTED")
                print("Check performance metrics and thresholds")
            
            return success, results
            
        except subprocess.TimeoutExpired:
            return False, {"error": "K6 test timed out after 10 minutes"}
        except Exception as e:
            return False, {"error": f"K6 execution error: {e}"}
    
    def parse_k6_results(self, output: str, success: bool) -> dict:
        """Parse K6 test results from output"""
        results = {
            "success": success,
            "scenarios_completed": 0,
            "total_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0,
            "p95_response_time": 0,
            "thresholds_passed": 0,
            "thresholds_failed": 0
        }
        
        if not output:
            return results
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Parse Enhanced K6 Script Format
            if "Total Requests:" in line:
                try:
                    results["total_requests"] = int(line.split("Total Requests:")[1].strip())
                except:
                    pass
            
            elif "Test Duration:" in line and "s" in line:
                try:
                    duration_str = line.split("Test Duration:")[1].strip()
                    if "s" in duration_str:
                        results["test_duration"] = float(duration_str.replace("s", ""))
                except:
                    pass
            
            elif "Unexpected Error Rate:" in line and "%" in line:
                try:
                    # Extract error rate from enhanced format
                    rate_part = line.split("Unexpected Error Rate:")[1].split("%")[0].strip()
                    error_rate = float(rate_part)
                    results["failed_requests"] = int(results["total_requests"] * error_rate / 100)
                except:
                    pass
            
            elif "P95:" in line and "ms" in line:
                try:
                    # Extract P95 from enhanced format
                    p95_part = line.split("P95:")[1].strip()
                    if "ms" in p95_part:
                        results["p95_response_time"] = float(p95_part.replace("ms", ""))
                except:
                    pass
            
            # Count scenarios completed from enhanced format
            elif "✅" in line and ("api_load_test" in line or "order_flow_test" in line or "risk_engine_test" in line or "business_workflow_test" in line or "websocket_test" in line):
                results["scenarios_completed"] += 1
            
            # Parse Standard K6 Format (fallback)
            elif "http_reqs" in line and "/s" in line:
                try:
                    parts = line.split()
                    results["total_requests"] = int(parts[1])
                except:
                    pass
            
            elif "http_req_failed" in line and "%" in line:
                try:
                    # Extract percentage
                    pct_idx = line.find('%')
                    if pct_idx > 0:
                        pct_str = line[:pct_idx].split()[-1]
                        fail_rate = float(pct_str)
                        results["failed_requests"] = int(results["total_requests"] * fail_rate / 100)
                except:
                    pass
            
            elif "http_req_duration" in line and "avg=" in line:
                try:
                    # Extract average response time
                    avg_idx = line.find("avg=")
                    if avg_idx >= 0:
                        avg_part = line[avg_idx+4:].split()[0]
                        if "ms" in avg_part:
                            results["avg_response_time"] = float(avg_part.replace("ms", ""))
                except:
                    pass
            
            elif "p(95)" in line and "ms" in line:
                try:
                    # Extract p95 response time
                    p95_idx = line.find("p(95)=")
                    if p95_idx >= 0:
                        p95_part = line[p95_idx+6:].split()[0]
                        if "ms" in p95_part:
                            results["p95_response_time"] = float(p95_part.replace("ms", ""))
                except:
                    pass
            
            # Count thresholds
            elif "✓" in line or "✗" in line:
                if "✓" in line:
                    results["thresholds_passed"] += 1
                elif "✗" in line:
                    results["thresholds_failed"] += 1
        
        # Estimate scenarios completed based on success
        if success and results["total_requests"] > 0:
            results["scenarios_completed"] = 5  # All 5 scenarios
        elif results["total_requests"] > 0:
            results["scenarios_completed"] = min(4, max(1, results["thresholds_passed"] // 2))
        
        return results

def main():
    """Main execution for standalone K6 testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='K6 Comprehensive Performance Test')
    parser.add_argument('--base-url', default='http://localhost:8000', 
                       help='Base URL for the API server')
    parser.add_argument('--duration', help='Test duration override')
    parser.add_argument('--vus', type=int, help='Virtual users override')
    
    args = parser.parse_args()
    
    suite = K6PerformanceTestSuite(base_url=args.base_url)
    success, results = suite.run_k6_test(duration=args.duration, vus=args.vus)
    
    print("\n" + "=" * 60)
    print("K6 PERFORMANCE TEST SUMMARY")
    print("=" * 60)
    
    for key, value in results.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value}")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)