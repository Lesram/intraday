import { useState, useCallback } from 'react';
import { message } from 'antd';
import { AxiosError } from 'axios';

interface ErrorState {
  message: string;
  code?: string;
  details?: unknown;
}

interface UseErrorHandlerReturn {
  error: ErrorState | null;
  setError: (error: ErrorState | null) => void;
  clearError: () => void;
  handleError: (error: unknown) => void;
  isError: boolean;
}

/**
 * Custom hook for centralized error handling
 * Provides consistent error messaging and logging
 */
export const useErrorHandler = (): UseErrorHandlerReturn => {
  const [error, setError] = useState<ErrorState | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const handleError = useCallback((err: unknown) => {
    console.error('Error occurred:', err);

    let errorState: ErrorState;

    // Handle Axios errors (API calls)
    if (err instanceof AxiosError) {
      const status = err.response?.status;
      const data = err.response?.data;

      switch (status) {
        case 400:
          errorState = {
            message: data?.detail || 'Invalid request. Please check your input.',
            code: 'BAD_REQUEST',
            details: data,
          };
          break;

        case 401:
          errorState = {
            message: 'Your session has expired. Please log in again.',
            code: 'UNAUTHORIZED',
            details: data,
          };
          // Redirect to login
          setTimeout(() => {
            window.location.href = '/login';
          }, 2000);
          break;

        case 403:
          errorState = {
            message: 'You do not have permission to perform this action.',
            code: 'FORBIDDEN',
            details: data,
          };
          break;

        case 404:
          errorState = {
            message: data?.detail || 'The requested resource was not found.',
            code: 'NOT_FOUND',
            details: data,
          };
          break;

        case 409:
          errorState = {
            message: data?.detail || 'A conflict occurred. Please try again.',
            code: 'CONFLICT',
            details: data,
          };
          break;

        case 422:
          errorState = {
            message: 'Validation error. Please check your input.',
            code: 'VALIDATION_ERROR',
            details: data,
          };
          break;

        case 429:
          errorState = {
            message: 'Too many requests. Please wait a moment and try again.',
            code: 'RATE_LIMIT',
            details: data,
          };
          break;

        case 500:
        case 502:
        case 503:
        case 504:
          errorState = {
            message: 'Server error. Please try again later.',
            code: 'SERVER_ERROR',
            details: data,
          };
          break;

        default:
          errorState = {
            message: data?.detail || err.message || 'An unexpected error occurred.',
            code: 'UNKNOWN_ERROR',
            details: data,
          };
      }

      // Show user-friendly message
      message.error(errorState.message);
    }
    // Handle network errors
    else if (err instanceof Error) {
      if (err.message === 'Network Error') {
        errorState = {
          message: 'Network error. Please check your internet connection.',
          code: 'NETWORK_ERROR',
        };
      } else if (err.message.includes('timeout')) {
        errorState = {
          message: 'Request timed out. Please try again.',
          code: 'TIMEOUT',
        };
      } else {
        errorState = {
          message: err.message || 'An unexpected error occurred.',
          code: 'UNKNOWN_ERROR',
        };
      }

      message.error(errorState.message);
    }
    // Handle unknown errors
    else {
      errorState = {
        message: 'An unexpected error occurred.',
        code: 'UNKNOWN_ERROR',
        details: err,
      };

      message.error(errorState.message);
    }

    setError(errorState);

    // Log to error tracking service in production
    if (process.env.NODE_ENV === 'production') {
      // TODO: Send to error tracking service
      // logErrorToService(errorState);
    }
  }, []);

  return {
    error,
    setError,
    clearError,
    handleError,
    isError: error !== null,
  };
};

/**
 * Helper function to get user-friendly error message
 */
export const getErrorMessage = (error: unknown): string => {
  if (error instanceof AxiosError) {
    return error.response?.data?.detail || error.message || 'An error occurred';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
};

/**
 * Helper function to check if error is retryable
 */
export const isRetryableError = (error: unknown): boolean => {
  if (error instanceof AxiosError) {
    const status = error.response?.status;
    // Retry on network errors, timeouts, and 5xx errors
    return !status || status >= 500 || error.code === 'ECONNABORTED';
  }
  return false;
};
