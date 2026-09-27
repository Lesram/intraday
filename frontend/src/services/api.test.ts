import axios, { AxiosError } from 'axios';
import { afterEach, expect, it, vi } from 'vitest';
import { apiClient } from './api';
import { useAuthStore } from '@/store/authStore';
const user = { id: 'alice', email: '', name: 'Alice', role: 'viewer' as const, is_active: true, created_at: '' };
const originalAdapter = apiClient.defaults.adapter;
afterEach(() => { apiClient.defaults.adapter = originalAdapter; vi.restoreAllMocks(); useAuthStore.getState().clearAuth(); });
it('concurrent 401 without refresh settle, and later login can refresh and retry', async () => {
  useAuthStore.setState({ user, isAuthenticated: true, accessToken: 'old', refreshToken: null });
  let retrySucceeds = false;
  apiClient.defaults.adapter = async (config) => {
    if (retrySucceeds && config.headers.Authorization === 'Bearer new') return { data: { current: true }, status: 200, statusText: 'OK', headers: {}, config };
    throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, { status: 401, statusText: 'Unauthorized', data: {}, headers: {}, config });
  };
  const first = Promise.allSettled([apiClient.get('/synthetic/a'), apiClient.get('/synthetic/b')]);
  const settled = await Promise.race([first, new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Requests hung')), 1000))]);
  expect(settled.map((v) => v.status)).toEqual(['rejected', 'rejected']);
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
  useAuthStore.setState({ user, isAuthenticated: true, accessToken: 'again', refreshToken: 'synthetic-refresh' });
  vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'new', refresh_token: 'rotated' } });
  retrySucceeds = true;
  const response = await apiClient.get('/synthetic/recovered');
  expect(response.data).toEqual({ current: true });
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(vi.mocked(axios.post).mock.calls[0][2]).toEqual({ timeout: 30000 });
});

it.each(['success', 'failure'])('old refresh %s cannot overwrite or clear replacement login', async (outcome) => {
  useAuthStore.setState({ user, isAuthenticated: true, accessToken: 'old', refreshToken: 'old-refresh' });
  apiClient.defaults.adapter = async (config) => {
    throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, { status: 401, statusText: '', data: {}, headers: {}, config });
  };
  let finish!: (value: unknown) => void;
  let fail!: (reason: unknown) => void;
  vi.spyOn(axios, 'post').mockImplementation(() => new Promise((resolve, reject) => { finish = resolve; fail = reject; }));
  const result = apiClient.get('/synthetic/old').catch((error: unknown) => error);
  await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  useAuthStore.getState().clearAuth();
  useAuthStore.setState({ user: { ...user, id: 'bob' }, isAuthenticated: true, accessToken: 'bob-token', refreshToken: 'bob-refresh' });
  if (outcome === 'success') finish({ data: { access_token: 'old-refreshed', refresh_token: 'old-rotated' } });
  else fail(new Error('Denied'));
  await result;
  expect(useAuthStore.getState().accessToken).toBe('bob-token');
  expect(useAuthStore.getState().refreshToken).toBe('bob-refresh');
  expect(useAuthStore.getState().user?.id).toBe('bob');
  expect(useAuthStore.getState().isAuthenticated).toBe(true);
});

it('queued retry cannot dispatch old work as a replacement principal', async () => {
  useAuthStore.setState({ user, isAuthenticated: true, accessToken: 'old', refreshToken: 'refresh' });
  const dispatched: unknown[] = [];
  apiClient.defaults.adapter = async (config) => {
    dispatched.push(config.headers.Authorization);
    throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, { status: 401, statusText: '', data: {}, headers: {}, config });
  };
  vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'new', refresh_token: 'rotated' } });
  const interceptor = apiClient.interceptors.request.use((config) => {
    if ((config as typeof config & { _retry?: boolean })._retry) {
      useAuthStore.setState({ user: { ...user, id: 'bob' }, accessToken: 'bob', refreshToken: 'bob-refresh' });
    }
    return config;
  });
  try {
    await expect(apiClient.get('/synthetic/old-work')).rejects.toThrow('session changed');
    expect(dispatched).toEqual(['Bearer old']);
    expect(useAuthStore.getState().accessToken).toBe('bob');
  } finally { apiClient.interceptors.request.eject(interceptor); }
});
