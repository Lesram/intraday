import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { authService } from './authService';
import { apiClient } from './api';
import { useAuthStore } from '@/store/authStore';
import { usePortfolioStore } from '@/store/portfolioStore';
import { usePortfolio } from '@/hooks/useData';
import { portfolioFixture } from '@/test/portfolioFixture';
vi.mock('./api', () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }));
afterEach(() => { vi.clearAllMocks(); useAuthStore.getState().clearAuth(); usePortfolioStore.getState().reset(); });
it('actual backend LoginResponse normalizes principal through auth store and portfolio query', async () => {
  vi.mocked(apiClient.post).mockResolvedValue({ data: {
    access_token: 'synthetic', refresh_token: 'synthetic-refresh', token_type: 'bearer', expires_in: 3600,
    user_id: 'alice', user: { username: 'alice', roles: ['viewer'] },
  } });
  const data = await authService.login({ username: 'alice', password: 'synthetic' });
  expect(data.user.id).toBe('alice'); expect(data.user.role).toBe('viewer');
  useAuthStore.getState().setAuth(data.user, data.access_token, data.refresh_token, data.expires_in);
  vi.mocked(apiClient.get).mockResolvedValue({ data: portfolioFixture() });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, unmount } = renderHook(usePortfolio, { wrapper });
  await waitFor(() => expect(result.current.data?.userId).toBe('alice'));
  expect(result.current.data?.totalEquity).toBe(102000); expect(apiClient.get).toHaveBeenCalledWith('/portfolio');
  unmount(); client.clear();
});
it.each([
  { access_token: 'synthetic', user: {}, refresh_token: '' },
  { access_token: 'synthetic', user_id: 'alice', user: { username: 'bob', roles: [] } },
  { access_token: 'synthetic', user: { username: 'alice', roles: 'admin' } },
])('rejects invalid principal rather than inventing user identity', async (data) => {
  vi.mocked(apiClient.post).mockResolvedValue({ data });
  await expect(authService.login({ username: 'alice', password: 'synthetic' })).rejects.toThrow('Invalid authenticated user');
});
