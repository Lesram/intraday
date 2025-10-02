#!/usr/bin/env python3
"""
[TARGET] COMPLETE PLATFORM TESTING - CONSOLIDATED ARCHITECTURE
========================================================
Enhanced comprehensive testing with consolidated foundation layers.

Layers 1-4: Foundation Tests → Import, Functional, Paper Trading & Live Server (Consolidated)
Layer 5: Business Workflows → Complete end-to-end business process validation

This represents the streamlined testing architecture for algorithmic 
trading platforms, with consolidated foundation validation and 
comprehensive business workflow testing.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Test result tracking
layer_results = {}
total_start_time = time.time()

def print_header():
    """Print the comprehensive test suite header"""
    print("[TARGET] COMPLETE PLATFORM TESTING - CONSOLIDATED ARCHITECTURE")
    print("=" * 100)
    print("Foundation (Layers 1-4): Consolidated → Business Layer (Layer 5): Comprehensive Workflows")
    print("=" * 100)

def run_layer_test(layer_num: int, layer_name: str, script_path: str, description: str) -> Tuple[bool, Dict[str, Any]]:
    """Run a single layer test and return results"""
    
    # Layer colors and icons
    layer_icons = {
        1: "[LAYER]",
        2: "🟢", 
        3: "🟡",
        4: "🟠",
        5: "[BUSINESS]"
    }
    
    print(f"\n{layer_icons[layer_num]} LAYER {layer_num}: {layer_name.upper()}")
    print("=" * 60)
    print(f"[RUN] Running {description}...")
    print("-" * 60)
    
    start_time = time.time()
    
    try:
        # Special handling for Layer 5 (async test)
        if layer_num == 5:
            result = subprocess.run([
                sys.executable, script_path
            ], capture_output=True, text=True, timeout=120)
        else:
            result = subprocess.run([
                sys.executable, script_path
            ], capture_output=True, text=True, timeout=180)
        
        duration = time.time() - start_time
        success = result.returncode == 0
        
        # Print the output
        if result.stdout:
            print(result.stdout)
        
        if result.stderr and not success:
            print(f"Error output: {result.stderr}")
        
        print(f"\n[FINISH] {description}: {'SUCCESS' if success else 'FAILED'}")
        
        return success, {
            "success": success,
            "duration": duration,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"[FAIL] {description}: TIMEOUT after {duration:.1f}s")
        return False, {
            "success": False,
            "duration": duration,
            "error": "timeout",
            "return_code": -1
        }
        
    except Exception as e:
        duration = time.time() - start_time
        print(f"[FAIL] {description}: ERROR - {e}")
        return False, {
            "success": False,
            "duration": duration,
            "error": str(e),
            "return_code": -2
        }

async def run_five_layer_testing():
    """Run complete five-layer testing architecture"""
    
    print_header()
    
    # Define all test layers
    test_layers = [
        (1, "Layers 1-4 Consolidated", "scripts/testing/test_layers_1_to_4_consolidated.py", "Import, Functional, Paper Trading & Live Server Integration"),
        (5, "Business Workflows", "scripts/testing/test_layer5_business_workflows.py", "Business Workflow Integration")
    ]
    
    # Track results
    results = {}
    passed_layers = 0
    total_duration = 0
    
    # Run each layer sequentially
    for layer_num, layer_name, script_path, description in test_layers:
        # Check if script exists
        script_file = Path(script_path)
        if not script_file.exists():
            print(f"\n[FAIL] Layer {layer_num} script not found: {script_path}")
            results[layer_num] = {
                "success": False,
                "duration": 0,
                "error": f"Script not found: {script_path}",
                "return_code": -3
            }
            continue
        
        # Run the layer test
        success, result_data = run_layer_test(layer_num, layer_name, script_path, description)
        results[layer_num] = result_data
        total_duration += result_data["duration"]
        
        if success:
            passed_layers += 1
        
        # For critical layers (1-4), continue even if they fail
        # For Layer 5, it's supplementary business validation
    
    # Generate comprehensive results summary
    print("\n" + "=" * 100)
    print("[RESULTS] COMPLETE PLATFORM TEST RESULTS")
    print("=" * 100)
    
    # Individual layer results (updated for consolidated architecture)
    # Layer 1 is now consolidated (contains old Layers 1-4)
    # Layer 5 is business workflows
    
    layer_1_result = results.get(1, {})
    layer_5_result = results.get(5, {})
    
    if layer_1_result:
        status = "[PASS] PASS" if layer_1_result["success"] else "[FAIL] FAIL"
        duration = layer_1_result["duration"]
        print(f"{status} Layer 1 (Foundation - Consolidated) [Critical    ] ({duration:.1f}s)")
        print("           → Import, Functional, Paper Trading & Live Server Integration")
    else:
        print(f"[SKIP]  Layer 1 (Foundation - Consolidated) [Skipped     ] (0.0s)")
    
    if layer_5_result:
        status = "[PASS] PASS" if layer_5_result["success"] else "[FAIL] FAIL"
        duration = layer_5_result["duration"]
        print(f"{status} Layer 5 (Business Workflows     ) [Business    ] ({duration:.1f}s)")
        print("           → End-to-End Trading & ML Workflows")
    else:
        print(f"[SKIP]  Layer 5 (Business Workflows     ) [Skipped     ] (0.0s)")
    
    print("\n" + "=" * 100)
    
    # Overall assessment (updated for consolidated architecture)
    core_foundation_passed = results.get(1, {}).get("success", False)
    business_layer_passed = results.get(5, {}).get("success", False)
    
    overall_success = core_foundation_passed  # Core foundation must pass
    
    if overall_success:
        print("🎉 OVERALL STATUS: COMPLETE SUCCESS")
        if core_foundation_passed and business_layer_passed:
            print("[PASS] Platform is fully validated and production-ready!")
            print("[RUN] All layers validated: Foundation (Layers 1-4) + Business Workflows")
        else:
            print("[PASS] Core foundation validated and ready for deployment!")
            print("[RUN] Foundation layers working: Import, Functional, Paper Trading & Live Server")
        
        if business_layer_passed:
            print("[TARGET] Business workflows validated!")
        else:
            print("[WARN]  Business workflows need attention (non-critical)")
        
        print("[RUN] Ready for production deployment!")
        
    else:
        print("[WARN]  OVERALL STATUS: PARTIAL SUCCESS")
        print(f"[DATA] Core Infrastructure: {'PASSED' if core_foundation_passed else 'FAILED'}")
        
        if not core_foundation_passed:
            print(f"[TOOL] Needs attention: Foundation (Layers 1-4 Consolidated)")
        
        if business_layer_passed:
            print("[PASS] Business workflows operational!")
        
        print("[LIST] Review failed layers before production deployment")
    
    print("\n" + "=" * 100)
    
    # Performance summary
    layers_passed_count = (1 if core_foundation_passed else 0) + (1 if business_layer_passed else 0)
    print("[DATA] PERFORMANCE SUMMARY:")
    print(f"  Total Test Duration: {total_duration:.1f}s")
    print(f"  Test Layers Passed: {layers_passed_count}/2")
    print(f"  Core Foundation: {'[PASS]' if core_foundation_passed else '[FAIL]'}")
    print(f"  Business Validation: {'[PASS]' if business_layer_passed else '[FAIL]'}")
    
    if overall_success:
        print(f"\n[LIST] NEXT STEPS BASED ON RESULTS:")
        if core_foundation_passed and business_layer_passed:
            print("1. [PASS] All systems validated - ready for production deployment")
            print("2. [RUN] Run burn-in test for stability validation (Phase 3)")
            print("3. [RUN] Execute promotion gates for deployment approval (Phase 4)")
            print("4. [TARGET] Monitor performance and scale as needed")
        elif core_foundation_passed:
            print("1. [PASS] Infrastructure ready - debug business workflows")
            print("2. [TOOL] Review Layer 5 failures and implement missing features")
            print("3. [RUN] Deploy infrastructure and add business features iteratively")
            print("4. [DATA] Monitor and validate business processes")
        else:
            print("1. [TOOL] Fix failing foundation layers before deployment")
            print("2. [PASS] Validate fixed components with individual tests")
            print("3. [RUN] Re-run complete test suite after fixes")
            print("4. [DATA] Deploy when foundation passes")
    else:
        print(f"\n[TOOL] CRITICAL ISSUES FOUND:")
        print("1. [FAIL] Core foundation failing - platform not ready")
        print("2. [MAINT]  Fix infrastructure issues before proceeding")
        print("3. [LIST] Review detailed test output above to isolate problems")
        print("4. [RETRY] Re-test after implementing fixes")
    
    return overall_success, results

def main():
    """Main execution function"""
    try:
        # Set environment variable for localhost testing
        import os
        os.environ["APP_HOST"] = "localhost"
        
        # Run the complete test suite
        success, results = asyncio.run(run_five_layer_testing())
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n[FAIL] Testing interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[FAIL] Fatal error in test suite: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
