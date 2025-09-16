#!/usr/bin/env python3
"""
Phase 1.3: Function Signature Audit Script
Following AI Report 2 and Report 2 roadmap specifications

Identifies signature mismatches and TypeError sources:
- MomentumStrategy.__init__() missing arguments  
- Service function call updates
- Constructor parameter changes
"""

import inspect
import sys
import traceback
from pathlib import Path

def audit_function_signatures():
    """Audit critical function signatures as per roadmap"""
    print("=== PHASE 1.3: FUNCTION SIGNATURE AUDIT ===")
    print("Following Report 2 roadmap methodology")
    print()
    
    # 1. Check MomentumStrategy as specified in roadmap
    print("1. MOMENTUM STRATEGY SIGNATURE AUDIT")
    print("-" * 40)
    
    try:
        from backend.strategies import MomentumStrategy
        sig = inspect.signature(MomentumStrategy.__init__)
        print(f"MomentumStrategy.__init__: {sig}")
        
        # Check parameters
        params = list(sig.parameters.keys())
        print(f"Parameters: {params}")
        
        # Check for missing/required parameters
        required_params = [p for p, param in sig.parameters.items() 
                          if param.default == inspect.Parameter.empty and p != 'self']
        print(f"Required parameters: {required_params}")
        
    except ImportError as e:
        print(f"❌ Cannot import MomentumStrategy: {e}")
    except Exception as e:
        print(f"❌ Error analyzing MomentumStrategy: {e}")
    
    print()
    
    # 2. Check other critical classes mentioned in roadmap
    print("2. SERVICE FUNCTION AUDIT")
    print("-" * 40)
    
    critical_classes = [
        ('backend.models.ensemble_model', 'EnsembleModel'),
        ('backend.risk.risk_manager', 'RiskManager'),
        ('backend.api.factory', 'create_app'),
    ]
    
    for module_name, class_name in critical_classes:
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls_or_func = getattr(module, class_name)
            
            if inspect.isclass(cls_or_func):
                sig = inspect.signature(cls_or_func.__init__)
                print(f"{class_name}.__init__: {sig}")
            else:
                sig = inspect.signature(cls_or_func)
                print(f"{class_name}: {sig}")
                
        except Exception as e:
            print(f"❌ Error analyzing {module_name}.{class_name}: {e}")
    
    print()
    
    # 3. Generate signature compatibility matrix
    print("3. SIGNATURE COMPATIBILITY MATRIX")
    print("-" * 40)
    
    return audit_test_compatibility()

def audit_test_compatibility():
    """Check test calls against actual signatures"""
    issues = []
    
    # Look for common TypeError patterns in test files
    test_files = [
        "tests/strategies/test_momentum_strategy.py",
        "tests/models/test_ensemble_model.py", 
        "tests/risk/test_risk_manager.py"
    ]
    
    for test_file in test_files:
        path = Path(test_file)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Look for constructor calls
                if 'MomentumStrategy(' in content:
                    print(f"✓ Found MomentumStrategy usage in {test_file}")
                if 'EnsembleModel(' in content:
                    print(f"✓ Found EnsembleModel usage in {test_file}")
                if 'RiskManager(' in content:
                    print(f"✓ Found RiskManager usage in {test_file}")
                    
            except Exception as e:
                issues.append(f"Error reading {test_file}: {e}")
        else:
            issues.append(f"Test file not found: {test_file}")
    
    return issues

def find_typeerror_patterns():
    """Find actual TypeError patterns in codebase"""
    print()
    print("4. TYPEERROR PATTERN DETECTION")
    print("-" * 40)
    
    import subprocess
    
    try:
        # Run pytest to capture actual TypeErrors
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            '--tb=short', '--maxfail=5'
        ], capture_output=True, text=True, cwd='.', timeout=120)
        
        lines = result.stdout.split('\n')
        type_errors = []
        
        for line in lines:
            if 'TypeError' in line:
                type_errors.append(line.strip())
                
        if type_errors:
            print(f"Found {len(type_errors)} TypeError instances:")
            for i, error in enumerate(type_errors[:5]):
                print(f"  {i+1}. {error}")
        else:
            print("No TypeErrors found in current test run")
            
        return type_errors
        
    except Exception as e:
        print(f"Error running TypeError detection: {e}")
        return []

if __name__ == "__main__":
    print("Starting Phase 1.3 Function Signature Audit...")
    print("=" * 60)
    
    issues = audit_function_signatures()
    type_errors = find_typeerror_patterns()
    
    print()
    print("5. SUMMARY AND NEXT STEPS")
    print("-" * 40)
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  ❌ {issue}")
    
    if type_errors:
        print(f"TypeErrors detected: {len(type_errors)}")
        print("Proceeding with signature fixes...")
    else:
        print("✅ No immediate TypeErrors detected")
        print("Checking for potential signature mismatches...")
