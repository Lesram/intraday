#!/usr/bin/env python3
"""
COMPREHENSIVE TEST RESULTS ANALYZER
Analyzes all 3,907 tests for complete platform assessment and UI readiness
"""

import xml.etree.ElementTree as ET
import json
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

class ComprehensiveTestAnalyzer:
    def __init__(self, xml_file="full_test_results.xml"):
        self.xml_file = Path(xml_file)
        self.results = {}
        self.patterns = defaultdict(list)
        self.modules = defaultdict(dict)
        
    def parse_xml_results(self):
        """Parse JUnit XML results comprehensively"""
        if not self.xml_file.exists():
            return {"error": "XML results file not found"}
            
        try:
            tree = ET.parse(self.xml_file)
            root = tree.getroot()
            
            # Extract test suites and cases
            test_cases = root.findall(".//testcase")
            
            results = {
                "total_tests": len(test_cases),
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "execution_time": 0.0,
                "modules": defaultdict(lambda: {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}),
                "failure_patterns": defaultdict(int),
                "slowest_tests": [],
                "failed_tests": [],
                "error_details": []
            }
            
            for tc in test_cases:
                # Basic classification
                classname = tc.get("classname", "unknown")
                testname = tc.get("name", "unknown")
                time_taken = float(tc.get("time", 0))
                
                module = self.extract_module_name(classname)
                
                # Determine test status
                failures = tc.findall("failure")
                errors = tc.findall("error")
                skipped = tc.findall("skipped")
                
                if failures:
                    results["failed"] += 1
                    results["modules"][module]["failed"] += 1
                    
                    # Capture failure details
                    for failure in failures:
                        failure_msg = failure.get("message", "")
                        failure_type = failure.get("type", "")
                        results["failed_tests"].append({
                            "module": module,
                            "test": f"{classname}::{testname}",
                            "type": failure_type,
                            "message": failure_msg[:200] + "..." if len(failure_msg) > 200 else failure_msg
                        })
                        results["failure_patterns"][failure_type] += 1
                        
                elif errors:
                    results["errors"] += 1
                    results["modules"][module]["errors"] += 1
                    
                    # Capture error details  
                    for error in errors:
                        error_msg = error.get("message", "")
                        error_type = error.get("type", "")
                        results["error_details"].append({
                            "module": module,
                            "test": f"{classname}::{testname}",
                            "type": error_type,
                            "message": error_msg[:200] + "..." if len(error_msg) > 200 else error_msg
                        })
                        results["failure_patterns"][error_type] += 1
                        
                elif skipped:
                    results["skipped"] += 1
                    results["modules"][module]["skipped"] += 1
                    
                else:
                    results["passed"] += 1
                    results["modules"][module]["passed"] += 1
                
                # Track execution time
                results["execution_time"] += time_taken
                
                # Track slowest tests
                results["slowest_tests"].append({
                    "test": f"{classname}::{testname}",
                    "module": module,
                    "time": time_taken
                })
            
            # Sort slowest tests
            results["slowest_tests"].sort(key=lambda x: x["time"], reverse=True)
            results["slowest_tests"] = results["slowest_tests"][:20]  # Top 20
            
            return results
            
        except Exception as e:
            return {"error": f"XML parsing failed: {str(e)}"}
    
    def extract_module_name(self, classname):
        """Extract module name from test class name"""
        if not classname:
            return "unknown"
            
        parts = classname.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"  # e.g., "tests.api"
        return parts[0] if parts else "unknown"
    
    def calculate_metrics(self, results):
        """Calculate comprehensive metrics"""
        if "error" in results:
            return results
            
        total = results["total_tests"]
        passed = results["passed"]
        failed = results["failed"]
        errors = results["errors"]
        skipped = results["skipped"]
        
        executed = passed + failed + errors
        
        metrics = {
            "pass_rate": (passed / executed * 100) if executed > 0 else 0,
            "failure_rate": (failed / executed * 100) if executed > 0 else 0,
            "error_rate": (errors / executed * 100) if executed > 0 else 0,
            "skip_rate": (skipped / total * 100) if total > 0 else 0,
            "execution_coverage": (executed / total * 100) if total > 0 else 0,
            "avg_execution_time": results["execution_time"] / total if total > 0 else 0
        }
        
        return {**results, "metrics": metrics}
    
    def generate_module_analysis(self, results):
        """Generate detailed module-by-module analysis"""
        if "error" in results:
            return []
            
        module_analysis = []
        
        for module, stats in results["modules"].items():
            total_module = stats["passed"] + stats["failed"] + stats["errors"] + stats["skipped"]
            executed_module = stats["passed"] + stats["failed"] + stats["errors"]
            
            if executed_module > 0:
                pass_rate = (stats["passed"] / executed_module) * 100
                
                # Classify module health
                if pass_rate >= 90:
                    health = "EXCELLENT"
                elif pass_rate >= 80:
                    health = "GOOD"
                elif pass_rate >= 60:
                    health = "FAIR" 
                elif pass_rate >= 40:
                    health = "POOR"
                else:
                    health = "CRITICAL"
                    
                module_analysis.append({
                    "module": module,
                    "total": total_module,
                    "executed": executed_module,
                    "passed": stats["passed"],
                    "failed": stats["failed"],
                    "errors": stats["errors"],
                    "skipped": stats["skipped"],
                    "pass_rate": round(pass_rate, 2),
                    "health": health
                })
        
        # Sort by pass rate descending
        module_analysis.sort(key=lambda x: x["pass_rate"], reverse=True)
        return module_analysis
    
    def identify_improvement_priorities(self, results, module_analysis):
        """Identify priority areas for improvement"""
        priorities = {
            "critical_modules": [],
            "common_failures": [],
            "blocking_issues": [],
            "performance_issues": []
        }
        
        # Critical modules (pass rate < 50%)
        priorities["critical_modules"] = [
            m for m in module_analysis 
            if m["pass_rate"] < 50 and m["executed"] > 5
        ]
        
        # Most common failure patterns
        if "failure_patterns" in results:
            sorted_patterns = sorted(
                results["failure_patterns"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            priorities["common_failures"] = sorted_patterns[:10]
        
        # Performance issues (slowest tests)
        if "slowest_tests" in results:
            priorities["performance_issues"] = [
                test for test in results["slowest_tests"][:10]
                if test["time"] > 5.0  # Tests taking more than 5 seconds
            ]
        
        # Blocking issues (high-impact errors)
        blocking_keywords = ["ImportError", "ModuleNotFoundError", "ConnectionError", "DatabaseError"]
        if "error_details" in results:
            priorities["blocking_issues"] = [
                error for error in results["error_details"]
                if any(keyword in error["type"] for keyword in blocking_keywords)
            ][:20]
        
        return priorities
    
    def assess_ui_readiness(self, results, module_analysis):
        """Assess readiness for UI development phase"""
        if "error" in results:
            return {"ready": False, "reason": "Analysis failed"}
            
        # Define UI readiness criteria
        criteria = {
            "min_pass_rate": 75,  # Minimum 75% pass rate
            "api_module_health": "GOOD",  # API modules must be GOOD or better
            "max_critical_modules": 3,  # Max 3 critical modules allowed
            "max_blocking_issues": 10  # Max 10 blocking issues
        }
        
        # Check criteria
        readiness = {
            "overall_pass_rate": results.get("metrics", {}).get("pass_rate", 0),
            "api_modules_status": [],
            "critical_modules_count": 0,
            "blocking_issues_count": 0,
            "ready": True,
            "blockers": []
        }
        
        # Check API module health
        api_modules = [m for m in module_analysis if "api" in m["module"].lower()]
        for api_module in api_modules:
            readiness["api_modules_status"].append({
                "module": api_module["module"],
                "health": api_module["health"],
                "pass_rate": api_module["pass_rate"]
            })
            if api_module["health"] in ["POOR", "CRITICAL"]:
                readiness["ready"] = False
                readiness["blockers"].append(f"API module {api_module['module']} is {api_module['health']}")
        
        # Check overall pass rate
        if readiness["overall_pass_rate"] < criteria["min_pass_rate"]:
            readiness["ready"] = False
            readiness["blockers"].append(f"Overall pass rate {readiness['overall_pass_rate']:.1f}% below minimum {criteria['min_pass_rate']}%")
        
        # Count critical modules
        critical_modules = [m for m in module_analysis if m["health"] == "CRITICAL"]
        readiness["critical_modules_count"] = len(critical_modules)
        if len(critical_modules) > criteria["max_critical_modules"]:
            readiness["ready"] = False
            readiness["blockers"].append(f"Too many critical modules: {len(critical_modules)} > {criteria['max_critical_modules']}")
        
        return readiness
    
    def generate_comprehensive_report(self):
        """Generate the complete analysis report"""
        print("🔍 COMPREHENSIVE TEST ANALYSIS")
        print("=" * 80)
        print(f"Analysis started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Parse results
        print("📊 Parsing test results...")
        results = self.parse_xml_results()
        
        if "error" in results:
            print(f"❌ Analysis failed: {results['error']}")
            return results
        
        # Calculate metrics
        results = self.calculate_metrics(results)
        module_analysis = self.generate_module_analysis(results)
        priorities = self.identify_improvement_priorities(results, module_analysis)
        ui_readiness = self.assess_ui_readiness(results, module_analysis)
        
        # Generate report
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": results["total_tests"],
                "passed": results["passed"],
                "failed": results["failed"],
                "errors": results["errors"],
                "skipped": results["skipped"],
                "pass_rate": round(results["metrics"]["pass_rate"], 2),
                "execution_time": round(results["execution_time"], 2)
            },
            "modules": module_analysis,
            "priorities": priorities,
            "ui_readiness": ui_readiness,
            "raw_results": results
        }
        
        return report

def main():
    """Main analysis function"""
    analyzer = ComprehensiveTestAnalyzer()
    
    # Check if results file exists
    if not analyzer.xml_file.exists():
        print("❌ Test results file 'full_test_results.xml' not found.")
        print("💡 Make sure the comprehensive test suite has completed execution.")
        return
    
    # Generate comprehensive analysis
    report = analyzer.generate_comprehensive_report()
    
    if "error" in report:
        print(f"❌ Analysis failed: {report['error']}")
        return
    
    # Save report
    with open("comprehensive_test_analysis_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print("✅ Comprehensive analysis complete!")
    print("📄 Report saved to: comprehensive_test_analysis_report.json")
    print()
    print("🎯 KEY METRICS:")
    print(f"   Tests Executed: {report['summary']['total_tests']}")
    print(f"   Pass Rate: {report['summary']['pass_rate']:.2f}%")
    print(f"   UI Ready: {'✅ YES' if report['ui_readiness']['ready'] else '❌ NO'}")
    
    if not report['ui_readiness']['ready']:
        print(f"   Blockers: {len(report['ui_readiness']['blockers'])}")

if __name__ == "__main__":
    main()
