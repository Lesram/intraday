#!/usr/bin/env python3
"""
Fix BOM (Byte Order Mark) encoding issues in Python files.
Converts UTF-8 with BOM to UTF-8 without BOM.
"""

import sys
from pathlib import Path
from typing import List


def fix_bom_encoding(file_path: Path, dry_run: bool = False) -> bool:
    """Remove BOM from a file if present."""
    try:
        # Read with BOM handling
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        # Check if BOM was present
        with open(file_path, 'rb') as f:
            raw_content = f.read()
        
        has_bom = raw_content.startswith(b'\xef\xbb\xbf')
        
        if has_bom:
            if dry_run:
                print(f"[DRY RUN] Would remove BOM from: {file_path}")
            else:
                # Write without BOM
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Fixed: {file_path}")
            return True
        else:
            print(f"ℹ️  No BOM found: {file_path}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix BOM encoding in Python files')
    parser.add_argument('files', nargs='*', help='Files to fix (if none, fixes known problematic files)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--scan-all', action='store_true', help='Scan all Python files in backend/')
    
    args = parser.parse_args()
    
    # Known problematic files from audit
    known_files = [
        'backend/config_helpers.py',
        'backend/utils/utilities.py',
    ]
    
    files_to_fix: List[Path] = []
    
    if args.scan_all:
        print("🔍 Scanning all Python files in backend/...")
        root = Path.cwd()
        files_to_fix = list(root.glob('backend/**/*.py'))
        print(f"Found {len(files_to_fix)} Python files to check")
    elif args.files:
        files_to_fix = [Path(f) for f in args.files]
    else:
        root = Path.cwd()
        files_to_fix = [root / f for f in known_files]
    
    # Process files
    fixed_count = 0
    for file_path in files_to_fix:
        if file_path.exists():
            if fix_bom_encoding(file_path, dry_run=args.dry_run):
                fixed_count += 1
        else:
            print(f"⚠️  File not found: {file_path}")
    
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary: {fixed_count}/{len(files_to_fix)} files {'would be ' if args.dry_run else ''}fixed")
    
    if args.dry_run and fixed_count > 0:
        print("\nRun without --dry-run to apply changes")


if __name__ == '__main__':
    main()
