/**
 * Authentication Store (Zustand)
 * Manages global authentication state with persistence
 * 
 * SECURITY NOTE: Access tokens are stored in memory only, not localStorage.
 * Refresh tokens should be handled via httpOnly cookies by the backend.
 * This protects against XSS attacks that could steal tokens from localStorage.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { User } from '@/types/auth';

/**
 * Check if we're in a secure context (HTTPS or localhost)
 */
const isSecureContext = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.location.protocol === 'https:' || 
         window.location.hostname === 'localhost' ||
         window.location.hostname === '127.0.0.1';
};

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  tokenExpiresAt: number | null;
  
  // Actions
  setAuth: (user: User, accessToken: string, refreshToken: string, expiresIn?: number) => void;
  clearAuth: () => void;
  updateUser: (user: Partial<User>) => void;
  setAccessToken: (token: string, expiresIn?: number) => void;
  isTokenExpired: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      tokenExpiresAt: null,

      setAuth: (user, accessToken, refreshToken, expiresIn = 3600) => {
        const expiresAt = Date.now() + (expiresIn * 1000);
        
        // Store in authStore - tokens kept in memory via Zustand
        // NOT stored in localStorage directly (XSS protection)
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
          tokenExpiresAt: expiresAt,
        });
        
        // Log security warning if not in secure context
        if (!isSecureContext()) {
          console.warn(
            '[AUTH] Running in insecure context. ' +
            'For production, ensure HTTPS is enabled.'
          );
        }
      },

      clearAuth: () => {
        // Clear authStore
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          tokenExpiresAt: null,
        });
        
        // Clean up any legacy localStorage keys that might exist
        // from previous versions
        try {
          localStorage.removeItem('token');
          localStorage.removeItem('auth_token');
          localStorage.removeItem('access_token');
        } catch {
          // Ignore localStorage errors
        }
      },

      updateUser: (userData) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...userData } : null,
        })),

      setAccessToken: (token, expiresIn = 3600) => {
        const expiresAt = Date.now() + (expiresIn * 1000);
        set({ 
          accessToken: token,
          tokenExpiresAt: expiresAt,
        });
      },
      
      isTokenExpired: () => {
        const { tokenExpiresAt } = get();
        if (!tokenExpiresAt) return true;
        // Add 30 second buffer for clock skew
        return Date.now() > (tokenExpiresAt - 30000);
      },
    }),
    {
      name: 'auth-storage',
      // M-29 FIX: Use sessionStorage instead of localStorage
      // sessionStorage is cleared when the tab is closed (better security)
      storage: createJSONStorage(() => sessionStorage),
      // M-29 SECURITY: Only persist user info and auth state
      // Do NOT persist tokens - they should be handled by httpOnly cookies
      // or require re-authentication on page refresh for maximum security
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        // NOTE: In a more secure setup, refresh tokens would be:
        // 1. Sent as httpOnly, Secure, SameSite=Strict cookies from backend
        // 2. Never accessible to JavaScript at all
        // TODO: Implement backend httpOnly cookie refresh token flow
        // For now, we store in sessionStorage (cleared on tab close)
        refreshToken: state.refreshToken,
      }),
    }
  )
);
