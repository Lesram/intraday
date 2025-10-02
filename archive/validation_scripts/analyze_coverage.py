#!/usr/bin/env python3
"""
Extract comprehensive coverage report from HTML coverage files and test results
"""
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple
import sys

def parse_html_coverage(html_file_path: str) -> Dict[str, Dict]:
    """Parse HTML coverage report to extract module-level coverage data"""
    coverage_data = {}
    
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find the total coverage percentage
        total_coverage_elem = soup.find('span', class_='pc_cov')
        total_coverage = total_coverage_elem.text.strip('%') if total_coverage_elem else "0"
        
        # Find all table rows with coverage data
        table_rows = soup.find_all('tr', class_='region')
        
        for row in table_rows:
            cells = row.find_all('td')
            if len(cells) >= 6:
                # Extract file path
                file_link = cells[0].find('a')
                if file_link:
                    file_path = file_link.text.strip()
                    
                    # Extract coverage metrics
                    statements = cells[1].text.strip()
                    missing = cells[2].text.strip()
                    excluded = cells[3].text.strip()
                    branches = cells[4].text.strip() if len(cells) >= 7 else "0"
                    partial = cells[5].text.strip() if len(cells) >= 7 else "0"
                    coverage_cell = cells[-1]  # Last cell is coverage percentage
                    
                    # Extract percentage from coverage cell
                    coverage_match = re.search(r'(\d+)%', coverage_cell.text)
                    coverage_percentage = coverage_match.group(1) if coverage_match else "0"
                    
                    coverage_data[file_path] = {
                        'statements': int(statements),
                        'missing': int(missing),
                        'excluded': int(excluded),
                        'branches': int(branches) if branches.isdigit() else 0,
                        'partial': int(partial) if partial.isdigit() else 0,
                        'coverage': int(coverage_percentage)
                    }
        
        return {
            'total_coverage': int(total_coverage.strip('%')),
            'files': coverage_data
        }
        
    except Exception as e:
        print(f"Error parsing HTML coverage: {e}")
        return {'total_coverage': 0, 'files': {}}

def organize_by_module(coverage_data: Dict) -> Dict[str, Dict]:
    """Organize coverage data by backend modules"""
    modules = {}
    
    for file_path, metrics in coverage_data['files'].items():
        # Parse backend module path
        path_parts = file_path.replace('\\', '/').split('/')
        
        if len(path_parts) >= 2 and path_parts[0] == 'backend':
            module_name = path_parts[1]
            
            if module_name not in modules:
                modules[module_name] = {
                    'files': [],
                    'total_statements': 0,
                    'total_missing': 0,
                    'total_branches': 0,
                    'total_partial': 0,
                    'file_count': 0
                }
            
            modules[module_name]['files'].append({
                'path': file_path,
                'coverage': metrics['coverage'],
                'statements': metrics['statements'],
                'missing': metrics['missing']
            })
            
            modules[module_name]['total_statements'] += metrics['statements']
            modules[module_name]['total_missing'] += metrics['missing']
            modules[module_name]['total_branches'] += metrics['branches']
            modules[module_name]['total_partial'] += metrics['partial']
            modules[module_name]['file_count'] += 1
    
    # Calculate module-level coverage percentages
    for module_name, data in modules.items():
        if data['total_statements'] > 0:
            covered_statements = data['total_statements'] - data['total_missing']
            data['coverage_percentage'] = round((covered_statements / data['total_statements']) * 100, 1)
        else:
            data['coverage_percentage'] = 100.0
    
    return modules

def analyze_test_results(terminal_output: str) -> Dict[str, Dict]:
    """Analyze test results from terminal output to extract pass/fail by module"""
    test_results = {}
    
    # Extract test results patterns
    test_patterns = [
        r'test/backend/(\w+)/[^:]+::.*?(PASSED|FAILED|SKIPPED|ERROR)',
        r'FAILED test/backend/(\w+)/.*?- (.+?)(?:\n|$)',
        r'ERROR test/backend/(\w+)/.*?(?:\n|$)'
    ]
    
    # Count results by module
    for pattern in test_patterns:
        matches = re.findall(pattern, terminal_output, re.MULTILINE)
        for match in matches:
            if len(match) >= 2:
                module = match[0]
                status = match[1]
                
                if module not in test_results:
                    test_results[module] = {'PASSED': 0, 'FAILED': 0, 'SKIPPED': 0, 'ERROR': 0}
                
                if status in test_results[module]:
                    test_results[module][status] += 1
    
    return test_results

def generate_comprehensive_report(coverage_data: Dict, modules: Dict, test_results: Dict) -> str:
    """Generate comprehensive coverage and test report"""
    
    report = f"""
# COMPREHENSIVE COVERAGE & TEST RESULTS REPORT
Generated: {Path(__file__).name}

## OVERALL SUMMARY
- **Total Coverage**: {coverage_data['total_coverage']}%
- **Files Analyzed**: {len(coverage_data['files'])}
- **Modules Covered**: {len(modules)}

## MODULE-LEVEL COVERAGE BREAKDOWN

"""
    
    # Sort modules by coverage percentage
    sorted_modules = sorted(modules.items(), key=lambda x: x[1]['coverage_percentage'], reverse=True)
    
    for module_name, data in sorted_modules:
        test_stats = test_results.get(module_name, {'PASSED': 0, 'FAILED': 0, 'SKIPPED': 0, 'ERROR': 0})
        total_tests = sum(test_stats.values())
        pass_rate = (test_stats['PASSED'] / total_tests * 100) if total_tests > 0 else 0
        
        status_icon = "✅" if data['coverage_percentage'] >= 80 and pass_rate >= 80 else "⚠️" if data['coverage_percentage'] >= 60 else "❌"
        
        report += f"""### {status_icon} **{module_name.upper()}**
- **Coverage**: {data['coverage_percentage']}% ({data['total_statements'] - data['total_missing']}/{data['total_statements']} statements)
- **Files**: {data['file_count']} files
- **Test Results**: {test_stats['PASSED']} passed, {test_stats['FAILED']} failed, {test_stats['SKIPPED']} skipped, {test_stats['ERROR']} errors
- **Test Pass Rate**: {pass_rate:.1f}%

"""
        
        # Show top coverage files for high-performing modules
        if data['coverage_percentage'] >= 80:
            high_coverage_files = [f for f in data['files'] if f['coverage'] >= 90]
            if high_coverage_files:
                report += f"  **High Coverage Files ({len(high_coverage_files)} files ≥90%)**\n"
                for f in sorted(high_coverage_files[:5], key=lambda x: x['coverage'], reverse=True):
                    report += f"  - {f['path']}: {f['coverage']}%\n"
                if len(high_coverage_files) > 5:
                    report += f"  - ... and {len(high_coverage_files) - 5} more\n"
        
        # Show problematic files for low-performing modules  
        elif data['coverage_percentage'] < 70:
            low_coverage_files = [f for f in data['files'] if f['coverage'] < 50]
            if low_coverage_files:
                report += f"  **Low Coverage Files ({len(low_coverage_files)} files <50%)**\n"
                for f in sorted(low_coverage_files[:5], key=lambda x: x['coverage']):
                    report += f"  - {f['path']}: {f['coverage']}% ({f['missing']}/{f['statements']} missing)\n"
                if len(low_coverage_files) > 5:
                    report += f"  - ... and {len(low_coverage_files) - 5} more\n"
        
        report += "\n"
    
    # Summary statistics
    high_coverage_modules = [m for m, d in modules.items() if d['coverage_percentage'] >= 80]
    medium_coverage_modules = [m for m, d in modules.items() if 60 <= d['coverage_percentage'] < 80]
    low_coverage_modules = [m for m, d in modules.items() if d['coverage_percentage'] < 60]
    
    report += f"""
## COVERAGE SUMMARY BY CATEGORY

### ✅ **HIGH COVERAGE** (≥80%): {len(high_coverage_modules)} modules
{', '.join(sorted(high_coverage_modules)) if high_coverage_modules else 'None'}

### ⚠️ **MEDIUM COVERAGE** (60-79%): {len(medium_coverage_modules)} modules  
{', '.join(sorted(medium_coverage_modules)) if medium_coverage_modules else 'None'}

### ❌ **LOW COVERAGE** (<60%): {len(low_coverage_modules)} modules
{', '.join(sorted(low_coverage_modules)) if low_coverage_modules else 'None'}

## RECOMMENDATIONS

### Immediate Priority (Low Coverage)
"""
    
    for module in sorted(low_coverage_modules):
        data = modules[module]
        report += f"- **{module}**: {data['coverage_percentage']}% - Focus on covering {data['total_missing']} missing statements\n"
    
    if medium_coverage_modules:
        report += f"\n### Medium Priority (Medium Coverage)\n"
        for module in sorted(medium_coverage_modules):
            data = modules[module]
            report += f"- **{module}**: {data['coverage_percentage']}% - Improve by covering {data['total_missing']} missing statements\n"
    
    return report

def main():
    # Paths to coverage files
    coverage_master_path = "test_results/coverage_master_report/index.html"
    
    if not Path(coverage_master_path).exists():
        print(f"Coverage file not found: {coverage_master_path}")
        sys.exit(1)
    
    # Parse coverage data
    print("Parsing HTML coverage data...")
    coverage_data = parse_html_coverage(coverage_master_path)
    
    # Organize by modules
    print("Organizing coverage by modules...")
    modules = organize_by_module(coverage_data)
    
    # Simulate test results (since we have the terminal output)
    terminal_output = """
    # Insert terminal output here if needed for detailed analysis
    # For now, we'll use coverage data only
    """
    test_results = {}  # Would analyze terminal output if available
    
    # Generate report
    print("Generating comprehensive report...")
    report = generate_comprehensive_report(coverage_data, modules, test_results)
    
    # Save report
    with open("COMPREHENSIVE_COVERAGE_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report)
    
    print("Report saved to COMPREHENSIVE_COVERAGE_REPORT.md")
    print(f"\nQuick Summary:")
    print(f"Total Coverage: {coverage_data['total_coverage']}%")
    print(f"Modules: {len(modules)}")
    print(f"Files: {len(coverage_data['files'])}")

if __name__ == "__main__":
    main()