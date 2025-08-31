#!/usr/bin/env python3
"""
Parse batch XML results to get exact test pass rate metrics.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import sys

def parse_xml_results():
    """Parse all XML result files to get exact test metrics"""
    
    xml_files = list(Path('.').glob('batch_*_results.xml'))
    
    if not xml_files:
        print("❌ No XML result files found")
        return None
    
    print(f"📁 Parsing {len(xml_files)} XML result files...")
    
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    
    datetime_errors = 0
    assertion_errors = 0
    import_errors = 0
    other_errors = 0
    
    parsed_files = 0
    
    for xml_file in sorted(xml_files):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Handle both testsuite and testsuites root elements
            testsuites = root.findall('testsuite') if root.tag == 'testsuites' else [root]
            
            for testsuite in testsuites:
                # Get testsuite stats
                tests = int(testsuite.get('tests', 0))
                failures = int(testsuite.get('failures', 0))
                errors = int(testsuite.get('errors', 0))
                skipped = int(testsuite.get('skipped', 0))
                passed = tests - failures - errors - skipped
                
                total_tests += tests
                total_passed += passed
                total_failed += failures
                total_errors += errors
                total_skipped += skipped
                
                # Analyze error types
                for testcase in testsuite.findall('.//testcase'):
                    failure = testcase.find('failure')
                    error = testcase.find('error')
                    
                    if failure is not None:
                        message = (failure.get('message', '') + ' ' + (failure.text or '')).lower()
                        if 'datetime' in message and 'utcnow' in message:
                            datetime_errors += 1
                        elif 'assertion' in message:
                            assertion_errors += 1
                        elif 'import' in message:
                            import_errors += 1
                        else:
                            other_errors += 1
                            
                    if error is not None:
                        message = (error.get('message', '') + ' ' + (error.text or '')).lower()
                        if 'datetime' in message and 'utcnow' in message:
                            datetime_errors += 1
                        elif 'assertion' in message:
                            assertion_errors += 1
                        elif 'import' in message:
                            import_errors += 1
                        else:
                            other_errors += 1
            
            parsed_files += 1
            
        except Exception as e:
            print(f"⚠️  Could not parse {xml_file}: {e}")
            continue
    
    print(f"✅ Successfully parsed {parsed_files}/{len(xml_files)} XML files")
    
    return {
        'total_tests': total_tests,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'total_errors': total_errors,
        'total_skipped': total_skipped,
        'datetime_errors': datetime_errors,
        'assertion_errors': assertion_errors,
        'import_errors': import_errors,
        'other_errors': other_errors,
        'files_analyzed': parsed_files
    }

def main():
    """Main analysis"""
    print("🔍 EXACT TEST PASS RATE ANALYSIS")
    print("=" * 60)
    
    results = parse_xml_results()
    
    if not results:
        print("❌ No results to analyze")
        return 1
    
    total = results['total_tests']
    passed = results['total_passed']
    failed = results['total_failed']
    errors = results['total_errors']
    skipped = results['total_skipped']
    
    if total == 0:
        print("❌ No tests found in XML files")
        return 1
    
    pass_rate = (passed / total) * 100
    
    print(f"📊 CURRENT TEST METRICS:")
    print(f"   • Total Tests: {total:,}")
    print(f"   • Passed: {passed:,}")
    print(f"   • Failed: {failed:,}")
    print(f"   • Errors: {errors:,}")
    print(f"   • Skipped: {skipped:,}")
    print(f"   • Pass Rate: {pass_rate:.1f}%")
    print(f"   • Files Analyzed: {results['files_analyzed']}")
    
    print(f"\n📈 BASELINE COMPARISON:")
    baseline_total = 3065
    baseline_passed = 2526
    baseline_rate = 82.4
    
    print(f"   • Baseline: {baseline_passed:,}/{baseline_total:,} ({baseline_rate}%)")
    print(f"   • Current:  {passed:,}/{total:,} ({pass_rate:.1f}%)")
    
    if pass_rate > baseline_rate:
        improvement = pass_rate - baseline_rate
        print(f"   • ✅ IMPROVEMENT: +{improvement:.1f} percentage points")
    else:
        decline = baseline_rate - pass_rate
        print(f"   • 📉 Change: -{decline:.1f} percentage points")
    
    print(f"\n🔍 ERROR PATTERN ANALYSIS:")
    print(f"   • Datetime errors: {results['datetime_errors']}")
    print(f"   • Assertion errors: {results['assertion_errors']}")
    print(f"   • Import errors: {results['import_errors']}")
    print(f"   • Other errors: {results['other_errors']}")
    
    if results['datetime_errors'] == 0:
        print(f"   • ✅ SUCCESS: No datetime.utcnow() errors found!")
    else:
        print(f"   • ⚠️  Still {results['datetime_errors']} datetime errors remaining")
    
    print(f"\n🎯 NEXT PRIORITY:")
    if results['assertion_errors'] > results['import_errors']:
        print(f"   • Focus on AssertionError fixes ({results['assertion_errors']} instances)")
    elif results['import_errors'] > 0:
        print(f"   • Focus on ImportError fixes ({results['import_errors']} instances)")
    else:
        print(f"   • Focus on other error patterns ({results['other_errors']} instances)")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
