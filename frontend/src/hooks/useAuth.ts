/**
 * Authentication Hooks
 * React Query hooks for authentication operations
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { App } from 'antd';
import { authService } from '@/services/authService';
import { useAuthStore } from '@/store/authStore';
import { handleApiError } from '@/services/api';

/**
 * Login mutation hook
 */
export const useLogin = () => {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: authService.login,
    onSuccess: (data) => {
      // Some backends may not provide refresh_token/expires_in; authService normalizes.
      const expiresIn = (data as any).expires_in as number | undefined;
      setAuth(data.user, data.access_token, data.refresh_token, expiresIn);
      message.success(`Welcome back, ${data.user.name ?? data.user.email}!`);
      navigate('/');
    },
    onError: (error) => {
      const errorMessage = handleApiError(error);
      message.error(errorMessage);
    },
  });
};

/**
 * Register mutation hook
 */
export const useRegister = () => {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: authService.register,
    onSuccess: (data) => {
      setAuth(data.user, data.access_token, data.refresh_token);
      message.success(`Welcome, ${data.user.name}! Your account has been created.`);
      navigate('/');
    },
    onError: (error) => {
      const errorMessage = handleApiError(error);
      message.error(errorMessage);
    },
  });
};

/**
 * Logout mutation hook
 */
export const useLogout = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: authService.logout,
    onSuccess: () => {
      clearAuth();
      queryClient.clear(); // Clear all cached queries
      message.success('Logged out successfully');
      navigate('/login');
    },
    onError: (error) => {
      // Even if API call fails, clear local state
      clearAuth();
      queryClient.clear();
      const errorMessage = handleApiError(error);
      message.warning(`Logged out locally: ${errorMessage}`);
      navigate('/login');
    },
  });
};

/**
 * Get current user query hook
 */
export const useCurrentUser = () => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const updateUser = useAuthStore((state) => state.updateUser);

  const query = useQuery({
    queryKey: ['currentUser'],
    queryFn: authService.getCurrentUser,
    enabled: isAuthenticated, // Only fetch if authenticated
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });

  // Update user in store when data changes - use useEffect to avoid setState during render
  useEffect(() => {
    if (query.data) {
      updateUser(query.data);
    }
  }, [query.data, updateUser]);

  return query;
};

/**
 * Password change mutation hook
 */
export const useChangePassword = () => {
  const { message } = App.useApp();

  return useMutation({
    mutationFn: ({ currentPassword, newPassword }: { currentPassword: string; newPassword: string }) =>
      authService.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      message.success('Password changed successfully');
    },
    onError: (error) => {
      const errorMessage = handleApiError(error);
      message.error(errorMessage);
    },
  });
};

/**
 * Password reset request mutation hook
 */
export const useRequestPasswordReset = () => {
  const { message } = App.useApp();

  return useMutation({
    mutationFn: authService.requestPasswordReset,
    onSuccess: () => {
      message.success('Password reset email sent. Please check your inbox.');
    },
    onError: (error) => {
      const errorMessage = handleApiError(error);
      message.error(errorMessage);
    },
  });
};

/**
 * Password reset confirm mutation hook
 */
export const useConfirmPasswordReset = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: authService.confirmPasswordReset,
    onSuccess: () => {
      message.success('Password reset successfully. You can now login with your new password.');
      navigate('/login');
    },
    onError: (error) => {
      const errorMessage = handleApiError(error);
      message.error(errorMessage);
    },
  });
};
