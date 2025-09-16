"""
Utility functions expected by tests and application components.
"""

import asyncio
import decimal
import functools
import re
import threading
from datetime import datetime, timedelta
from typing import List, Any

async def async_retry(func, max_attempts=3, base_delay=1.0, max_delay=60.0, backoff_factor=2.0, jitter=True):
    """
    Retry function with exponential backoff, jitter, and timeout protection.
    
    Args:
        func: Function to retry (sync or async)
        max_attempts: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        backoff_factor: Exponential backoff multiplier
        jitter: Add random jitter to prevent thundering herd
        
    Returns:
        Function result if successful
        
    Raises:
        Last exception if all attempts fail
    """
    import random
    
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func()
            else:
                return func()
        except Exception as e:
            last_exception = e
            
            if attempt == max_attempts - 1:
                # Last attempt failed, re-raise the exception
                raise last_exception
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd effect
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            await asyncio.sleep(delay)
            last_exception = e
            
            if attempt == max_attempts - 1:
                # Last attempt failed, re-raise the exception
                raise last_exception
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd effect
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            await asyncio.sleep(delay)


from datetime import datetime, timedelta, UTC
import decimal
import re
import time
import functools
import threading
import asyncio
from typing import Iterator, Any, Callable, TypeVar, Union

F = TypeVar('F', bound=Callable[..., Any])

def parse_timestamp(s):
    """Parse timestamp string in various formats or Unix timestamp."""
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, tz=UTC)
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if s.endswith('Z'):
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            pass
    raise ValueError("Invalid timestamp")

def calculate_business_days(start, end):
    """Calculate business days between dates."""
    if start == end:
        return 0
    if start > end:
        return -calculate_business_days(end, start)
    days = 0
    cur = start.date()
    while cur < end.date():
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days

def sanitize_symbol(s):
    """Sanitize trading symbol.""" 
    cleaned = s.strip().upper()
    if not cleaned:
        raise ValueError("Empty symbol")
    if len(cleaned) > 10:
        raise ValueError("Symbol too long")
    if not re.match(r"^[A-Z][A-Z0-9\.\-]*$", cleaned):
        raise ValueError("Invalid symbol format")
    return cleaned

def validate_decimal_precision(value, max_places=2):
    """Validate decimal precision."""
    d = decimal.Decimal(str(value))
    return -d.as_tuple().exponent <= max_places

def chunks(iterable, size):
    """Split iterable into chunks."""
    it = iter(iterable)
    while True:
        batch = list([x for _, x in zip(range(size), it)])
        if not batch:
            break
        yield batch

async def retry_with_backoff(func, max_attempts=3, base_delay=1.0):
    """Retry function with backoff."""
    for attempt in range(max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func()
            else:
                return func()
        except Exception:
            if attempt == max_attempts - 1:
                raise
            wait_time = base_delay * (2 ** attempt)
            await asyncio.sleep(wait_time)

def rate_limit(calls_per_second):
    """Rate limit decorator."""
    lock = threading.Lock()
    call_times = []
    min_interval = 1.0 / calls_per_second
    
    def deco(f):
        @functools.wraps(f)  
        async def async_wrapper(*a, **k):
            nonlocal call_times
            now = time.time()
            
            with lock:
                # Clean old calls (older than 1 second)
                cutoff = now - 1.0
                call_times[:] = [t for t in call_times if t > cutoff]
                
                # If we have any recent calls, calculate wait time
                if call_times:
                    # Calculate when the next call can be made
                    last_call = call_times[-1]  # Most recent call
                    next_allowed = last_call + min_interval
                    wait_time = max(0, next_allowed - now)
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                
                # Record this call
                call_times.append(time.time())
            
            if asyncio.iscoroutinefunction(f):
                return await f(*a, **k)
            else:
                return f(*a, **k)
        
        if asyncio.iscoroutinefunction(f):
            return async_wrapper
        else:
            @functools.wraps(f)
            def wrapper(*a, **k):
                now = time.time()
                
                with lock:
                    cutoff = now - 1.0
                    call_times[:] = [t for t in call_times if t > cutoff]
                    
                    if call_times:
                        last_call = call_times[-1]
                        next_allowed = last_call + min_interval
                        wait_time = max(0, next_allowed - now)
                        if wait_time > 0:
                            time.sleep(wait_time)
                    
                    call_times.append(time.time())
                
                return f(*a, **k)
            return wrapper
    return deco

def format_currency_simple(value, precision=2):
    """Format currency string."""
    neg = value < 0
    v = abs(value)
    s = f"${v:,.{precision}f}"
    return f"-{s}" if neg else s
