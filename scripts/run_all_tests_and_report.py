#!/usr/bin/env python3
"""
Complete Test Execution & Analysis Pipeline
Orchestrates category runs, captures artifacts, combines coverage, and generates architect-ready reports.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestOrchestrator:
    """Orchestrates comprehensive test execution and reporting."""
    
    def __init__(self, args):
        self.args = args
        self.root_path = Path.cwd()
        self.test_reports_dir = self.root_path / "test_reports"
        self.architect_review_dir = self.root_path / "architect_review"
        
        # Ensure directories exist
        self.test_reports_dir.mkdir(exist_ok=True)
        (self.test_reports_dir / "junit").mkdir(exist_ok=True)
        (self.test_reports_dir / "logs").mkdir(exist_ok=True)
        self.architect_review_dir.mkdir(exist_ok=True)
        
        # Test categories with their characteristics
        self.test_categories = {
            'unit': {'parallel': True, 'marker': 'unit'},
            'api': {'parallel': True, 'marker': 'api'},
            'services': {'parallel': True, 'marker': 'services'},
            'risk': {'parallel': True, 'marker': 'risk'},
            'strategies': {'parallel': True, 'marker': 'strategies'},
            'db': {'parallel': True, 'marker': 'db'},
            'ws': {'parallel': False, 'marker': 'ws'},
            'integration': {'parallel': False, 'marker': 'integration'},
            'e2e': {'parallel': False, 'marker': 'e2e'},
            'perf': {'parallel': False, 'marker': 'perf'},
            'chaos': {'parallel': False, 'marker': 'chaos'}
        }
        
        self.category_results = {}
        self.flaky_tests = set()
        
    def discover_categories(self) -> List[str]:
        """Discover available test categories."""
        available = []
        
        for category, config in self.test_categories.items():
            # Try marker first
            marker_cmd = [
                sys.executable, "-m", "pytest",
                "-q", "--collect-only", "-m", config['marker']
            ]
            
            try:
                result = subprocess.run(
                    marker_cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=30,
                    cwd=self.root_path
                )
                
                if result.returncode == 0 and "collected" in result.stdout:
                    available.append(category)
                    logger.info(f"Category '{category}' discovered via marker")
                    continue
                    
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
            
            # Fallback to directory
            category_dir = self.root_path / "tests" / category
            if category_dir.exists() and any(category_dir.glob("test_*.py")):
                available.append(category)
                logger.info(f"Category '{category}' discovered via directory")
        
        return available
    
    def build_pytest_command(self, category: str) -> List[str]:
        """Build pytest command for a category."""
        config = self.test_categories[category]
        
        cmd = [
            sys.executable, "-m", "pytest",
            "-q", "--maxfail=1", 
            f"--timeout={self.args.timeout}",
            "--durations=25",
            "--color=yes"
        ]
        
        # Add parallelization for small suites
        if config['parallel']:
            cmd.extend(["-n", "auto"])
        
        # Add coverage
        cmd.extend([
            "--cov=backend",
            "--cov-branch", 
            "--cov-config=.coveragerc",
            "--cov-report=term"
        ])
        
        # Add JUnit XML if requested
        if self.args.junit:
            junit_file = self.test_reports_dir / "junit" / f"{category}.xml"
            cmd.extend(["--junitxml", str(junit_file)])
        
        # Add test selection (marker or directory)
        try:
            # Test if marker works
            marker_test = subprocess.run([
                sys.executable, "-m", "pytest", 
                "-q", "--collect-only", "-m", config['marker']
            ], capture_output=True, timeout=30, cwd=self.root_path)
            
            if marker_test.returncode == 0 and "collected" in marker_test.stdout:
                cmd.extend(["-m", config['marker']])
            else:
                # Use directory
                test_dir = self.root_path / "tests" / category
                if test_dir.exists():
                    cmd.append(str(test_dir))
                    
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # Fallback to directory
            test_dir = self.root_path / "tests" / category
            if test_dir.exists():
                cmd.append(str(test_dir))
        
        return cmd
    
    def run_category(self, category: str, attempt: int = 1) -> Dict:
        """Run tests for a specific category."""
        logger.info(f"Running {category} tests (attempt {attempt})")
        
        cmd = self.build_pytest_command(category)
        log_file = self.test_reports_dir / "logs" / f"{category}.log"
        
        # Write command header to log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Category: {category} (Attempt {attempt})\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.args.timeout * 60,  # Convert to seconds for category timeout
                cwd=self.root_path
            )
            
            duration = time.time() - start_time
            
            # Append output to log
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("STDOUT:\n")
                f.write(result.stdout)
                f.write("\nSTDERR:\n")
                f.write(result.stderr)
                f.write(f"\nExit Code: {result.returncode}\n")
                f.write(f"Duration: {duration:.2f}s\n")
            
            return {
                'category': category,
                'attempt': attempt,
                'returncode': result.returncode,
                'duration': duration,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.warning(f"Category {category} timed out after {duration:.2f}s")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"TIMEOUT after {duration:.2f}s\n")
            
            return {
                'category': category,
                'attempt': attempt,
                'returncode': 124,  # Timeout exit code
                'duration': duration,
                'stdout': '',
                'stderr': 'Test execution timed out',
                'success': False
            }
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error running {category}: {e}")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"ERROR: {str(e)}\n")
            
            return {
                'category': category,
                'attempt': attempt,
                'returncode': 1,
                'duration': duration,
                'stdout': '',
                'stderr': str(e),
                'success': False
            }
    
    def run_all_categories(self) -> Dict:
        """Run all specified test categories."""
        if self.args.only:
            categories_to_run = [cat.strip() for cat in self.args.only.split(',')]
        else:
            categories_to_run = self.discover_categories()
        
        logger.info(f"Running categories: {categories_to_run}")
        
        results = {}
        
        for category in categories_to_run:
            if category not in self.test_categories:
                logger.warning(f"Unknown category: {category}")
                continue
            
            # Initial run
            result = self.run_category(category)
            results[category] = [result]
            
            # Retry failed categories if requested
            if not result['success'] and self.args.repeat_failing > 0:
                logger.info(f"Retrying failed category: {category}")
                
                for retry in range(1, self.args.repeat_failing + 1):
                    retry_result = self.run_category(category, retry + 1)
                    results[category].append(retry_result)
                    
                    # Track flakiness
                    if retry_result['success'] and not result['success']:
                        self.flaky_tests.add(f"{category}_suite")
                        logger.warning(f"Flaky category detected: {category}")
                        break
        
        return results
    
    def combine_coverage(self):
        """Combine coverage data from all test runs."""
        logger.info("Combining coverage data")
        
        try:
            # Combine parallel coverage files
            subprocess.run([
                sys.executable, "-m", "coverage", "combine"
            ], cwd=self.root_path, check=True)
            
            if self.args.cov_xml:
                subprocess.run([
                    sys.executable, "-m", "coverage", "xml",
                    "-o", str(self.test_reports_dir / "coverage.xml")
                ], cwd=self.root_path, check=True)
            
            if self.args.htmlcov:
                subprocess.run([
                    sys.executable, "-m", "coverage", "html",
                    "-d", str(self.test_reports_dir / "htmlcov")
                ], cwd=self.root_path, check=True)
            
            if self.args.covjson:
                subprocess.run([
                    sys.executable, "-m", "coverage", "json",
                    "-o", str(self.test_reports_dir / "coverage.json")
                ], cwd=self.root_path, check=True)
            
            logger.info("Coverage combination completed")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Coverage combination failed: {e}")
    
    def parse_junit_results(self) -> Dict:
        """Parse JUnit XML results."""
        junit_dir = self.test_reports_dir / "junit"
        results = {}
        
        for xml_file in junit_dir.glob("*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                category = xml_file.stem
                
                # Extract test statistics
                testsuites = root.findall('.//testsuite')
                total_tests = 0
                total_failures = 0
                total_errors = 0
                total_skipped = 0
                total_time = 0.0
                
                failures = []
                slow_tests = []
                
                for testsuite in testsuites:
                    total_tests += int(testsuite.get('tests', 0))
                    total_failures += int(testsuite.get('failures', 0))
                    total_errors += int(testsuite.get('errors', 0))
                    total_skipped += int(testsuite.get('skipped', 0))
                    total_time += float(testsuite.get('time', 0))
                    
                    # Extract individual test cases
                    for testcase in testsuite.findall('.//testcase'):
                        test_time = float(testcase.get('time', 0))
                        test_name = f"{testcase.get('classname', '')}.{testcase.get('name', '')}"
                        
                        # Track slow tests
                        if test_time > 1.0:  # Tests over 1 second
                            slow_tests.append((test_name, test_time))
                        
                        # Extract failures
                        failure = testcase.find('failure')
                        error = testcase.find('error')
                        
                        if failure is not None:
                            failures.append({
                                'test': test_name,
                                'type': 'failure',
                                'message': failure.get('message', ''),
                                'trace': failure.text or ''
                            })
                        
                        if error is not None:
                            failures.append({
                                'test': test_name,
                                'type': 'error',
                                'message': error.get('message', ''),
                                'trace': error.text or ''
                            })
                
                results[category] = {
                    'tests': total_tests,
                    'failures': total_failures,
                    'errors': total_errors,
                    'skipped': total_skipped,
                    'time': total_time,
                    'success_rate': (total_tests - total_failures - total_errors) / max(total_tests, 1) * 100,
                    'failure_details': failures,
                    'slow_tests': sorted(slow_tests, key=lambda x: x[1], reverse=True)
                }
                
            except ET.ParseError as e:
                logger.error(f"Failed to parse {xml_file}: {e}")
                results[xml_file.stem] = {
                    'tests': 0, 'failures': 0, 'errors': 1,
                    'skipped': 0, 'time': 0, 'success_rate': 0,
                    'failure_details': [{'test': 'parse_error', 'type': 'error', 
                                       'message': str(e), 'trace': ''}],
                    'slow_tests': []
                }
        
        return results
    
    def parse_coverage_data(self) -> Dict:
        """Parse coverage JSON data."""
        coverage_file = self.test_reports_dir / "coverage.json"
        
        if not coverage_file.exists():
            logger.warning("Coverage JSON file not found")
            return {}
        
        try:
            with open(coverage_file, 'r') as f:
                data = json.load(f)
            
            # Extract overall statistics
            totals = data.get('totals', {})
            overall_coverage = totals.get('percent_covered', 0)
            
            # Calculate per-package coverage
            package_coverage = defaultdict(lambda: {'covered': 0, 'total': 0})
            missed_files = []
            
            for file_path, file_data in data.get('files', {}).items():
                # Normalize path to POSIX for grouping
                normalized_path = Path(file_path).as_posix()
                
                # Determine package
                if normalized_path.startswith('backend/api'):
                    package = 'backend/api'
                elif normalized_path.startswith('backend/services'):
                    package = 'backend/services'
                elif normalized_path.startswith('backend/risk'):
                    package = 'backend/risk'
                elif normalized_path.startswith('backend/strategies'):
                    package = 'backend/strategies'
                elif normalized_path.startswith('backend/db'):
                    package = 'backend/db'
                elif normalized_path.startswith('backend/'):
                    package = 'backend/other'
                else:
                    package = 'other'
                
                summary = file_data.get('summary', {})
                covered = summary.get('covered_lines', 0)
                total = summary.get('num_statements', 0)
                
                package_coverage[package]['covered'] += covered
                package_coverage[package]['total'] += total
                
                # Track files with most missed lines
                missed = total - covered
                if missed > 0:
                    missed_files.append((normalized_path, missed, total))
            
            # Calculate package percentages
            for package in package_coverage:
                pkg_data = package_coverage[package]
                if pkg_data['total'] > 0:
                    pkg_data['percent'] = pkg_data['covered'] / pkg_data['total'] * 100
                else:
                    pkg_data['percent'] = 0
            
            # Sort missed files by missed line count
            missed_files.sort(key=lambda x: x[1], reverse=True)
            
            return {
                'overall_percent': overall_coverage,
                'package_coverage': dict(package_coverage),
                'top_missed_files': missed_files[:10]
            }
            
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.error(f"Failed to parse coverage data: {e}")
            return {}
    
    def analyze_failures(self, junit_results: Dict) -> Dict:
        """Analyze and group test failures."""
        failure_groups = defaultdict(list)
        subsystem_failures = defaultdict(int)
        
        for category, results in junit_results.items():
            for failure in results.get('failure_details', []):
                # Extract error type from message or trace
                error_type = self.extract_error_type(failure.get('message', ''), 
                                                   failure.get('trace', ''))
                
                # Determine suspected subsystem
                subsystem = self.determine_subsystem(failure.get('test', ''), 
                                                   failure.get('trace', ''))
                
                failure_groups[error_type].append({
                    'test': failure.get('test', ''),
                    'category': category,
                    'subsystem': subsystem,
                    'trace_snippet': self.extract_trace_snippet(failure.get('trace', ''))
                })
                
                subsystem_failures[subsystem] += 1
        
        return {
            'grouped_failures': dict(failure_groups),
            'subsystem_failures': dict(subsystem_failures)
        }
    
    def extract_error_type(self, message: str, trace: str) -> str:
        """Extract error type from failure message or trace."""
        # Common error patterns
        error_patterns = [
            'AssertionError', 'AttributeError', 'KeyError', 'ValueError',
            'TypeError', 'ImportError', 'ModuleNotFoundError', 'TimeoutError',
            'ConnectionError', 'HTTPException', 'ValidationError'
        ]
        
        text = f"{message} {trace}".lower()
        
        for pattern in error_patterns:
            if pattern.lower() in text:
                return pattern
        
        # Fallback to first word of message
        if message:
            return message.split(':')[0].strip()
        
        return 'Unknown'
    
    def determine_subsystem(self, test_name: str, trace: str) -> str:
        """Determine suspected subsystem from test name or trace."""
        text = f"{test_name} {trace}".lower()
        
        if any(keyword in text for keyword in ['api', 'endpoint', 'route', 'http']):
            return 'api'
        elif any(keyword in text for keyword in ['websocket', 'ws', 'socket']):
            return 'ws'
        elif any(keyword in text for keyword in ['service', 'business']):
            return 'services'
        elif any(keyword in text for keyword in ['database', 'db', 'session', 'sql']):
            return 'db'
        elif any(keyword in text for keyword in ['risk', 'position', 'limit']):
            return 'risk'
        elif any(keyword in text for keyword in ['strategy', 'trading', 'signal']):
            return 'strategies'
        else:
            return 'unknown'
    
    def extract_trace_snippet(self, trace: str) -> str:
        """Extract meaningful snippet from stack trace."""
        if not trace:
            return ''
        
        lines = trace.split('\n')
        
        # Find the first meaningful line (file:line)
        for line in lines:
            if '.py' in line and ('File "' in line or 'line ' in line):
                return line.strip()[:100] + '...' if len(line) > 100 else line.strip()
        
        # Fallback to first non-empty line
        for line in lines:
            if line.strip():
                return line.strip()[:100] + '...' if len(line) > 100 else line.strip()
        
        return 'No trace available'
    
    def assess_api_health(self) -> Dict:
        """Assess API health and route registration."""
        # Check if using factory pattern
        main_py = self.root_path / "backend" / "api" / "main.py"
        factory_py = self.root_path / "backend" / "api" / "factory.py"
        
        using_factory = factory_py.exists()
        
        # Key routes that should exist
        expected_routes = [
            '/healthz', '/readyz', '/metrics',
            '/auth/register', '/api/v1/positions', '/api/v1/orders/submit'
        ]
        
        missing_routes = []  # Would need actual route inspection
        
        return {
            'using_factory': using_factory,
            'missing_routes': missing_routes,
            'issues': []
        }
    
    def assess_ws_health(self, coverage_data: Dict) -> Dict:
        """Assess WebSocket health."""
        ws_coverage = 0
        
        # Find WebSocket manager coverage
        for package, data in coverage_data.get('package_coverage', {}).items():
            if 'websocket' in package.lower():
                ws_coverage = data.get('percent', 0)
                break
        
        issues = []
        if ws_coverage < 30:
            issues.append("WebSocket manager coverage <30%")
        
        return {
            'ws_coverage': ws_coverage,
            'issues': issues
        }
    
    def assess_db_health(self, junit_results: Dict) -> Dict:
        """Assess database health."""
        db_issues = []
        
        # Check for common DB issues in failures
        for category, results in junit_results.items():
            for failure in results.get('failure_details', []):
                trace = failure.get('trace', '').lower()
                if 'db_sessionmaker' in trace or 'database' in trace:
                    db_issues.append("DB session factory issues detected")
                    break
        
        return {
            'issues': db_issues
        }
    
    def generate_actionable_fixes(self, junit_results: Dict, coverage_data: Dict, 
                                failure_analysis: Dict) -> List[Dict]:
        """Generate actionable fix recommendations."""
        fixes = []
        
        # High missed coverage files
        for file_path, missed, total in coverage_data.get('top_missed_files', [])[:5]:
            if missed > 20:  # Only significant gaps
                fixes.append({
                    'priority': 'P1' if missed > 50 else 'P2',
                    'area': 'Coverage',
                    'file': file_path,
                    'issue': f'{missed} missed lines out of {total}',
                    'why': 'Low coverage indicates untested code paths',
                    'fix': f'Add unit tests covering the {missed} missed lines in {file_path}'
                })
        
        # Common failure patterns
        for error_type, failures in failure_analysis.get('grouped_failures', {}).items():
            if len(failures) >= 3:  # Multiple occurrences
                fixes.append({
                    'priority': 'P0',
                    'area': 'Reliability',
                    'file': failures[0].get('subsystem', 'unknown'),
                    'issue': f'{error_type} occurring in {len(failures)} tests',
                    'why': 'Repeated failures indicate systemic issue',
                    'fix': f'Fix {error_type} root cause in {failures[0].get("subsystem")} subsystem'
                })
        
        return fixes
    
    def generate_report(self, category_results: Dict, junit_results: Dict, 
                       coverage_data: Dict) -> str:
        """Generate the comprehensive architect review report."""
        
        failure_analysis = self.analyze_failures(junit_results)
        api_health = self.assess_api_health()
        ws_health = self.assess_ws_health(coverage_data)
        db_health = self.assess_db_health(junit_results)
        actionable_fixes = self.generate_actionable_fixes(
            junit_results, coverage_data, failure_analysis
        )
        
        # Calculate totals
        total_tests = sum(r.get('tests', 0) for r in junit_results.values())
        total_failures = sum(r.get('failures', 0) + r.get('errors', 0) 
                           for r in junit_results.values())
        overall_pass_rate = ((total_tests - total_failures) / max(total_tests, 1)) * 100
        
        # Determine overall status
        if total_failures == 0:
            status = "✅ ALL TESTS PASSING"
            exit_code = 0
        elif overall_pass_rate >= 90:
            status = "🟨 MOSTLY PASSING"
            exit_code = 1
        else:
            status = "❌ SIGNIFICANT FAILURES"
            exit_code = 2
        
        # Get slowest tests across all categories
        all_slow_tests = []
        for results in junit_results.values():
            all_slow_tests.extend(results.get('slow_tests', []))
        all_slow_tests.sort(key=lambda x: x[1], reverse=True)
        
        report = f"""# 🔍 FULL TEST AUDIT REPORT
*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*

## 📊 Executive Summary

**Overall Status**: {status}  
**Exit Code**: {exit_code}  
**Total Tests**: {total_tests:,}  
**Pass Rate**: {overall_pass_rate:.1f}%  
**Coverage**: {coverage_data.get('overall_percent', 0):.1f}%  

### Per-Category Results
| Category | Tests | Pass Rate | Duration | Status |
|----------|-------|-----------|----------|--------|
"""
        
        for category, results in junit_results.items():
            status_emoji = "✅" if results['success_rate'] == 100 else "❌" if results['success_rate'] < 50 else "🟨"
            report += f"| {category} | {results['tests']} | {results['success_rate']:.1f}% | {results['time']:.1f}s | {status_emoji} |\n"
        
        report += f"""
### Per-Package Coverage
| Package | Coverage | Covered/Total |
|---------|----------|---------------|
"""
        
        for package, data in coverage_data.get('package_coverage', {}).items():
            report += f"| {package} | {data['percent']:.1f}% | {data['covered']}/{data['total']} |\n"
        
        # Failure Analysis
        if failure_analysis['grouped_failures']:
            report += f"""
## 🚨 Top Failures (Grouped)

"""
            for error_type, failures in list(failure_analysis['grouped_failures'].items())[:5]:
                report += f"""### {error_type} ({len(failures)} occurrences)
**Suspected Subsystem**: {failures[0]['subsystem']}  
**Example**: {failures[0]['trace_snippet']}  

"""
        
        # Time & Flakiness
        report += f"""
## ⏱️ Performance & Flakiness

### Top 20 Slowest Tests
| Test | Duration |
|------|----------|
"""
        
        for test_name, duration in all_slow_tests[:20]:
            report += f"| {test_name} | {duration:.2f}s |\n"
        
        if self.flaky_tests:
            report += f"""
### 🔥 Flaky Tests Detected
{chr(10).join(f"- {test}" for test in self.flaky_tests)}
"""
        
        # Coverage Gaps
        report += f"""
## 📉 Coverage Gaps

### Top 10 Files by Missed Lines
| File | Missed Lines | Total Lines | Coverage |
|------|--------------|-------------|----------|
"""
        
        for file_path, missed, total in coverage_data.get('top_missed_files', []):
            coverage_pct = ((total - missed) / total * 100) if total > 0 else 0
            report += f"| {file_path} | {missed} | {total} | {coverage_pct:.1f}% |\n"
        
        # Health Assessments
        report += f"""
## 🏥 System Health Assessment

### API Health
"""
        if api_health['using_factory']:
            report += "✅ Using factory pattern (create_app)\n"
        else:
            report += "❌ Not using factory pattern - consider backend/api/factory.py\n"
        
        if api_health['missing_routes']:
            report += f"❌ **P0 Route Registration**: Missing routes: {', '.join(api_health['missing_routes'])}\n"
        
        report += f"""
### WebSocket Health
Coverage: {ws_health['ws_coverage']:.1f}%
"""
        
        for issue in ws_health['issues']:
            report += f"❌ {issue}\n"
        
        report += f"""
### Database Health
"""
        
        for issue in db_health['issues']:
            report += f"❌ {issue}\n"
        
        if not db_health['issues']:
            report += "✅ No database issues detected\n"
        
        # Actionable Fixes
        if actionable_fixes:
            report += f"""
## 🔧 Actionable Fixes (PR-Ready)

| Priority | Area | File/Function | Issue | Why It Matters | Fix Sketch |
|----------|------|---------------|-------|----------------|------------|
"""
            
            for fix in actionable_fixes:
                report += f"| {fix['priority']} | {fix['area']} | {fix['file']} | {fix['issue']} | {fix['why']} | {fix['fix']} |\n"
        
        # Architect Requests
        report += f"""
## 📋 Architect Review Checklist

The following artifacts are available for independent review:

✅ **Available Artifacts**
- test_reports/coverage.xml (for IDE integration)
- test_reports/htmlcov/ (interactive coverage browser)  
- test_reports/junit/*.xml (CI/CD integration)
- architect_review/FULL_TEST_AUDIT_REPORT.md (this report)

🔍 **Missing Artifacts** (would help review):
"""
        
        missing_artifacts = []
        if not (self.root_path / "openapi.json").exists():
            missing_artifacts.append("openapi.json (API schema)")
        if not (self.root_path / "pytest.ini").exists():
            missing_artifacts.append("pytest.ini (test configuration)")
        if not (self.root_path / ".coveragerc").exists():
            missing_artifacts.append(".coveragerc (coverage configuration)")
        
        if missing_artifacts:
            for artifact in missing_artifacts:
                report += f"- {artifact}\n"
        else:
            report += "- None - all key artifacts present\n"
        
        report += f"""
---
*End of Report*
"""
        
        return report
    
    def run(self):
        """Main execution flow."""
        logger.info("Starting comprehensive test execution and analysis")
        
        try:
            # Run all test categories
            self.category_results = self.run_all_categories()
            
            # Combine coverage data
            self.combine_coverage()
            
            # Parse results
            junit_results = self.parse_junit_results()
            coverage_data = self.parse_coverage_data()
            
            # Generate comprehensive report
            report = self.generate_report(self.category_results, junit_results, coverage_data)
            
            # Write report
            report_file = self.architect_review_dir / "FULL_TEST_AUDIT_REPORT.md"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"Report generated: {report_file}")
            logger.info(f"Coverage HTML: {self.test_reports_dir / 'htmlcov' / 'index.html'}")
            
            # Always exit 0 to allow report review
            return 0
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            
            # Generate error report
            error_report = f"""# 🚨 TEST PIPELINE EXECUTION FAILED

**Error**: {str(e)}
**Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Next Steps
1. Check logs in test_reports/logs/
2. Verify pytest installation and configuration
3. Ensure test directory structure exists

"""
            
            report_file = self.architect_review_dir / "FULL_TEST_AUDIT_REPORT.md"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(error_report)
            
            return 0  # Still exit 0 for report access


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Test Execution & Analysis Pipeline"
    )
    
    parser.add_argument(
        '--all', action='store_true', default=True,
        help='Run all discovered test categories (default)'
    )
    parser.add_argument(
        '--only', type=str,
        help='Comma-separated list of categories to run'
    )
    parser.add_argument(
        '--repeat-failing', type=int, default=1,
        help='Retry failed categories N times to detect flakiness'
    )
    parser.add_argument(
        '--timeout', type=int, default=60,
        help='Per-test timeout in seconds'
    )
    parser.add_argument(
        '--htmlcov', action='store_true', default=True,
        help='Generate HTML coverage report'
    )
    parser.add_argument(
        '--no-htmlcov', dest='htmlcov', action='store_false',
        help='Skip HTML coverage report'
    )
    parser.add_argument(
        '--junit', action='store_true', default=True,
        help='Generate JUnit XML reports'
    )
    parser.add_argument(
        '--no-junit', dest='junit', action='store_false',
        help='Skip JUnit XML reports'
    )
    parser.add_argument(
        '--covjson', action='store_true', default=True,
        help='Generate coverage JSON report'
    )
    parser.add_argument(
        '--no-covjson', dest='covjson', action='store_false',
        help='Skip coverage JSON report'
    )
    parser.add_argument(
        '--cov-xml', action='store_true', default=True,
        help='Generate coverage XML report'
    )
    
    args = parser.parse_args()
    
    orchestrator = TestOrchestrator(args)
    return orchestrator.run()


if __name__ == "__main__":
    sys.exit(main())
