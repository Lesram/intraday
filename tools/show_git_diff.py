import subprocess
import sys

try:
    # Run git diff to show changes
    result = subprocess.run(
        ["git", "diff", "backend/api/factory.py"], 
        capture_output=True, 
        text=True,
        cwd="c:\\Users\\Marsel\\intra\\algotrading_platform"
    )
    
    print("GIT DIFF OUTPUT:")
    print("=" * 50)
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Return code: {result.returncode}")
    
except Exception as e:
    print(f"Error running git diff: {e}")
