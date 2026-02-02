/**
 * Accessibility Testing Utilities
 * Helper functions for testing accessibility features
 */

/**
 * Test if element has proper ARIA label
 */
export function hasAriaLabel(element: HTMLElement): boolean {
  return !!(
    element.getAttribute('aria-label') ||
    element.getAttribute('aria-labelledby')
  );
}

/**
 * Test if interactive element is keyboard accessible
 */
export function isKeyboardAccessible(element: HTMLElement): boolean {
  const tagName = element.tagName.toLowerCase();
  const role = element.getAttribute('role');
  
  // Native keyboard accessible elements
  if (['a', 'button', 'input', 'select', 'textarea'].includes(tagName)) {
    return true;
  }
  
  // Elements with interactive roles and tabindex
  if (role && ['button', 'link', 'menuitem', 'tab'].includes(role)) {
    const tabindex = element.getAttribute('tabindex');
    return tabindex !== '-1';
  }
  
  return false;
}

/**
 * Test color contrast ratio
 */
export function getContrastRatio(foreground: string, background: string): number {
  const getLuminance = (hex: string): number => {
    // Convert hex to RGB
    const rgb = parseInt(hex.slice(1), 16);
    const r = ((rgb >> 16) & 0xff) / 255;
    const g = ((rgb >> 8) & 0xff) / 255;
    const b = ((rgb >> 0) & 0xff) / 255;
    
    // Calculate relative luminance
    const rsRGB = r <= 0.03928 ? r / 12.92 : Math.pow((r + 0.055) / 1.055, 2.4);
    const gsRGB = g <= 0.03928 ? g / 12.92 : Math.pow((g + 0.055) / 1.055, 2.4);
    const bsRGB = b <= 0.03928 ? b / 12.92 : Math.pow((b + 0.055) / 1.055, 2.4);
    
    return 0.2126 * rsRGB + 0.7152 * gsRGB + 0.0722 * bsRGB;
  };
  
  const l1 = getLuminance(foreground);
  const l2 = getLuminance(background);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Test if element meets WCAG contrast requirements
 */
export function meetsContrastRequirements(
  foreground: string,
  background: string,
  level: 'AA' | 'AAA' = 'AA',
  isLargeText: boolean = false
): boolean {
  const ratio = getContrastRatio(foreground, background);
  
  if (level === 'AAA') {
    return isLargeText ? ratio >= 4.5 : ratio >= 7;
  }
  
  return isLargeText ? ratio >= 3 : ratio >= 4.5;
}

/**
 * Test if element has focus indicator
 */
export function hasFocusIndicator(element: HTMLElement): boolean {
  const computedStyle = window.getComputedStyle(element, ':focus');
  const outlineWidth = computedStyle.outlineWidth;
  const outlineStyle = computedStyle.outlineStyle;
  
  return outlineStyle !== 'none' && outlineWidth !== '0px';
}

/**
 * Test if touch target is large enough (44x44px minimum)
 */
export function meetsTouchTargetSize(element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  return rect.width >= 44 && rect.height >= 44;
}

/**
 * Test if page has skip links
 */
export function hasSkipLinks(): boolean {
  const skipLinks = document.querySelectorAll('a[href^="#main"]');
  return skipLinks.length > 0;
}

/**
 * Test if page has proper heading hierarchy
 */
export function hasProperHeadingHierarchy(): { valid: boolean; errors: string[] } {
  const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
  const errors: string[] = [];
  
  if (headings.length === 0) {
    errors.push('No headings found on page');
    return { valid: false, errors };
  }
  
  // Check for h1
  const h1Count = headings.filter(h => h.tagName === 'H1').length;
  if (h1Count === 0) {
    errors.push('No H1 heading found');
  } else if (h1Count > 1) {
    errors.push(`Multiple H1 headings found (${h1Count})`);
  }
  
  // Check hierarchy
  let prevLevel = 0;
  headings.forEach((heading, index) => {
    const level = parseInt(heading.tagName.charAt(1));
    
    if (index > 0 && level > prevLevel + 1) {
      errors.push(`Heading level skipped: H${prevLevel} to H${level}`);
    }
    
    prevLevel = level;
  });
  
  return { valid: errors.length === 0, errors };
}

/**
 * Test if images have alt text
 */
export function imagesHaveAltText(): { valid: boolean; missing: number } {
  const images = Array.from(document.querySelectorAll('img'));
  const missing = images.filter(img => !img.hasAttribute('alt')).length;
  
  return { valid: missing === 0, missing };
}

/**
 * Test if form inputs have labels
 */
export function formInputsHaveLabels(): { valid: boolean; missing: number } {
  const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
  const missing = inputs.filter(input => {
    const id = input.id;
    if (!id) return true;
    
    const label = document.querySelector(`label[for="${id}"]`);
    const ariaLabel = input.getAttribute('aria-label');
    const ariaLabelledby = input.getAttribute('aria-labelledby');
    
    return !label && !ariaLabel && !ariaLabelledby;
  }).length;
  
  return { valid: missing === 0, missing };
}

/**
 * Run all accessibility tests
 */
export function runAccessibilityAudit(): {
  passed: number;
  failed: number;
  warnings: number;
  results: Array<{ test: string; status: 'pass' | 'fail' | 'warning'; message: string }>;
} {
  const results: Array<{ test: string; status: 'pass' | 'fail' | 'warning'; message: string }> = [];
  
  // Test skip links
  const skipLinksTest = hasSkipLinks();
  results.push({
    test: 'Skip Links',
    status: skipLinksTest ? 'pass' : 'warning',
    message: skipLinksTest ? 'Skip links found' : 'No skip links found',
  });
  
  // Test heading hierarchy
  const headingTest = hasProperHeadingHierarchy();
  results.push({
    test: 'Heading Hierarchy',
    status: headingTest.valid ? 'pass' : 'fail',
    message: headingTest.valid ? 'Proper heading hierarchy' : headingTest.errors.join(', '),
  });
  
  // Test images
  const imageTest = imagesHaveAltText();
  results.push({
    test: 'Image Alt Text',
    status: imageTest.valid ? 'pass' : 'fail',
    message: imageTest.valid ? 'All images have alt text' : `${imageTest.missing} images missing alt text`,
  });
  
  // Test form labels
  const formTest = formInputsHaveLabels();
  results.push({
    test: 'Form Labels',
    status: formTest.valid ? 'pass' : 'fail',
    message: formTest.valid ? 'All form inputs have labels' : `${formTest.missing} inputs missing labels`,
  });
  
  // Count results
  const passed = results.filter(r => r.status === 'pass').length;
  const failed = results.filter(r => r.status === 'fail').length;
  const warnings = results.filter(r => r.status === 'warning').length;
  
  return { passed, failed, warnings, results };
}

/**
 * Log accessibility audit to console
 */
export function logAccessibilityAudit(): void {
  const audit = runAccessibilityAudit();
  
  console.group('🔍 Accessibility Audit');
  console.log(`✅ Passed: ${audit.passed}`);
  console.log(`❌ Failed: ${audit.failed}`);
  console.log(`⚠️ Warnings: ${audit.warnings}`);
  console.log('\nDetails:');
  
  audit.results.forEach(result => {
    const icon = result.status === 'pass' ? '✅' : result.status === 'fail' ? '❌' : '⚠️';
    console.log(`${icon} ${result.test}: ${result.message}`);
  });
  
  console.groupEnd();
}
