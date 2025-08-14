#!/usr/bin/env python3
"""
Comprehensive test runner for the trading platform.

Provides organized test execution with detailed reporting, coverage analysis,
and performance benchmarking. Supports different test suites and configurations.
"""

import os
import sys
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime
import json


class TestRunner:
    """Main test runner with comprehensive test suite management."""
    
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.test_dir = self.project_root / "tests"
        self.reports_dir = self.project_root / "test_reports"
        self.reports_dir.mkdir(exist_ok=True)
        
        # Test suite definitions
        self.test_suites = {
            "unit": {
                "path": "tests/unit/",
                "markers": "unit",
                "description": "Unit tests for individual components",
                "timeout": 300,  # 5 minutes
            },
            "integration": {
                "path": "tests/integration/",
                "markers": "integration", 
                "description": "Integration tests for component interactions",
                "timeout": 600,  # 10 minutes
            },
            "e2e": {
                "path": "tests/e2e/",
                "markers": "e2e",
                "description": "End-to-end system tests",
                "timeout": 1800,  # 30 minutes
            },
            "performance": {
                "path": "tests/performance/",
                "markers": "performance",
                "description": "Performance and benchmark tests",
                "timeout": 900,  # 15 minutes
            },
            "fuzz": {
                "path": "tests/fuzz/",
                "markers": "fuzz",
                "description": "Fuzz testing and chaos engineering",
                "timeout": 1200,  # 20 minutes
            },
            "smoke": {
                "path": "tests/",
                "markers": "not slow and not e2e and not performance and not fuzz",
                "description": "Quick smoke tests (fast unit tests)",
                "timeout": 120,  # 2 minutes
            },
            "full": {
                "path": "tests/",
                "markers": "",  # All tests
                "description": "Complete test suite",
                "timeout": 3600,  # 1 hour
            },
        }
    
    def run_test_suite(self, suite_name, coverage=True, html_report=True, 
                      verbose=True, parallel=False, fail_fast=False):
        """Run a specific test suite with configurable options."""
        
        if suite_name not in self.test_suites:
            available_suites = ", ".join(self.test_suites.keys())
            raise ValueError(f"Unknown test suite: {suite_name}. Available: {available_suites}")
        
        suite_config = self.test_suites[suite_name]
        
        print(f"\n{'='*60}")
        print(f"RUNNING TEST SUITE: {suite_name.upper()}")
        print(f"Description: {suite_config['description']}")
        print(f"Path: {suite_config['path']}")
        print(f"Timeout: {suite_config['timeout']}s")
        print(f"{'='*60}\n")
        
        # Build pytest command
        cmd = ["python", "-m", "pytest"]
        
        # Test path
        cmd.append(suite_config["path"])
        
        # Test markers
        if suite_config["markers"]:
            cmd.extend(["-m", suite_config["markers"]])
        
        # Coverage options
        if coverage:
            cmd.extend([
                "--cov=backend",
                "--cov-branch",
                "--cov-report=term-missing",
                f"--cov-report=xml:{self.reports_dir}/{suite_name}_coverage.xml",
            ])
            
            if html_report:
                cmd.extend([f"--cov-report=html:{self.reports_dir}/{suite_name}_coverage_html"])
        
        # Output options
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")
        
        # Parallel execution
        if parallel and suite_name in ["unit", "integration", "performance"]:
            try:
                import pytest_xdist
                cmd.extend(["-n", "auto"])  # Use all available CPUs
            except ImportError:
                print("Warning: pytest-xdist not installed, running sequentially")
        
        # Fail fast option
        if fail_fast:
            cmd.extend(["-x", "--tb=short"])
        
        # Test timeout
        cmd.extend(["--timeout", str(suite_config["timeout"])])
        
        # JUnit XML report
        cmd.extend([f"--junit-xml={self.reports_dir}/{suite_name}_junit.xml"])
        
        # JSON report (if available)
        try:
            import pytest_json_report
            cmd.extend([f"--json-report", f"--json-report-file={self.reports_dir}/{suite_name}_report.json"])
        except ImportError:
            pass
        
        # Run tests
        start_time = time.time()
        
        print("Command:", " ".join(cmd))
        print()
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, timeout=suite_config["timeout"] + 60)
            return_code = result.returncode
            
        except subprocess.TimeoutExpired:
            print(f"\n❌ TEST SUITE TIMEOUT: {suite_name} exceeded {suite_config['timeout']}s")
            return_code = 124  # Timeout exit code
        
        except KeyboardInterrupt:
            print(f"\n⚠️  TEST SUITE INTERRUPTED: {suite_name}")
            return_code = 130  # Interrupt exit code
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Report results
        self._report_suite_results(suite_name, return_code, duration)
        
        return return_code == 0
    
    def run_coverage_analysis(self):
        """Run comprehensive coverage analysis."""
        print("\n📊 RUNNING COVERAGE ANALYSIS")
        print("="*50)
        
        # Run all unit and integration tests with coverage
        cmd = [
            "python", "-m", "pytest",
            "tests/unit/", "tests/integration/",
            "--cov=backend",
            "--cov-branch",
            "--cov-report=term-missing",
            f"--cov-report=html:{self.reports_dir}/full_coverage_html",
            f"--cov-report=xml:{self.reports_dir}/full_coverage.xml",
            f"--cov-report=json:{self.reports_dir}/full_coverage.json",
            "--cov-fail-under=90",  # Fail if coverage < 90%
        ]
        
        result = subprocess.run(cmd, cwd=self.project_root)
        
        if result.returncode == 0:
            print("✅ Coverage target achieved (≥90%)")
        else:
            print("❌ Coverage target not met (<90%)")
        
        return result.returncode == 0
    
    def run_security_tests(self):
        """Run security-focused tests."""
        print("\n🔒 RUNNING SECURITY TESTS")
        print("="*40)
        
        security_tests = []
        
        # 1. Run Bandit security linter
        try:
            cmd = ["python", "-m", "bandit", "-r", "backend/", "-f", "json", 
                  "-o", f"{self.reports_dir}/security_bandit.json"]
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Bandit security scan: PASSED")
            else:
                print(f"❌ Bandit security scan: FAILED ({result.returncode} issues)")
                
            security_tests.append(("bandit", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  Bandit not installed, skipping security scan")
        
        # 2. Run safety check for vulnerable dependencies
        try:
            cmd = ["python", "-m", "safety", "check", "--json", 
                  "--output", f"{self.reports_dir}/security_safety.json"]
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Safety dependency check: PASSED")
            else:
                print(f"❌ Safety dependency check: FAILED ({result.returncode} vulnerabilities)")
                
            security_tests.append(("safety", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  Safety not installed, skipping dependency check")
        
        # 3. Run fuzz tests (focused on security)
        result = subprocess.run([
            "python", "-m", "pytest",
            "tests/fuzz/",
            "-m", "fuzz",
            "-v",
            f"--junit-xml={self.reports_dir}/security_fuzz_junit.xml"
        ], cwd=self.project_root)
        
        if result.returncode == 0:
            print("✅ Security fuzz tests: PASSED")
        else:
            print("❌ Security fuzz tests: FAILED")
            
        security_tests.append(("fuzz_security", result.returncode == 0))
        
        # Overall security assessment
        passed_tests = sum(1 for _, passed in security_tests if passed)
        total_tests = len(security_tests)
        
        print(f"\n🔒 Security Assessment: {passed_tests}/{total_tests} tests passed")
        
        return passed_tests == total_tests
    
    def run_performance_benchmarks(self):
        """Run performance benchmarks and generate reports."""
        print("\n⚡ RUNNING PERFORMANCE BENCHMARKS")
        print("="*45)
        
        # Run performance tests with detailed output
        cmd = [
            "python", "-m", "pytest",
            "tests/performance/",
            "-m", "performance",
            "-v", "-s",  # Show print statements
            f"--junit-xml={self.reports_dir}/performance_junit.xml",
            "--tb=short",
        ]
        
        # Add benchmark plugin if available
        try:
            import pytest_benchmark
            cmd.extend([
                f"--benchmark-json={self.reports_dir}/benchmarks.json",
                "--benchmark-sort=mean",
            ])
        except ImportError:
            print("⚠️  pytest-benchmark not installed, basic performance tests only")
        
        result = subprocess.run(cmd, cwd=self.project_root)
        
        if result.returncode == 0:
            print("✅ Performance benchmarks: PASSED")
        else:
            print("❌ Performance benchmarks: FAILED")
        
        return result.returncode == 0
    
    def run_quality_checks(self):
        """Run code quality checks (linting, type checking, formatting)."""
        print("\n📋 RUNNING QUALITY CHECKS")
        print("="*40)
        
        quality_results = []
        
        # 1. Black formatting check
        try:
            result = subprocess.run([
                "python", "-m", "black", "--check", "--diff", "backend/", "tests/"
            ], cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Black formatting: PASSED")
            else:
                print("❌ Black formatting: FAILED")
                print("Run: black backend/ tests/")
                
            quality_results.append(("black", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  Black not installed, skipping format check")
        
        # 2. isort import sorting check
        try:
            result = subprocess.run([
                "python", "-m", "isort", "--check-only", "--diff", "backend/", "tests/"
            ], cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ isort import sorting: PASSED")
            else:
                print("❌ isort import sorting: FAILED") 
                print("Run: isort backend/ tests/")
                
            quality_results.append(("isort", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  isort not installed, skipping import check")
        
        # 3. flake8 linting
        try:
            result = subprocess.run([
                "python", "-m", "flake8", "backend/", "tests/",
                "--output-file", f"{self.reports_dir}/flake8_report.txt"
            ], cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ flake8 linting: PASSED")
            else:
                print("❌ flake8 linting: FAILED")
                
            quality_results.append(("flake8", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  flake8 not installed, skipping linting")
        
        # 4. mypy type checking
        try:
            result = subprocess.run([
                "python", "-m", "mypy", "backend/",
                "--ignore-missing-imports",
                "--report", f"{self.reports_dir}/mypy_report"
            ], cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ mypy type checking: PASSED")
            else:
                print("❌ mypy type checking: FAILED")
                
            quality_results.append(("mypy", result.returncode == 0))
            
        except FileNotFoundError:
            print("⚠️  mypy not installed, skipping type check")
        
        # Overall quality assessment
        passed_checks = sum(1 for _, passed in quality_results if passed)
        total_checks = len(quality_results)
        
        print(f"\n📋 Quality Assessment: {passed_checks}/{total_checks} checks passed")
        
        return passed_checks == total_checks
    
    def _report_suite_results(self, suite_name, return_code, duration):
        """Generate detailed test suite report."""
        
        status = "✅ PASSED" if return_code == 0 else "❌ FAILED"
        
        print(f"\n{'-'*50}")
        print(f"TEST SUITE RESULTS: {suite_name.upper()}")
        print(f"Status: {status}")
        print(f"Duration: {duration:.2f}s")
        print(f"Exit Code: {return_code}")
        
        # Check for report files
        reports_found = []
        
        junit_file = self.reports_dir / f"{suite_name}_junit.xml"
        if junit_file.exists():
            reports_found.append(f"JUnit XML: {junit_file}")
        
        coverage_file = self.reports_dir / f"{suite_name}_coverage.xml"
        if coverage_file.exists():
            reports_found.append(f"Coverage XML: {coverage_file}")
        
        coverage_html = self.reports_dir / f"{suite_name}_coverage_html"
        if coverage_html.exists():
            reports_found.append(f"Coverage HTML: {coverage_html}/index.html")
        
        json_file = self.reports_dir / f"{suite_name}_report.json"
        if json_file.exists():
            reports_found.append(f"JSON Report: {json_file}")
        
        if reports_found:
            print("Reports Generated:")
            for report in reports_found:
                print(f"  - {report}")
        
        print(f"{'-'*50}\n")
    
    def generate_summary_report(self):
        """Generate overall test execution summary."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        summary_file = self.reports_dir / f"test_summary_{timestamp}.json"
        
        # Collect all available reports
        summary = {
            "timestamp": timestamp,
            "project_root": str(self.project_root),
            "reports_directory": str(self.reports_dir),
            "available_reports": [],
        }
        
        # Find all report files
        for report_file in self.reports_dir.glob("*"):
            if report_file.is_file():
                summary["available_reports"].append({
                    "name": report_file.name,
                    "path": str(report_file),
                    "size_bytes": report_file.stat().st_size,
                    "modified": datetime.fromtimestamp(report_file.stat().st_mtime).isoformat(),
                })
        
        # Write summary
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"📄 Test Summary Report: {summary_file}")
        
        return str(summary_file)


def main():
    """Main entry point for test runner."""
    
    parser = argparse.ArgumentParser(
        description="Comprehensive test runner for trading platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Suites:
  unit         - Unit tests for individual components (fast)
  integration  - Integration tests for component interactions  
  e2e          - End-to-end system tests (slow)
  performance  - Performance benchmarks and load tests
  fuzz         - Fuzz testing and chaos engineering
  smoke        - Quick smoke tests (subset of unit tests)
  full         - All tests (very slow)

Examples:
  python run_tests.py smoke                    # Quick tests
  python run_tests.py unit --coverage          # Unit tests with coverage
  python run_tests.py full --no-coverage       # All tests, no coverage
  python run_tests.py --quality --security     # Quality and security checks
  python run_tests.py performance --verbose    # Performance tests with details
        """
    )
    
    # Test suite selection
    parser.add_argument(
        "suite", 
        nargs="?", 
        default="smoke",
        choices=["unit", "integration", "e2e", "performance", "fuzz", "smoke", "full"],
        help="Test suite to run (default: smoke)"
    )
    
    # Test options
    parser.add_argument("--coverage", dest="coverage", action="store_true", default=True,
                       help="Include coverage analysis (default)")
    parser.add_argument("--no-coverage", dest="coverage", action="store_false",
                       help="Skip coverage analysis")
    
    parser.add_argument("--html", action="store_true", default=True,
                       help="Generate HTML reports (default)")
    parser.add_argument("--no-html", dest="html", action="store_false",
                       help="Skip HTML report generation")
    
    parser.add_argument("--verbose", "-v", action="store_true", default=True,
                       help="Verbose test output (default)")
    parser.add_argument("--quiet", "-q", dest="verbose", action="store_false",
                       help="Quiet test output")
    
    parser.add_argument("--parallel", "-j", action="store_true", 
                       help="Run tests in parallel (when supported)")
    
    parser.add_argument("--fail-fast", "-x", action="store_true",
                       help="Stop on first test failure")
    
    # Additional checks
    parser.add_argument("--quality", action="store_true",
                       help="Run code quality checks (linting, formatting)")
    
    parser.add_argument("--security", action="store_true", 
                       help="Run security tests and vulnerability scans")
    
    parser.add_argument("--benchmarks", action="store_true",
                       help="Run performance benchmarks")
    
    parser.add_argument("--all-checks", action="store_true",
                       help="Run tests plus quality, security, and benchmarks")
    
    # Configuration
    parser.add_argument("--project-root", type=str,
                       help="Project root directory (default: current directory)")
    
    args = parser.parse_args()
    
    # Initialize test runner
    runner = TestRunner(project_root=args.project_root)
    
    print("🧪 TRADING PLATFORM TEST RUNNER")
    print("="*50)
    print(f"Project Root: {runner.project_root}")
    print(f"Test Directory: {runner.test_dir}")
    print(f"Reports Directory: {runner.reports_dir}")
    print()
    
    all_passed = True
    
    # Run main test suite
    if not args.all_checks or args.suite != "smoke":
        suite_passed = runner.run_test_suite(
            suite_name=args.suite,
            coverage=args.coverage,
            html_report=args.html,
            verbose=args.verbose,
            parallel=args.parallel,
            fail_fast=args.fail_fast,
        )
        all_passed = all_passed and suite_passed
    
    # Run additional checks
    if args.quality or args.all_checks:
        quality_passed = runner.run_quality_checks()
        all_passed = all_passed and quality_passed
    
    if args.security or args.all_checks:
        security_passed = runner.run_security_tests()
        all_passed = all_passed and security_passed
    
    if args.benchmarks or args.all_checks:
        benchmark_passed = runner.run_performance_benchmarks()
        all_passed = all_passed and benchmark_passed
    
    # Coverage analysis for comprehensive runs
    if args.coverage and (args.all_checks or args.suite in ["full", "integration"]):
        coverage_passed = runner.run_coverage_analysis()
        all_passed = all_passed and coverage_passed
    
    # Generate summary report
    summary_file = runner.generate_summary_report()
    
    # Final results
    print("\n" + "="*60)
    print("FINAL TEST RESULTS")
    print("="*60)
    
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        exit_code = 0
    else:
        print("💥 SOME TESTS FAILED!")
        exit_code = 1
    
    print(f"📊 Summary Report: {summary_file}")
    print("="*60)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
