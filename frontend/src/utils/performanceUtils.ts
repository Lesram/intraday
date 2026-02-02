/**
 * Performance Optimization Utilities
 * Helper functions for optimizing React components
 */

/**
 * Deep comparison function for React.memo
 * More expensive but accurate for complex props
 */
export function deepEqual(obj1: unknown, obj2: unknown): boolean {
  if (obj1 === obj2) return true;

  if (
    typeof obj1 !== 'object' ||
    obj1 === null ||
    typeof obj2 !== 'object' ||
    obj2 === null
  ) {
    return false;
  }

  const keys1 = Object.keys(obj1 as Record<string, unknown>);
  const keys2 = Object.keys(obj2 as Record<string, unknown>);

  if (keys1.length !== keys2.length) return false;

  for (const key of keys1) {
    if (!keys2.includes(key)) return false;
    if (!deepEqual((obj1 as Record<string, unknown>)[key], (obj2 as Record<string, unknown>)[key])) return false;
  }

  return true;
}

/**
 * Shallow comparison function for React.memo
 * Faster than deep comparison, good for most cases
 */
export function shallowEqual(obj1: unknown, obj2: unknown): boolean {
  if (obj1 === obj2) return true;

  if (
    typeof obj1 !== 'object' ||
    obj1 === null ||
    typeof obj2 !== 'object' ||
    obj2 === null
  ) {
    return false;
  }

  const keys1 = Object.keys(obj1 as Record<string, unknown>);
  const keys2 = Object.keys(obj2 as Record<string, unknown>);

  if (keys1.length !== keys2.length) return false;

  for (const key of keys1) {
    if ((obj1 as Record<string, unknown>)[key] !== (obj2 as Record<string, unknown>)[key]) return false;
  }

  return true;
}

/**
 * Check if component should render based on prop changes
 */
export function shouldComponentUpdate<P extends object>(
  prevProps: P,
  nextProps: P,
  compareKeys?: (keyof P)[]
): boolean {
  if (compareKeys) {
    return compareKeys.some((key) => prevProps[key] !== nextProps[key]);
  }
  return !shallowEqual(prevProps, nextProps);
}

/**
 * Check if value has changed (useful in useEffect dependencies)
 */
export function hasChanged(prev: unknown, next: unknown): boolean {
  return prev !== next;
}

/**
 * Virtual list helper - calculate visible items
 */
export interface VirtualListConfig {
  totalItems: number;
  itemHeight: number;
  containerHeight: number;
  scrollTop: number;
  overscan?: number;
}

export function calculateVisibleRange(config: VirtualListConfig) {
  const { totalItems, itemHeight, containerHeight, scrollTop, overscan = 3 } = config;

  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(
    totalItems - 1,
    Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan
  );

  const visibleItems = endIndex - startIndex + 1;
  const offsetY = startIndex * itemHeight;
  const totalHeight = totalItems * itemHeight;

  return {
    startIndex,
    endIndex,
    visibleItems,
    offsetY,
    totalHeight,
  };
}

/**
 * Batch array processing to avoid blocking UI
 */
export async function processBatch<T, R>(
  items: T[],
  processor: (item: T) => R,
  batchSize: number = 100
): Promise<R[]> {
  const results: R[] = [];
  
  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    const batchResults = batch.map(processor);
    results.push(...batchResults);
    
    // Yield to browser
    await new Promise(resolve => setTimeout(resolve, 0));
  }
  
  return results;
}
