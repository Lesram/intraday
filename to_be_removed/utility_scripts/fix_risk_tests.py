"""
Script to fix the test_risk_manager_math_edges.py file systematically.
This will correct all the method calls to match the actual RiskMathUtils API.
"""

import re

def fix_test_file():
    file_path = r"c:\Users\Marsel\intra\algotrading_platform\tests\unit\test_risk_manager_math_edges.py"
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix parametric_var calls: parametric_var(portfolio_value, returns, confidence) -> parametric_var(returns, confidence)
    content = re.sub(
        r'RiskMathUtils\.parametric_var\([^,]+,\s*([^,]+),\s*([^)]+)\)',
        r'RiskMathUtils.parametric_var(\1, \2)',
        content
    )
    
    # Fix parametric_var calls: parametric_var(portfolio_value, returns) -> parametric_var(returns)
    content = re.sub(
        r'RiskMathUtils\.parametric_var\([^,]+,\s*([^)]+)\)',
        r'RiskMathUtils.parametric_var(\1)',
        content
    )
    
    # Fix historical_cvar calls: historical_cvar(portfolio_value, returns, confidence) -> historical_cvar(returns, confidence)
    content = re.sub(
        r'RiskMathUtils\.historical_cvar\([^,]+,\s*([^,]+),\s*([^)]+)\)',
        r'RiskMathUtils.historical_cvar(\1, \2)',
        content
    )
    
    # Fix historical_cvar calls: historical_cvar(portfolio_value, returns) -> historical_cvar(returns)  
    content = re.sub(
        r'RiskMathUtils\.historical_cvar\([^,]+,\s*([^)]+)\)',
        r'RiskMathUtils.historical_cvar(\1)',
        content
    )
    
    # Remove portfolio_value variable definitions that are no longer needed
    content = re.sub(r'\s*portfolio_value = \d+\n', '', content)
    
    # Fix expected_fallback calculations that used portfolio_value
    content = re.sub(r'expected_fallback = portfolio_value \* ([\d.]+)', r'expected_fallback = \1', content)
    
    # Fix assertions that compared to portfolio_value  
    content = re.sub(r'assert var < portfolio_value', 'assert var < 1.0', content)
    content = re.sub(r'assert cvar < portfolio_value', 'assert cvar < 1.0', content)
    
    # Write the fixed content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Fixed test file successfully!")

if __name__ == "__main__":
    fix_test_file()
