/**
 * Responsive Hooks
 * Hooks for detecting screen size and device type
 */

import { useState, useEffect } from 'react';
import { Grid } from 'antd';

const { useBreakpoint } = Grid;

/**
 * Breakpoint definitions matching Ant Design
 */
export const breakpoints = {
  xs: 480,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1600,
};

/**
 * Hook to detect if screen is mobile (< md breakpoint)
 */
export const useIsMobile = (): boolean => {
  const screens = useBreakpoint();
  return !screens.md;
};

/**
 * Hook to detect if screen is tablet (md to lg)
 */
export const useIsTablet = (): boolean => {
  const screens = useBreakpoint();
  return !!(screens.md && !screens.lg);
};

/**
 * Hook to detect if screen is desktop (>= lg)
 */
export const useIsDesktop = (): boolean => {
  const screens = useBreakpoint();
  return !!screens.lg;
};

/**
 * Hook to get current screen breakpoint
 */
export const useScreenSize = (): keyof typeof breakpoints | 'xs' => {
  const screens = useBreakpoint();
  
  if (screens.xxl) return 'xxl';
  if (screens.xl) return 'xl';
  if (screens.lg) return 'lg';
  if (screens.md) return 'md';
  if (screens.sm) return 'sm';
  return 'xs';
};

/**
 * Hook to get window dimensions
 */
export const useWindowSize = () => {
  const [windowSize, setWindowSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  useEffect(() => {
    const handleResize = () => {
      setWindowSize({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return windowSize;
};

/**
 * Hook to detect touch device
 */
export const useIsTouchDevice = (): boolean => {
  const [isTouch, setIsTouch] = useState(false);

  useEffect(() => {
    setIsTouch(
      'ontouchstart' in window ||
      navigator.maxTouchPoints > 0 ||
      ((navigator as { msMaxTouchPoints?: number }).msMaxTouchPoints !== undefined && (navigator as { msMaxTouchPoints?: number }).msMaxTouchPoints! > 0)
    );
  }, []);

  return isTouch;
};

/**
 * Hook to detect device orientation
 */
export const useOrientation = (): 'portrait' | 'landscape' => {
  const [orientation, setOrientation] = useState<'portrait' | 'landscape'>(
    window.innerHeight > window.innerWidth ? 'portrait' : 'landscape'
  );

  useEffect(() => {
    const handleOrientationChange = () => {
      setOrientation(
        window.innerHeight > window.innerWidth ? 'portrait' : 'landscape'
      );
    };

    window.addEventListener('resize', handleOrientationChange);
    window.addEventListener('orientationchange', handleOrientationChange);

    return () => {
      window.removeEventListener('resize', handleOrientationChange);
      window.removeEventListener('orientationchange', handleOrientationChange);
    };
  }, []);

  return orientation;
};

/**
 * Responsive value selector hook
 * Returns different values based on screen size
 */
export const useResponsiveValue = <T,>(values: {
  xs?: T;
  sm?: T;
  md?: T;
  lg?: T;
  xl?: T;
  xxl?: T;
  default: T;
}): T => {
  const screenSize = useScreenSize();
  return values[screenSize] ?? values.default;
};

/**
 * Hook to detect if user prefers reduced motion
 */
export const usePrefersReducedMotion = (): boolean => {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handleChange = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  return prefersReducedMotion;
};
