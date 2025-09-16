import json

# Load coverage data
with open('coverage.json', 'r') as f:
    coverage_data = json.load(f)

files = coverage_data['files']

# Categorize modules by coverage level
zero_coverage = []
low_coverage = []  # 1-25%
medium_coverage = []  # 26-75%
high_coverage = []  # 76-100%

for file_path, file_data in files.items():
    if file_path.startswith('backend/'):
        coverage_pct = file_data['summary']['percent_covered']
        module_info = {
            'file': file_path,
            'coverage': coverage_pct,
            'lines': file_data['summary']['num_statements'],
            'missing': file_data['summary']['missing_lines']
        }
        
        if coverage_pct == 0:
            zero_coverage.append(module_info)
        elif coverage_pct <= 25:
            low_coverage.append(module_info)
        elif coverage_pct <= 75:
            medium_coverage.append(module_info)
        else:
            high_coverage.append(module_info)

print("="*80)
print("DETAILED MODULE COVERAGE ANALYSIS - AI AGENT COMPLIANCE CHECK")
print("="*80)

print(f"\n🚨 ZERO COVERAGE MODULES ({len(zero_coverage)} modules):")
print("These are the critical modules AI agent identified for immediate attention:")
for module in sorted(zero_coverage, key=lambda x: x['lines'], reverse=True):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<35} ({module['lines']} lines)")

print(f"\n⚠️  LOW COVERAGE MODULES (1-25% coverage, {len(low_coverage)} modules):")
for module in sorted(low_coverage, key=lambda x: x['coverage']):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<35} {module['coverage']:.1f}% ({module['missing']} lines missing)")

print(f"\n🔶 MEDIUM COVERAGE MODULES (26-75% coverage, {len(medium_coverage)} modules):")
for module in sorted(medium_coverage, key=lambda x: x['coverage']):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<35} {module['coverage']:.1f}% ({module['missing']} lines missing)")

print(f"\n✅ HIGH COVERAGE MODULES (76-100% coverage, {len(high_coverage)} modules):")
for module in sorted(high_coverage, key=lambda x: x['coverage'], reverse=True):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<35} {module['coverage']:.1f}% ({module['missing']} lines missing)")

# AI Agent's specific examples
print(f"\n🎯 AI AGENT'S SPECIFIC EXAMPLES:")
ai_examples = [
    'backend/config.py',
    'backend/database/connection.py', 
    'backend/services/order_integrity_service.py',
    'backend/services/order_fsm.py',
    'backend/services/positions_service.py',
    'backend/services/signal_service.py'
]

print("Checking AI agent's specific examples:")
for example in ai_examples:
    if example in files:
        coverage_pct = files[example]['summary']['percent_covered']
        lines = files[example]['summary']['num_statements']
        print(f"  • {example.replace('backend/', ''):<35} {coverage_pct:.1f}% ({lines} lines)")
    else:
        print(f"  • {example.replace('backend/', ''):<35} FILE NOT FOUND")
