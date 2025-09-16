"""
Batch Test Runner with Light Mode
Runs tests in small batches to prevent hanging issues while maintaining light mode protection.
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def get_test_files(test_dirs):
    """Get all test files from specified directories"""
    test_files = []
    for test_dir in test_dirs:
        test_path = Path(test_dir)
        if test_path.is_file():
            test_files.append(str(test_path))
        elif test_path.is_dir():
            # Find all test files in directory
            for file_path in test_path.rglob("test_*.py"):
                test_files.append(str(file_path))
    return test_files

def run_test_batch(test_files, batch_size=3, timeout=60):
    """Run tests in small batches"""
    print(f"🔬 Running {len(test_files)} test files in batches of {batch_size}")
    
    total_passed = 0
    total_failed = 0
    failed_batches = []
    
    # Process in batches
    for i in range(0, len(test_files), batch_size):
        batch = test_files[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(test_files) + batch_size - 1) // batch_size
        
        print(f"\n📦 Batch {batch_num}/{total_batches}: {len(batch)} files")
        for test_file in batch:
            print(f"   • {test_file}")
        
        # Run this batch
        cmd = [
            sys.executable, "pytest_light.py"
        ] + batch + [
            "-v", "--tb=short", f"--timeout={timeout}", 
            "--maxfail=5", f"--junit-xml=batch_{batch_num}_results.xml"
        ]
        
        print(f"🚀 Executing batch {batch_num}...")
        start_time = time.time()
        
        try:
            result = subprocess.run(cmd, timeout=timeout+30, capture_output=True, text=True)
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                print(f"✅ Batch {batch_num} PASSED in {elapsed:.1f}s")
                total_passed += len(batch)
            else:
                print(f"❌ Batch {batch_num} FAILED in {elapsed:.1f}s")
                print(f"   Exit code: {result.returncode}")
                if result.stdout:
                    print("   STDOUT:", result.stdout[-500:])  # Last 500 chars
                if result.stderr:
                    print("   STDERR:", result.stderr[-300:])  # Last 300 chars
                total_failed += len(batch)
                failed_batches.append((batch_num, batch))
                
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            print(f"⏰ Batch {batch_num} TIMEOUT after {elapsed:.1f}s")
            total_failed += len(batch)
            failed_batches.append((batch_num, batch))
        
        # Small delay between batches
        time.sleep(1)
    
    # Summary
    print(f"\n📊 Final Results:")
    print(f"   Total Test Files: {len(test_files)}")
    print(f"   Passed: {total_passed}")
    print(f"   Failed: {total_failed}")
    print(f"   Success Rate: {(total_passed/len(test_files)*100):.1f}%")
    
    if failed_batches:
        print(f"\n❌ Failed Batches:")
        for batch_num, batch_files in failed_batches:
            print(f"   Batch {batch_num}: {', '.join(batch_files)}")
    
    return total_failed == 0

def main():
    """Main execution"""
    if len(sys.argv) < 2:
        print("Usage: python batch_test_runner.py <test_dirs...> [--batch-size N] [--timeout N]")
        print("Example: python batch_test_runner.py tests/api tests/utils --batch-size 2")
        sys.exit(1)
    
    # Parse arguments
    args = sys.argv[1:]
    batch_size = 3
    timeout = 60
    test_dirs = []
    
    i = 0
    while i < len(args):
        if args[i] == "--batch-size":
            batch_size = int(args[i+1])
            i += 2
        elif args[i] == "--timeout":
            timeout = int(args[i+1])
            i += 2
        else:
            test_dirs.append(args[i])
            i += 1
    
    print("🚀 Batch Test Runner with Light Mode")
    print(f"   Test Directories: {test_dirs}")
    print(f"   Batch Size: {batch_size}")
    print(f"   Timeout: {timeout}s")
    
    # Validate light mode setup
    print("\n🧪 Validating Light Mode...")
    try:
        import conftest_light_mode
        print("✅ Light mode validation successful")
    except Exception as e:
        print(f"❌ Light mode validation failed: {e}")
        sys.exit(1)
    
    # Get test files
    test_files = get_test_files(test_dirs)
    if not test_files:
        print("❌ No test files found")
        sys.exit(1)
    
    # Run batched tests
    success = run_test_batch(test_files, batch_size, timeout)
    
    if success:
        print("\n🎉 All batches completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some batches failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
