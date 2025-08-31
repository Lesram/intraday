#!/usr/bin/env python3
"""
Archive Old Test Procedures - Archive all failed/unused test scripts
Creates a comprehensive archive of all the test scripts that were created but are no longer working
"""

import os
import zipfile
import json
from datetime import datetime

def create_old_test_archive():
    """Archive all old/unused test procedures."""
    print("🗄️ ARCHIVING OLD TEST PROCEDURES")
    print("=" * 60)
    
    # Get timestamp for unique archive name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"old_test_procedures_archive_{timestamp}.zip"
    
    # Define all the old/unused test files to archive
    old_test_files = [
        # Comprehensive test attempts
        "comprehensive_test_analysis.py",
        "comprehensive_test.py", 
        "generate_comprehensive_test_command.py",
        "fresh_comprehensive_test.py",
        "comprehensive_analyzer.py",
        
        # Bulletproof test attempts
        "bulletproof_test_runner.py",
        "bulletproof_phase_3_validation.py", 
        "bulletproof_phase_2b_validation.py",
        
        # Old comprehensive individual test files
        "test_comprehensive.py",
        "test_comprehensive_old.py",
        
        # Other failed test attempts
        "test_b24_outbox_comprehensive.py",
        "test_risk_manager_comprehensive.py",
    ]
    
    # Additional patterns to find old test files
    old_test_patterns = [
        "test_*_comprehensive.py",
        "*comprehensive*.py", 
        "*bulletproof*.py",
        "*fresh*.py"
    ]
    
    archived_files = []
    
    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as archive:
        # Archive specific files
        for file_name in old_test_files:
            if os.path.exists(file_name):
                print(f"📦 Archiving: {file_name}")
                archive.write(file_name, f"old_procedures/{file_name}")
                archived_files.append(file_name)
        
        # Find and archive pattern-based files
        import glob
        for pattern in old_test_patterns:
            for file_path in glob.glob(pattern):
                if os.path.isfile(file_path) and file_path not in old_test_files:
                    print(f"📦 Archiving: {file_path}")
                    archive.write(file_path, f"old_procedures/{file_path}")
                    archived_files.append(file_path)
        
        # Archive documentation about old procedures
        old_docs = [
            "COMPREHENSIVE_PHASE_TESTING_REPORT_AUGUST_25_2025.md",
            "COMPLETE_PLATFORM_TEST_ANALYSIS_COMPREHENSIVE.md",
            "COMPREHENSIVE_ENDPOINT_ANALYSIS_REPORT.md",
            "ACCURATE_COMPLETE_TEST_INVENTORY.md",
            "ACCURATE_COMPREHENSIVE_TEST_EXECUTION_SCRIPT.py"
        ]
        
        for doc in old_docs:
            if os.path.exists(doc):
                print(f"📄 Archiving doc: {doc}")
                archive.write(doc, f"old_documentation/{doc}")
                archived_files.append(doc)
        
        # Create archive manifest
        manifest = {
            "archive_created": datetime.now().isoformat(),
            "purpose": "Archive of old/unused test procedures that were created but no longer working",
            "total_files_archived": len(archived_files),
            "archived_files": archived_files,
            "note": "These files are preserved for reference but are not part of the working test system",
            "working_system": "batch_test_runner.py with pytest_light.py"
        }
        
        # Add manifest to archive
        manifest_json = json.dumps(manifest, indent=2)
        archive.writestr("ARCHIVE_MANIFEST.json", manifest_json)
        
        # Create archive summary
        summary = f"""# OLD TEST PROCEDURES ARCHIVE
        
## Purpose
This archive contains all the test procedures that were created during development but are no longer in use or working properly.

## Archive Contents
- **Old Test Scripts**: {len([f for f in archived_files if f.endswith('.py')])} Python files
- **Documentation**: {len([f for f in archived_files if f.endswith('.md')])} Markdown files
- **Total Files**: {len(archived_files)} files

## Working System
The current working test system consists of:
- `batch_test_runner.py` - Main batch execution system
- `pytest_light.py` - Light mode wrapper with ML dependency protection
- `conftest_light_mode.py` - Light mode configuration

## Archive Date
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Files Archived
"""
        for file in sorted(archived_files):
            summary += f"- {file}\n"
        
        archive.writestr("README.md", summary)
    
    file_size = os.path.getsize(archive_name)
    print(f"\n✅ ARCHIVE CREATED: {archive_name}")
    print(f"📊 Archive size: {file_size:,} bytes")
    print(f"📁 Files archived: {len(archived_files)}")
    print(f"🗑️  Old procedures safely archived and ready for cleanup")
    
    return archive_name, archived_files

def cleanup_old_files(archived_files, confirm=True):
    """Optionally remove old files after archiving."""
    if confirm:
        response = input(f"\n🗑️  Remove {len(archived_files)} old files from workspace? (y/N): ")
        if response.lower() != 'y':
            print("📁 Old files kept in workspace (also archived)")
            return
    
    removed_count = 0
    for file_path in archived_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️  Removed: {file_path}")
                removed_count += 1
        except Exception as e:
            print(f"⚠️  Could not remove {file_path}: {e}")
    
    print(f"✅ Cleanup complete: {removed_count} files removed")

if __name__ == "__main__":
    archive_name, archived_files = create_old_test_archive()
    
    print(f"\n🎯 READY FOR COMPREHENSIVE TEST EXECUTION")
    print(f"📦 Old procedures archived in: {archive_name}")
    print(f"🚀 Use: python batch_test_runner.py tests/ for ALL {3907} tests")
