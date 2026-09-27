import { StrictMode, useEffect } from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import axios from 'axios';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { io } from 'socket.io-client';
import { useAuthStore } from '@/store/authStore';
import { apiClient } from '@/services/api';
import { websocketManager } from '@/services/websocketManager';
import AuthBootstrap from './AuthBootstrap';
import ProtectedRoute from './ProtectedRoute';

vi.mock('socket.io-client', () => ({ io: vi.fn(() => ({
  on: vi.fn(), emit: vi.fn(), disconnect: vi.fn(), removeAllListeners: vi.fn(), connected: false,
})) }));
const user = { id: 'alice', name: 'Alice', email: 'alice', role: 'admin' as const, is_active: true, created_at: '' };
const fresh = { access_token: 'restored-access', refresh_token: 'rotated-refresh', token_type: 'bearer' };
// Actual /auth/me response shape, not the frontend User type.
const me = { user_id: 'alice', username: 'alice', email: null, roles: ['viewer'], is_active: true, authenticated: true, is_admin: false, created_at: null, last_login: null };
const originalAdapter = apiClient.defaults.adapter;
const deferred = () => {
  let resolve!: (value: unknown) => void; let reject!: (reason: unknown) => void;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const persistReload = async (overrides: Record<string, unknown> = {}) => {
  useAuthStore.getState().clearAuth();
  sessionStorage.setItem('auth-storage', JSON.stringify({ version: 0, state: {
    user, isAuthenticated: true, refreshToken: 'persisted-refresh', ...overrides,
  } }));
  await useAuthStore.persist.rehydrate();
};
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); useAuthStore.getState().clearAuth(); });
afterEach(() => { cleanup(); websocketManager.disconnect(); useAuthStore.getState().clearAuth(); apiClient.defaults.adapter = originalAdapter; vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllEnvs(); });

it('reload restores once under StrictMode before protected HTTP/socket traffic', async () => {
  await persistReload({ accessToken: 'must-not-rehydrate', tokenExpiresAt: 9999999999999, sessionReady: true });
  const response = deferred(); const identity = deferred();
  const post = vi.spyOn(axios, 'post').mockReturnValue(response.promise as ReturnType<typeof axios.post>);
  const get = vi.spyOn(axios, 'get').mockReturnValue(identity.promise as ReturnType<typeof axios.get>);
  const adapter = vi.fn(async (config) => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config }));
  apiClient.defaults.adapter = adapter;
  function ProtectedTraffic() {
    useEffect(() => {
      void apiClient.get('/portfolio');
      websocketManager.connect(useAuthStore.getState().accessToken!);
      return () => websocketManager.disconnect();
    }, []);
    return <div>Protected portfolio</div>;
  }
  render(<StrictMode><AuthBootstrap><MemoryRouter initialEntries={['/portfolio']}><Routes>
    <Route path="/portfolio" element={<ProtectedRoute><ProtectedTraffic /></ProtectedRoute>} />
    <Route path="/login" element={<div>Sign in</div>} />
  </Routes></MemoryRouter></AuthBootstrap></StrictMode>);
  expect(useAuthStore.getState().accessToken).toBeNull();
  expect(screen.getByRole('status')).toHaveTextContent('Restoring session');
  expect(post).toHaveBeenCalledTimes(1); expect(adapter).not.toHaveBeenCalled(); expect(io).not.toHaveBeenCalled();
  await act(async () => { response.resolve({ data: fresh }); });
  expect(get).toHaveBeenCalledWith(`${window.location.origin}/api/v1/auth/me`, expect.objectContaining({ headers: { Authorization: 'Bearer restored-access' } }));
  expect(adapter).not.toHaveBeenCalled(); expect(io).not.toHaveBeenCalled();
  await act(async () => { identity.resolve({ data: me }); });
  await screen.findByText('Protected portfolio');
  await waitFor(() => expect(adapter).toHaveBeenCalled());
  expect(adapter.mock.calls.every(([config]) => config.headers.Authorization === 'Bearer restored-access')).toBe(true);
  expect(io).toHaveBeenCalledWith(window.location.origin, expect.objectContaining({ auth: { token: 'restored-access' } }));
  expect(useAuthStore.getState().user?.role).toBe('viewer');
  expect(useAuthStore.getState().refreshToken).toBe('rotated-refresh');
  const persisted = JSON.parse(sessionStorage.getItem('auth-storage')!).state;
  expect(persisted).not.toHaveProperty('accessToken'); expect(persisted).not.toHaveProperty('tokenExpiresAt'); expect(persisted).not.toHaveProperty('sessionReady');
});

it.each(['missing-refresh', 'refresh-rejected', 'malformed-refresh', 'me-rejected', 'wrong-principal', 'inactive', 'malformed-roles'])('restoration %s clears and redirects without mounting protected content', async (kind) => {
  await persistReload(kind === 'missing-refresh' ? { refreshToken: null } : {});
  const post = vi.spyOn(axios, 'post').mockImplementation(async () => {
    if (kind === 'refresh-rejected') throw new Error('synthetic denial');
    return { data: kind === 'malformed-refresh' ? { ...fresh, access_token: null } : fresh };
  });
  vi.spyOn(axios, 'get').mockImplementation(async () => {
    if (kind === 'me-rejected') throw new Error('synthetic denial');
    return { data: { ...me, ...(kind === 'wrong-principal' ? { user_id: 'bob', username: 'bob' } : {}), ...(kind === 'inactive' ? { is_active: false } : {}), ...(kind === 'malformed-roles' ? { roles: null } : {}) } };
  });
  const protectedRender = vi.fn();
  function ProtectedChild() { protectedRender(); return <div>Private data</div>; }
  render(<AuthBootstrap><MemoryRouter initialEntries={['/portfolio']}><Routes>
    <Route path="/portfolio" element={<ProtectedRoute><ProtectedChild /></ProtectedRoute>} />
    <Route path="/login" element={<div>Sign in</div>} />
  </Routes></MemoryRouter></AuthBootstrap>);
  await screen.findByText('Sign in');
  expect(protectedRender).not.toHaveBeenCalled(); expect(useAuthStore.getState().isAuthenticated).toBe(false);
  expect(useAuthStore.getState().refreshToken).toBeNull(); expect(useAuthStore.getState().sessionReady).toBe(true);
  if (kind === 'missing-refresh') expect(post).not.toHaveBeenCalled();
});

const races = ['logout', 'new-login'].flatMap(action => ['refresh', 'me'].flatMap(phase => ['success', 'failure'].map(outcome => ({ action, phase, outcome }))));
it.each(races)('stale $phase $outcome after $action cannot resurrect or clear a session', async ({ action, phase, outcome }) => {
  await persistReload();
  const delayed = deferred();
  const post = vi.spyOn(axios, 'post').mockImplementation(() => phase === 'refresh' ? delayed.promise as ReturnType<typeof axios.post> : Promise.resolve({ data: fresh }));
  const get = vi.spyOn(axios, 'get').mockReturnValue(delayed.promise as ReturnType<typeof axios.get>);
  const first = useAuthStore.getState().restoreSession();
  const second = useAuthStore.getState().restoreSession();
  expect(first).toBe(second);
  await waitFor(() => expect(phase === 'refresh' ? post : get).toHaveBeenCalledTimes(1));
  if (action === 'logout') useAuthStore.getState().clearAuth();
  else useAuthStore.getState().setAuth(user, 'replacement-access', 'replacement-refresh');
  if (outcome === 'failure') delayed.reject(new Error('synthetic denial'));
  else delayed.resolve({ data: phase === 'refresh' ? fresh : me });
  await first;
  expect(useAuthStore.getState().sessionReady).toBe(true);
  if (action === 'logout') {
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull(); expect(useAuthStore.getState().user).toBeNull();
  } else {
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe('replacement-access');
    expect(useAuthStore.getState().refreshToken).toBe('replacement-refresh');
  }
  if (phase === 'refresh') expect(get).not.toHaveBeenCalled();
});

it('a nonresponding refresh is aborted at the whole-session deadline', async () => {
  vi.useFakeTimers(); await persistReload();
  vi.spyOn(axios, 'post').mockImplementation((_url, _body, options) => new Promise((_resolve, reject) => {
    options!.signal!.addEventListener!('abort', () => reject(new Error('synthetic aborted request')));
  }));
  const done = useAuthStore.getState().restoreSession();
  await vi.advanceTimersByTimeAsync(29999);
  expect(useAuthStore.getState().sessionReady).toBe(false);
  await vi.advanceTimersByTimeAsync(1); await done;
  expect(useAuthStore.getState().sessionReady).toBe(true);
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
});

it('anonymous startup finishes without network and explicit API origin is honored on reload', async () => {
  const post = vi.spyOn(axios, 'post').mockResolvedValue({ data: fresh });
  const get = vi.spyOn(axios, 'get').mockResolvedValue({ data: me });
  useAuthStore.setState({ sessionReady: false });
  await useAuthStore.getState().restoreSession();
  expect(post).not.toHaveBeenCalled(); expect(get).not.toHaveBeenCalled();
  vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test'); await persistReload();
  await useAuthStore.getState().restoreSession();
  expect(post).toHaveBeenCalledWith('https://api.example.test/api/v1/auth/token/refresh', { refresh_token: 'persisted-refresh' }, expect.objectContaining({ timeout: 30000 }));
  expect(get).toHaveBeenCalledWith('https://api.example.test/api/v1/auth/me', expect.objectContaining({ timeout: 30000 }));
  expect(useAuthStore.getState().accessToken).toBe('restored-access');
});

it.each(['refresh', 'me'])('deadline clears the captured session even if %s resolves after abort', async (phase) => {
  vi.useFakeTimers(); await persistReload();
  const delayed = deferred();
  vi.spyOn(axios, 'post').mockImplementation(() => phase === 'refresh' ? delayed.promise as ReturnType<typeof axios.post> : Promise.resolve({ data: fresh }));
  const get = vi.spyOn(axios, 'get').mockReturnValue(delayed.promise as ReturnType<typeof axios.get>);
  const done = useAuthStore.getState().restoreSession();
  await vi.advanceTimersByTimeAsync(30000);
  expect(useAuthStore.getState().sessionReady).toBe(true);
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
  delayed.resolve({ data: phase === 'refresh' ? fresh : me });
  await done;
  expect(useAuthStore.getState().accessToken).toBeNull();
  expect(useAuthStore.getState().refreshToken).toBeNull();
  if (phase === 'refresh') expect(get).not.toHaveBeenCalled();
});
