/**
 * Performance Optimization Hooks
 * Custom hooks for debouncing, throttling, and performance monitoring
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

/**
 * Debounce hook - delays execution until user stops typing
 * Perfect for search inputs, filters, API calls
 */
export function useDebounce<T>(value: T, delay: number = 500): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Debounced callback hook - delays function execution
 * Use when you need to debounce a specific function
 */
export function useDebouncedCallback<T extends (...args: unknown[]) => unknown>(
  callback: T,
  delay: number = 500
): (...args: Parameters<T>) => void {
  const timeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = setTimeout(() => {
        callback(...args);
      }, delay);
    },
    [callback, delay]
  );
}

/**
 * Throttle hook - limits execution rate
 * Perfect for scroll handlers, resize handlers
 */
export function useThrottle<T>(value: T, limit: number = 200): T {
  const [throttledValue, setThrottledValue] = useState<T>(value);
  const lastRan = useRef<number>(Date.now());

  useEffect(() => {
    const handler = setTimeout(() => {
      if (Date.now() - lastRan.current >= limit) {
        setThrottledValue(value);
        lastRan.current = Date.now();
      }
    }, limit - (Date.now() - lastRan.current));

    return () => {
      clearTimeout(handler);
    };
  }, [value, limit]);

  return throttledValue;
}

/**
 * Throttled callback hook - limits function execution rate
 */
export function useThrottledCallback<T extends (...args: unknown[]) => unknown>(
  callback: T,
  limit: number = 200
): (...args: Parameters<T>) => void {
  const inThrottle = useRef<boolean>(false);

  return useCallback(
    (...args: Parameters<T>) => {
      if (!inThrottle.current) {
        callback(...args);
        inThrottle.current = true;
        setTimeout(() => {
          inThrottle.current = false;
        }, limit);
      }
    },
    [callback, limit]
  );
}

/**
 * Memoized computation hook with dependency array
 * More explicit than useMemo for complex calculations
 */
export function useMemoizedValue<T>(
  factory: () => T,
  deps: React.DependencyList
): T {
  return useMemo(factory, deps);
}

/**
 * Previous value hook - access previous render's value
 * Useful for comparing changes and optimization
 */
export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined);

  useEffect(() => {
    ref.current = value;
  }, [value]);

  return ref.current;
}

/**
 * Update effect hook - skip first render
 * Only runs on updates, not initial mount
 */
export function useUpdateEffect(
  effect: React.EffectCallback,
  deps?: React.DependencyList
) {
  const isMounted = useRef(false);

  useEffect(() => {
    if (isMounted.current) {
      return effect();
    } else {
      isMounted.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/**
 * Lazy state hook - only initializes on first access
 * Useful for expensive initial state calculations
 */
export function useLazyState<T>(
  initializer: () => T
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(initializer);
  return [state, setState];
}

/**
 * Async memoization hook - cache async results
 * Perfect for expensive API calls or calculations
 */
export function useAsyncMemo<T>(
  factory: () => Promise<T>,
  deps: React.DependencyList,
  defaultValue: T
): T {
  const [value, setValue] = useState<T>(defaultValue);

  useEffect(() => {
    let cancelled = false;
    
    factory().then((result) => {
      if (!cancelled) {
        setValue(result);
      }
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return value;
}

/**
 * Performance monitoring hook
 * Logs render times in development
 */
export function useRenderCount(componentName: string) {
  const renderCount = useRef(0);
  const startTime = useRef(performance.now());

  useEffect(() => {
    renderCount.current += 1;
    const endTime = performance.now();
    const renderTime = endTime - startTime.current;

    if (process.env.NODE_ENV === 'development') {
      console.log(
        `[${componentName}] Render #${renderCount.current} took ${renderTime.toFixed(2)}ms`
      );
    }

    startTime.current = performance.now();
  });

  return renderCount.current;
}

/**
 * Intersection observer hook for lazy loading
 * Detects when element enters viewport
 */
export function useIntersectionObserver(
  ref: React.RefObject<Element>,
  options: IntersectionObserverInit = {}
): boolean {
  const [isIntersecting, setIsIntersecting] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(([entry]) => {
      setIsIntersecting(entry.isIntersecting);
    }, options);

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [ref, options]);

  return isIntersecting;
}

/**
 * Idle callback hook - run code when browser is idle
 * Perfect for non-critical background tasks
 */
export function useIdleCallback(
  callback: () => void,
  deps: React.DependencyList
) {
  useEffect(() => {
    if ('requestIdleCallback' in window) {
      const id = requestIdleCallback(callback);
      return () => cancelIdleCallback(id);
    } else {
      // Fallback for browsers without requestIdleCallback
      const timeout = setTimeout(callback, 1);
      return () => clearTimeout(timeout);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/**
 * Local storage with memoization
 * Caches values to avoid repeated parsing
 */
export function useLocalStorage<T>(
  key: string,
  initialValue: T
): [T, (value: T | ((val: T) => T)) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.warn(`Error loading localStorage key "${key}":`, error);
      return initialValue;
    }
  });

  const setValue = useCallback(
    (value: T | ((val: T) => T)) => {
      try {
        const valueToStore = value instanceof Function ? value(storedValue) : value;
        setStoredValue(valueToStore);
        window.localStorage.setItem(key, JSON.stringify(valueToStore));
      } catch (error) {
        console.warn(`Error saving localStorage key "${key}":`, error);
      }
    },
    [key, storedValue]
  );

  return [storedValue, setValue];
}
