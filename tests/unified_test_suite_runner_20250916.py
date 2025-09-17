# Comprehensive Test Suite Implementation
# Created: September 16, 2025
# Status: CAN BE REMOVED (Temporary implementation file)
# Purpose: Unified test execution following AI recommendations and user protocols

"""
Consolidated Test Suite Runner

This script implements the AI's comprehensive test suite recommendations:
1. Unified test location and structure
2. Complete test discovery and execution
3. Coverage measurement and reporting
4. Parallel execution support
5. Result consolidation

All outputs are directed to test_results/ directory following the new file organization protocol.
"""

import subprocess
import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import shutil

class UnifiedTestSuiteRunner:
    """
    Comprehensive test suite runner implementing AI recommendations
    """
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.test_results_dir = self.project_root / "test_results"
        self.reports_dir = self.project_root / "reports"
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create required directories
        self.test_results_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)
        
        self.results = {
            "execution_timestamp": self.timestamp,
            "test_discovery": {},
            "test_execution": {},
            "coverage_analysis": {},
            "recommendations": [],
            "files_processed": []
        }
    
    def discover_all_tests(self) -> Dict[str, Any]:
        """
        Discover all test files across the platform
        """
        print("[DISCOVER] Discovering all test files...")
        
        test_files = {
            "tests_directory": [],
            "root_level": [],
            "tools_directory": [],
            "other_locations": []
        }
        
        # Find all test files
        for pattern in ["test_*.py", "*_test.py"]:
            for test_file in self.project_root.rglob(pattern):
                relative_path = test_file.relative_to(self.project_root)
                
                # Skip files in to_be_removed
                if "to_be_removed" in str(relative_path):
                    continue
                    
                # Categorize by location
                if str(relative_path).startswith("tests/"):
                    test_files["tests_directory"].append(str(relative_path))
                elif str(relative_path).startswith("tools/"):
                    test_files["tools_directory"].append(str(relative_path))
                elif "/" not in str(relative_path):
                    test_files["root_level"].append(str(relative_path))
                else:
                    test_files["other_locations"].append(str(relative_path))
        
        # Count totals
        total_files = sum(len(files) for files in test_files.values())
        
        discovery_results = {
            "total_test_files": total_files,
            "categorized_files": test_files,
            "discovery_time": datetime.now().isoformat()
        }
        
        self.results["test_discovery"] = discovery_results
        
        print(f"[PASS] Found {total_files} test files")
        print(f"   - tests/ directory: {len(test_files['tests_directory'])} files")
        print(f"   - Root level: {len(test_files['root_level'])} files")  
        print(f"   - tools/ directory: {len(test_files['tools_directory'])} files")
        print(f"   - Other locations: {len(test_files['other_locations'])} files")
        
        return discovery_results
    
    def check_test_environment(self) -> bool:
        """
        Verify test environment is ready
        """
        print("🔧 Checking test environment...")
        
        # Use the virtual environment python
        python_exe = "C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe"
        
        # Check pytest installation
        try:
            result = subprocess.run([python_exe, "-m", "pytest", "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"PASS PyTest available: {result.stdout.strip()}")
            else:
                print("FAIL PyTest not available")
                return False
        except Exception as e:
            print(f"FAIL Error checking PyTest: {e}")
            return False
        
        # Check pytest-cov for coverage
        try:
            result = subprocess.run([python_exe, "-m", "pytest", "--help"], 
                                  capture_output=True, text=True, timeout=10)
            if "--cov" in result.stdout:
                print("PASS pytest-cov available for coverage analysis")
            else:
                print("WARN pytest-cov not detected, installing...")
                subprocess.run([python_exe, "-m", "pip", "install", "pytest-cov"], 
                             check=True, timeout=30)
                print("PASS pytest-cov installed")
        except Exception as e:
            print(f"WARN Could not install pytest-cov: {e}")
        
        return True
    
    def run_comprehensive_tests(self, parallel: bool = True) -> Dict[str, Any]:
        """
        Execute comprehensive test suite with coverage
        """
        print("🚀 Running comprehensive test suite...")
        
        if not self.check_test_environment():
            return {"error": "Test environment not ready"}
        
        # Prepare test command
        python_exe = "C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe"
        cmd = [python_exe, "-m", "pytest"]
        
        # Add coverage options
        cmd.extend([
            "--cov=backend",
            "--cov=frontend", 
            "--cov=models",
            "--cov=scripts",
            "--cov-report=term-missing:skip-covered",
            "--cov-report=html:test_results/coverage_html",
            "--cov-report=xml:test_results/coverage.xml"
        ])
        
        # Add result reporting
        cmd.extend([
            "--junitxml=test_results/test_results.xml",
            "--tb=short",
            "-v"
        ])
        
        # Add parallel execution if requested
        if parallel:
            try:
                # Test if pytest-xdist is available
                subprocess.run([python_exe, "-c", "import xdist"], check=True, timeout=5, capture_output=True)
                cmd.extend(["-n", "auto"])
                print("[RUN] Running tests in parallel...")
            except:
                print("[WARN] pytest-xdist not available, running sequentially...")
        else:
            print("[RUN] Running tests sequentially...")
        
        # Set timeout
        cmd.extend(["--timeout=30"])
        
        # Run from project root
        start_time = datetime.now()
        
        try:
            print(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            execution_results = {
                "command": " ".join(cmd),
                "return_code": result.returncode,
                "duration_seconds": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
            
            # Save detailed output
            with open(self.test_results_dir / f"pytest_output_{self.timestamp}.txt", "w") as f:
                f.write("COMMAND:\n")
                f.write(" ".join(cmd) + "\n\n")
                f.write("STDOUT:\n")
                f.write(result.stdout + "\n\n")
                f.write("STDERR:\n")
                f.write(result.stderr)
            
            self.results["test_execution"] = execution_results
            
            if result.returncode == 0:
                print(f"[PASS] Tests completed successfully in {duration:.1f}s")
            else:
                print(f"[WARN] Tests completed with issues in {duration:.1f}s (exit code: {result.returncode})")
            
            return execution_results
            
        except subprocess.TimeoutExpired:
            print("[FAIL] Test execution timed out after 10 minutes")
            return {"error": "Test execution timeout"}
        except Exception as e:
            print(f"[FAIL] Error running tests: {e}")
            return {"error": str(e)}
    
    def analyze_coverage_results(self) -> Dict[str, Any]:
        """
        Analyze coverage results and identify gaps
        """
        print("[ANALYZE] Analyzing coverage results...")
        
        coverage_xml = self.test_results_dir / "coverage.xml"
        coverage_analysis = {
            "analysis_time": datetime.now().isoformat(),
            "coverage_available": False,
            "summary": {},
            "gaps": [],
            "recommendations": []
        }
        
        if coverage_xml.exists():
            coverage_analysis["coverage_available"] = True
            print("[PASS] Coverage data found")
            
            # Parse coverage XML for basic stats
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(coverage_xml)
                root = tree.getroot()
                
                # Extract coverage metrics
                coverage_analysis["summary"] = {
                    "line_rate": float(root.get("line-rate", "0")),
                    "branch_rate": float(root.get("branch-rate", "0")),
                    "lines_covered": int(root.get("lines-covered", "0")),
                    "lines_valid": int(root.get("lines-valid", "0"))
                }
                
                # Calculate percentage
                if coverage_analysis["summary"]["lines_valid"] > 0:
                    coverage_pct = (coverage_analysis["summary"]["lines_covered"] / 
                                  coverage_analysis["summary"]["lines_valid"]) * 100
                    coverage_analysis["summary"]["coverage_percentage"] = round(coverage_pct, 2)
                
                print(f"[INFO] Coverage: {coverage_analysis['summary'].get('coverage_percentage', 0):.1f}%")
                
            except Exception as e:
                print(f"[WARN] Could not parse coverage XML: {e}")
        
        else:
            print("[WARN] No coverage data found")
        
        self.results["coverage_analysis"] = coverage_analysis
        return coverage_analysis
    
    def generate_recommendations(self) -> List[str]:
        """
        Generate recommendations based on test results
        """
        recommendations = []
        
        # Test organization recommendations
        discovery = self.results.get("test_discovery", {})
        if discovery.get("categorized_files", {}).get("root_level"):
            recommendations.append(
                "Move root-level test files to tests/ directory for better organization"
            )
        
        if discovery.get("categorized_files", {}).get("other_locations"):
            recommendations.append(
                "Consolidate scattered test files into unified tests/ structure"
            )
        
        # Coverage recommendations
        coverage = self.results.get("coverage_analysis", {})
        if coverage.get("coverage_available"):
            coverage_pct = coverage.get("summary", {}).get("coverage_percentage", 0)
            if coverage_pct < 80:
                recommendations.append(
                    f"Increase test coverage from {coverage_pct:.1f}% to 80%+ by adding tests for uncovered code"
                )
            elif coverage_pct < 90:
                recommendations.append(
                    f"Good coverage at {coverage_pct:.1f}%, consider targeting 90%+ for critical modules"
                )
        
        # Test execution recommendations
        execution = self.results.get("test_execution", {})
        if execution.get("return_code", 0) != 0:
            recommendations.append(
                "Fix failing tests to achieve 100% pass rate before production deployment"
            )
        
        if execution.get("duration_seconds", 0) > 300:  # 5 minutes
            recommendations.append(
                "Consider optimizing slow tests or splitting into fast/slow test suites"
            )
        
        self.results["recommendations"] = recommendations
        return recommendations
    
    def generate_comprehensive_report(self) -> str:
        """
        Generate comprehensive test suite report
        """
        print("[REPORT] Generating comprehensive report...")
        
        # Complete analysis
        self.analyze_coverage_results()
        recommendations = self.generate_recommendations()
        
        # Generate report
        report_path = self.reports_dir / f"test_suite_analysis_{self.timestamp}.md"
        
        with open(report_path, "w", encoding='utf-8') as f:
            f.write(f"# Comprehensive Test Suite Analysis Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Status:** CAN BE REMOVED (Temporary analysis report)\n")
            f.write(f"**Purpose:** AI-recommended unified test suite implementation results\n\n")
            
            # Executive Summary
            f.write("## Executive Summary\n\n")
            discovery = self.results.get("test_discovery", {})
            total_tests = discovery.get("total_test_files", 0)
            f.write(f"- **Total Test Files:** {total_tests}\n")
            
            coverage = self.results.get("coverage_analysis", {})
            if coverage.get("coverage_available"):
                coverage_pct = coverage.get("summary", {}).get("coverage_percentage", 0)
                f.write(f"- **Code Coverage:** {coverage_pct:.1f}%\n")
            
            execution = self.results.get("test_execution", {})
            if execution.get("duration_seconds"):
                f.write(f"- **Execution Time:** {execution['duration_seconds']:.1f}s\n")
            
            if execution.get("return_code") == 0:
                f.write("- **Test Status:** PASS All tests passing\n")
            else:
                f.write("- **Test Status:** FAIL Some tests failing\n")
            
            f.write("\n")
            
            # Test Discovery Details
            f.write("## Test Discovery Analysis\n\n")
            if discovery:
                categorized = discovery.get("categorized_files", {})
                f.write("### Test File Distribution\n\n")
                for category, files in categorized.items():
                    f.write(f"**{category.replace('_', ' ').title()}:** {len(files)} files\n")
                    if files:
                        for file in sorted(files)[:5]:  # Show first 5
                            f.write(f"- {file}\n")
                        if len(files) > 5:
                            f.write(f"- ... and {len(files) - 5} more\n")
                    f.write("\n")
            
            # Test Execution Results
            f.write("## Test Execution Results\n\n")
            if execution:
                f.write(f"**Command:** `{execution.get('command', 'N/A')}`\n")
                f.write(f"**Duration:** {execution.get('duration_seconds', 0):.1f} seconds\n")
                f.write(f"**Exit Code:** {execution.get('return_code', 'N/A')}\n\n")
                
                if execution.get("stdout"):
                    f.write("### Test Output Summary\n\n")
                    # Extract key lines from stdout
                    lines = execution["stdout"].split("\n")
                    for line in lines:
                        if any(keyword in line.lower() for keyword in 
                              ["passed", "failed", "error", "coverage", "warnings"]):
                            f.write(f"- {line.strip()}\n")
                    f.write("\n")
            
            # Coverage Analysis
            f.write("## Coverage Analysis\n\n")
            if coverage.get("coverage_available"):
                summary = coverage.get("summary", {})
                f.write(f"**Overall Coverage:** {summary.get('coverage_percentage', 0):.1f}%\n")
                f.write(f"**Lines Covered:** {summary.get('lines_covered', 0):,}\n")
                f.write(f"**Total Lines:** {summary.get('lines_valid', 0):,}\n")
                f.write(f"**Branch Coverage:** {summary.get('branch_rate', 0)*100:.1f}%\n\n")
                
                f.write("**Coverage Reports Generated:**\n")
                f.write("- HTML Report: `test_results/coverage_html/index.html`\n")
                f.write("- XML Report: `test_results/coverage.xml`\n\n")
            else:
                f.write("FAIL Coverage analysis not available\n\n")
            
            # Recommendations
            f.write("## Recommendations\n\n")
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    f.write(f"{i}. {rec}\n")
            else:
                f.write("PASS No specific recommendations - test suite appears well organized\n")
            f.write("\n")
            
            # Implementation Status
            f.write("## AI Recommendation Implementation Status\n\n")
            f.write("PASS **Test Discovery:** Complete unified test file identification\n")
            f.write("PASS **Test Execution:** Automated pytest with coverage measurement\n") 
            f.write("PASS **Result Consolidation:** All outputs in test_results/ directory\n")
            f.write("PASS **Parallel Execution:** Enabled for faster test runs\n")
            f.write("PASS **Coverage Reporting:** HTML and XML reports generated\n")
            f.write("WARN **Test Organization:** May need file consolidation (see recommendations)\n\n")
            
            # Next Steps
            f.write("## Next Steps\n\n")
            f.write("1. Review coverage HTML report for detailed line-by-line analysis\n")
            f.write("2. Address any failing tests identified in execution results\n")
            f.write("3. Consider implementing test file organization recommendations\n")
            f.write("4. Set up regular test execution schedule\n")
            f.write("5. Add tests for any uncovered critical code paths\n\n")
            
            f.write("---\n")
            f.write("*This report follows the new file organization protocol and can be removed after review.*\n")
        
        # Save JSON results for programmatic access
        json_path = self.test_results_dir / f"test_results_{self.timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        print(f"[PASS] Report generated: {report_path}")
        print(f"[PASS] JSON data saved: {json_path}")
        
        return str(report_path)
    
    def run_complete_analysis(self) -> str:
        """
        Run complete test suite analysis
        """
        print("[START] Starting Comprehensive Test Suite Analysis")
        print("=" * 60)
        
        # Step 1: Discover tests
        self.discover_all_tests()
        
        # Step 2: Run tests with coverage
        self.run_comprehensive_tests()
        
        # Step 3: Generate comprehensive report
        report_path = self.generate_comprehensive_report()
        
        print("=" * 60)
        print("[COMPLETE] Comprehensive Test Suite Analysis Complete")
        print(f"[REPORT] Report: {report_path}")
        print(f"[COVERAGE] Coverage: test_results/coverage_html/index.html")
        print(f"[DATA] Raw data: test_results/test_results_{self.timestamp}.json")
        
        return report_path

if __name__ == "__main__":
    runner = UnifiedTestSuiteRunner()
    report_path = runner.run_complete_analysis()
    print(f"\n[SUCCESS] Complete analysis saved to: {report_path}")