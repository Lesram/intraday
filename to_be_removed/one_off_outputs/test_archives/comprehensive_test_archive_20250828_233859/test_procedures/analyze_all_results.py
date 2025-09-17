#!/usr/bin/env python3
"""
COMPREHENSIVE TEST RESULTS ANALYZER
Combines all batch test results into a single comprehensive report
"""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

platform_root = Path(r"C:\Users\Marsel\intra\algotrading_platform")
os.chdir(platform_root)

print("🎯 COMPREHENSIVE TEST RESULTS ANALYSIS")
print("=" * 60)

# Find all XML result files
xml_files = list(Path('.').glob('*.xml'))
batch_files = [f for f in xml_files if f.name.startswith('batch_') and f.name.endswith('_results.xml')]

print(f"📊 Found {len(batch_files)} batch result files")
print(f"📁 Total XML files in directory: {len(xml_files)}")

# Analyze all batch results
total_tests = 0
total_failures = 0
total_errors = 0
total_skipped = 0
total_passed = 0

batch_summary = []

for batch_file in sorted(batch_files, key=lambda x: int(re.findall(r'\d+', x.name)[0]) if re.findall(r'\d+', x.name) else 0):
    try:
        tree = ET.parse(batch_file)
        root = tree.getroot()
        
        for testsuite in root.findall('testsuite'):
            tests = int(testsuite.get('tests', 0))
            failures = int(testsuite.get('failures', 0))
            errors = int(testsuite.get('errors', 0))
            skipped = int(testsuite.get('skipped', 0))
            passed = tests - failures - errors - skipped
            
            total_tests += tests
            total_failures += failures
            total_errors += errors
            total_skipped += skipped
            total_passed += passed
            
            batch_summary.append({
                'file': batch_file.name,
                'tests': tests,
                'passed': passed,
                'failures': failures,
                'errors': errors,
                'skipped': skipped
            })
            
    except Exception as e:
        print(f"⚠️  Error parsing {batch_file}: {e}")

print("\n📈 COMPREHENSIVE TEST SUMMARY:")
print("=" * 60)
print(f"🎯 TOTAL TESTS EXECUTED: {total_tests}")
print(f"✅ PASSED: {total_passed} ({(total_passed/total_tests*100):.1f}%)")
print(f"❌ FAILED: {total_failures} ({(total_failures/total_tests*100):.1f}%)")
print(f"💥 ERRORS: {total_errors} ({(total_errors/total_tests*100):.1f}%)")
print(f"⏭️  SKIPPED: {total_skipped} ({(total_skipped/total_tests*100):.1f}%)")

print(f"\n🎉 SUCCESS RATE: {(total_passed/total_tests*100):.1f}%")
print(f"📊 COMPLETION RATE: {(total_tests/3907*100):.1f}% of target 3,907 tests")

# Show top failing batches
print(f"\n🔥 TOP 10 BATCHES WITH MOST FAILURES:")
failing_batches = sorted([b for b in batch_summary if b['failures'] > 0], 
                        key=lambda x: x['failures'], reverse=True)[:10]

for batch in failing_batches:
    print(f"  {batch['file']}: {batch['failures']} failures out of {batch['tests']} tests")

print(f"\n✅ EXECUTION COMPLETE - {total_tests} tests analyzed from {len(batch_files)} batch files")
