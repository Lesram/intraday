import { afterEach, expect, it, vi } from 'vitest';
import { io } from 'socket.io-client';

vi.mock('socket.io-client', () => ({ io: vi.fn(() => ({
  on: vi.fn(), emit: vi.fn(), disconnect: vi.fn(), removeAllListeners: vi.fn(), connected: false,
})) }));
let disconnect: (() => void) | undefined;
afterEach(() => {
  disconnect?.(); disconnect = undefined;
  vi.unstubAllEnvs(); vi.clearAllMocks(); vi.resetModules();
});

it.each([undefined, ''])('HTTP defaults to page origin when override is %s', async (override) => {
  vi.stubEnv('VITE_API_BASE_URL', override);
  const { apiClient } = await import('./api');
  expect(apiClient.defaults.baseURL).toBe(`${window.location.origin}/api/v1`);
});
it('HTTP preserves an explicit deployment origin', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test');
  const { apiClient } = await import('./api');
  expect(apiClient.defaults.baseURL).toBe('https://api.example.test/api/v1');
});

it.each([undefined, '', 'https://socket.example.test'])('Socket.IO uses the selected origin (%s)', async (override) => {
  vi.stubEnv('VITE_WS_BASE_URL', override);
  const { useAuthStore } = await import('@/store/authStore');
  useAuthStore.setState({ isAuthenticated: true, accessToken: 'synthetic-test-token' });
  const { websocketManager } = await import('./websocketManager');
  disconnect = () => websocketManager.disconnect();
  websocketManager.connect('synthetic-test-token');
  expect(io).toHaveBeenCalledWith(override || window.location.origin, expect.objectContaining({
    auth: { token: 'synthetic-test-token' }, transports: ['websocket'],
  }));
});
