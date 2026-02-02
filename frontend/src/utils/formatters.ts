/**
 * Number formatting utilities for financial data
 * Following design system specifications
 */

/**
 * Format currency with proper decimal places
 */
export const formatCurrency = (value: number, decimals = 2): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};

/**
 * Format percent with sign prefix
 */
export const formatPercent = (value: number | undefined | null, decimals = 2): string => {
  if (value === undefined || value === null) return '+0.00%';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

/**
 * Format large numbers with K/M suffixes
 */
export const formatNumber = (value: number): string => {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  return value.toFixed(2);
};

/**
 * Format price with variable decimals based on value
 */
export const formatPrice = (value: number): string => {
  if (value < 1) return value.toFixed(4);      // Penny stocks
  if (value < 10) return value.toFixed(3);
  return value.toFixed(2);
};

/**
 * Format P&L with sign and color indicator
 */
export const formatPnL = (value: number, decimals = 2): { 
  text: string; 
  isPositive: boolean 
} => {
  const sign = value >= 0 ? '+' : '';
  return {
    text: `${sign}${formatCurrency(value, decimals)}`,
    isPositive: value >= 0,
  };
};

/**
 * Format quantity (no decimal places for shares)
 */
export const formatQuantity = (value: number): string => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

/**
 * Format date/time for display in user's local timezone
 * Backend sends UTC timestamps, this converts to local time automatically
 */
export const formatDateTime = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  
  // Detect user's timezone automatically
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: userTimezone, // Use user's local timezone
    timeZoneName: 'short', // Show timezone abbreviation (e.g., PST, EST)
  }).format(d);
};

/**
 * Format date only in user's local timezone
 */
export const formatDate = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  
  // Detect user's timezone automatically
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: userTimezone,
  }).format(d);
};

/**
 * Format time only in user's local timezone
 */
export const formatTime = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  
  // Detect user's timezone automatically
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: userTimezone,
    timeZoneName: 'short',
  }).format(d);
};
