import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortfolioPage from './PortfolioPage';
import { usePortfolio } from '@/hooks/useData';
import { usePortfolioStore } from '@/store/portfolioStore';
import { portfolioFixture } from '@/test/portfolioFixture';
vi.mock('@/hooks/useData', () => ({ usePortfolio: vi.fn() }));
vi.mock('@/services/api', () => ({ apiClient: { get: vi.fn().mockResolvedValue({ data: {} }) } }));
it('an unavailable hook cannot be overridden by a previously healthy store', () => {
  usePortfolioStore.getState().setPortfolio(portfolioFixture());
  vi.mocked(usePortfolio).mockReturnValue({ data: undefined, isLoading: false, error: new Error('unavailable'), refetch: vi.fn() } as never);
  const client = new QueryClient();
  const { unmount } = render(<QueryClientProvider client={client}><PortfolioPage /></QueryClientProvider>);
  expect(screen.getByText('Portfolio Error')).toBeInTheDocument();
  expect(screen.queryByText('Account Equity')).not.toBeInTheDocument();
  unmount(); client.clear(); usePortfolioStore.getState().reset();
});
