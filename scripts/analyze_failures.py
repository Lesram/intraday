#!/usr/bin/env python3
"""Analyze failing tests and group by file"""
import subprocess
import sys
import re
from collections import defaultdict

print("=== ANALYZING FAILING TESTS ===")
print("Running pytest...")

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--ignore=tests/unit/deep", "--tb=no"],
    capture_output=True,
    text=True
)

# Find all FAILED lines
failures = []
for line in result.stdout.split('\n'):
    if line.startswith('FAILED'):
        failures.append(line)

# Group by file
by_file = defaultdict(list)
for f in failures:
    match = re.match(r'FAILED (tests/[^:]+)::', f)
    if match:
        file_path = match.group(1)
        test_name = f.split('::')[-1].split(' -')[0] if '::' in f else "unknown"
        by_file[file_path].append(test_name)

print(f"\n{len(failures)} total failures across {len(by_file)} files\n")
print("Files with most failures:")
for file_path, tests in sorted(by_file.items(), key=lambda x: -len(x[1]))[:10]:
    print(f"  {len(tests):2d} failures: {file_path}")

# Show a few error patterns
print("\nSample failures:")
for f in failures[:5]:
    print(f"  {f[:100]}...")
