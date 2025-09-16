#!/usr/bin/env python3
"""
Real Test Health Assessment Tool
Actual test file collection and health analysis
"""

import os
import subprocess
import json
import ast
import time
from pathlib import Path
from collections import defaultdict, Counter

def get_actual_test_files():
    """Get all actual Python test files that exist"""
    test_files = []
    
    for root, dirs, files in os.walk('tests'):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                test_files.append(os.path.join(root, file))
    
    return sorted(test_files)

def run_collection_test(test_files, batch_size=10):
    """Test actual pytest collection in batches"""
    collection_results = {
        'successful': [],
        'failed': [],
        'errors': []
    }
    
    total_files = len(test_files)
    
    for i in range(0, total_files, batch_size):
        batch = test_files[i:i+batch_size]
        print(f"Testing batch {i//batch_size + 1}/{(total_files-1)//batch_size + 1}: {len(batch)} files")
        
        try:
            cmd = ['python', '-m', 'pytest'] + batch + ['--collect-only', '-q']
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30,
                cwd=os.getcwd()
            )
            
            if result.returncode == 0:
                collection_results['successful'].extend(batch)
                # Extract test count from output
                for line in result.stdout.split('\n'):
                    if 'collected' in line and 'items' in line:
                        print(f"  ✓ Batch collected successfully")
                        break
            else:
                collection_results['failed'].extend(batch)
                collection_results['errors'].append({
                    'batch': batch,
                    'error': result.stderr[-500:] if result.stderr else result.stdout[-500:]
                })
                print(f"  ✗ Batch failed: {result.stderr[:100] if result.stderr else 'Unknown error'}")
                
        except subprocess.TimeoutExpired:
            collection_results['failed'].extend(batch)
            collection_results['errors'].append({
                'batch': batch,
                'error': 'Timeout during collection'
            })
            print(f"  ✗ Batch timed out")
            
        except Exception as e:
            collection_results['failed'].extend(batch)
            collection_results['errors'].append({
                'batch': batch,
                'error': str(e)
            })
            print(f"  ✗ Batch error: {e}")
    
    return collection_results

def analyze_test_file_patterns(test_files):
    """Analyze patterns in test file names to identify categories"""
    patterns = defaultdict(list)
    
    for file in test_files:
        filename = os.path.basename(file)
        
        # Remove test_ prefix and .py suffix
        core_name = filename[5:-3] if filename.startswith('test_') else filename[:-3]
        
        # Identify patterns
        if 'comprehensive' in core_name:
            patterns['comprehensive'].append(file)
        elif 'integration' in core_name:
            patterns['integration'].append(file)
        elif 'unit' in core_name or file.startswith('tests/unit/'):
            patterns['unit'].append(file)
        elif 'api' in core_name or file.startswith('tests/api/'):
            patterns['api'].append(file)
        elif 'performance' in core_name:
            patterns['performance'].append(file)
        elif 'stress' in core_name or 'chaos' in core_name:
            patterns['stress'].append(file)
        elif 'security' in core_name:
            patterns['security'].append(file)
        elif 'ml' in core_name or 'model' in core_name:
            patterns['ml'].append(file)
        elif 'risk' in core_name:
            patterns['risk'].append(file)
        elif 'order' in core_name:
            patterns['order'].append(file)
        elif 'portfolio' in core_name:
            patterns['portfolio'].append(file)
        elif 'websocket' in core_name:
            patterns['websocket'].append(file)
        else:
            patterns['other'].append(file)
    
    return dict(patterns)

def check_file_syntax(test_files):
    """Check Python syntax of test files"""
    syntax_results = {
        'valid': [],
        'invalid': []
    }
    
    for file in test_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            ast.parse(content, filename=file)
            syntax_results['valid'].append(file)
            
        except SyntaxError as e:
            syntax_results['invalid'].append({
                'file': file,
                'error': str(e),
                'line': e.lineno
            })
        except Exception as e:
            syntax_results['invalid'].append({
                'file': file,
                'error': str(e),
                'line': None
            })
    
    return syntax_results

def main():
    """Run comprehensive real test health check"""
    print("=== REAL TEST HEALTH CHECK ===")
    print(f"Working directory: {os.getcwd()}")
    
    # Get actual test files
    print("\n1. Discovering actual test files...")
    test_files = get_actual_test_files()
    print(f"Found {len(test_files)} test files")
    
    # Analyze patterns
    print("\n2. Analyzing test file patterns...")
    patterns = analyze_test_file_patterns(test_files)
    for category, files in patterns.items():
        print(f"  {category}: {len(files)} files")
    
    # Check syntax
    print("\n3. Checking Python syntax...")
    syntax_results = check_file_syntax(test_files)
    print(f"  Valid syntax: {len(syntax_results['valid'])} files")
    print(f"  Syntax errors: {len(syntax_results['invalid'])} files")
    
    if syntax_results['invalid']:
        print("  Syntax error files:")
        for error in syntax_results['invalid'][:5]:  # Show first 5
            print(f"    {error['file']}: {error['error']}")
    
    # Test collection
    print("\n4. Testing pytest collection...")
    collection_results = run_collection_test(test_files, batch_size=10)
    
    print(f"  Successful collection: {len(collection_results['successful'])} files")
    print(f"  Failed collection: {len(collection_results['failed'])} files")
    
    if collection_results['errors']:
        print("  Collection errors:")
        for error in collection_results['errors'][:3]:  # Show first 3
            print(f"    {error['error'][:100]}...")
    
    # Calculate health score
    total_files = len(test_files)
    syntax_ok = len(syntax_results['valid'])
    collection_ok = len(collection_results['successful'])
    
    health_score = (syntax_ok * 0.3 + collection_ok * 0.7) / total_files * 100
    
    print(f"\n=== HEALTH SUMMARY ===")
    print(f"Total test files: {total_files}")
    print(f"Syntax valid: {syntax_ok}/{total_files} ({syntax_ok/total_files*100:.1f}%)")
    print(f"Collection successful: {collection_ok}/{total_files} ({collection_ok/total_files*100:.1f}%)")
    print(f"Overall health score: {health_score:.1f}%")
    
    # Save detailed results
    results = {
        'timestamp': time.time(),
        'total_files': total_files,
        'patterns': {k: len(v) for k, v in patterns.items()},
        'syntax': {
            'valid_count': len(syntax_results['valid']),
            'invalid_count': len(syntax_results['invalid']),
            'invalid_files': syntax_results['invalid']
        },
        'collection': {
            'successful_count': len(collection_results['successful']),
            'failed_count': len(collection_results['failed']),
            'successful_files': collection_results['successful'],
            'failed_files': collection_results['failed'],
            'errors': collection_results['errors']
        },
        'health_score': health_score
    }
    
    with open('real_test_health_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to: real_test_health_results.json")
    
    return health_score

if __name__ == '__main__':
    main()
