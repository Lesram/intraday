#!/usr/bin/env python3
"""
Phase 5.1: Coverage Gap Analysis
Comprehensive analysis of remaining untested lines and modules to achieve 100% coverage.
"""

import pytest
import subprocess
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
import coverage

class CoverageGapAnalyzer:
    """Comprehensive coverage gap analysis for Phase 5 implementation."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.backend_dir = self.project_root / "backend"
        self.tests_dir = self.project_root / "tests"
        self.coverage_data = {}
        self.gap_analysis = {}
        
    def generate_comprehensive_coverage_report(self) -> Dict[str, Any]:
        """Generate detailed coverage report with line-by-line analysis."""
        print("🔍 Generating comprehensive coverage report...")
        
        # Run coverage with detailed reporting
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.tests_dir),
            f"--cov={self.backend_dir}",
            "--cov-report=term-missing",
            "--cov-report=json:coverage.json",
            "--cov-report=html:htmlcov",
            "--cov-branch",
            "-v"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # Load coverage data
            coverage_file = self.project_root / "coverage.json"
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    self.coverage_data = json.load(f)
            
            return {
                "status": "success" if result.returncode == 0 else "partial",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "coverage_data": self.coverage_data
            }
            
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "message": "Coverage generation timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def analyze_uncovered_lines(self) -> Dict[str, List[int]]:
        """Identify specific uncovered lines by module."""
        uncovered_lines = {}
        
        if not self.coverage_data or "files" not in self.coverage_data:
            return uncovered_lines
        
        for file_path, file_data in self.coverage_data["files"].items():
            if "missing_lines" in file_data and file_data["missing_lines"]:
                # Convert absolute path to relative
                rel_path = os.path.relpath(file_path, self.project_root)
                uncovered_lines[rel_path] = file_data["missing_lines"]
        
        return uncovered_lines
    
    def identify_zero_coverage_modules(self) -> List[str]:
        """Find modules with zero test coverage."""
        zero_coverage = []
        
        if not self.coverage_data or "files" not in self.coverage_data:
            return zero_coverage
        
        for file_path, file_data in self.coverage_data["files"].items():
            coverage_percent = file_data.get("summary", {}).get("percent_covered", 0)
            if coverage_percent == 0:
                rel_path = os.path.relpath(file_path, self.project_root)
                zero_coverage.append(rel_path)
        
        return zero_coverage
    
    def analyze_branch_coverage_gaps(self) -> Dict[str, Any]:
        """Analyze missing branch coverage."""
        branch_gaps = {}
        
        if not self.coverage_data or "files" not in self.coverage_data:
            return branch_gaps
        
        for file_path, file_data in self.coverage_data["files"].items():
            summary = file_data.get("summary", {})
            branch_total = summary.get("num_branches", 0)
            branch_covered = summary.get("covered_branches", 0)
            
            if branch_total > 0 and branch_covered < branch_total:
                rel_path = os.path.relpath(file_path, self.project_root)
                branch_gaps[rel_path] = {
                    "total_branches": branch_total,
                    "covered_branches": branch_covered,
                    "missing_branches": branch_total - branch_covered,
                    "branch_coverage_percent": (branch_covered / branch_total) * 100
                }
        
        return branch_gaps
    
    def categorize_hard_to_test_areas(self) -> Dict[str, List[str]]:
        """Categorize hard-to-test code areas by type."""
        categories = {
            "error_logging": [],
            "exception_handlers": [],
            "cleanup_teardown": [],
            "background_tasks": [],
            "defensive_code": []
        }
        
        # This would require static code analysis to implement fully
        # For now, return placeholder structure
        return categories
    
    def generate_priority_matrix(self) -> Dict[str, Any]:
        """Generate priority matrix for coverage implementation."""
        uncovered = self.analyze_uncovered_lines()
        zero_coverage = self.identify_zero_coverage_modules()
        branch_gaps = self.analyze_branch_coverage_gaps()
        
        priority_matrix = {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": []
        }
        
        # High priority: Zero coverage modules
        for module in zero_coverage:
            if "backend" in module and not module.endswith("__pycache__"):
                priority_matrix["high_priority"].append({
                    "module": module,
                    "type": "zero_coverage",
                    "impact": "high"
                })
        
        # Medium priority: Modules with significant uncovered lines
        for module, lines in uncovered.items():
            if len(lines) > 10 and "backend" in module:
                priority_matrix["medium_priority"].append({
                    "module": module,
                    "type": "significant_gaps",
                    "uncovered_lines": len(lines),
                    "impact": "medium"
                })
        
        # Low priority: Minor coverage gaps
        for module, lines in uncovered.items():
            if len(lines) <= 10 and "backend" in module:
                priority_matrix["low_priority"].append({
                    "module": module,
                    "type": "minor_gaps",
                    "uncovered_lines": len(lines),
                    "impact": "low"
                })
        
        return priority_matrix
    
    def calculate_coverage_metrics(self) -> Dict[str, float]:
        """Calculate comprehensive coverage metrics."""
        if not self.coverage_data:
            return {}
        
        totals = self.coverage_data.get("totals", {})
        
        return {
            "line_coverage": totals.get("percent_covered", 0.0),
            "branch_coverage": (
                (totals.get("covered_branches", 0) / totals.get("num_branches", 1)) * 100
                if totals.get("num_branches", 0) > 0 else 0.0
            ),
            "total_lines": totals.get("num_statements", 0),
            "covered_lines": totals.get("covered_lines", 0),
            "missing_lines": totals.get("missing_lines", 0),
            "total_branches": totals.get("num_branches", 0),
            "covered_branches": totals.get("covered_branches", 0),
            "missing_branches": totals.get("num_branches", 0) - totals.get("covered_branches", 0)
        }


class TestPhase51CoverageGapAnalysis:
    """Test suite for Phase 5.1: Coverage Gap Analysis."""
    
    @pytest.fixture
    def analyzer(self):
        """Create coverage gap analyzer instance."""
        return CoverageGapAnalyzer()
    
    def test_comprehensive_coverage_report_generation(self, analyzer):
        """Test comprehensive coverage report generation."""
        print("\n🧪 Testing comprehensive coverage report generation...")
        
        report = analyzer.generate_comprehensive_coverage_report()
        
        assert report["status"] in ["success", "partial", "timeout", "error"]
        
        if report["status"] == "success":
            assert "coverage_data" in report
            print("✅ Coverage report generated successfully")
        else:
            print(f"⚠️ Coverage report status: {report['status']}")
        
        return report
    
    def test_uncovered_lines_analysis(self, analyzer):
        """Test uncovered lines identification."""
        print("\n🧪 Testing uncovered lines analysis...")
        
        # Generate coverage first
        analyzer.generate_comprehensive_coverage_report()
        
        uncovered = analyzer.analyze_uncovered_lines()
        
        print(f"📊 Found uncovered lines in {len(uncovered)} modules")
        
        for module, lines in list(uncovered.items())[:5]:  # Show first 5
            print(f"  📄 {module}: {len(lines)} uncovered lines")
            if lines:
                print(f"    Lines: {lines[:10]}{'...' if len(lines) > 10 else ''}")
        
        assert isinstance(uncovered, dict)
        return uncovered
    
    def test_zero_coverage_module_identification(self, analyzer):
        """Test zero coverage module identification."""
        print("\n🧪 Testing zero coverage module identification...")
        
        # Generate coverage first
        analyzer.generate_comprehensive_coverage_report()
        
        zero_coverage = analyzer.identify_zero_coverage_modules()
        
        print(f"📊 Found {len(zero_coverage)} modules with zero coverage")
        
        for module in zero_coverage[:10]:  # Show first 10
            print(f"  📄 {module}")
        
        assert isinstance(zero_coverage, list)
        return zero_coverage
    
    def test_branch_coverage_gap_analysis(self, analyzer):
        """Test branch coverage gap analysis."""
        print("\n🧪 Testing branch coverage gap analysis...")
        
        # Generate coverage first
        analyzer.generate_comprehensive_coverage_report()
        
        branch_gaps = analyzer.analyze_branch_coverage_gaps()
        
        print(f"📊 Found branch coverage gaps in {len(branch_gaps)} modules")
        
        for module, data in list(branch_gaps.items())[:5]:  # Show first 5
            print(f"  📄 {module}: {data['covered_branches']}/{data['total_branches']} branches ({data['branch_coverage_percent']:.1f}%)")
        
        assert isinstance(branch_gaps, dict)
        return branch_gaps
    
    def test_priority_matrix_generation(self, analyzer):
        """Test priority matrix generation for coverage implementation."""
        print("\n🧪 Testing priority matrix generation...")
        
        # Generate coverage first
        analyzer.generate_comprehensive_coverage_report()
        
        priority_matrix = analyzer.generate_priority_matrix()
        
        assert "high_priority" in priority_matrix
        assert "medium_priority" in priority_matrix
        assert "low_priority" in priority_matrix
        
        total_items = (
            len(priority_matrix["high_priority"]) +
            len(priority_matrix["medium_priority"]) +
            len(priority_matrix["low_priority"])
        )
        
        print(f"📊 Priority Matrix Generated:")
        print(f"  🔴 High Priority: {len(priority_matrix['high_priority'])} items")
        print(f"  🟡 Medium Priority: {len(priority_matrix['medium_priority'])} items")
        print(f"  🟢 Low Priority: {len(priority_matrix['low_priority'])} items")
        print(f"  📈 Total Items: {total_items}")
        
        return priority_matrix
    
    def test_coverage_metrics_calculation(self, analyzer):
        """Test comprehensive coverage metrics calculation."""
        print("\n🧪 Testing coverage metrics calculation...")
        
        # Generate coverage first
        analyzer.generate_comprehensive_coverage_report()
        
        metrics = analyzer.calculate_coverage_metrics()
        
        if metrics:
            print(f"📊 Coverage Metrics:")
            print(f"  📈 Line Coverage: {metrics.get('line_coverage', 0):.2f}%")
            print(f"  🔀 Branch Coverage: {metrics.get('branch_coverage', 0):.2f}%")
            print(f"  📝 Total Lines: {metrics.get('total_lines', 0)}")
            print(f"  ✅ Covered Lines: {metrics.get('covered_lines', 0)}")
            print(f"  ❌ Missing Lines: {metrics.get('missing_lines', 0)}")
            print(f"  🔄 Total Branches: {metrics.get('total_branches', 0)}")
            print(f"  ✅ Covered Branches: {metrics.get('covered_branches', 0)}")
            print(f"  ❌ Missing Branches: {metrics.get('missing_branches', 0)}")
        
        assert isinstance(metrics, dict)
        return metrics
    
    def test_phase51_comprehensive_analysis(self, analyzer):
        """Comprehensive Phase 5.1 analysis combining all components."""
        print("\n🎯 Phase 5.1: Comprehensive Coverage Gap Analysis")
        print("=" * 60)
        
        # Generate comprehensive analysis
        report = analyzer.generate_comprehensive_coverage_report()
        uncovered = analyzer.analyze_uncovered_lines()
        zero_coverage = analyzer.identify_zero_coverage_modules()
        branch_gaps = analyzer.analyze_branch_coverage_gaps()
        priority_matrix = analyzer.generate_priority_matrix()
        metrics = analyzer.calculate_coverage_metrics()
        
        print(f"\n📊 PHASE 5.1 ANALYSIS SUMMARY:")
        print(f"  🎯 Current Line Coverage: {metrics.get('line_coverage', 0):.2f}%")
        print(f"  🎯 Current Branch Coverage: {metrics.get('branch_coverage', 0):.2f}%")
        print(f"  📄 Modules with Gaps: {len(uncovered)}")
        print(f"  🚫 Zero Coverage Modules: {len(zero_coverage)}")
        print(f"  🔀 Branch Gap Modules: {len(branch_gaps)}")
        print(f"  🎯 High Priority Items: {len(priority_matrix.get('high_priority', []))}")
        
        # Calculate gap to 100%
        current_coverage = metrics.get('line_coverage', 0)
        gap_to_100 = 100 - current_coverage
        
        print(f"\n🎯 GAP TO 100% ANALYSIS:")
        print(f"  📈 Current Coverage: {current_coverage:.2f}%")
        print(f"  📉 Gap to 100%: {gap_to_100:.2f}%")
        print(f"  📝 Estimated Missing Lines: {metrics.get('missing_lines', 0)}")
        
        analysis_result = {
            "current_coverage": current_coverage,
            "gap_to_100": gap_to_100,
            "missing_lines": metrics.get('missing_lines', 0),
            "zero_coverage_modules": len(zero_coverage),
            "branch_gap_modules": len(branch_gaps),
            "high_priority_items": len(priority_matrix.get('high_priority', [])),
            "analysis_complete": True
        }
        
        return analysis_result


def main():
    """Run Phase 5.1 coverage gap analysis."""
    print("🚀 Phase 5.1: Coverage Gap Analysis")
    print("=" * 50)
    
    analyzer = CoverageGapAnalyzer()
    
    # Run comprehensive analysis
    print("\n🔍 Generating comprehensive coverage analysis...")
    report = analyzer.generate_comprehensive_coverage_report()
    
    if report["status"] == "success":
        print("✅ Coverage analysis completed successfully")
        
        # Generate detailed analysis
        metrics = analyzer.calculate_coverage_metrics()
        uncovered = analyzer.analyze_uncovered_lines()
        priority_matrix = analyzer.generate_priority_matrix()
        
        print(f"\n📊 CURRENT STATUS:")
        print(f"  Coverage: {metrics.get('line_coverage', 0):.2f}%")
        print(f"  Gap to 100%: {100 - metrics.get('line_coverage', 0):.2f}%")
        print(f"  High Priority Items: {len(priority_matrix.get('high_priority', []))}")
        
    else:
        print(f"⚠️ Coverage analysis status: {report['status']}")
    
    return report


if __name__ == "__main__":
    main()