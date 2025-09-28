#!/usr/bin/env python3
"""
Move service blueprints from runtime package to documentation.

This script moves unused service modules from backend/services/ to docs/blueprints/services/
while preserving only the active services (order_service.py and signal_service.py).
"""

import os
import shutil
import sys
from pathlib import Path


def main():
    """Move service blueprint files to documentation directory."""
    # Define paths
    source_dir = Path("backend/services")
    dest_dir = Path("docs/blueprints/services")
    
    # Files to keep in runtime (active services)
    keep_files = {
        "__init__.py",
        "order_service.py", 
        "signal_service.py"
    }
    
    # Create destination directory if it doesn't exist
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Track moved files
    moved_files = []
    
    print("Moving service blueprint files...")
    print(f"Source: {source_dir}")
    print(f"Destination: {dest_dir}")
    print()
    
    # Check source directory exists
    if not source_dir.exists():
        print(f"ERROR: Source directory {source_dir} does not exist")
        return 1
    
    # Process all .py files in source directory
    for py_file in source_dir.glob("*.py"):
        if py_file.name not in keep_files:
            dest_file = dest_dir / py_file.name
            
            # Move the file
            try:
                shutil.move(str(py_file), str(dest_file))
                moved_files.append(py_file.name)
                print(f"Moved: {py_file.name}")
            except Exception as e:
                print(f"ERROR moving {py_file.name}: {e}")
                return 1
    
    # Create README.md index
    readme_content = """# Service Blueprints

This directory contains service module blueprints that have been moved from the runtime package.
These modules are primarily documentation/placeholder code and are not actively used in the runtime.

## Moved Files

The following files were moved from `backend/services/` to this directory:

"""
    
    for filename in sorted(moved_files):
        readme_content += f"- `{filename}` - moved from runtime package to blueprint docs\n"
    
    readme_content += f"""
## Active Runtime Services

The following services remain in the runtime package (`backend/services/`):

- `order_service.py` - Core order management and execution service
- `signal_service.py` - Trading signal processing and management service
- `__init__.py` - Package initialization

## Usage

These blueprint files can be used as:
- Documentation of planned/potential services
- Templates for future service implementations  
- Reference architecture examples

To activate a service blueprint:
1. Move it back to `backend/services/`
2. Implement the actual functionality
3. Add proper imports and integration
4. Update tests and documentation
"""

    readme_path = dest_dir / "README.md"
    try:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        print(f"Created: {readme_path}")
    except Exception as e:
        print(f"ERROR creating README: {e}")
        return 1
    
    # Print summary
    print()
    print("="*50)
    print("MOVE SUMMARY")
    print("="*50)
    print(f"Files moved: {len(moved_files)}")
    print(f"Destination: {dest_dir}")
    print()
    
    if moved_files:
        print("Moved files:")
        for filename in sorted(moved_files):
            print(f"  - {filename}")
    else:
        print("No files were moved (all were already moved or are kept active)")
    
    print()
    print("Files kept in runtime:")
    for filename in sorted(keep_files):
        runtime_file = source_dir / filename
        if runtime_file.exists():
            print(f"  - {filename}")
    
    print("="*50)
    print("Move operation completed successfully!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())