#!/usr/bin/env python3
"""
Comprehensive AlgoTrading Platform Testing Analysis
Analyzes all test categories and provides platform-wide test health assessment.
"""

import os
import subprocess
import sys
from pathlib import Path
import json
from datetime import datetime

def run_command(cmd, cwd=None, capture_output=True):
    """Run shell command and return result."""
    try:
        if isinstance(cmd, str):
            cmd = cmd.split()
        result = subprocess.run(
            cmd, 
            cwd=cwd, 
            capture_output=capture_output, 
            text=True, 
            timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except Exception as e:
        return "", str(e), -1

def analyze_test_structure():
    """Analyze test directory structure and categorize tests."""
    test_dir = Path("tests")
    if not test_dir.exists():
        return {}
    
    categories = {}
    total_files = 0
    
    for root, dirs, files in os.walk(test_dir):
        # Skip __pycache__ and other non-test directories
        dirs[:] = [d for d in dirs if not d.startswith('__')]
        
        test_files = [f for f in files if f.startswith('test_') and f.endswith('.py')]
        if test_files:
            rel_path = os.path.relpath(root, test_dir)
            category = rel_path if rel_path != '.' else 'root'
            categories[category] = {
                'path': root,
                'files': test_files,
                'count': len(test_files)
            }
            total_files += len(test_files)
    
    return categories, total_files

def get_test_collection_summary():
    """Get comprehensive test collection summary."""
    print("🔍 Collecting all tests...")
    stdout, stderr, rc = run_command(
        "python -m pytest tests/ --collect-only -q --tb=no"
    )
    
    if rc != 0:
        return {"error": f"Collection failed: {stderr}", "total_tests": 0}
    
    lines = stdout.strip().split('\n')
    test_functions = [line for line in lines if '::' in line and 'test_' in line]
    
    # Extract summary line
    summary_lines = [line for line in lines if 'collected' in line and 'items' in line]
    total_tests = 0
    if summary_lines:
        import re
        match = re.search(r'(\d+) items', summary_lines[-1])
        if match:
            total_tests = int(match.group(1))
    
    return {
        "total_tests": total_tests or len(test_functions),
        "test_functions": len(test_functions)
    }

def run_quick_test_sample():
    """Run a quick sample of tests from each category to assess health."""
    print("🧪 Running quick test samples...")
    
    # Test a few key areas
    test_commands = [
        ("API Health", "python -m pytest tests/api/test_http_endpoints.py::TestCoreEndpoints::test_health_endpoint_happy_path -v"),
        ("Unit Basic", "python -m pytest tests/unit/test_utilities.py::TestTimeUtilities::test_parse_timestamp_iso_format -v"),
        ("Features", "python -m pytest tests/unit/test_features.py::TestFeatureEngineering::test_rsi_calculation -v"),
        ("Risk Management", "python -m pytest tests/unit/test_risk_management.py::TestRiskManager::test_position_size_check_approved -v"),
        ("Security", "python -m pytest tests/unit/test_security_hardening.py::TestSecuritySettings::test_security_settings_default_values -v"),
    ]
    
    results = {}
    for name, cmd in test_commands:
        print(f"  Testing {name}...")
        stdout, stderr, rc = run_command(cmd)
        
        results[name] = {
            "command": cmd,
            "return_code": rc,
            "status": "PASS" if rc == 0 else "FAIL",
            "output_lines": len(stdout.split('\n')) if stdout else 0,
            "error": stderr[:200] if stderr and rc != 0 else None
        }
    
    return results

def analyze_coverage_report():
    """Parse the coverage report for insight."""
    print("📊 Analyzing coverage data...")
    try:
        # Try to get coverage summary
        stdout, stderr, rc = run_command(
            "python -m pytest tests/ --cov=backend --cov-report=term-missing --cov-fail-under=1 --maxfail=1 -x"
        )
        
        if "TOTAL" in stdout:
            # Extract coverage percentage
            lines = stdout.split('\n')
            for line in lines:
                if 'TOTAL' in line and '%' in line:
                    # Parse coverage line: "TOTAL    7996   5623   2112     50  24.0%"
                    parts = line.split()
                    if len(parts) >= 5 and parts[-1].endswith('%'):
                        coverage_pct = parts[-1].rstrip('%')
                        return {
                            "coverage_percentage": float(coverage_pct),
                            "status": "measured",
                            "total_lines": parts[1] if len(parts) > 1 else "unknown"
                        }
        
        return {"status": "error", "coverage_percentage": 0}
    except:
        return {"status": "unavailable", "coverage_percentage": 0}

def main():
    """Main analysis function."""
    print("🚀 AlgoTrading Platform - Comprehensive Test Analysis")
    print("=" * 60)
    
    analysis_start = datetime.now()
    
    # 1. Test Structure Analysis
    print("\n1️⃣ TEST STRUCTURE ANALYSIS")
    print("-" * 30)
    categories, total_files = analyze_test_structure()
    
    print(f"📁 Total Test Files: {total_files}")
    print(f"📂 Test Categories: {len(categories)}")
    print("\nCategory Breakdown:")
    
    for category, info in sorted(categories.items(), key=lambda x: x[1]['count'], reverse=True):
        print(f"  {category:20} │ {info['count']:3d} files")
    
    # 2. Test Collection Summary
    print("\n2️⃣ TEST COLLECTION SUMMARY")
    print("-" * 30)
    collection_info = get_test_collection_summary()
    
    if "error" in collection_info:
        print(f"❌ Collection Error: {collection_info['error']}")
    else:
        print(f"🧪 Total Test Functions: {collection_info['total_tests']:,}")
        print(f"📋 Average Tests per File: {collection_info['total_tests'] / total_files:.1f}")
    
    # 3. Quick Test Sample
    print("\n3️⃣ QUICK TEST HEALTH CHECK")
    print("-" * 30)
    quick_results = run_quick_test_sample()
    
    passed_count = sum(1 for r in quick_results.values() if r['status'] == 'PASS')
    total_count = len(quick_results)
    
    print(f"✅ Quick Test Results: {passed_count}/{total_count} passed")
    
    for name, result in quick_results.items():
        status_icon = "✅" if result['status'] == 'PASS' else "❌"
        print(f"  {status_icon} {name:15} │ {result['status']}")
        if result.get('error'):
            print(f"     └─ Error: {result['error'][:100]}...")
    
    # 4. Coverage Analysis
    print("\n4️⃣ COVERAGE ANALYSIS")
    print("-" * 30)
    coverage_info = analyze_coverage_report()
    
    if coverage_info['status'] == 'measured':
        coverage_pct = coverage_info['coverage_percentage']
        coverage_icon = "🟢" if coverage_pct >= 40 else "🟡" if coverage_pct >= 20 else "🔴"
        print(f"{coverage_icon} Code Coverage: {coverage_pct:.1f}%")
        print(f"📏 Total Code Lines: {coverage_info.get('total_lines', 'unknown')}")
    else:
        print(f"❌ Coverage Status: {coverage_info['status']}")
    
    # 5. Overall Assessment
    print("\n5️⃣ PLATFORM TESTING HEALTH ASSESSMENT")
    print("-" * 40)
    
    # Calculate health score
    structure_score = min(100, (total_files / 100) * 100)  # Up to 100 files = 100%
    collection_score = 100 if collection_info.get('total_tests', 0) > 1000 else 50
    sample_score = (passed_count / total_count) * 100 if total_count > 0 else 0
    coverage_score = coverage_info.get('coverage_percentage', 0)
    
    overall_score = (structure_score + collection_score + sample_score + coverage_score) / 4
    
    if overall_score >= 80:
        health_icon = "🟢"
        health_status = "EXCELLENT"
    elif overall_score >= 60:
        health_icon = "🟡"
        health_status = "GOOD"
    elif overall_score >= 40:
        health_icon = "🟠"
        health_status = "FAIR"
    else:
        health_icon = "🔴"
        health_status = "NEEDS IMPROVEMENT"
    
    print(f"{health_icon} Overall Testing Health: {health_status} ({overall_score:.1f}/100)")
    
    print("\nComponent Scores:")
    print(f"  📁 Test Structure:     {structure_score:.1f}/100")
    print(f"  🧪 Test Collection:    {collection_score:.1f}/100")
    print(f"  ⚡ Quick Test Health:  {sample_score:.1f}/100")
    print(f"  📊 Code Coverage:      {coverage_score:.1f}/100")
    
    # 6. Key Issues and Recommendations
    print("\n6️⃣ KEY ISSUES & RECOMMENDATIONS")
    print("-" * 40)
    
    issues = []
    recommendations = []
    
    if coverage_info.get('coverage_percentage', 0) < 40:
        issues.append("🔴 Code coverage below 40% target")
        recommendations.append("• Focus on increasing test coverage for core modules")
    
    if passed_count < total_count:
        issues.append(f"🟡 {total_count - passed_count} test categories failing quick checks")
        recommendations.append("• Investigate and fix failing test categories")
    
    if collection_info.get('total_tests', 0) == 0:
        issues.append("🔴 Test collection failed")
        recommendations.append("• Fix test collection and import issues")
    
    if not issues:
        print("✅ No critical issues identified in quick analysis")
    else:
        print("Issues Found:")
        for issue in issues:
            print(f"  {issue}")
        
        print("\nRecommendations:")
        for rec in recommendations:
            print(f"  {rec}")
    
    # Summary
    analysis_end = datetime.now()
    duration = (analysis_end - analysis_start).total_seconds()
    
    print(f"\n⏱️  Analysis completed in {duration:.1f}s")
    print(f"📈 Platform Scale: {total_files} test files, {collection_info.get('total_tests', 0):,} test functions")
    print(f"🎯 Next Steps: {'Focus on test execution and coverage improvement' if overall_score < 70 else 'Platform testing infrastructure is robust'}")
    
    return overall_score

if __name__ == "__main__":
    try:
        score = main()
        sys.exit(0 if score >= 60 else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        sys.exit(1)
