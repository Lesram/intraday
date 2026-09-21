import { act, renderHook, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/store/authStore';
import { useScannerWebSocket } from './useScannerWebSocket';

vi.mock('antd', () => ({ message: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

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
const setToken = (token: string) => useAuthStore.getState().setAccessToken(token);
const socket = () => MockSocket.instances.at(-1)!;
const logged = () => [...vi.mocked(console.log).mock.calls, ...vi.mocked(console.error).mock.calls]
  .flat().map(value => value instanceof Error ? value.message : JSON.stringify(value)).join(' ');

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('require', undefined); // Browser ESM has no CommonJS loader.
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
  vi.stubEnv('VITE_WS_BASE_URL', '');
  MockSocket.instances = [];
  MockSocket.failConstruction = false;
  useAuthStore.getState().clearAuth();
  setToken(initialToken);
});

afterEach(() => {
  cleanup();
  useAuthStore.getState().clearAuth();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('scanner browser authentication', () => {
  it('connects without require and preserves the encoded query-token route', () => {
    const { result } = renderHook(() => useScannerWebSocket());
    act(() => result.current.connect());
    expect(MockSocket.instances).toHaveLength(1);
    const url = new URL(socket().url);
    expect(url.host).toBe(window.location.host);
    expect(url.pathname).toBe('/api/v1/scanner/ws');
    expect([...url.searchParams]).toEqual([['token', initialToken]]);
    act(() => socket().open());
    expect(result.current.isConnected).toBe(true);
    act(() => result.current.startScanning({ price_min: 10 }, 15));
    expect(socket().send).toHaveBeenCalledWith(JSON.stringify({ action: 'start', filters: { price_min: 10 }, interval: 15 }));
  });

  it('preserves the explicit secure WebSocket base override', () => {
    vi.stubEnv('VITE_WS_BASE_URL', 'wss://example.invalid/');
    const { result } = renderHook(() => useScannerWebSocket());
    act(() => result.current.connect());
    expect(socket().url).toBe(`wss://example.invalid/api/v1/scanner/ws?token=${encodeURIComponent(initialToken)}`);
  });

  it('reads a refreshed token when the reconnect timer actually fires', () => {
    renderHook(() => useScannerWebSocket(true));
    expect(MockSocket.instances).toHaveLength(1);
    act(() => { socket().open(); socket().close(1006); });
    setToken(refreshedToken);
    act(() => vi.advanceTimersByTime(5000));
    expect(MockSocket.instances).toHaveLength(2);
    expect(new URL(socket().url).searchParams.get('token')).toBe(refreshedToken);
  });

  it('does not reconnect after logout even if a legacy token remains', () => {
    const { result } = renderHook(() => useScannerWebSocket(true));
    expect(MockSocket.instances).toHaveLength(1);
    act(() => { socket().open(); socket().close(1006); });
    useAuthStore.getState().clearAuth();
    localStorage.setItem('auth_token', 'synthetic-legacy');
    act(() => vi.advanceTimersByTime(5000));
    expect(MockSocket.instances).toHaveLength(1);
    expect(result.current.connectionStatus).toBe('error');
  });

  it('does not open an unauthenticated socket', () => {
    useAuthStore.getState().clearAuth();
    const { result } = renderHook(() => useScannerWebSocket());
    act(() => result.current.connect());
    expect(MockSocket.instances).toHaveLength(0);
    expect(result.current.connectionStatus).toBe('error');
  });

  it('cancels a scheduled reconnect on explicit disconnect', () => {
    const { result } = renderHook(() => useScannerWebSocket(true));
    expect(MockSocket.instances).toHaveLength(1);
    act(() => { socket().open(); socket().close(1006); result.current.disconnect(); });
    act(() => vi.advanceTimersByTime(5000));
    expect(MockSocket.instances).toHaveLength(1);
    expect(result.current.connectionStatus).toBe('disconnected');
  });

  it('does not log URL-bearing error events or constructor failures', () => {
    const { result } = renderHook(() => useScannerWebSocket());
    act(() => result.current.connect());
    expect(MockSocket.instances).toHaveLength(1);
    act(() => socket().onerror?.({ target: { url: socket().url } }));
    act(() => result.current.disconnect());
    MockSocket.failConstruction = true;
    act(() => result.current.connect());
    expect(logged()).not.toContain(initialToken);
    expect(logged()).not.toContain(encodeURIComponent(initialToken));
    expect(result.current.error).not.toContain(encodeURIComponent(initialToken));
  });
});
