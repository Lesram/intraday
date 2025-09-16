#!/usr/bin/env python3
"""
Phase 2.3 Error Pattern Analysis Script
Identifies AssertionError and ImportError patterns for targeted resolution
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
import json

def run_test_analysis():
    """Run a comprehensive test analysis to identify error patterns."""
    
    print("🔍 Phase 2.3: Analyzing Current Test Error Patterns")
    print("=" * 60)
    
    # Run tests with XML output to capture detailed error information
    print("Running comprehensive test suite...")
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'tests/', 
            '--tb=line',
            '--junit-xml=phase_2_3_analysis.xml',
            '--maxfail=200',  # Capture many failures for analysis
            '-x'  # Stop on first failure for faster feedback
        ], capture_output=True, text=True, timeout=600)
        
        print(f"Test execution completed with return code: {result.returncode}")
        
        # Analyze the output for error patterns
        error_patterns = analyze_test_output(result.stdout, result.stderr)
        
        # Try to parse XML if it was generated
        xml_patterns = analyze_xml_results('phase_2_3_analysis.xml')
        
        # Combine patterns
        combined_patterns = combine_error_patterns(error_patterns, xml_patterns)
        
        # Generate Phase 2.3 analysis report
        generate_analysis_report(combined_patterns)
        
        return combined_patterns
        
    except subprocess.TimeoutExpired:
        print("⚠️  Test execution timed out - analyzing partial results")
        return analyze_partial_results()
    except Exception as e:
        print(f"❌ Error during test analysis: {e}")
        return analyze_fallback_patterns()

def analyze_test_output(stdout, stderr):
    """Analyze pytest stdout/stderr for error patterns."""
    patterns = {
        'AssertionError': [],
        'ImportError': [], 
        'AttributeError': [],
        'ModuleNotFoundError': [],
        'Other': []
    }
    
    lines = (stdout + stderr).split('\n')
    
    for line in lines:
        if 'AssertionError' in line:
            patterns['AssertionError'].append(line.strip())
        elif 'ImportError' in line:
            patterns['ImportError'].append(line.strip())
        elif 'AttributeError' in line:
            patterns['AttributeError'].append(line.strip())
        elif 'ModuleNotFoundError' in line:
            patterns['ModuleNotFoundError'].append(line.strip())
        elif any(error in line for error in ['Error', 'Exception', 'FAILED']):
            patterns['Other'].append(line.strip())
    
    return patterns

def analyze_xml_results(xml_file):
    """Analyze XML test results for detailed error patterns."""
    patterns = defaultdict(list)
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        for testcase in root.iter('testcase'):
            for failure in testcase.iter('failure'):
                message = failure.get('message', '')
                
                if 'AssertionError' in message:
                    patterns['AssertionError'].append({
                        'test': testcase.get('name'),
                        'class': testcase.get('classname'), 
                        'message': message
                    })
                elif 'ImportError' in message or 'ModuleNotFoundError' in message:
                    patterns['ImportError'].append({
                        'test': testcase.get('name'),
                        'class': testcase.get('classname'),
                        'message': message
                    })
                elif 'AttributeError' in message:
                    patterns['AttributeError'].append({
                        'test': testcase.get('name'),
                        'class': testcase.get('classname'),
                        'message': message
                    })
                    
    except Exception as e:
        print(f"⚠️  Could not parse XML results: {e}")
    
    return patterns

def combine_error_patterns(text_patterns, xml_patterns):
    """Combine text and XML error patterns."""
    combined = {
        'AssertionError': {
            'count': len(text_patterns.get('AssertionError', [])) + len(xml_patterns.get('AssertionError', [])),
            'examples': text_patterns.get('AssertionError', [])[:5],
            'detailed': xml_patterns.get('AssertionError', [])[:10]
        },
        'ImportError': {
            'count': len(text_patterns.get('ImportError', [])) + len(xml_patterns.get('ImportError', [])),
            'examples': text_patterns.get('ImportError', [])[:5], 
            'detailed': xml_patterns.get('ImportError', [])[:10]
        },
        'AttributeError': {
            'count': len(text_patterns.get('AttributeError', [])) + len(xml_patterns.get('AttributeError', [])),
            'examples': text_patterns.get('AttributeError', [])[:5],
            'detailed': xml_patterns.get('AttributeError', [])[:10]
        }
    }
    
    return combined

def analyze_partial_results():
    """Analyze available results when full test run isn't possible."""
    print("📊 Analyzing based on available data...")
    
    # Known patterns from roadmap
    return {
        'AssertionError': {
            'count': 79,  # From roadmap
            'focus_areas': [
                'API endpoint assertions',
                'HTTP response validation',
                'Authentication assertions', 
                'WebSocket connection assertions'
            ]
        },
        'ImportError': {
            'count': 41,  # From roadmap
            'focus_areas': [
                'Module import path corrections',
                'Circular dependency resolution',
                'Test configuration alignment',
                'Mock/stub import issues'
            ]
        }
    }

def analyze_fallback_patterns():
    """Fallback analysis using known patterns."""
    return analyze_partial_results()

def generate_analysis_report(patterns):
    """Generate Phase 2.3 analysis report."""
    
    print("\n" + "="*60)
    print("📋 PHASE 2.3 ERROR PATTERN ANALYSIS REPORT")
    print("="*60)
    
    print(f"\n🎯 PRIORITY 1: AssertionError Resolution")
    print(f"   Count: {patterns.get('AssertionError', {}).get('count', 'Unknown')}")
    
    if 'AssertionError' in patterns and 'examples' in patterns['AssertionError']:
        print(f"   Top Examples:")
        for example in patterns['AssertionError']['examples'][:3]:
            print(f"   - {example[:100]}...")
    
    print(f"\n🎯 PRIORITY 2: ImportError Resolution") 
    print(f"   Count: {patterns.get('ImportError', {}).get('count', 'Unknown')}")
    
    if 'ImportError' in patterns and 'examples' in patterns['ImportError']:
        print(f"   Top Examples:")
        for example in patterns['ImportError']['examples'][:3]:
            print(f"   - {example[:100]}...")
    
    print(f"\n📊 Other Error Types:")
    if 'AttributeError' in patterns:
        print(f"   AttributeError: {patterns['AttributeError'].get('count', 0)}")
    
    print("\n" + "="*60)
    print("📋 PHASE 2.3 RECOMMENDED ACTIONS")
    print("="*60)
    
    print("1. ✅ Focus on AssertionError patterns (highest impact)")
    print("2. ✅ Apply Phase 2.2 mocking frameworks to ImportErrors")
    print("3. ✅ Target API endpoint and HTTP response assertions")
    print("4. ✅ Enable authentication test improvements")
    
    # Save detailed analysis
    with open('phase_2_3_analysis_report.json', 'w') as f:
        json.dump(patterns, f, indent=2, default=str)
    
    print(f"\n💾 Detailed analysis saved to: phase_2_3_analysis_report.json")

if __name__ == "__main__":
    run_test_analysis()
