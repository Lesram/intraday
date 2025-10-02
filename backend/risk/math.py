"""
Risk mathematics utilities with robust input normalization.

Provides numerically stable VaR and CVaR calculations with input coercion
to handle various data types and edge cases gracefully.
"""

from typing import Any

import numpy as np


def align_for_risk_math(other: Any, length: int) -> np.ndarray:
    """
    Normalize inputs for risk math operations to numpy arrays.
    
    Handles pandas Series/DataFrame inputs by extracting values,
    and converts other types to compatible numpy arrays.
    
    Args:
        other: Input data (scalar, list, pandas Series/DataFrame, etc.)
        length: Expected length for alignment
        
    Returns:
        numpy array with proper shape for risk calculations
    """
    # Handle pandas types (check for pandas methods rather than imports)
    if hasattr(other, 'values'):  # pandas Series or DataFrame
        if hasattr(other, 'iloc') and hasattr(other, 'columns'):  # DataFrame - take first column
            return np.asarray(other.iloc[:, 0].values, dtype=float)
        else:  # Series
            return np.asarray(other.values, dtype=float)
    
    # Handle other types using existing _to_series logic
    return _to_series(other)


def _to_series(x: Any) -> np.ndarray:
    """
    Coerce input to numpy array with robust type handling.
    
    Args:
        x: Input data - can be None, scalar, list, numpy array, or any iterable
        
    Returns:
        Normalized numpy array of float64 values
        
    Examples:
        >>> _to_series(None)
        array([], dtype=float64)
        >>> _to_series(5.0)  
        array([5.])
        >>> _to_series([1, 2, 3])
        array([1., 2., 3.])
    """
    if x is None:
        return np.asarray([], dtype=float)
    
    if isinstance(x, (int, float)):
        return np.asarray([x], dtype=float)
    
    try:
        # Try to convert iterable to numpy array
        return np.asarray(list(x), dtype=float)
    except (TypeError, ValueError):
        # Fallback for non-numeric inputs - return empty array
        try:
            return np.asarray([float(x)], dtype=float)
        except (TypeError, ValueError):
            return np.asarray([], dtype=float)


def value_at_risk(returns: Any, alpha: float = 0.95) -> float:
    """
    Calculate Value at Risk with robust input handling.
    
    Args:
        returns: Return data (scalar, list, numpy array, pandas Series/DataFrame, etc.)
        alpha: Confidence level (default 0.95 for 95% VaR)
        
    Returns:
        VaR value as float. Returns 0.0 for empty inputs.
        
    Examples:
        >>> value_at_risk([0.1, -0.05, 0.02, -0.1, 0.03], 0.95)
        -0.05
        >>> value_at_risk([], 0.95)
        0.0
        >>> value_at_risk(None, 0.95)  
        0.0
        >>> value_at_risk(0.05, 0.95)
        0.05
    """
    # Use alignment for pandas inputs, fallback to _to_series for others
    if hasattr(returns, 'values'):  # pandas type
        r = align_for_risk_math(returns, 0)
    else:
        r = _to_series(returns)
    
    if r.size == 0:
        return 0.0
    
    # Handle edge cases before quantile calculation
    if r.size == 1:
        return float(r[0])
        
    # Remove any NaN values
    r_clean = r[~np.isnan(r)]
    if r_clean.size == 0:
        return 0.0
        
    try:
        return float(np.quantile(r_clean, 1 - alpha))
    except (ValueError, TypeError):
        # Fallback to sorted array approach
        sorted_r = np.sort(r_clean)
        index = int((1 - alpha) * len(sorted_r))
        index = max(0, min(index, len(sorted_r) - 1))
        return float(sorted_r[index])


def conditional_var(returns: Any, alpha: float = 0.95) -> float:
    """
    Calculate Conditional Value at Risk (Expected Shortfall) with robust input handling.
    
    Args:
        returns: Return data (scalar, list, numpy array, pandas Series/DataFrame, etc.) 
        alpha: Confidence level (default 0.95 for 95% CVaR)
        
    Returns:
        CVaR value as float. Returns 0.0 for empty inputs.
        
    Examples:
        >>> conditional_var([-0.1, -0.05, -0.02, 0.01, 0.03], 0.95) 
        -0.1
        >>> conditional_var([], 0.95)
        0.0  
        >>> conditional_var(None, 0.95)
        0.0
        >>> conditional_var(-0.05, 0.95) 
        -0.05
    """
    # Use alignment for pandas inputs, fallback to _to_series for others
    if hasattr(returns, 'values'):  # pandas type
        r = align_for_risk_math(returns, 0)
    else:
        r = _to_series(returns)
    
    if r.size == 0:
        return 0.0
    
    # Handle edge cases
    if r.size == 1:
        return float(r[0])
    
    # Remove any NaN values
    r_clean = r[~np.isnan(r)]
    if r_clean.size == 0:
        return 0.0
        
    try:
        q = np.quantile(r_clean, 1 - alpha)
        tail = r_clean[r_clean <= q]
        return float(tail.mean()) if tail.size > 0 else 0.0
    except (ValueError, TypeError):
        # Fallback to sorted array approach
        sorted_r = np.sort(r_clean)
        index = int((1 - alpha) * len(sorted_r))
        index = max(0, min(index, len(sorted_r) - 1))
        threshold = sorted_r[index]
        tail = sorted_r[sorted_r <= threshold]
        return float(np.mean(tail)) if tail.size > 0 else 0.0


def historical_var(returns: Any, alpha: float = 0.95) -> float:
    """
    Calculate historical VaR (alias for value_at_risk for consistency).
    
    Args:
        returns: Return data (scalar, list, numpy array, etc.)
        alpha: Confidence level (default 0.95 for 95% VaR)
        
    Returns:
        Historical VaR value as float
    """
    return value_at_risk(returns, alpha)


def expected_shortfall(returns: Any, alpha: float = 0.95) -> float:
    """
    Calculate Expected Shortfall (alias for conditional_var for consistency).
    
    Args:
        returns: Return data (scalar, list, numpy array, etc.)
        alpha: Confidence level (default 0.95 for 95% ES)
        
    Returns:
        Expected Shortfall value as float
    """
    return conditional_var(returns, alpha)


def parametric_var(
    returns: Any, 
    alpha: float = 0.95, 
    mean: float | None = None,
    std: float | None = None
) -> float:
    """
    Calculate parametric VaR assuming normal distribution.
    
    Args:
        returns: Return data for calculating mean/std if not provided
        alpha: Confidence level (default 0.95 for 95% VaR)  
        mean: Optional pre-calculated mean (calculated from returns if None)
        std: Optional pre-calculated standard deviation (calculated from returns if None)
        
    Returns:
        Parametric VaR value as float
        
    Examples:
        >>> parametric_var([0.1, -0.05, 0.02, -0.1, 0.03], 0.95)
        # Uses calculated mean and std from returns
        >>> parametric_var(None, 0.95, mean=0.01, std=0.05) 
        # Uses provided mean and std
    """
    r = _to_series(returns)
    
    # Use provided parameters or calculate from data
    if mean is None or std is None:
        if r.size == 0:
            return 0.0
        calc_mean = float(np.mean(r)) if mean is None else mean
        calc_std = float(np.std(r, ddof=1)) if std is None else std
    else:
        calc_mean = mean
        calc_std = std
        
    if calc_std <= 0:
        return calc_mean
        
    # Standard normal quantile approximations to avoid scipy dependency
    if alpha >= 0.999:
        z_score = -3.09  # 99.9% VaR
    elif alpha >= 0.99:
        z_score = -2.33  # 99% VaR  
    elif alpha >= 0.95:
        z_score = -1.645  # 95% VaR
    elif alpha >= 0.90:
        z_score = -1.28  # 90% VaR
    else:
        z_score = -1.0  # Conservative fallback
        
    return calc_mean + z_score * calc_std


def coherent_risk_measures(returns: Any, alpha: float = 0.95) -> dict:
    """
    Calculate multiple coherent risk measures in one pass.
    
    Args:
        returns: Return data (scalar, list, numpy array, etc.)
        alpha: Confidence level (default 0.95)
        
    Returns:
        Dictionary containing VaR, CVaR, and parametric VaR
        
    Examples:
        >>> measures = coherent_risk_measures([-0.1, -0.05, 0.02, 0.01, 0.03])
        >>> measures['var']  # Historical VaR
        >>> measures['cvar'] # Conditional VaR  
        >>> measures['parametric_var'] # Parametric VaR
    """
    r = _to_series(returns)
    
    result = {
        'var': value_at_risk(r, alpha),
        'cvar': conditional_var(r, alpha),
        'parametric_var': parametric_var(r, alpha),
        'mean': float(np.mean(r)) if r.size > 0 else 0.0,
        'std': float(np.std(r, ddof=1)) if r.size > 1 else 0.0,
        'observations': int(r.size)
    }
    
    return result
