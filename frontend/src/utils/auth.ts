/**
 * Authentication Token Utility
 * 
 * Centralized token access for the entire application.
 * ALL components must use this instead of direct localStorage access.
 * 
 * SECURITY: Tokens are stored in Zustand (memory/sessionStorage),
 * NOT in localStorage, to protect against XSS attacks.
 */

import { useAuthStore } from '@/store/authStore';

/**
 * Get the current authentication token
 * 
 * This function provides a single source of truth for accessing the auth token.
 * It reads from the Zustand auth store, which keeps tokens in memory.
 * 
 * @returns The JWT access token, or null if not authenticated
 * 
 * @example
 * ```typescript
 * const token = getAuthToken();
 * if (token) {
 *   headers['Authorization'] = `Bearer ${token}`;
 * }
 * ```
 */
export function getAuthToken(): string | null {
  return useAuthStore.getState().accessToken;
}

/**
 * Check if user is authenticated with a valid (non-expired) token
 * 
 * @returns True if user has a valid, non-expired token
 */
export function isAuthenticated(): boolean {
  const store = useAuthStore.getState();
  return store.isAuthenticated && 
         !!store.accessToken && 
         !store.isTokenExpired();
}

/**
 * Get authorization headers for API calls
 * 
 * @returns Object with Authorization header if authenticated, empty object otherwise
 * 
 * @example
 * ```typescript
 * const response = await fetch('/api/endpoint', {
 *   headers: {
 *     'Content-Type': 'application/json',
 *     ...getAuthHeaders(),
 *   },
 * });
 * ```
 */
export function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

/**
 * DEPRECATED: This function is no longer used.
 * Tokens should not be stored in localStorage for security reasons.
 * 
 * @deprecated Use setAuth from useAuthStore instead
 */
export function storeLegacyToken(_token: string): void {
  console.warn(
    '[DEPRECATED] storeLegacyToken is deprecated and does nothing. ' +
    'Use useAuthStore.getState().setAuth() instead.'
  );
}

/**
 * Clear any legacy token storage from previous versions.
 * Called during logout to ensure complete cleanup.
 */
export function clearLegacyTokens(): void {
  try {
    localStorage.removeItem('token');
    localStorage.removeItem('auth_token');
    localStorage.removeItem('access_token');
  } catch {
    // Ignore localStorage errors in SSR or when blocked
  }
}
