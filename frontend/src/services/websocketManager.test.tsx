import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const fake = vi.hoisted(() => ({ sockets: [] as Array<{ connected: boolean; auth: unknown; handlers: Map<string, (...args: unknown[]) => void>; on: ReturnType<typeof vi.fn>; emit: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>; removeAllListeners: ReturnType<typeof vi.fn> }> }));
vi.mock('socket.io-client', () => ({ io: vi.fn((_url, options) => {
  const handlers = new Map();
  const socket = { connected: false, auth: options.auth, handlers, on: vi.fn((event, fn) => handlers.set(event, fn)), emit: vi.fn(), disconnect: vi.fn(), removeAllListeners: vi.fn(() => handlers.clear()) };
  fake.sockets.push(socket); return socket;
}) }));
import { useAuthStore } from '@/store/authStore';
import { useWebSocket, useWebSocketConnection } from '@/hooks/useWebSocket';
import { websocketManager } from './websocketManager';
const setAuth = (token: string | null, user = 'alice') => useAuthStore.setState({ accessToken: token, isAuthenticated: !!token, user: token ? { id: user, name: user, role: 'viewer', email: '', is_active: true, created_at: '' } : null });
beforeEach(() => { websocketManager.disconnect(); fake.sockets.length = 0; vi.clearAllMocks(); setAuth('first'); });
afterEach(() => { websocketManager.disconnect(); setAuth(null); });
it('logout closes connected session and removes private-delivery callbacks', () => {
  const handler = vi.fn(); const { unmount } = renderHook(() => { useWebSocketConnection(); useWebSocket('portfolio', handler); });
  const first = fake.sockets[0]; first.connected = true;
  act(() => first.handlers.get('connect')?.());
  act(() => first.handlers.get('portfolio_update')?.({ synthetic: 'alice' }));
  expect(handler).toHaveBeenCalledTimes(1);
  act(() => setAuth(null));
  expect(first.disconnect).toHaveBeenCalled(); expect(first.handlers.size).toBe(0);
  expect(websocketManager.isConnected()).toBe(false); unmount();
});
it('token rotation while connected or connecting retires old transport and resubscribes once', () => {
  const handler = vi.fn(); const { unmount } = renderHook(() => { useWebSocketConnection(); useWebSocket('portfolio', handler); });
  const first = fake.sockets[0]; expect(fake.sockets).toHaveLength(1);
  act(() => setAuth('second')); const second = fake.sockets[1];
  expect(first.disconnect).toHaveBeenCalled(); expect(first.handlers.size).toBe(0);
  expect(second.auth).toEqual({ token: 'second' }); expect(fake.sockets).toHaveLength(2);
  second.connected = true; act(() => second.handlers.get('connect')?.());
  act(() => second.handlers.get('portfolio_update')?.({ synthetic: 'updated' }));
  expect(handler).toHaveBeenCalledTimes(1);
  expect(second.emit.mock.calls.filter(([event]) => event === 'subscribe')).toHaveLength(1);
  act(() => setAuth('third', 'bob')); expect(second.disconnect).toHaveBeenCalled();
  expect(fake.sockets[2].auth).toEqual({ token: 'third' });
  unmount();
});
it('an obsolete caller cannot open a socket using a retired token', () => {
  websocketManager.connect('wrong'); expect(fake.sockets).toHaveLength(0);
});
