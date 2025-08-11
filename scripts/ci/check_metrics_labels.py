#!/usr/bin/env python3
"""
Metrics Label Linter for CI Pipeline
Validates Prometheus metrics configuration for proper labeling practices.

This script scans the metrics registry and ensures:
1. All metric names follow naming conventions
2. Label keys are from an allowed list
3. No label values contain IDs or free-form text
4. Cardinality is within reasonable bounds
"""

import argparse
import ast
from pathlib import Path
import re
import sys

# Configuration
ALLOWED_LABEL_KEYS = {
    # Service identification
    "service", "version", "environment", "instance",

    # Request/Response
    "method", "endpoint", "status_code", "status",

    # Trading specific
    "symbol", "side", "order_type", "strategy",
    "exchange", "asset_class", "timeframe",

    # Technical
    "component", "operation", "result", "error_type",
    "source", "destination", "queue_type",

    # WebSocket
    "client_type", "connection_id", "message_type", "direction",

    # Infrastructure
    "node", "pod", "container", "namespace",
    "database", "table", "cache_key",
}

METRIC_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
FORBIDDEN_LABEL_VALUE_PATTERNS = [
    re.compile(r'uuid-[0-9a-f-]{36}'),     # UUID patterns
    re.compile(r'[0-9]{10,}'),              # Long numeric IDs
    re.compile(r'user_\d+'),                # User IDs
    re.compile(r'session_[a-zA-Z0-9]{20,}'), # Session IDs
    re.compile(r'[a-zA-Z0-9+/]{20,}'),      # Base64-like strings
]

HIGH_CARDINALITY_THRESHOLD = 1000


class MetricsLinter:
    """Lints Prometheus metrics for proper labeling practices."""

    def __init__(self, backend_path: Path):
        self.backend_path = backend_path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def lint_all(self) -> bool:
        """Run all linting checks."""
        print("🔍 Scanning metrics configuration...")

        # Find metrics definition files
        metrics_files = self._find_metrics_files()
        if not metrics_files:
            self.warnings.append("No metrics files found")
            return True

        # Parse and validate each file
        for metrics_file in metrics_files:
            self._lint_metrics_file(metrics_file)

        # Report results
        self._report_results()

        return len(self.errors) == 0

    def _find_metrics_files(self) -> list[Path]:
        """Find Python files that define metrics."""
        metrics_files = []

        # Common patterns for metrics files
        patterns = [
            "**/metrics.py",
            "**/metrics/*.py",
            "**/infra/metrics.py",
            "**/monitoring/*.py",
        ]

        for pattern in patterns:
            metrics_files.extend(self.backend_path.glob(pattern))

        return metrics_files

    def _lint_metrics_file(self, file_path: Path) -> None:
        """Lint a specific metrics file."""
        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))

            # Look for Prometheus metric definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    self._check_metric_call(node, file_path)

        except Exception as e:
            self.errors.append(f"Failed to parse {file_path}: {e}")

    def _check_metric_call(self, node: ast.Call, file_path: Path) -> None:
        """Check a function call that might be creating a metric."""
        if not isinstance(node.func, ast.Attribute):
            return

        # Look for Prometheus metric constructors
        metric_types = ['Counter', 'Histogram', 'Gauge', 'Summary']
        func_name = getattr(node.func, 'attr', '')

        if func_name not in metric_types and not any(
            isinstance(arg, ast.Constant) and arg.value in metric_types
            for arg in node.args
        ):
            return

        # Extract metric name and labels
        metric_name = self._extract_metric_name(node)
        labels = self._extract_labels(node)

        if metric_name:
            self._validate_metric_name(metric_name, file_path)

        if labels:
            self._validate_labels(labels, metric_name or "unknown", file_path)

    def _extract_metric_name(self, node: ast.Call) -> str:
        """Extract metric name from AST node."""
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                # First string argument is usually the metric name
                return arg.value
        return ""

    def _extract_labels(self, node: ast.Call) -> list[str]:
        """Extract label keys from AST node."""
        labels = []

        # Look for labelnames argument
        for keyword in node.keywords:
            if keyword.arg == 'labelnames':
                if isinstance(keyword.value, ast.List):
                    for elt in keyword.value.elts:
                        if isinstance(elt, ast.Constant):
                            labels.append(elt.value)

        return labels

    def _validate_metric_name(self, name: str, file_path: Path) -> None:
        """Validate metric name follows conventions."""
        if not METRIC_NAME_PATTERN.match(name):
            self.errors.append(
                f"{file_path}: Invalid metric name '{name}' - "
                f"must match pattern {METRIC_NAME_PATTERN.pattern}"
            )

        # Check for common naming issues
        if not name.endswith(('_total', '_seconds', '_ratio', '_count', '_size', '_bytes')):
            if any(word in name for word in ['count', 'total', 'time', 'duration']):
                self.warnings.append(
                    f"{file_path}: Metric '{name}' should have descriptive suffix "
                    f"like '_total', '_seconds', etc."
                )

    def _validate_labels(self, labels: list[str], metric_name: str, file_path: Path) -> None:
        """Validate label keys and estimate cardinality."""
        # Check label keys against allow-list
        for label in labels:
            if label not in ALLOWED_LABEL_KEYS:
                self.errors.append(
                    f"{file_path}: Metric '{metric_name}' uses disallowed label '{label}'. "
                    f"Allowed labels: {sorted(ALLOWED_LABEL_KEYS)}"
                )

        # Check for high cardinality risk
        if len(labels) > 5:
            self.warnings.append(
                f"{file_path}: Metric '{metric_name}' has {len(labels)} labels - "
                f"consider reducing for lower cardinality"
            )

        # Check for common problematic patterns
        problematic = {'id', 'uuid', 'session', 'token', 'timestamp', 'user_id'}
        for label in labels:
            if any(prob in label.lower() for prob in problematic):
                self.errors.append(
                    f"{file_path}: Metric '{metric_name}' label '{label}' likely has "
                    f"high cardinality - avoid IDs in labels"
                )

    def _report_results(self) -> None:
        """Report linting results."""
        print("\n📊 Metrics Linting Results:")

        if self.errors:
            print(f"❌ {len(self.errors)} errors found:")
            for error in self.errors:
                print(f"  • {error}")

        if self.warnings:
            print(f"⚠️ {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print(f"  • {warning}")

        if not self.errors and not self.warnings:
            print("✅ No metrics issues found")

        print(f"\n🏷️ Allowed label keys ({len(ALLOWED_LABEL_KEYS)}):")
        for key in sorted(ALLOWED_LABEL_KEYS):
            print(f"  • {key}")


def check_label_value_usage(backend_path: Path) -> list[str]:
    """
    Additional check: scan for hardcoded label values that look problematic.
    This is a heuristic check for actual usage patterns.
    """
    issues = []

    for py_file in backend_path.rglob("*.py"):
        if "test" in str(py_file) or "__pycache__" in str(py_file):
            continue

        try:
            with open(py_file, encoding='utf-8') as f:
                content = f.read()

            # Look for .labels() calls with suspicious values
            for line_num, line in enumerate(content.split('\n'), 1):
                if '.labels(' in line:
                    for pattern in FORBIDDEN_LABEL_VALUE_PATTERNS:
                        if pattern.search(line):
                            issues.append(
                                f"{py_file}:{line_num}: Suspicious label value "
                                f"pattern in: {line.strip()}"
                            )

        except Exception:
            continue  # Skip files we can't read

    return issues


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Lint Prometheus metrics configuration")
    parser.add_argument(
        "--backend-path",
        type=Path,
        default=Path("backend"),
        help="Path to backend code directory"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )

    args = parser.parse_args()

    if not args.backend_path.exists():
        print(f"❌ Backend path {args.backend_path} does not exist")
        return 1

    # Run main linting
    linter = MetricsLinter(args.backend_path)
    success = linter.lint_all()

    # Check for problematic label value usage
    print("\n🔍 Checking for problematic label value patterns...")
    usage_issues = check_label_value_usage(args.backend_path)

    if usage_issues:
        print(f"⚠️ Found {len(usage_issues)} potential label value issues:")
        for issue in usage_issues:
            print(f"  • {issue}")

        if args.strict:
            success = False
    else:
        print("✅ No problematic label value patterns found")

    # Final result
    if success and not (args.strict and usage_issues):
        print("\n🎉 Metrics linting passed!")
        return 0
    else:
        print("\n❌ Metrics linting failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
