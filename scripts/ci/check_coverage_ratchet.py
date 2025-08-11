#!/usr/bin/env python3
"""
Coverage ratchet script for CI - ensures coverage never decreases vs baseline.
Used in GitHub Actions to fail PRs if coverage drops below main branch.

Usage:
    python check_coverage_ratchet.py --current coverage.xml --baseline baseline-coverage.xml
    python check_coverage_ratchet.py --current coverage.xml --min-coverage 30.0
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple


def extract_coverage_from_xml(xml_path: Path) -> Optional[float]:
    """Extract line coverage percentage from coverage.xml file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Find coverage element with line-rate attribute
        coverage_elem = root.find('.//coverage')
        if coverage_elem is not None and 'line-rate' in coverage_elem.attrib:
            line_rate = float(coverage_elem.attrib['line-rate'])
            return line_rate * 100  # Convert to percentage
        
        # Alternative: look for overall coverage in different format
        for elem in root.iter():
            if 'line-rate' in elem.attrib:
                line_rate = float(elem.attrib['line-rate'])
                return line_rate * 100
                
        print(f"⚠️  Could not find line-rate in {xml_path}")
        return None
        
    except ET.ParseError as e:
        print(f"❌ Failed to parse XML file {xml_path}: {e}")
        return None
    except FileNotFoundError:
        print(f"❌ Coverage file not found: {xml_path}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error reading {xml_path}: {e}")
        return None


def get_coverage_details_from_xml(xml_path: Path) -> Tuple[Optional[float], dict]:
    """Extract detailed coverage metrics from coverage.xml."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Overall coverage
        coverage_elem = root.find('.//coverage')
        overall_coverage = None
        
        if coverage_elem is not None and 'line-rate' in coverage_elem.attrib:
            overall_coverage = float(coverage_elem.attrib['line-rate']) * 100
        
        # Per-package coverage
        package_coverage = {}
        for package in root.findall('.//package'):
            name = package.get('name', 'unknown')
            line_rate = package.get('line-rate')
            if line_rate:
                package_coverage[name] = float(line_rate) * 100
        
        details = {
            'packages': package_coverage,
            'total_lines': coverage_elem.get('lines-valid') if coverage_elem else None,
            'covered_lines': coverage_elem.get('lines-covered') if coverage_elem else None,
        }
        
        return overall_coverage, details
        
    except Exception as e:
        print(f"❌ Error extracting coverage details: {e}")
        return None, {}


def compare_coverage(current: float, baseline: float, tolerance: float = 0.1) -> bool:
    """
    Compare current coverage to baseline with tolerance.
    Returns True if coverage is acceptable (within tolerance or higher).
    """
    if current >= baseline:
        return True
    
    # Allow small decrease within tolerance
    decrease = baseline - current
    return decrease <= tolerance


def format_coverage_change(current: float, baseline: float) -> str:
    """Format coverage change for display."""
    diff = current - baseline
    if diff >= 0:
        return f"+{diff:.2f}%"
    else:
        return f"{diff:.2f}%"


def main():
    parser = argparse.ArgumentParser(description='Coverage ratchet checker for CI')
    parser.add_argument('--current', type=Path, required=True,
                       help='Path to current coverage.xml file')
    parser.add_argument('--baseline', type=Path, 
                       help='Path to baseline coverage.xml file (from main branch)')
    parser.add_argument('--min-coverage', type=float,
                       help='Minimum acceptable coverage percentage')
    parser.add_argument('--tolerance', type=float, default=0.5,
                       help='Tolerance for coverage decrease (default: 0.5%)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed coverage breakdown')
    
    args = parser.parse_args()
    
    # Extract current coverage
    current_coverage = extract_coverage_from_xml(args.current)
    if current_coverage is None:
        print("❌ Failed to extract current coverage")
        sys.exit(1)
    
    print(f"📊 Current coverage: {current_coverage:.2f}%")
    
    # Check minimum coverage threshold
    if args.min_coverage:
        if current_coverage < args.min_coverage:
            print(f"❌ Coverage {current_coverage:.2f}% is below minimum threshold {args.min_coverage}%")
            sys.exit(1)
        else:
            print(f"✅ Coverage meets minimum threshold ({args.min_coverage}%)")
    
    # Compare with baseline if provided
    if args.baseline:
        if not args.baseline.exists():
            print(f"⚠️  Baseline file not found: {args.baseline}")
            print("🔍 This might be a new branch - treating as acceptable")
            sys.exit(0)
        
        baseline_coverage = extract_coverage_from_xml(args.baseline)
        if baseline_coverage is None:
            print("⚠️  Could not extract baseline coverage - skipping comparison")
            sys.exit(0)
        
        print(f"📈 Baseline coverage: {baseline_coverage:.2f}%")
        print(f"📈 Coverage change: {format_coverage_change(current_coverage, baseline_coverage)}")
        
        if not compare_coverage(current_coverage, baseline_coverage, args.tolerance):
            decrease = baseline_coverage - current_coverage
            print(f"❌ Coverage decreased by {decrease:.2f}% (tolerance: {args.tolerance}%)")
            print("💡 Please add tests to maintain or improve coverage")
            sys.exit(1)
        else:
            if current_coverage > baseline_coverage:
                print("🎉 Coverage improved!")
            else:
                print("✅ Coverage maintained within tolerance")
    
    # Show detailed breakdown if requested
    if args.verbose:
        print("\n📋 Coverage Details:")
        coverage, details = get_coverage_details_from_xml(args.current)
        
        if details.get('packages'):
            print("  Per-package coverage:")
            for package, pkg_coverage in sorted(details['packages'].items()):
                print(f"    {package}: {pkg_coverage:.2f}%")
        
        if details.get('total_lines'):
            covered = details.get('covered_lines', '?')
            total = details['total_lines']
            print(f"  Lines covered: {covered}/{total}")
    
    print("✅ Coverage check passed!")


if __name__ == '__main__':
    main()
