/**
 * Authentication Types
 * All types related to user authentication, login, registration
 */

export interface LoginRequest {
  username: string;  // Backend expects 'username', which is the email address
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  permissions?: string[];
}

export type UserRole = 'admin' | 'trader' | 'viewer' | 'risk_manager';

export interface TokenRefreshRequest {
  refresh_token: string;
}

export interface TokenRefreshResponse {
  access_token: string;
  token_type: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}
