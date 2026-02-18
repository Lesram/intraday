/**
 * Authentication Service
 * API calls for authentication operations
 */

import { apiClient } from './api';
import type {
  LoginRequest,
  RegisterRequest,
  AuthResponse,
  User,
  TokenRefreshRequest,
  TokenRefreshResponse,
  PasswordResetRequest,
  PasswordResetConfirm,
} from '@/types/auth';

type BackendLoginResponse = {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user_id?: string | null;
  refresh_token?: string; // M-30 FIX: Added to avoid 'as any' cast
  user?: {
    username?: string;
    roles?: string[];
  } | null;
};

const derivePrimaryRole = (roles: string[] | undefined): User['role'] => {
  const normalized = (roles ?? []).map((r) => String(r).toLowerCase());
  if (normalized.includes('admin')) return 'admin';
  if (normalized.includes('trader')) return 'trader';
  if (normalized.includes('risk_manager') || normalized.includes('risk-manager')) return 'risk_manager';
  return 'viewer';
};

const normalizeLoginResponse = (raw: unknown): AuthResponse => {
  // M-30 FIX: Use type guard to avoid 'as any' casts
  const isFullAuthResponse = (obj: unknown): obj is AuthResponse => {
    return (
      obj !== null &&
      typeof obj === 'object' &&
      'access_token' in obj &&
      'user' in obj &&
      'refresh_token' in obj
    );
  };

  // If backend already matches the frontend contract, return it.
  if (isFullAuthResponse(raw)) {
    return raw;
  }

  const data = raw as BackendLoginResponse;
  const username =
    data?.user?.username ||
    data?.user_id ||
    'unknown@example.com';

  const roles = data?.user?.roles ?? [];
  const role = derivePrimaryRole(roles);
  const name = username.includes('@') ? username.split('@')[0] : username;

  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token || '', // M-30 FIX: Use typed property
    token_type: data.token_type ?? 'bearer',
    expires_in: data.expires_in ?? 3600,
    user: {
      id: username,
      email: username,
      name,
      role,
      is_active: true,
      created_at: new Date().toISOString(),
      permissions: roles,
    },
  };
};

export const authService = {
  /**
   * Login with email and password
   */
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/login', credentials);
    return normalizeLoginResponse(response.data);
  },

  /**
   * Register a new user
   */
  register: async (data: RegisterRequest): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/register', data);
    // Backend registration currently does not return tokens; keep shape consistent.
    return normalizeLoginResponse(response.data);
  },

  /**
   * Logout current user
   */
  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout');
  },

  /**
   * Get current authenticated user
   */
  getCurrentUser: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },

  /**
   * Refresh access token using refresh token
   */
  refreshToken: async (data: TokenRefreshRequest): Promise<TokenRefreshResponse> => {
    const response = await apiClient.post<TokenRefreshResponse>('/auth/token/refresh', data);
    return response.data;
  },

  /**
   * Validate a token
   */
  validateToken: async (_token: string): Promise<boolean> => {
    try {
      const response = await apiClient.post('/auth/token/validate');
      return response.data.valid;
    } catch {
      return false;
    }
  },

  /**
   * Request password reset email
   */
  requestPasswordReset: async (data: PasswordResetRequest): Promise<void> => {
    await apiClient.post('/auth/password-reset/request', data);
  },

  /**
   * Confirm password reset with token
   */
  confirmPasswordReset: async (data: PasswordResetConfirm): Promise<void> => {
    await apiClient.post('/auth/password-reset/confirm', data);
  },

  /**
   * Change password for authenticated user
   */
  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await apiClient.post('/auth/password-change', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },
};
