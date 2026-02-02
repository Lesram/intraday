/**
 * Virtual List Component
 * Renders only visible items for better performance with large datasets
 */
import React, { useRef, useState, useCallback } from 'react';
import { calculateVisibleRange } from '@/utils/performanceUtils';

interface VirtualListProps<T> {
  items: T[];
  itemHeight: number;
  containerHeight?: number;
  overscan?: number;
  renderItem: (item: T, index: number) => React.ReactNode;
  className?: string;
}

export function VirtualList<T>({
  items,
  itemHeight,
  containerHeight = 600,
  overscan = 3,
  renderItem,
  className = '',
}: VirtualListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  const { startIndex, endIndex, offsetY, totalHeight } = calculateVisibleRange({
    totalItems: items.length,
    itemHeight,
    containerHeight,
    scrollTop,
    overscan,
  });

  const visibleItems = items.slice(startIndex, endIndex + 1);

  return (
    <div
      ref={containerRef}
      className={`virtual-list-container ${className}`}
      style={{
        height: containerHeight,
        overflow: 'auto',
        position: 'relative',
      }}
      onScroll={handleScroll}
    >
      <div
        className="virtual-list-spacer"
        style={{
          height: totalHeight,
          position: 'relative',
        }}
      >
        <div
          className="virtual-list-content"
          style={{
            position: 'absolute',
            top: offsetY,
            left: 0,
            right: 0,
          }}
        >
          {visibleItems.map((item, i) => (
            <div
              key={startIndex + i}
              className="virtual-list-item"
              style={{ height: itemHeight }}
            >
              {renderItem(item, startIndex + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
