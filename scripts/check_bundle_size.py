#!/usr/bin/env python3
"""
Bundle Size Check Script (L-12)

Checks frontend bundle size against defined thresholds.
Can be run locally or in CI pipelines.

Usage:
    python scripts/check_bundle_size.py
    python scripts/check_bundle_size.py --ci  # Strict mode for CI
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BundleBudget:
    """Bundle size budget configuration."""
    # All sizes in KB
    initial_js_max: int = 500      # Initial JavaScript bundle
    initial_css_max: int = 100     # Initial CSS bundle
    total_js_max: int = 2000       # Total JS (all chunks)
    chunk_max: int = 600           # Single chunk maximum
    warning_threshold: float = 0.9  # Warn at 90% of budget


class BundleSizeChecker:
    """Checks frontend bundle sizes against budgets."""

    def __init__(self, frontend_dir: Path, budget: BundleBudget):
        self.frontend_dir = frontend_dir
        self.budget = budget
        self.dist_dir = frontend_dir / "dist"
        self.assets_dir = self.dist_dir / "assets"

    def build_frontend(self) -> bool:
        """Build the frontend if dist doesn't exist."""
        if not self.dist_dir.exists():
            print("📦 Building frontend...")
            try:
                subprocess.run(
                    ["npm", "run", "build"],
                    cwd=self.frontend_dir,
                    check=True,
                    capture_output=True,
                    shell=True,
                )
                print("✅ Build complete")
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Build failed: {e.stderr.decode()}")
                return False
        return True

    def get_file_sizes(self) -> dict[str, int]:
        """Get sizes of all bundle files in KB."""
        sizes = {}
        
        if not self.assets_dir.exists():
            print(f"⚠️ Assets directory not found: {self.assets_dir}")
            return sizes

        for file_path in self.assets_dir.iterdir():
            if file_path.is_file():
                size_kb = file_path.stat().st_size / 1024
                sizes[file_path.name] = round(size_kb, 2)

        return sizes

    def analyze_bundles(self, sizes: dict[str, int]) -> dict:
        """Analyze bundle sizes and categorize them."""
        js_files = {k: v for k, v in sizes.items() if k.endswith('.js')}
        css_files = {k: v for k, v in sizes.items() if k.endswith('.css')}
        
        # Find initial bundles (typically index-*.js)
        initial_js = sum(v for k, v in js_files.items() if 'index' in k.lower())
        initial_css = sum(v for k, v in css_files.items() if 'index' in k.lower())
        
        # Total sizes
        total_js = sum(js_files.values())
        total_css = sum(css_files.values())
        
        # Largest chunk
        largest_chunk = max(js_files.values()) if js_files else 0
        largest_chunk_name = max(js_files, key=js_files.get) if js_files else "N/A"

        return {
            "initial_js": initial_js,
            "initial_css": initial_css,
            "total_js": total_js,
            "total_css": total_css,
            "largest_chunk": largest_chunk,
            "largest_chunk_name": largest_chunk_name,
            "js_files": js_files,
            "css_files": css_files,
        }

    def check_budget(self, analysis: dict, strict: bool = False) -> tuple[bool, list[str]]:
        """Check if bundle sizes are within budget.
        
        Returns:
            Tuple of (passed, list of issues)
        """
        issues = []
        warnings = []
        
        # Check initial JS
        if analysis["initial_js"] > self.budget.initial_js_max:
            issues.append(
                f"Initial JS ({analysis['initial_js']:.0f}KB) exceeds budget "
                f"({self.budget.initial_js_max}KB)"
            )
        elif analysis["initial_js"] > self.budget.initial_js_max * self.budget.warning_threshold:
            warnings.append(
                f"Initial JS ({analysis['initial_js']:.0f}KB) approaching budget "
                f"({self.budget.initial_js_max}KB)"
            )

        # Check total JS
        if analysis["total_js"] > self.budget.total_js_max:
            issues.append(
                f"Total JS ({analysis['total_js']:.0f}KB) exceeds budget "
                f"({self.budget.total_js_max}KB)"
            )
        elif analysis["total_js"] > self.budget.total_js_max * self.budget.warning_threshold:
            warnings.append(
                f"Total JS ({analysis['total_js']:.0f}KB) approaching budget "
                f"({self.budget.total_js_max}KB)"
            )

        # Check largest chunk
        if analysis["largest_chunk"] > self.budget.chunk_max:
            issues.append(
                f"Chunk '{analysis['largest_chunk_name']}' ({analysis['largest_chunk']:.0f}KB) "
                f"exceeds chunk budget ({self.budget.chunk_max}KB)"
            )

        # Check initial CSS
        if analysis["initial_css"] > self.budget.initial_css_max:
            issues.append(
                f"Initial CSS ({analysis['initial_css']:.0f}KB) exceeds budget "
                f"({self.budget.initial_css_max}KB)"
            )

        # Print warnings
        for warning in warnings:
            print(f"⚠️ Warning: {warning}")

        # In strict mode, warnings become errors
        if strict:
            issues.extend(warnings)

        return len(issues) == 0, issues

    def run(self, strict: bool = False, skip_build: bool = False) -> int:
        """Run the bundle size check.
        
        Returns:
            Exit code (0 = pass, 1 = fail)
        """
        print("=" * 60)
        print("📊 Frontend Bundle Size Check")
        print("=" * 60)

        # Build if needed
        if not skip_build and not self.build_frontend():
            return 1

        # Get file sizes
        sizes = self.get_file_sizes()
        if not sizes:
            print("❌ No bundle files found. Run 'npm run build' first.")
            return 1

        # Analyze bundles
        analysis = self.analyze_bundles(sizes)

        # Print analysis
        print("\n📈 Bundle Analysis:")
        print("-" * 40)
        print(f"  Initial JS:     {analysis['initial_js']:>8.1f} KB / {self.budget.initial_js_max} KB")
        print(f"  Initial CSS:    {analysis['initial_css']:>8.1f} KB / {self.budget.initial_css_max} KB")
        print(f"  Total JS:       {analysis['total_js']:>8.1f} KB / {self.budget.total_js_max} KB")
        print(f"  Largest Chunk:  {analysis['largest_chunk']:>8.1f} KB / {self.budget.chunk_max} KB")
        print(f"                  ({analysis['largest_chunk_name']})")

        # List all JS files
        print("\n📁 JavaScript Bundles:")
        for name, size in sorted(analysis["js_files"].items(), key=lambda x: -x[1]):
            indicator = "🔴" if size > self.budget.chunk_max else "🟢"
            print(f"  {indicator} {name}: {size:.1f} KB")

        # Check budget
        passed, issues = self.check_budget(analysis, strict=strict)

        print("\n" + "=" * 60)
        if passed:
            print("✅ Bundle size check PASSED")
            return 0
        else:
            print("❌ Bundle size check FAILED:")
            for issue in issues:
                print(f"   - {issue}")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Check frontend bundle sizes")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run in CI mode (strict, warnings are errors)"
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building, use existing dist folder"
    )
    parser.add_argument(
        "--frontend-dir",
        type=Path,
        default=None,
        help="Path to frontend directory"
    )
    args = parser.parse_args()

    # Find frontend directory
    if args.frontend_dir:
        frontend_dir = args.frontend_dir
    else:
        # Try to find relative to script location
        script_dir = Path(__file__).parent.parent
        frontend_dir = script_dir / "frontend"
        
        if not frontend_dir.exists():
            # Try current directory
            frontend_dir = Path.cwd() / "frontend"

    if not frontend_dir.exists():
        print(f"❌ Frontend directory not found: {frontend_dir}")
        sys.exit(1)

    # Run check
    budget = BundleBudget()
    checker = BundleSizeChecker(frontend_dir, budget)
    exit_code = checker.run(strict=args.ci, skip_build=args.skip_build)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
