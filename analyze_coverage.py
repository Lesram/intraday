import json

# Load coverage data
with open('coverage.json', 'r') as f:
    coverage_data = json.load(f)

# Get overall metrics
totals = coverage_data['totals']
print("="*60)
print("BASELINE COVERAGE REPORT - August 26, 2025")
print("="*60)
print(f"Overall Coverage: {totals['percent_covered']:.1f}%")
print(f"Total Lines: {totals['num_statements']}")
print(f"Covered Lines: {totals['covered_lines']}")
print(f"Missing Lines: {totals['missing_lines']}")
print()

# Get module breakdown
print("MODULE-LEVEL COVERAGE BREAKDOWN:")
print("-" * 60)
files = coverage_data['files']

# Sort by coverage percentage
module_data = []
for file_path, file_data in files.items():
    if file_path.startswith('backend/'):
        coverage_pct = file_data['summary']['percent_covered']
        lines = file_data['summary']['num_statements']
        covered = file_data['summary']['covered_lines']
        missing = file_data['summary']['missing_lines']
        
        module_data.append({
            'file': file_path,
            'coverage': coverage_pct,
            'lines': lines,
            'covered': covered,
            'missing': missing
        })

# Sort by coverage (lowest first to identify priorities)
module_data.sort(key=lambda x: x['coverage'])

print(f"{'Module':<40} {'Coverage':<10} {'Lines':<8} {'Missing':<8}")
print("-" * 70)

for module in module_data:
    file_name = module['file'].replace('backend/', '').replace('.py', '')
    coverage_str = f"{module['coverage']:.1f}%"
    print(f"{file_name:<40} {coverage_str:<10} {module['lines']:<8} {module['missing']:<8}")

print("\n" + "="*60)
print("PRIORITY AREAS (0-50% coverage):")
low_coverage = [m for m in module_data if m['coverage'] < 50]
for module in low_coverage[:10]:  # Top 10 priorities
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name}: {module['coverage']:.1f}% ({module['missing']} lines missing)")
