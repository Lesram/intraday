/**
 * Timezone utilities for consistent date/time handling across the application
 * 
 * Backend sends all timestamps in UTC format (ISO 8601)
 * Frontend automatically converts to user's local timezone
 */

/**
 * Get the user's detected timezone
 * @returns IANA timezone string (e.g., "America/New_York", "Europe/London")
 */
export const getUserTimezone = (): string => {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
};

/**
 * Get the user's timezone offset in hours
 * @returns Offset in hours (e.g., -5 for EST, +1 for CET)
 */
export const getTimezoneOffset = (date: Date = new Date()): number => {
  return -date.getTimezoneOffset() / 60;
};

/**
 * Get timezone abbreviation (e.g., "PST", "EST", "GMT")
 */
export const getTimezoneAbbreviation = (date: Date = new Date()): string => {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZoneName: 'short',
    timeZone: getUserTimezone(),
  });
  
  const parts = formatter.formatToParts(date);
  const timeZonePart = parts.find(part => part.type === 'timeZoneName');
  
  return timeZonePart?.value || 'UTC';
};

/**
 * Convert UTC timestamp to user's local timezone
 * @param utcDate UTC date string or Date object
 * @returns Date object in user's local timezone
 */
export const utcToLocal = (utcDate: string | Date): Date => {
  return typeof utcDate === 'string' ? new Date(utcDate) : utcDate;
};

/**
 * Format date in user's timezone with full context
 * @param date Date to format
 * @returns Formatted string like "Oct 14, 2025, 3:30:45 PM PST"
 */
export const formatWithTimezone = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: getUserTimezone(),
    timeZoneName: 'short',
  }).format(d);
};

/**
 * Get user-friendly timezone info for display
 * @returns Object with timezone details
 */
export const getTimezoneInfo = () => {
  const now = new Date();
  return {
    timezone: getUserTimezone(),
    abbreviation: getTimezoneAbbreviation(now),
    offset: getTimezoneOffset(now),
    offsetString: `UTC${getTimezoneOffset(now) >= 0 ? '+' : ''}${getTimezoneOffset(now)}`,
  };
};

/**
 * Check if a timezone is different from ET (market timezone)
 * @returns true if user is not in ET timezone
 */
export const isDifferentFromMarketTimezone = (): boolean => {
  const userTz = getUserTimezone();
  // Market timezone is America/New_York (Eastern Time)
  return !userTz.includes('New_York') && !userTz.includes('America/Toronto');
};
