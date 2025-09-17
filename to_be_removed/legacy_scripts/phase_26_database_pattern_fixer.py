#!/usr/bin/env python3
"""
Phase 2.6 ImportError Resolution Pattern Application Script

Applies systematic fixes for:
1. ImportError: cannot import name 'connection' from backend.database
2. TypeError: reload() argument must be a module  
3. NoneType database session errors

Pattern: Replace complex patching with direct module manipulation
"""

import re
import sys
from pathlib import Path

def apply_phase_26_database_pattern(file_path: str):
    """Apply Phase 2.6 database ImportError resolution pattern to a test file."""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern 1: Fix complex backend.database patching with connection import
    # Replace: patch.dict('sys.modules', {'backend.database': Mock(spec=[])}) patterns
    pattern1 = r'''with patch\.dict\(['"]sys\.modules['"], \{['"]backend\.database['"]:\s*Mock\(spec=\[\]\)\}\):\s*
\s*# Import and reload to get clean state\s*
\s*from backend\.database import connection\s*
\s*reload\(connection\)'''
    
    replacement1 = '''# Import the connection module directly
        import backend.database.connection as connection
        
        # Store original SessionLocal and set to None for testing
        original_sessionlocal = connection.SessionLocal
        connection.SessionLocal = None
        
        try:'''
    
    content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE)
    
    # Pattern 2: Fix async context managers in patched environments
    # Add try/finally blocks to restore SessionLocal
    pattern2 = r'''(\s+)(async with connection\.get_database_session\(\) as session:
\s+assert session is None)'''
    
    replacement2 = r'''\1\2
        finally:
            # Restore original SessionLocal value
            connection.SessionLocal = original_sessionlocal'''
    
    content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE)
    
    # Pattern 3: Fix other backend.database patching patterns
    pattern3 = r'''with patch\.dict\(['"]sys\.modules['"], \{['"]backend\.database['"]:\s*Mock\([^}]*\)\}\):'''
    replacement3 = '''# Use direct module manipulation instead of complex patching
        import backend.database.connection as connection
        original_sessionlocal = connection.SessionLocal
        try:'''
    
    content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE)
    
    return content

def main():
    """Apply Phase 2.6 pattern to database test files."""
    
    test_files = [
        'tests/unit/test_database_connection_comprehensive.py',
        'tests/unit/test_database_focused.py', 
        'tests/unit/test_database_master_roadmap.py'
    ]
    
    for file_path in test_files:
        if Path(file_path).exists():
            print(f"Applying Phase 2.6 patterns to {file_path}...")
            try:
                fixed_content = apply_phase_26_database_pattern(file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_content)
                print(f"✅ Successfully applied Phase 2.6 patterns to {file_path}")
            except Exception as e:
                print(f"❌ Error processing {file_path}: {e}")
        else:
            print(f"⚠️  File not found: {file_path}")

if __name__ == "__main__":
    main()