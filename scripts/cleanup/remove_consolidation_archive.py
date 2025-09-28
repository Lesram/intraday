#!/usr/bin/env python3
"""
Remove obsolete archive modules from consolidation repository.

This script deletes all *.py files under archive/module_files/ directory.
The script is idempotent and will log each deletion while gracefully handling missing files.
"""

import os
import sys
from pathlib import Path


def main():
    """Remove obsolete archive module files."""
    # Define the archive directory path
    archive_dir = Path("archive/module_files")
    
    print(f"Removing obsolete archive modules from: {archive_dir}")
    print("=" * 60)
    
    # Check if archive directory exists
    if not archive_dir.exists():
        print(f"Archive directory {archive_dir} does not exist - nothing to clean up")
        return 0
    
    # Find all Python files in the archive directory
    py_files = list(archive_dir.glob("*.py"))
    
    if not py_files:
        print("No Python files found in archive directory")
        return 0
    
    # Track deletion results
    deleted_files = []
    failed_deletions = []
    
    # Delete each Python file
    for py_file in py_files:
        try:
            if py_file.exists():
                py_file.unlink()  # Delete the file
                deleted_files.append(py_file.name)
                print(f"✓ Deleted: {py_file}")
            else:
                print(f"⚠ Already missing: {py_file}")
                
        except Exception as e:
            failed_deletions.append((py_file.name, str(e)))
            print(f"✗ Failed to delete {py_file}: {e}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("CLEANUP SUMMARY")
    print("=" * 60)
    
    print(f"Total files processed: {len(py_files)}")
    print(f"Successfully deleted: {len(deleted_files)}")
    print(f"Failed deletions: {len(failed_deletions)}")
    
    if deleted_files:
        print("\nDeleted files:")
        for filename in sorted(deleted_files):
            print(f"  - {filename}")
    
    if failed_deletions:
        print("\nFailed deletions:")
        for filename, error in failed_deletions:
            print(f"  - {filename}: {error}")
    
    # Check if directory is now empty and remove it if so
    try:
        remaining_files = list(archive_dir.iterdir())
        if not remaining_files:
            archive_dir.rmdir()
            print(f"\n✓ Removed empty directory: {archive_dir}")
        elif len(remaining_files) == 0:
            print(f"\n⚠ Directory {archive_dir} is now empty but not removed (might contain hidden files)")
    except Exception as e:
        print(f"\n⚠ Could not check/remove directory {archive_dir}: {e}")
    
    print("=" * 60)
    
    # Return non-zero if any deletions failed
    if failed_deletions:
        print(f"Cleanup completed with {len(failed_deletions)} failures")
        return 1
    else:
        print("Cleanup completed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())