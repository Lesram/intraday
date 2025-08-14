#!/usr/bin/env python3
"""
Enhanced Coverage Checker for Intraday Trading Platform
Validates per-package coverage floors with gradual gate raising.
"""

import sys
import argparse
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET


class CoverageChecker:
    """Enhanced coverage validation with per-package floors."""
    
    # Per-package minimum coverage requirements
    PACKAGE_FLOORS = {
        "backend/risk": 85,          # Risk management - critical
        "backend/services": 85,      # Core services - critical  
        "backend/api": 75,          # API endpoints - high importance
        "backend/strategies": 80,    # Trading strategies - high importance
        "backend/infra": 60,        # Infrastructure - moderate
        "backend/models": 70,       # Data models - moderate-high
        "backend/utils": 50,        # Utilities - moderate
    }
    
    def __init__(self, soft_mode: bool = False):
        self.soft_mode = soft_mode
        self.violations = []
        self.warnings = []
    
    def parse_coverage_xml(self, xml_path: str) -> Dict[str, float]:
        """Parse coverage.xml file to extract per-package coverage."""
        if not Path(xml_path).exists():
            raise FileNotFoundError(f"Coverage XML file not found: {xml_path}")
        
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        package_coverage = {}
        
        # Parse packages from coverage XML
        for package in root.findall(".//package"):
            package_name = package.get("name", "").replace(".", "/")
            
            # Calculate coverage percentage
            line_rate = float(package.get("line-rate", 0))
            branch_rate = float(package.get("branch-rate", 0))
            
            # Weighted average: 70% lines, 30% branches
            coverage_pct = (line_rate * 0.7 + branch_rate * 0.3) * 100
            package_coverage[package_name] = coverage_pct
        
        return package_coverage
    
    def check_package_floors(self, package_coverage: Dict[str, float]) -> bool:
        """Check if packages meet minimum coverage floors."""
        all_passed = True
        
        for package, min_coverage in self.PACKAGE_FLOORS.items():
            actual_coverage = package_coverage.get(package, 0.0)
            
            if actual_coverage < min_coverage:
                message = f"{package}: {actual_coverage:.1f}% < {min_coverage}% (required)"
                
                if self.soft_mode:
                    self.warnings.append(message)
                    print(f"⚠️  WARNING: {message}")
                else:
                    self.violations.append(message)
                    print(f"❌ {message}")
                    all_passed = False
            else:
                print(f"✅ {package}: {actual_coverage:.1f}% ≥ {min_coverage}% (required)")
        
        return all_passed
    
    def generate_report(self) -> str:
        """Generate a coverage report summary."""
        report_lines = [
            "📊 Coverage Floor Check Results",
            "=" * 40,
        ]
        
        if self.violations:
            report_lines.extend([
                f"❌ FAILURES ({len(self.violations)}):",
                *[f"   {violation}" for violation in self.violations],
                ""
            ])
        
        if self.warnings:
            report_lines.extend([
                f"⚠️  WARNINGS ({len(self.warnings)}):",
                *[f"   {warning}" for warning in self.warnings],
                ""
            ])
        
        if not self.violations and not self.warnings:
            report_lines.append("🎉 All packages meet coverage requirements!")
        
        return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="Check coverage floors for critical packages")
    parser.add_argument("--soft", action="store_true", 
                       help="Emit warnings locally without failing the run")
    parser.add_argument("--coverage-file", default="coverage.xml",
                       help="Path to coverage.xml file")
    
    args = parser.parse_args()
    
    try:
        checker = CoverageChecker(soft_mode=args.soft)
        
        # Parse coverage results if XML file exists
        if Path(args.coverage_file).exists():
            print("🔍 Checking per-package coverage requirements...")
            package_coverage = checker.parse_coverage_xml(args.coverage_file)
        else:
            print("🔍 Running coverage analysis...")
            # Run coverage analysis
            subprocess.run([
                "python", "-m", "pytest", 
                "--cov=backend", 
                "--cov-branch",
                f"--cov-report=xml:{args.coverage_file}",
                "--cov-report=term-missing:skip-covered",
                "--quiet"
            ], check=True)
            package_coverage = checker.parse_coverage_xml(args.coverage_file)
        
        # Check package floors
        floors_passed = checker.check_package_floors(package_coverage)
        
        # Generate and display report
        print(f"\n{checker.generate_report()}")
        
        if not floors_passed and not args.soft:
            print("\n💥 Coverage check FAILED! Some packages are below required minimums.")
            return 1
        
        print("\n✅ Coverage check PASSED!")
        return 0
        
    except Exception as e:
        print(f"❌ Coverage check failed with error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
