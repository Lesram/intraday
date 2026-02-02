"""
Verification Script - Test Framework Integration Check
Validates all fixes before deep test run
"""

import sys
import json
from pathlib import Path

def check_k6_cache_manager():
    """Verify K6CacheManager has all required methods"""
    print("\n🔍 Checking K6CacheManager...")
    
    errors = []
    warnings = []
    
    k6_file = Path("scripts/testing/k6_cache_manager.py")
    if not k6_file.exists():
        errors.append("❌ k6_cache_manager.py not found")
        return errors, warnings
    
    content = k6_file.read_text(encoding='utf-8')
    
    # Check for required methods/fixes
    checks = [
        ("_extract_standard_metrics", "Method for extracting latency metrics"),
        ("_extract_route_metrics", "Method for extracting per-route metrics"),
        ("_evaluate_test_success", "Method for evaluating test results"),
        ("float(values.get('p(95)', 0) or 0)", "Robust P95 parsing"),
        ("float(values.get('p(99)', 0) or 0)", "Robust P99 parsing"),
        ("if return_code not in [0, 99]:", "K6 exit code 99 handling"),
        ("http_req_duration{name:", "Route metrics tag parsing"),
        ("logger.info(", "Logging for verification"),
    ]
    
    for check_str, description in checks:
        if check_str in content:
            print(f"  ✅ {description}")
        else:
            errors.append(f"❌ Missing: {description}")
    
    return errors, warnings

def check_promotion_gates():
    """Verify automated_promotion_gates has all required methods"""
    print("\n🔍 Checking Promotion Gates...")
    
    errors = []
    warnings = []
    
    gates_file = Path("scripts/testing/automated_promotion_gates.py")
    if not gates_file.exists():
        errors.append("❌ automated_promotion_gates.py not found")
        return errors, warnings
    
    content = gates_file.read_text(encoding='utf-8')
    
    # Check for required methods/fixes
    checks = [
        ("async def _get_slo_data", "SLO data fetching method"),
        ("async def _calculate_slo_from_metrics", "SLO calculation from metrics"),
        ("_generate_synthetic_slo_gates", "Synthetic gates method"),
        ("average_success_rate", "Burn-in success rate usage"),
        ("error_budget_remaining", "Error budget calculation"),
    ]
    
    for check_str, description in checks:
        if check_str in content:
            print(f"  ✅ {description}")
        else:
            errors.append(f"❌ Missing: {description}")
    
    # Critical check: Does _load_latest_burn_in_report exist?
    if "_load_latest_burn_in_report" in content:
        # Check if it's defined as a method
        if "async def _load_latest_burn_in_report" in content or "def _load_latest_burn_in_report" in content:
            print(f"  ✅ Burn-in report loading method defined")
        else:
            errors.append(f"❌ CRITICAL: _load_latest_burn_in_report called but not defined!")
    
    return errors, warnings

def check_burn_in_framework():
    """Verify burn_in_framework generates proper output"""
    print("\n🔍 Checking Burn-In Framework...")
    
    errors = []
    warnings = []
    
    # Check if burn-in report exists
    burn_in_dir = Path("test_results/burn_in")
    if not burn_in_dir.exists():
        warnings.append("⚠️  No burn_in directory (will be created on first run)")
        return errors, warnings
    
    reports = list(burn_in_dir.glob("burn_in_report_*.json"))
    if not reports:
        warnings.append("⚠️  No burn-in reports found (need to run burn-in test)")
        return errors, warnings
    
    # Validate latest report structure
    latest = max(reports, key=lambda p: p.stat().st_mtime)
    print(f"  📄 Found report: {latest.name}")
    
    try:
        with open(latest) as f:
            report = json.load(f)
        
        # Check required fields
        required_fields = {
            "burn_in_summary": ["all_sessions_passed", "sessions_completed"],
            "aggregate_metrics": ["total_requests", "average_success_rate", "stability_score"],
            "session_results": [],
            "promotion_gate_status": ["ready_for_production"]
        }
        
        for section, subfields in required_fields.items():
            if section in report:
                print(f"  ✅ Section: {section}")
                for subfield in subfields:
                    if subfield in report[section]:
                        print(f"    ✅ {subfield}")
                    else:
                        errors.append(f"❌ Missing field: {section}.{subfield}")
            else:
                errors.append(f"❌ Missing section: {section}")
        
        # Check P95 values
        for session in report.get('session_results', []):
            p95 = session.get('p95_latency_ms', -1)
            if p95 == 0.0:
                warnings.append(f"⚠️  Session {session['session_id']}: P95 still 0.0ms (needs re-run)")
            elif p95 > 0:
                print(f"  ✅ Session {session['session_id']}: P95 = {p95:.1f}ms")
        
    except Exception as e:
        errors.append(f"❌ Failed to parse report: {str(e)}")
    
    return errors, warnings

def check_k6_script():
    """Verify K6 script outputs proper format"""
    print("\n🔍 Checking K6 Script...")
    
    errors = []
    warnings = []
    
    k6_script = Path("scripts/testing/k6_enhanced_comprehensive_test.js")
    if not k6_script.exists():
        errors.append("❌ K6 script not found")
        return errors, warnings
    
    content = k6_script.read_text(encoding='utf-8')
    
    # Check for required exports and functions
    checks = [
        ("export function handleSummary", "Summary handler"),
        ("http_req_duration{name:", "Tagged metrics"),
        ("endpoint_latencies", "Per-endpoint latencies"),
        ("overall_p95_ms", "Overall P95 metric"),
        ("unexpected_error_rate", "Error rate metric"),
    ]
    
    for check_str, description in checks:
        if check_str in content:
            print(f"  ✅ {description}")
        else:
            warnings.append(f"⚠️  {description} might be missing")
    
    return errors, warnings

def main():
    print("=" * 70)
    print("🔧 PRE-FLIGHT CHECK - Test Framework Verification")
    print("=" * 70)
    
    all_errors = []
    all_warnings = []
    
    # Run all checks
    checks = [
        check_k6_cache_manager,
        check_promotion_gates,
        check_burn_in_framework,
        check_k6_script
    ]
    
    for check_func in checks:
        errors, warnings = check_func()
        all_errors.extend(errors)
        all_warnings.extend(warnings)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 70)
    
    if all_errors:
        print(f"\n❌ ERRORS FOUND: {len(all_errors)}")
        for error in all_errors:
            print(f"  {error}")
    
    if all_warnings:
        print(f"\n⚠️  WARNINGS: {len(all_warnings)}")
        for warning in all_warnings:
            print(f"  {warning}")
    
    if not all_errors and not all_warnings:
        print("\n✅ ALL CHECKS PASSED - Ready for deep test!")
    elif not all_errors:
        print("\n✅ NO CRITICAL ERRORS - Ready for deep test!")
        print("   (Warnings can be addressed during/after testing)")
    else:
        print("\n❌ CRITICAL ERRORS FOUND - Fix before running tests!")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
