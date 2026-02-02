/**
 * React Query hook for pre-trade order validation
 * 
 * Calls POST /api/v1/orders/validate to validate an order before submission
 * Provides loading, error, and success states for UI feedback
 * 
 * Usage:
 * ```tsx
 * const validation = usePreTradeValidation();
 * 
 * const handlePreview = () => {
 *   validation.mutate({
 *     symbol: 'AAPL',
 *     side: 'buy',
 *     quantity: 10,
 *     orderType: 'market'
 *   });
 * };
 * 
 * if (validation.isSuccess) {
 *   // Show validation results
 *   console.log(validation.data.valid);
 * }
 * ```
 */

import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/services/api';
import type { 
  OrderValidationRequest, 
  OrderValidationResponse 
} from '@/types/trading';

/**
 * Hook for pre-trade order validation
 * 
 * @returns React Query mutation object with validation state
 */
export const usePreTradeValidation = () => {
  return useMutation({
    mutationKey: ['validateOrder'],
    
    mutationFn: async (data: OrderValidationRequest): Promise<OrderValidationResponse> => {
      try {
        // POST to validation endpoint
        const response = await apiClient.post<OrderValidationResponse>(
          '/orders/validate',
          data
        );
        
        return response.data;
      } catch (error: unknown) {
        const err = error as { response?: { data?: { detail?: string }; message?: string } };
        // Handle API errors gracefully
        console.error('Order validation failed:', error);
        
        // If we have a response with validation data, return it
        if (err.response?.data) {
          return err.response.data as OrderValidationResponse;
        }
        
        // Otherwise, create a system error response
        throw new Error(
          err.response?.data?.detail || 
          err.response?.message || 
          'Failed to validate order. Please try again.'
        );
      }
    },
    
    // Don't retry validation requests (they're fast and deterministic)
    retry: false,
    
    // Cache validation results briefly (30 seconds)
    // This prevents redundant calls if user clicks preview multiple times quickly
    gcTime: 30000,
  });
};

/**
 * Hook for pre-trade validation with callbacks
 * Convenience wrapper that adds onSuccess and onError handlers
 * 
 * @param options - Success and error callbacks
 * @returns React Query mutation object
 */
export const usePreTradeValidationWithCallbacks = (options?: {
  onSuccess?: (data: OrderValidationResponse) => void;
  onError?: (error: Error) => void;
}) => {
  return useMutation({
    mutationKey: ['validateOrder'],
    
    mutationFn: async (data: OrderValidationRequest): Promise<OrderValidationResponse> => {
      const response = await apiClient.post<OrderValidationResponse>(
        '/orders/validate',
        data
      );
      return response.data;
    },
    
    retry: false,
    gcTime: 30000,
    
    onSuccess: options?.onSuccess,
    onError: options?.onError,
  });
};
