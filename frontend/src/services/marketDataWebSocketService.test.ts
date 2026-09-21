import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MarketDataWebSocketService } from './marketDataWebSocketService';
import type { useAuthStore as AuthStore } from '@/store/authStore';

class MockSocket {
  static OPEN = 1;
  static instances: MockSocket[] = [];
  static failConstruction = false;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  send = vi.fn();
  constructor(public url: string) {
    if (MockSocket.failConstruction) throw new Error(`Failed to open ${url}`);
    MockSocket.instances.push(this);
  }
  open() { this.readyState = 1; this.onopen?.(); }
  close(code = 1000, reason = '') { this.readyState = 3; this.onclose?.({ code, reason }); }
}

const initialToken = 'synthetic-initial+/?&token=extra';
const refreshedToken = 'synthetic-refreshed+/?&token=extra';
let service: MarketDataWebSocketService;
let authStore: typeof AuthStore;
const socket = () => MockSocket.instances.at(-1)!;
const setToken = (token: string) => authStore.getState().setAccessToken(token);
const logged = () => [...vi.mocked(console.log).mock.calls, ...vi.mocked(console.error).mock.calls]
  .flat().map(value => value instanceof Error ? value.message : JSON.stringify(value)).join(' ');

async function openConnection(callerToken = initialToken) {
  const connecting = service.connect(callerToken);
  socket().open();
  await vi.advanceTimersByTimeAsync(100);
  await connecting;
}

beforeEach(async () => {
  vi.resetModules(); // Fresh singleton, while exercising the real store/helper imports.
  vi.useFakeTimers();
  vi.stubGlobal('require', undefined);
  vi.stubGlobal('WebSocket', MockSocket);
  const legacyStorage = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => legacyStorage.get(key) ?? null,
    setItem: (key: string, value: string) => legacyStorage.set(key, value),
    removeItem: (key: string) => legacyStorage.delete(key),
  });
  vi.stubGlobal('fetch', vi.fn(() => { throw new Error('Network forbidden'); }));
  vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(() => { throw new Error('Network forbidden'); });
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(Math, 'random').mockReturnValue(0);
  vi.stubEnv('VITE_WS_BASE_URL', '');
  MockSocket.instances = [];
  MockSocket.failConstruction = false;
  authStore = (await import('@/store/authStore')).useAuthStore;
  authStore.getState().clearAuth();
  setToken(initialToken);
  service = (await import('./marketDataWebSocketService')).getMarketDataService({
    reconnectInterval: 100, maxReconnectAttempts: 3,
  });
});

afterEach(() => {
  service?.disconnect();
  authStore?.getState().clearAuth();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('market data browser authentication', () => {
  it('uses the actual current store token rather than a stale caller argument', async () => {
    await openConnection('synthetic-stale-caller');
    const url = new URL(socket().url);
    expect(url.host).toBe(window.location.host);
    expect(url.pathname).toBe('/api/v1/market-data/ws');
    expect([...url.searchParams]).toEqual([['token', initialToken]]);
    expect(service.getConnectionState()).toBe('CONNECTED');
    service.subscribe('aapl', vi.fn());
    expect(socket().send).toHaveBeenCalledWith(JSON.stringify({ action: 'subscribe', symbol: 'AAPL' }));
  });

  it('reconnects without require and ignores a stale legacy token', async () => {
    await openConnection();
    localStorage.setItem('auth_token', 'synthetic-legacy');
    socket().close(1006);
    setToken(refreshedToken); // Refresh after scheduling, before actual attempt.
    await vi.advanceTimersByTimeAsync(100);
    expect(MockSocket.instances).toHaveLength(2);
    expect(new URL(socket().url).searchParams.get('token')).toBe(refreshedToken);
    socket().open();
    await vi.advanceTimersByTimeAsync(100);
  });

  it('reconnects from the current store when there is no legacy storage', async () => {
    await openConnection();
    socket().close(1006);
    await vi.advanceTimersByTimeAsync(100);
    expect(MockSocket.instances).toHaveLength(2);
    socket().open();
    await vi.advanceTimersByTimeAsync(100);
  });

  it('does not reuse captured or legacy credentials after logout during backoff', async () => {
    await openConnection();
    localStorage.setItem('auth_token', 'synthetic-legacy');
    socket().close(1006);
    authStore.getState().clearAuth();
    localStorage.setItem('auth_token', 'synthetic-leftover');
    await vi.advanceTimersByTimeAsync(100);
    expect(MockSocket.instances).toHaveLength(1);
    expect(service.getConnectionState()).toBe('FAILED');
  });

  it('rejects missing current credentials even when a caller supplies an old token', async () => {
    authStore.getState().clearAuth();
    const connection = service.connect('synthetic-stale-caller');
    const rejected = expect(connection).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(5000);
    await rejected;
    expect(MockSocket.instances).toHaveLength(0);
  });

  it('cancels the reconnect timer on explicit disconnect', async () => {
    await openConnection();
    localStorage.setItem('auth_token', 'synthetic-legacy');
    socket().close(1006);
    service.disconnect();
    await vi.advanceTimersByTimeAsync(1000);
    expect(MockSocket.instances).toHaveLength(1);
    expect(service.getConnectionState()).toBe('DISCONNECTED');
  });

  it('does not log encoded credentials or raw URL-bearing events', async () => {
    await openConnection();
    socket().onerror?.({ target: { url: socket().url } });
    expect(logged()).not.toContain(initialToken);
    expect(logged()).not.toContain(encodeURIComponent(initialToken));
  });

  it('sanitizes constructor errors and refreshes credentials before a failed-connect retry', async () => {
    MockSocket.failConstruction = true;
    const failure = await service.connect(initialToken).catch(error => error);
    expect(failure).toBeInstanceOf(Error);
    expect(failure.message).not.toContain(encodeURIComponent(initialToken));
    expect(logged()).not.toContain(encodeURIComponent(initialToken));
    MockSocket.failConstruction = false;
    setToken(refreshedToken);
    await vi.advanceTimersByTimeAsync(1000);
    expect(MockSocket.instances).toHaveLength(1);
    expect(new URL(socket().url).searchParams.get('token')).toBe(refreshedToken);
    socket().open();
    await vi.advanceTimersByTimeAsync(100);
  });
});
