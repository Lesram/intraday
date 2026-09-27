import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { authService } from './authService';
import { apiClient } from './api';
import { useAuthStore } from '@/store/authStore';
import { usePortfolioStore } from '@/store/portfolioStore';
import { usePortfolio } from '@/hooks/useData';
import { portfolioFixture } from '@/test/portfolioFixture';
import { useLogin } from '@/hooks/useAuth';
const loginEffects = vi.hoisted(() => ({ navigate: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => loginEffects.navigate }));
vi.mock('antd', () => ({ App: { useApp: () => ({ message: loginEffects }) } }));
vi.mock('./api', () => ({
  apiClient: { post: vi.fn(), get: vi.fn() },
  handleApiError: () => 'Invalid authenticated user response',
}));
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
  { access_token: 'synthetic', user: {}, refresh_token: 'synthetic-refresh' },
  { access_token: 'synthetic', refresh_token: 'synthetic-refresh', user_id: 'alice', user: { username: 'bob', roles: [] } },
  { access_token: 'synthetic', refresh_token: 'synthetic-refresh', user: { username: 'alice', roles: 'admin' } },
])('rejects invalid principal rather than inventing user identity', async (data) => {
  vi.mocked(apiClient.post).mockResolvedValue({ data });
  await expect(authService.login({ username: 'alice', password: 'synthetic' })).rejects.toThrow('Invalid authenticated user');
});

const loginResponses = {
  full: () => ({
    access_token: 'synthetic-access', refresh_token: 'synthetic-refresh',
    token_type: 'bearer', expires_in: 3600,
    user: { id: 'alice', email: 'alice', name: 'Alice', role: 'viewer',
      is_active: true, created_at: '2026-09-27T00:00:00Z' },
  }),
  backend: () => ({
    access_token: 'synthetic-access', refresh_token: 'synthetic-refresh',
    token_type: 'bearer', expires_in: 3600,
    user_id: 'alice', user: { username: 'alice', roles: ['viewer'] },
  }),
};
const malformedTokens = [
  ['missing', undefined], ['null', null], ['number', 42], ['boolean', true],
  ['object', { value: 'synthetic' }], ['array', ['synthetic']],
  ['empty', ''], ['whitespace', ' \t\n '],
] as const;

for (const [shape, response] of Object.entries(loginResponses)) {
  for (const field of ['access_token', 'refresh_token']) {
    it.each(malformedTokens)(`${shape} login rejects ${field} that is %s`, async (kind, value) => {
      const data: Record<string, unknown> = response();
      if (kind === 'missing') delete data[field];
      else data[field] = value;
      vi.mocked(apiClient.post).mockResolvedValue({ data });
      await expect(authService.login({ username: 'alice', password: 'synthetic' }))
        .rejects.toThrow('Invalid authenticated user response');
    });
  }

  it(`${shape} login preserves valid credentials and principal`, async () => {
    const raw = response();
    vi.mocked(apiClient.post).mockResolvedValue({ data: raw });
    const data = await authService.login({ username: 'alice', password: 'synthetic' });
    expect(data.access_token).toBe(raw.access_token);
    expect(data.refresh_token).toBe(raw.refresh_token);
    expect(data.user.id).toBe('alice');
    expect(data.user.role).toBe('viewer');
  });

  it.each(['access_token', 'refresh_token'])(`${shape} malformed %s never authenticates the login hook`, async (field) => {
    useAuthStore.getState().clearAuth();
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ...response(), [field]: null } });
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result, unmount } = renderHook(useLogin, { wrapper });
    try {
      await act(async () => {
        await expect(result.current.mutateAsync({ username: 'alice', password: 'synthetic' }))
          .rejects.toThrow('Invalid authenticated user response');
      });
      expect(useAuthStore.getState()).toMatchObject({
        user: null, accessToken: null, refreshToken: null, isAuthenticated: false,
      });
      expect(loginEffects.navigate).not.toHaveBeenCalled();
      expect(loginEffects.success).not.toHaveBeenCalled();
      expect(loginEffects.error).toHaveBeenCalledOnce();
    } finally {
      unmount(); client.clear();
    }
  });

  it(`${shape} valid login authenticates and navigates`, async () => {
    useAuthStore.getState().clearAuth();
    vi.mocked(apiClient.post).mockResolvedValue({ data: response() });
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result, unmount } = renderHook(useLogin, { wrapper });
    try {
      await act(async () => { await result.current.mutateAsync({ username: 'alice', password: 'synthetic' }); });
      expect(useAuthStore.getState()).toMatchObject({
        accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh', isAuthenticated: true,
        user: { id: 'alice', role: 'viewer' },
      });
      expect(loginEffects.navigate).toHaveBeenCalledWith('/');
      expect(loginEffects.success).toHaveBeenCalledOnce();
      expect(loginEffects.error).not.toHaveBeenCalled();
    } finally {
      unmount(); client.clear();
    }
  });
}

it.each([
  [['admin'], 'admin'], [['trader'], 'trader'], [['risk_manager'], 'risk_manager'],
  [['risk-manager'], 'risk_manager'], [['viewer'], 'viewer'], [['paper_monitor'], 'viewer'],
])('preserves valid backend roles %j as %s', async (roles, expected) => {
  vi.mocked(apiClient.post).mockResolvedValue({ data: {
    ...loginResponses.backend(), user: { username: 'alice', roles },
  } });
  const data = await authService.login({ username: 'alice', password: 'synthetic' });
  expect(data.user.role).toBe(expected);
  expect(data.user.permissions).toEqual(roles);
});
