/**
 * Frontend Logger Utility
 * 
 * Provides environment-aware logging that:
 * - Logs in development mode
 * - Silences verbose logs in production
 * - Always logs errors
 */

const isDevelopment = import.meta.env.DEV || import.meta.env.MODE === 'development';

export const logger = {
  /**
   * Debug log - only in development
   */
  debug: (...args: unknown[]) => {
    if (isDevelopment) {
      console.log(...args);
    }
  },

  /**
   * Info log - only in development  
   */
  info: (...args: unknown[]) => {
    if (isDevelopment) {
      console.log(...args);
    }
  },

  /**
   * Warning log - always shown
   */
  warn: (...args: unknown[]) => {
    console.warn(...args);
  },

  /**
   * Error log - always shown
   */
  error: (...args: unknown[]) => {
    console.error(...args);
  },
};

export default logger;
