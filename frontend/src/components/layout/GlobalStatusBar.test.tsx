import { render, screen, waitFor, act } from '@testing-library/react';
import { portfolioFixture } from '@/test/portfolioFixture';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/services/websocketManager', () => ({ websocketManager: {
  onConnectionChange: () => () => {}, isConnected: () => false,
} }));
import { apiClient } from '@/services/api';
import { useAuthStore } from '@/store/authStore';
import { GlobalStatusBar } from './GlobalStatusBar';

const valid = () => ({ status: 200, data: portfolioFixture() });

describe('portfolio observation status', () => {
  beforeEach(() => { vi.clearAllMocks(); useAuthStore.setState({ isAuthenticated: true, accessToken: 'synthetic', tokenExpiresAt: Date.now() + 3600000, user: { id: 'alice', name: '', email: '', role: 'viewer', is_active: true, created_at: '' } }); });
  it('labels a genuine current portfolio without claiming broker connectivity', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(valid());
    render(<GlobalStatusBar />);
    expect(await screen.findByText('PORTFOLIO: CURRENT')).toBeInTheDocument();
    expect(screen.queryByText('ALPACA: OK')).not.toBeInTheDocument();
  });
  it.each(['stale', 'future', 'missing', 'nan', 'error'])('does not mark %s portfolio data current', async (kind) => {
    const response = valid();
    if (kind === 'stale') response.data.lastUpdate = new Date(Date.now() - 60000).toISOString();
    if (kind === 'future') response.data.lastUpdate = new Date(Date.now() + 60000).toISOString();
    if (kind === 'missing') response.data.lastUpdate = '';
    if (kind === 'nan') response.data.totalEquity = NaN;
    if (kind === 'error') vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('synthetic secret'));
    else vi.mocked(apiClient.get).mockResolvedValueOnce(response);
    render(<GlobalStatusBar />);
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('PORTFOLIO: UNAVAILABLE')).toBeInTheDocument();
    expect(screen.queryByText('PORTFOLIO: CURRENT')).not.toBeInTheDocument();
  });
});

it('ignores old user response after identity changes during request', async () => {
  let resolveAlice!: (value: unknown) => void;
  let resolveBob!: (value: unknown) => void;
  vi.mocked(apiClient.get).mockImplementationOnce(() => new Promise((resolve) => { resolveAlice = resolve; }));
  vi.mocked(apiClient.get).mockImplementationOnce(() => new Promise((resolve) => { resolveBob = resolve; }));
  useAuthStore.setState({ isAuthenticated: true, accessToken: 'alice-token', tokenExpiresAt: Date.now() + 3600000, user: { id: 'alice', name: '', email: '', role: 'viewer', is_active: true, created_at: '' } });
  render(<GlobalStatusBar />);
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
  act(() => useAuthStore.setState({ accessToken: 'bob-token', user: { id: 'bob', name: '', email: '', role: 'viewer', is_active: true, created_at: '' } }));
  await act(async () => { resolveAlice(valid()); });
  expect(screen.queryByText('PORTFOLIO: CURRENT')).not.toBeInTheDocument();
  await act(async () => { resolveBob({ status: 200, data: portfolioFixture({ userId: 'bob' }) }); });
  expect(await screen.findByText('PORTFOLIO: CURRENT')).toBeInTheDocument();
});
