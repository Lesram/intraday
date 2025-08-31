#!/usr/bin/env python3
"""
UNIFIED DAILY TEST EXECUTION & PROGRESS TRACKER
Consolidates all testing approaches into single daily execution script
Tracks progress toward 100% coverage and pass rate goals
"""

import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import json
import sys

class UnifiedTestTracker:
    """Consolidated test execution and progress tracking"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.results = {
            'timestamp': self.start_time.isoformat(),
            'pass_rate': 0.0,
            'coverage': 0.0,
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'error_tests': 0,
            'skipped_tests': 0,
            'error_patterns': {},
            'coverage_gaps': [],
            'daily_targets': self._get_daily_targets()
        }
        
    def _get_daily_targets(self):
        """Calculate daily targets based on 10-week roadmap"""
        # Week 1: 83% → 90% pass rate
        # Week 10: 100% coverage, 100% pass rate
        base_pass_rate = 83.0
        base_coverage = 48.0
        
        return {
            'pass_rate_target': min(100.0, base_pass_rate + 2.0),  # +2% per week initially
            'coverage_target': min(100.0, base_coverage + 7.0),    # +7% per week initially
            'max_failures': 20,  # Down from current ~540 total failures
            'max_skipped': 0     # Zero skipped tests goal
        }
    
    def run_comprehensive_tests(self):
        """Execute comprehensive test suite with all metrics"""
        print("🚀 UNIFIED DAILY TEST EXECUTION")
        print("=" * 60)
        print(f"📅 Date: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Targets: {self.results['daily_targets']['pass_rate_target']:.1f}% pass rate, {self.results['daily_targets']['coverage_target']:.1f}% coverage")
        print()
        
        # Step 1: Run tests with XML output
        print("📊 Step 1: Comprehensive Test Execution...")
        xml_file = f"daily_test_results_{self.start_time.strftime('%Y%m%d_%H%M%S')}.xml"
        
        test_cmd = [
            'python', '-m', 'pytest', 'tests/', 
            '--tb=short',
            '--junit-xml', xml_file,
            '-v'
        ]
        
        try:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=600)
            self._parse_test_results(xml_file, result)
        except subprocess.TimeoutExpired:
            print("⚠️  Test execution timed out after 10 minutes")
            return False
        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            return False
            
        # Step 2: Generate coverage report
        print("\n📈 Step 2: Coverage Analysis...")
        self._generate_coverage_report()
        
        # Step 3: Analyze results
        print("\n🔍 Step 3: Results Analysis...")
        self._analyze_results()
        
        # Step 4: Generate recommendations
        print("\n🎯 Step 4: Next Actions...")
        self._generate_recommendations()
        
        # Step 5: Save progress
        self._save_daily_progress()
        
        return True
    
    def _parse_test_results(self, xml_file, result):
        """Parse XML test results for detailed metrics"""
        if not Path(xml_file).exists():
            print(f"⚠️  XML file not found: {xml_file}")
            return
            
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Handle both testsuite and testsuites root elements
            testsuites = root.findall('testsuite') if root.tag == 'testsuites' else [root]
            
            for testsuite in testsuites:
                tests = int(testsuite.get('tests', 0))
                failures = int(testsuite.get('failures', 0))
                errors = int(testsuite.get('errors', 0))
                skipped = int(testsuite.get('skipped', 0))
                passed = tests - failures - errors - skipped
                
                self.results['total_tests'] += tests
                self.results['passed_tests'] += passed
                self.results['failed_tests'] += failures
                self.results['error_tests'] += errors
                self.results['skipped_tests'] += skipped
                
                # Analyze error patterns
                self._analyze_error_patterns(testsuite)
                
        except Exception as e:
            print(f"⚠️  Could not parse XML results: {e}")
            
        # Calculate pass rate
        if self.results['total_tests'] > 0:
            self.results['pass_rate'] = (self.results['passed_tests'] / self.results['total_tests']) * 100
    
    def _analyze_error_patterns(self, testsuite):
        """Analyze error patterns from test results"""
        for testcase in testsuite.findall('.//testcase'):
            failure = testcase.find('failure')
            error = testcase.find('error')
            
            if failure is not None:
                message = (failure.get('message', '') + ' ' + (failure.text or '')).lower()
                self._categorize_error(message)
                
            if error is not None:
                message = (error.get('message', '') + ' ' + (error.text or '')).lower()
                self._categorize_error(message)
    
    def _categorize_error(self, message):
        """Categorize error messages into patterns"""
        if 'assertion' in message:
            self.results['error_patterns']['AssertionError'] = self.results['error_patterns'].get('AssertionError', 0) + 1
        elif 'import' in message:
            self.results['error_patterns']['ImportError'] = self.results['error_patterns'].get('ImportError', 0) + 1
        elif 'datetime' in message and 'utcnow' in message:
            self.results['error_patterns']['DateTimeError'] = self.results['error_patterns'].get('DateTimeError', 0) + 1
        elif 'mock' in message:
            self.results['error_patterns']['MockError'] = self.results['error_patterns'].get('MockError', 0) + 1
        elif 'timeout' in message:
            self.results['error_patterns']['TimeoutError'] = self.results['error_patterns'].get('TimeoutError', 0) + 1
        else:
            self.results['error_patterns']['Other'] = self.results['error_patterns'].get('Other', 0) + 1
    
    def _generate_coverage_report(self):
        """Generate and parse coverage report"""
        try:
            # Generate coverage report
            coverage_cmd = [
                'python', '-m', 'pytest', 'tests/',
                '--cov=backend',
                '--cov-report=json:coverage.json',
                '--cov-report=term-missing',
                '--tb=no',
                '-q'
            ]
            
            result = subprocess.run(coverage_cmd, capture_output=True, text=True, timeout=300)
            
            # Parse coverage JSON if available
            if Path('coverage.json').exists():
                with open('coverage.json', 'r') as f:
                    coverage_data = json.load(f)
                    self.results['coverage'] = coverage_data.get('totals', {}).get('percent_covered', 0)
                    
                    # Identify coverage gaps
                    for filename, file_data in coverage_data.get('files', {}).items():
                        if file_data.get('summary', {}).get('percent_covered', 100) < 90:
                            self.results['coverage_gaps'].append({
                                'file': filename,
                                'coverage': file_data.get('summary', {}).get('percent_covered', 0),
                                'missing_lines': len(file_data.get('missing_lines', []))
                            })
            
        except Exception as e:
            print(f"⚠️  Coverage generation failed: {e}")
    
    def _analyze_results(self):
        """Analyze and display current results"""
        print(f"📊 CURRENT METRICS:")
        print(f"   • Total Tests: {self.results['total_tests']:,}")
        print(f"   • Passed: {self.results['passed_tests']:,}")
        print(f"   • Failed: {self.results['failed_tests']:,}")
        print(f"   • Errors: {self.results['error_tests']:,}")
        print(f"   • Skipped: {self.results['skipped_tests']:,}")
        print(f"   • Pass Rate: {self.results['pass_rate']:.1f}%")
        print(f"   • Coverage: {self.results['coverage']:.1f}%")
        
        print(f"\n📈 TARGET COMPARISON:")
        targets = self.results['daily_targets']
        pass_status = "✅" if self.results['pass_rate'] >= targets['pass_rate_target'] else "❌"
        coverage_status = "✅" if self.results['coverage'] >= targets['coverage_target'] else "❌"
        
        print(f"   • Pass Rate: {self.results['pass_rate']:.1f}% / {targets['pass_rate_target']:.1f}% {pass_status}")
        print(f"   • Coverage: {self.results['coverage']:.1f}% / {targets['coverage_target']:.1f}% {coverage_status}")
        
        if self.results['error_patterns']:
            print(f"\n🔍 ERROR PATTERNS:")
            for pattern, count in sorted(self.results['error_patterns'].items(), key=lambda x: x[1], reverse=True):
                print(f"   • {pattern}: {count} instances")
    
    def _generate_recommendations(self):
        """Generate specific next actions based on results"""
        recommendations = []
        
        # Pass rate recommendations
        if self.results['pass_rate'] < self.results['daily_targets']['pass_rate_target']:
            top_error = max(self.results['error_patterns'].items(), key=lambda x: x[1]) if self.results['error_patterns'] else None
            if top_error:
                recommendations.append(f"🎯 Focus on {top_error[0]} fixes ({top_error[1]} instances)")
        
        # Coverage recommendations  
        if self.results['coverage'] < self.results['daily_targets']['coverage_target']:
            if self.results['coverage_gaps']:
                top_gaps = sorted(self.results['coverage_gaps'], key=lambda x: x['coverage'])[:3]
                for gap in top_gaps:
                    recommendations.append(f"📈 Improve coverage in {Path(gap['file']).name} ({gap['coverage']:.1f}%)")
        
        # Skipped test recommendations
        if self.results['skipped_tests'] > 0:
            recommendations.append(f"🔧 Resolve {self.results['skipped_tests']} skipped tests")
        
        # General recommendations
        if not recommendations:
            recommendations.append("🏆 Targets met! Focus on edge cases and error path testing")
        
        print("PRIORITY ACTIONS:")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"   {i}. {rec}")
    
    def _save_daily_progress(self):
        """Save daily progress to tracking file"""
        progress_file = "daily_progress_tracking.json"
        
        # Load existing progress
        progress_history = []
        if Path(progress_file).exists():
            try:
                with open(progress_file, 'r') as f:
                    progress_history = json.load(f)
            except:
                progress_history = []
        
        # Add today's results
        progress_history.append(self.results)
        
        # Save updated progress
        with open(progress_file, 'w') as f:
            json.dump(progress_history, f, indent=2)
        
        print(f"\n💾 Progress saved to {progress_file}")
        
        # Generate trend analysis if we have history
        if len(progress_history) > 1:
            self._analyze_trends(progress_history)
    
    def _analyze_trends(self, history):
        """Analyze trends over time"""
        if len(history) < 2:
            return
            
        prev = history[-2]
        curr = history[-1]
        
        pass_rate_change = curr['pass_rate'] - prev['pass_rate']
        coverage_change = curr['coverage'] - prev['coverage']
        
        print(f"\n📈 TREND ANALYSIS:")
        print(f"   • Pass Rate Change: {pass_rate_change:+.1f} percentage points")
        print(f"   • Coverage Change: {coverage_change:+.1f} percentage points")
        
        if pass_rate_change >= 0 and coverage_change >= 0:
            print("   • ✅ Positive trajectory - continue current approach")
        else:
            print("   • ⚠️  Regression detected - review recent changes")

def main():
    """Main execution function"""
    print("🎯 UNIFIED MASTER CONSOLIDATION - DAILY TRACKER")
    print("Comprehensive test execution toward 100% coverage and pass rate")
    print()
    
    # Change to platform directory
    if not Path('tests').exists():
        print("❌ No tests directory found. Please run from platform root.")
        return 1
    
    tracker = UnifiedTestTracker()
    
    try:
        success = tracker.run_comprehensive_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
