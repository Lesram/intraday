/**
 * Authentication Store (Zustand)
 * Manages global authentication state with persistence
 * 
 * SECURITY NOTE: Access tokens are stored in memory only, not localStorage.
 * The existing refresh token is persisted in sessionStorage; it is still
 * JavaScript-accessible. This change does not introduce a cookie architecture.
 */

import axios from 'axios';
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

let sessionEpoch = 0;
let restoration: { epoch: number; controller: AbortController; promise: Promise<void> } | null = null;
const invalidateRestoration = () => {
  sessionEpoch += 1;
  restoration?.controller.abort();
  restoration = null;
};

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  tokenExpiresAt: number | null;
  sessionReady: boolean;
  restoreSession: () => Promise<void>;
  
  // Actions
  setAuth: (user: User, accessToken: string, refreshToken: string, expiresIn?: number) => void;
  clearAuth: () => void;
  updateUser: (user: Partial<User>) => void;
  setAccessToken: (token: string, expiresIn?: number) => void;
  setRefreshToken: (token: string) => void;
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
      sessionReady: false,

      restoreSession: () => {
        const owner = get();
        if (owner.sessionReady) return Promise.resolve();
        if (owner.isAuthenticated !== true || typeof owner.user?.id !== 'string' || !owner.user.id
            || typeof owner.refreshToken !== 'string' || !owner.refreshToken.trim()) {
          get().clearAuth();
          return Promise.resolve();
        }
        if (restoration?.epoch === sessionEpoch) return restoration.promise;
        const epoch = sessionEpoch;
        const ownerId = owner.user.id;
        const controller = new AbortController();
        const sameOwner = () => {
          const current = get();
          return sessionEpoch === epoch && !current.sessionReady
            && current.user?.id === ownerId && current.refreshToken === owner.refreshToken
            && current.accessToken === owner.accessToken;
        };
        const pending = { epoch, controller, promise: Promise.resolve() };
        restoration = pending;
        pending.promise = (async () => {
          const timer = setTimeout(() => {
            controller.abort();
            // Clear readiness even if a transport/import ignores cancellation.
            if (sameOwner()) get().clearAuth();
          }, 30000);
          try {
            const base = import.meta.env.VITE_API_BASE_URL || window.location.origin;
            const options = { timeout: 30000, signal: controller.signal };
            // Direct client avoids recursively invoking the normal 401 refresh queue.
            const response = await axios.post(`${base}/api/v1/auth/token/refresh`, {
              refresh_token: owner.refreshToken,
            }, options);
            if (!sameOwner()) return;
            const { access_token, refresh_token } = response.data;
            if (typeof access_token !== 'string' || !access_token.trim()
                || typeof refresh_token !== 'string' || !refresh_token.trim()) {
              throw new Error('Invalid restored session');
            }
            const me = (await axios.get(`${base}/api/v1/auth/me`, {
              ...options, headers: { Authorization: `Bearer ${access_token}` },
            })).data;
            if (!sameOwner()) return;
            if (me?.authenticated !== true || me.is_active !== true
                || me.user_id !== ownerId || me.username !== ownerId) {
              throw new Error('Restored session principal mismatch');
            }
            const { normalizeLoginResponse } = await import('@/services/authService');
            if (!sameOwner()) return;
            const verified = normalizeLoginResponse({
              access_token, refresh_token, user_id: me.user_id,
              user: { username: me.username, roles: me.roles },
            });
            get().setAuth(verified.user, verified.access_token, verified.refresh_token, verified.expires_in);
          } catch {
            // A stale completion must never clear or resurrect a replacement session.
            if (sameOwner()) get().clearAuth();
          } finally {
            clearTimeout(timer);
            if (restoration === pending) restoration = null;
          }
        })();
        return pending.promise;
      },

      setAuth: (user, accessToken, refreshToken, expiresIn = 3600) => {
        invalidateRestoration();
        const expiresAt = Date.now() + (expiresIn * 1000);
        
        // Access token and expiry remain in memory; only the existing
        // refresh-token/identity fields below are persisted in sessionStorage.
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
          tokenExpiresAt: expiresAt,
          sessionReady: true,
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
        invalidateRestoration();
        // Clear authStore
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          tokenExpiresAt: null,
          sessionReady: true,
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

      setRefreshToken: (token) => {
        set({ refreshToken: token });
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
      // Persisted metadata never constitutes a current authenticated session.
      merge: (persisted, current) => {
        const saved = persisted as Partial<AuthState> | null;
        return {
          ...current,
          user: saved?.user ?? null,
          refreshToken: typeof saved?.refreshToken === 'string' ? saved.refreshToken : null,
          isAuthenticated: saved?.isAuthenticated === true,
          accessToken: null, tokenExpiresAt: null, sessionReady: false,
        };
      },
      // Keep access tokens, expiry and readiness in memory only.
      // Existing refresh-token storage is retained for bounded restoration.
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
