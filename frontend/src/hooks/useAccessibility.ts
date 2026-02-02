/**
 * Accessibility Hooks
 * Custom hooks for improved accessibility features
 */
import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Generate unique IDs for ARIA attributes
 */
let idCounter = 0;
export function useAriaId(prefix: string = 'aria'): string {
  const [id] = useState(() => `${prefix}-${++idCounter}`);
  return id;
}

/**
 * Announce messages to screen readers
 */
export function useAnnouncer() {
  const announcerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // Create live region for announcements
    const announcer = document.createElement('div');
    announcer.setAttribute('role', 'status');
    announcer.setAttribute('aria-live', 'polite');
    announcer.setAttribute('aria-atomic', 'true');
    announcer.className = 'sr-only';
    announcer.style.cssText = `
      position: absolute;
      left: -10000px;
      width: 1px;
      height: 1px;
      overflow: hidden;
    `;
    document.body.appendChild(announcer);
    announcerRef.current = announcer;

    return () => {
      if (announcerRef.current) {
        document.body.removeChild(announcerRef.current);
      }
    };
  }, []);

  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    if (announcerRef.current) {
      announcerRef.current.setAttribute('aria-live', priority);
      announcerRef.current.textContent = message;
      
      // Clear after announcement
      setTimeout(() => {
        if (announcerRef.current) {
          announcerRef.current.textContent = '';
        }
      }, 1000);
    }
  }, []);

  return announce;
}

/**
 * Manage focus trap in modals/dialogs
 */
export function useFocusTrap(isActive: boolean = true) {
  const containerRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isActive || !containerRef.current) return;

    // Save current focus
    previousFocusRef.current = document.activeElement as HTMLElement;

    const container = containerRef.current;
    const focusableElements = container.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );

    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    // Focus first element
    firstElement?.focus();

    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    container.addEventListener('keydown', handleTab);

    return () => {
      container.removeEventListener('keydown', handleTab);
      
      // Restore previous focus
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
      }
    };
  }, [isActive]);

  return containerRef;
}

/**
 * Detect if user prefers reduced motion
 */
export function usePrefersReducedMotion(): boolean {
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
}

/**
 * Handle keyboard shortcuts
 */
export function useKeyboardShortcut(
  key: string,
  callback: () => void,
  modifiers: {
    ctrl?: boolean;
    shift?: boolean;
    alt?: boolean;
  } = {}
) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const matchesKey = e.key.toLowerCase() === key.toLowerCase();
      const matchesCtrl = !modifiers.ctrl || e.ctrlKey;
      const matchesShift = !modifiers.shift || e.shiftKey;
      const matchesAlt = !modifiers.alt || e.altKey;

      if (matchesKey && matchesCtrl && matchesShift && matchesAlt) {
        e.preventDefault();
        callback();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [key, callback, modifiers]);
}

/**
 * Manage skip links for keyboard navigation
 */
export function useSkipLinks(skipLinkId: string = 'main-content') {
  const skipToContent = useCallback(() => {
    const mainContent = document.getElementById(skipLinkId);
    if (mainContent) {
      mainContent.focus();
      mainContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [skipLinkId]);

  return skipToContent;
}

/**
 * Handle roving tabindex for arrow key navigation
 */
export function useRovingTabIndex<T extends HTMLElement>(
  itemsCount: number,
  orientation: 'horizontal' | 'vertical' = 'vertical'
) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const itemRefs = useRef<(T | null)[]>([]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const isNext =
        (orientation === 'vertical' && e.key === 'ArrowDown') ||
        (orientation === 'horizontal' && e.key === 'ArrowRight');
      const isPrev =
        (orientation === 'vertical' && e.key === 'ArrowUp') ||
        (orientation === 'horizontal' && e.key === 'ArrowLeft');
      const isHome = e.key === 'Home';
      const isEnd = e.key === 'End';

      if (isNext || isPrev || isHome || isEnd) {
        e.preventDefault();

        let newIndex = currentIndex;
        if (isNext) newIndex = Math.min(currentIndex + 1, itemsCount - 1);
        if (isPrev) newIndex = Math.max(currentIndex - 1, 0);
        if (isHome) newIndex = 0;
        if (isEnd) newIndex = itemsCount - 1;

        setCurrentIndex(newIndex);
        itemRefs.current[newIndex]?.focus();
      }
    },
    [currentIndex, itemsCount, orientation]
  );

  const getItemProps = useCallback(
    (index: number) => ({
      ref: (el: T | null) => {
        itemRefs.current[index] = el;
      },
      tabIndex: index === currentIndex ? 0 : -1,
      onKeyDown: handleKeyDown,
    }),
    [currentIndex, handleKeyDown]
  );

  return { getItemProps, currentIndex, setCurrentIndex };
}

/**
 * Announce loading states to screen readers
 */
export function useLoadingAnnouncement(isLoading: boolean, message: string = 'Loading') {
  const announce = useAnnouncer();

  useEffect(() => {
    if (isLoading) {
      announce(message, 'polite');
    }
  }, [isLoading, message, announce]);
}

/**
 * Create accessible description relationship
 */
export function useAriaDescription(description: string) {
  const descriptionId = useAriaId('description');
  
  return {
    'aria-describedby': descriptionId,
    descriptionId,
    description,
  };
}
