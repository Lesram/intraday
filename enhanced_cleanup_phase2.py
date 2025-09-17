#!/usr/bin/env python3
"""
Enhanced Cleanup Script - Phase 2
Identifies and stages additional legacy files for removal based on user-specified patterns.
"""

import os
import shutil
import glob
from pathlib import Path
import json

class EnhancedCleanupAnalyzer:
    def __init__(self, root_dir="."):
        self.root_dir = Path(root_dir)
        self.staging_dir = self.root_dir / "to_be_removed"
        
        # Ensure staging subdirectories exist
        (self.staging_dir / "legacy_scripts").mkdir(exist_ok=True)
        (self.staging_dir / "analysis_files").mkdir(exist_ok=True)
        (self.staging_dir / "test_artifacts").mkdir(exist_ok=True)
        (self.staging_dir / "documentation").mkdir(exist_ok=True)
        
    def find_pattern_files(self):
        """Find files matching the specified legacy patterns."""
        patterns = {
            "branch_files": [
                "BRANCH_*.md",
                "branch_*.py",
                "branch_*.json"
            ],
            "ai_files": [
                "AI_*.md",
                "ai_*.py",
                "ai_*.json"
            ],
            "phase_files": [
                "phase_*.py",
                "phase_*.json",
                "PHASE_*.md"
            ],
            "step_files": [
                "step4*.py", 
                "step4*.json",
                "STEP*.md"
            ],
            "validation_files": [
                "validate_*.py"
            ],
            "bulletproof_files": [
                "bulletproof*"
            ],
            "consolidation_files": [
                "*CONSOLIDAT*.md",
                "*consolidat*.py"
            ],
            "analysis_files": [
                "*analysis*.py",
                "*analysis*.json",
                "analyze_*.py",
                "comprehensive_*.py",
                "detailed_*.py"
            ],
            "test_artifacts": [
                "test_health*.json",
                "*test_results*.xml",
                "*test_results*.json",
                "real_test_*.py",
                "real_test_*.json"
            ]
        }
        
        found_files = {}
        
        for category, pattern_list in patterns.items():
            found_files[category] = []
            for pattern in pattern_list:
                # Search in root directory
                matches = list(self.root_dir.glob(pattern))
                # Filter out files already in staging
                matches = [f for f in matches if not str(f).startswith(str(self.staging_dir))]
                found_files[category].extend(matches)
        
        return found_files
    
    def stage_files(self, file_categories):
        """Move files to appropriate staging directories."""
        staging_map = {
            "branch_files": "documentation",
            "ai_files": "documentation", 
            "phase_files": "legacy_scripts",
            "step_files": "legacy_scripts",
            "validation_files": "legacy_scripts",
            "bulletproof_files": "test_artifacts",
            "consolidation_files": "documentation",
            "analysis_files": "analysis_files",
            "test_artifacts": "test_artifacts"
        }
        
        moved_files = {}
        
        for category, files in file_categories.items():
            moved_files[category] = []
            staging_subdir = staging_map.get(category, "legacy_scripts")
            dest_dir = self.staging_dir / staging_subdir
            
            for file_path in files:
                if file_path.exists() and file_path.is_file():
                    try:
                        # Preserve relative structure within staging area
                        relative_path = file_path.relative_to(self.root_dir)
                        dest_path = dest_dir / relative_path.name
                        
                        # Handle name conflicts
                        counter = 1
                        original_dest = dest_path
                        while dest_path.exists():
                            stem = original_dest.stem
                            suffix = original_dest.suffix
                            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                        
                        shutil.move(str(file_path), str(dest_path))
                        moved_files[category].append({
                            "original": str(file_path),
                            "moved_to": str(dest_path)
                        })
                        print(f"Moved: {file_path} -> {dest_path}")
                        
                    except Exception as e:
                        print(f"Error moving {file_path}: {e}")
        
        return moved_files
    
    def generate_report(self, moved_files):
        """Generate a detailed report of moved files."""
        total_moved = sum(len(files) for files in moved_files.values())
        
        report = {
            "cleanup_phase": 2,
            "timestamp": "2025-09-16",
            "total_files_moved": total_moved,
            "categories": {}
        }
        
        for category, files in moved_files.items():
            report["categories"][category] = {
                "count": len(files),
                "files": files
            }
        
        report_path = self.staging_dir / "phase2_cleanup_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 PHASE 2 CLEANUP SUMMARY")
        print(f"{'=' * 50}")
        print(f"Total files moved: {total_moved}")
        
        for category, files in moved_files.items():
            if files:
                print(f"{category}: {len(files)} files")
        
        print(f"\nDetailed report saved to: {report_path}")
        return report

def main():
    analyzer = EnhancedCleanupAnalyzer()
    
    print("🔍 ENHANCED CLEANUP - PHASE 2")
    print("=" * 50)
    print("Searching for legacy pattern files...")
    
    # Find all pattern files
    found_files = analyzer.find_pattern_files()
    
    total_found = sum(len(files) for files in found_files.values())
    print(f"Found {total_found} files to stage for removal")
    
    # Show what was found
    for category, files in found_files.items():
        if files:
            print(f"\n{category}: {len(files)} files")
            for file in files[:5]:  # Show first 5
                print(f"  - {file}")
            if len(files) > 5:
                print(f"  ... and {len(files) - 5} more")
    
    if total_found > 0:
        print(f"\n🚀 STAGING {total_found} FILES...")
        print("-" * 50)
        
        # Stage the files
        moved_files = analyzer.stage_files(found_files)
        
        # Generate report
        report = analyzer.generate_report(moved_files)
        
        print("\n✅ PHASE 2 CLEANUP COMPLETE!")
    else:
        print("\n✅ No additional files found matching legacy patterns")

if __name__ == "__main__":
    main()