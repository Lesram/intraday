import json

# Load coverage data
with open('coverage.json', 'r') as f:
    coverage_data = json.load(f)

files = coverage_data['files']

# Categorize modules by coverage level
zero_coverage = []
low_coverage = []  # 1-25%
critical_modules = []

print("="*80)
print("AI AGENT COMPLIANCE: DETAILED MODULE COVERAGE ANALYSIS")
print("="*80)

for file_path, file_data in files.items():
    if file_path.startswith('backend\\') or file_path.startswith('backend/'):
        coverage_pct = file_data['summary']['percent_covered']
        module_info = {
            'file': file_path.replace('\\', '/'),
            'coverage': coverage_pct,
            'lines': file_data['summary']['num_statements'],
            'missing': file_data['summary']['missing_lines']
        }
        
        if coverage_pct == 0:
            zero_coverage.append(module_info)
        elif coverage_pct <= 25:
            low_coverage.append(module_info)

# AI Agent's critical modules to check
ai_critical = [
    'config.py', 'database/connection.py', 'services/order_integrity_service.py',
    'services/order_fsm.py', 'services/positions_service.py', 'services/signal_service.py',
    'data/alpaca_client.py'  # We know this one exists
]

print(f"🚨 ZERO COVERAGE MODULES ({len(zero_coverage)} modules):")
print("AI Agent: 'several critical modules at 0% coverage'")
for module in sorted(zero_coverage, key=lambda x: x['lines'], reverse=True):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<40} ({module['lines']:>3} lines)")

print(f"\n⚠️  LOW COVERAGE MODULES (1-25%, {len(low_coverage)} modules):")
print("AI Agent: 'pinpoint which files have little or no test coverage'")
for module in sorted(low_coverage, key=lambda x: x['coverage']):
    file_name = module['file'].replace('backend/', '')
    print(f"  • {file_name:<40} {module['coverage']:>5.1f}% ({module['missing']:>3} missing)")

# Check AI agent's specific examples
print(f"\n🎯 AI AGENT'S CRITICAL EXAMPLES STATUS:")
found_examples = []
for file_path in files:
    clean_path = file_path.replace('\\', '/').replace('backend/', '')
    for example in ai_critical:
        if clean_path.endswith(example):
            coverage_pct = files[file_path]['summary']['percent_covered']
            lines = files[file_path]['summary']['num_statements']
            missing = files[file_path]['summary']['missing_lines']
            found_examples.append(example)
            
            if coverage_pct == 0:
                status = "🚨 ZERO COVERAGE - HIGH PRIORITY"
            elif coverage_pct < 50:
                status = "⚠️  LOW COVERAGE - MEDIUM PRIORITY"
            else:
                status = "✅ ADEQUATE COVERAGE"
                
            print(f"  • {clean_path:<40} {coverage_pct:>5.1f}% ({missing:>3} missing) {status}")

# Report missing critical modules
missing_examples = set(ai_critical) - set(found_examples)
if missing_examples:
    print(f"\n❌ MISSING CRITICAL MODULES (not found in codebase):")
    for missing in missing_examples:
        print(f"  • {missing} - May not exist or need different path")

print(f"\n📊 SUMMARY:")
print(f"  • Total backend files analyzed: {len([f for f in files if f.startswith('backend')])}")
print(f"  • Zero coverage files: {len(zero_coverage)}")
print(f"  • Low coverage files: {len(low_coverage)}")
print(f"  • AI critical examples found: {len(found_examples)}/{len(ai_critical)}")

total_zero_lines = sum(m['lines'] for m in zero_coverage)
total_low_missing = sum(m['missing'] for m in low_coverage)
print(f"  • Lines needing coverage: {total_zero_lines + total_low_missing:,}")
