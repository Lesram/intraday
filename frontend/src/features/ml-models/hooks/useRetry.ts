import { useState, useCallback } from 'react';
import { message } from 'antd';

interface UseRetryOptions {
  maxRetries?: number;
  retryDelay?: number;
  onRetry?: (attempt: number) => void;
  onMaxRetriesReached?: () => void;
}

interface UseRetryReturn<T> {
  execute: (fn: () => Promise<T>) => Promise<T | null>;
  isRetrying: boolean;
  retryCount: number;
  reset: () => void;
}

/**
 * Custom hook for retry logic with exponential backoff
 * Automatically retries failed operations
 */
export const useRetry = <T = unknown>(
  options: UseRetryOptions = {}
): UseRetryReturn<T> => {
  const {
    maxRetries = 3,
    retryDelay = 1000,
    onRetry,
    onMaxRetriesReached,
  } = options;

  const [isRetrying, setIsRetrying] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  const reset = useCallback(() => {
    setIsRetrying(false);
    setRetryCount(0);
  }, []);

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const execute = useCallback(
    async (fn: () => Promise<T>): Promise<T | null> => {
      let currentAttempt = 0;

      while (currentAttempt <= maxRetries) {
        try {
          const result = await fn();
          reset();
          return result;
        } catch (error) {
          currentAttempt++;
          setRetryCount(currentAttempt);

          if (currentAttempt > maxRetries) {
            setIsRetrying(false);
            message.error(`Failed after ${maxRetries} attempts. Please try again later.`);
            
            if (onMaxRetriesReached) {
              onMaxRetriesReached();
            }
            
            throw error;
          }

          // Exponential backoff: 1s, 2s, 4s, etc.
          const delay = retryDelay * Math.pow(2, currentAttempt - 1);
          
          setIsRetrying(true);
          message.warning(`Retry attempt ${currentAttempt}/${maxRetries}...`);

          if (onRetry) {
            onRetry(currentAttempt);
          }

          await sleep(delay);
        }
      }

      return null;
    },
    [maxRetries, retryDelay, onRetry, onMaxRetriesReached, reset]
  );

  return {
    execute,
    isRetrying,
    retryCount,
    reset,
  };
};

/**
 * Helper hook for retrying with custom condition
 */
export const useConditionalRetry = <T = unknown>(
  shouldRetry: (error: unknown) => boolean,
  options: UseRetryOptions = {}
): UseRetryReturn<T> => {
  const retry = useRetry<T>(options);

  const conditionalExecute = useCallback(
    async (fn: () => Promise<T>): Promise<T | null> => {
      try {
        return await retry.execute(fn);
      } catch (error) {
        if (!shouldRetry(error)) {
          // Don't retry if condition not met
          throw error;
        }
        return null;
      }
    },
    [retry, shouldRetry]
  );

  return {
    ...retry,
    execute: conditionalExecute,
  };
};
