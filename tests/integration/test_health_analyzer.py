#!/usr/bin/env python3
"""
Comprehensive Test Health Assessment Script
Analyzes all 4,068 tests for executability, relevance, and health
"""

import os
import subprocess
import sys
from pathlib import Path
import re
import json
from typing import Dict, List, Tuple, Optional

class TestHealthAnalyzer:
    def __init__(self):
        self.results = {
            'total_files': 0,
            'total_tests': 0,
            'executable': [],
            'collection_errors': [],
            'deprecated_tests': [],
            'import_issues': [],
            'duplicate_files': [],
            'outdated_files': [],
            'high_priority_issues': [],
            'recommendations': []
        }
        
    def analyze_test_collection(self) -> Dict:
        """Run pytest collection to identify issues"""
        print("🔍 Running test collection analysis...")
        
        try:
            # Run collection on entire test suite
            cmd = [sys.executable, "-m", "pytest", ".", "--collect-only", "-q", "--tb=line"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Parse successful collection
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if '.py:' in line and line.strip().endswith(tuple('0123456789')):
                        file_path = line.split(':')[0].strip()
                        test_count = int(line.split(':')[1].strip())
                        self.results['executable'].append({
                            'file': file_path,
                            'tests': test_count,
                            'status': 'OK'
                        })
                        self.results['total_tests'] += test_count
                        
            else:
                # Parse collection errors
                error_lines = result.stderr.split('\n') + result.stdout.split('\n')
                for line in error_lines:
                    if 'ERROR' in line and '.py' in line:
                        self.results['collection_errors'].append(line.strip())
                        
        except subprocess.TimeoutExpired:
            self.results['collection_errors'].append("Test collection timed out (> 300s)")
        except Exception as e:
            self.results['collection_errors'].append(f"Collection failed: {str(e)}")
            
        return self.results
        
    def analyze_deprecated_tests(self):
        """Find deprecated or obsolete test files"""
        print("🗑️ Analyzing deprecated tests...")
        
        deprecated_indicators = [
            'DEPRECATED', 'OBSOLETE', 'TODO.*remove', 'FIXME.*remove',
            'legacy.*test', 'old.*test', '_deprecated', '_obsolete',
            'comprehensive_old', 'phase.*test', 'prompt.*test'
        ]
        
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    
                    # Check filename for deprecated patterns
                    for pattern in deprecated_indicators:
                        if re.search(pattern, file, re.IGNORECASE):
                            self.results['deprecated_tests'].append({
                                'file': file_path,
                                'reason': f'Filename matches pattern: {pattern}',
                                'priority': 'LOW'
                            })
                            break
                    
                    # Check file content for deprecated markers
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            for pattern in deprecated_indicators:
                                if re.search(pattern, content, re.IGNORECASE):
                                    self.results['deprecated_tests'].append({
                                        'file': file_path,
                                        'reason': f'Content contains: {pattern}',
                                        'priority': 'MEDIUM'
                                    })
                                    break
                    except Exception:
                        continue
                        
    def analyze_duplicate_files(self):
        """Find potential duplicate test files"""
        print("🔍 Analyzing duplicate files...")
        
        file_groups = {}
        
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    # Group by similar names
                    base_name = re.sub(r'_(old|new|fixed|backup|v\d+|comprehensive|simple)\.py$', '.py', file)
                    if base_name not in file_groups:
                        file_groups[base_name] = []
                    file_groups[base_name].append(os.path.join(root, file))
        
        # Find groups with multiple files
        for base_name, files in file_groups.items():
            if len(files) > 1:
                self.results['duplicate_files'].append({
                    'base_name': base_name,
                    'files': files,
                    'count': len(files)
                })
                
    def analyze_import_health(self):
        """Check for import issues in test files"""
        print("📦 Analyzing import health...")
        
        critical_imports = [
            'backend.api.main',
            'backend.database',
            'backend.models.ensemble_model',
            'backend.services.order_service',
            'backend.risk.risk_manager'
        ]
        
        for import_module in critical_imports:
            try:
                subprocess.run([sys.executable, "-c", f"import {import_module}"], 
                             check=True, capture_output=True, timeout=10)
            except subprocess.CalledProcessError as e:
                self.results['import_issues'].append({
                    'module': import_module,
                    'error': e.stderr.decode() if e.stderr else 'Import failed',
                    'priority': 'HIGH'
                })
            except subprocess.TimeoutExpired:
                self.results['import_issues'].append({
                    'module': import_module,
                    'error': 'Import timeout',
                    'priority': 'HIGH'
                })
                
    def identify_outdated_files(self):
        """Identify potentially outdated test files"""
        print("📅 Identifying outdated files...")
        
        outdated_patterns = [
            r'test_prompt_\d+',  # Prompt-based development tests
            r'test_phase_\d+',   # Phase-based development tests
            r'test_.*_old',      # Explicitly old tests
            r'test_.*_backup',   # Backup tests
            r'test_comprehensive_old',  # Old comprehensive tests
            r'test_.*_v\d+'      # Versioned tests
        ]
        
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    for pattern in outdated_patterns:
                        if re.match(pattern, file):
                            self.results['outdated_files'].append({
                                'file': os.path.join(root, file),
                                'pattern': pattern,
                                'recommendation': 'Consider archiving or updating'
                            })
                            break
                            
    def generate_recommendations(self):
        """Generate actionable recommendations"""
        print("💡 Generating recommendations...")
        
        # High priority issues
        if self.results['collection_errors']:
            self.results['high_priority_issues'].append(
                f"CRITICAL: {len(self.results['collection_errors'])} test files have collection errors"
            )
            
        if self.results['import_issues']:
            critical_import_issues = [i for i in self.results['import_issues'] if i['priority'] == 'HIGH']
            if critical_import_issues:
                self.results['high_priority_issues'].append(
                    f"CRITICAL: {len(critical_import_issues)} critical import failures"
                )
        
        # Recommendations
        if self.results['deprecated_tests']:
            self.results['recommendations'].append(
                f"Archive or update {len(self.results['deprecated_tests'])} deprecated test files"
            )
            
        if self.results['duplicate_files']:
            self.results['recommendations'].append(
                f"Consolidate {len(self.results['duplicate_files'])} groups of duplicate test files"
            )
            
        if self.results['outdated_files']:
            self.results['recommendations'].append(
                f"Review and update {len(self.results['outdated_files'])} potentially outdated test files"
            )
            
    def run_full_analysis(self) -> Dict:
        """Run complete test health analysis"""
        print("🧪 COMPREHENSIVE TEST HEALTH ANALYSIS")
        print("=" * 50)
        
        self.analyze_test_collection()
        self.analyze_deprecated_tests()
        self.analyze_duplicate_files()
        self.analyze_import_health()
        self.identify_outdated_files()
        self.generate_recommendations()
        
        return self.results
        
    def print_summary(self):
        """Print analysis summary"""
        print("\n📊 TEST HEALTH SUMMARY")
        print("=" * 50)
        
        print(f"✅ Executable test files: {len(self.results['executable'])}")
        print(f"🎯 Total test cases: {self.results['total_tests']}")
        print(f"❌ Collection errors: {len(self.results['collection_errors'])}")
        print(f"🗑️ Deprecated tests: {len(self.results['deprecated_tests'])}")
        print(f"📦 Import issues: {len(self.results['import_issues'])}")
        print(f"👥 Duplicate file groups: {len(self.results['duplicate_files'])}")
        print(f"📅 Outdated files: {len(self.results['outdated_files'])}")
        
        if self.results['high_priority_issues']:
            print("\n🚨 HIGH PRIORITY ISSUES:")
            for issue in self.results['high_priority_issues']:
                print(f"  • {issue}")
                
        if self.results['recommendations']:
            print("\n💡 RECOMMENDATIONS:")
            for rec in self.results['recommendations']:
                print(f"  • {rec}")

def main():
    analyzer = TestHealthAnalyzer()
    results = analyzer.run_full_analysis()
    analyzer.print_summary()
    
    # Save detailed results
    with open('test_health_analysis.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: test_health_analysis.json")
    
    # Return overall health score
    total_files = len(results['executable']) + len(results['collection_errors'])
    health_score = len(results['executable']) / total_files * 100 if total_files > 0 else 0
    
    print(f"\n🎯 OVERALL TEST HEALTH SCORE: {health_score:.1f}%")
    
    return results

if __name__ == "__main__":
    main()
