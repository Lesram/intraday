"""
Final cleanup script for syntax errors and undefined variables.
"""

def final_fix():
    file_path = "c:/Users/Marsel/intra/algotrading_platform/tests/unit/test_risk_manager_math_edges.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix concatenated lines
    content = content.replace(
        '"""Test CVaR precision around percentile boundaries."""        returns = np.linspace(-0.1, 0.1, 100)  # Uniform distribution',
        '"""Test CVaR precision around percentile boundaries."""\n        returns = np.linspace(-0.1, 0.1, 100)  # Uniform distribution'
    )
    
    content = content.replace(
        '"""Test that CVaR maintains expected shortfall property."""        np.random.seed(456)',
        '"""Test that CVaR maintains expected shortfall property."""\n        np.random.seed(456)'
    )
    
    content = content.replace(
        'np.random.seed(789)        returns = np.random.normal(0.01, 0.02, 252).tolist()  # One year of daily returns',
        'np.random.seed(789)\n        returns = np.random.normal(0.01, 0.02, 252).tolist()  # One year of daily returns'
    )
    
    # Remove undefined portfolio_value references
    content = content.replace('assert cvar > portfolio_value * 0.1  # Should be significant given extreme tail', 
                             'assert cvar > 0.1  # Should be significant given extreme tail')
    
    content = content.replace('expected_cvar = abs(np.mean(tail_returns)) * portfolio_value',
                             'expected_cvar = abs(np.mean(tail_returns))')
    
    content = content.replace('assert abs(cvar_95 - expected_cvar) < portfolio_value * 0.01  # 1% tolerance',
                             'assert abs(cvar_95 - expected_cvar) < 0.01  # 1% tolerance')
    
    content = content.replace('assert var_95 < portfolio_value * 0.5  # Sanity check',
                             'assert var_95 < 0.5  # Sanity check')
    
    content = content.replace('assert cvar_95 < portfolio_value * 0.5  # Sanity check',
                             'assert cvar_95 < 0.5  # Sanity check')
    
    # Convert returns to list
    content = content.replace(')', ').tolist()')
    
    # Fix doubled .tolist()
    content = content.replace('.tolist().tolist()', '.tolist()')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Final cleanup completed!")

if __name__ == "__main__":
    final_fix()
