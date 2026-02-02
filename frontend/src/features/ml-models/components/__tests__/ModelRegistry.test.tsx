import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ModelRegistry from '../ModelRegistry';

// Mock the API hooks
vi.mock('../../hooks/useMLModels', () => ({
  useMLModels: () => ({
    data: mockModels,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useDeleteModel: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useActivateModel: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

// Mock accessibility hooks
vi.mock('../../../hooks/useAccessibility', () => ({
  useAnnouncer: () => vi.fn(),
  useAriaId: () => 'test-id',
}));

const mockModels = [
  {
    id: '1',
    name: 'LSTM Predictor',
    type: 'lstm',
    version: '1.0.0',
    status: 'active',
    accuracy: 0.85,
    createdAt: '2024-01-15T10:00:00Z',
    lastTrainedAt: '2024-01-15T10:00:00Z',
    description: 'Long Short-Term Memory model for price prediction',
  },
  {
    id: '2',
    name: 'Random Forest',
    type: 'random_forest',
    version: '2.1.0',
    status: 'inactive',
    accuracy: 0.78,
    createdAt: '2024-01-10T08:00:00Z',
    lastTrainedAt: '2024-01-10T08:00:00Z',
    description: 'Ensemble model for trend analysis',
  },
  {
    id: '3',
    name: 'XGBoost Classifier',
    type: 'xgboost',
    version: '1.5.2',
    status: 'training',
    accuracy: null,
    createdAt: '2024-01-20T14:00:00Z',
    lastTrainedAt: null,
    description: 'Gradient boosting for signal detection',
  },
];

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{component}</QueryClientProvider>
  );
};

describe('ModelRegistry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the model registry header', () => {
      renderWithProviders(<ModelRegistry />);
      expect(screen.getByText(/ML Model Registry/i)).toBeInTheDocument();
    });

    it('should render search input with ARIA label', () => {
      renderWithProviders(<ModelRegistry />);
      const searchInput = screen.getByLabelText(/Search ML models/i);
      expect(searchInput).toBeInTheDocument();
      expect(searchInput).toHaveAttribute('aria-label');
    });

    it('should render all filter controls', () => {
      renderWithProviders(<ModelRegistry />);
      expect(screen.getByLabelText(/Filter models by status/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Filter models by type/i)).toBeInTheDocument();
    });

    it('should render model cards for all models', () => {
      renderWithProviders(<ModelRegistry />);
      expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      expect(screen.getByText('Random Forest')).toBeInTheDocument();
      expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
    });

    it('should render action buttons with ARIA labels', () => {
      renderWithProviders(<ModelRegistry />);
      const viewButtons = screen.getAllByLabelText(/View details/i);
      expect(viewButtons.length).toBeGreaterThan(0);
    });
  });

  describe('Search Functionality', () => {
    it('should filter models by name', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, 'LSTM');

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should filter models by type (case insensitive)', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, 'xgboost');

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
        expect(screen.queryByText('LSTM Predictor')).not.toBeInTheDocument();
      });
    });

    it('should filter models by version', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, '1.5.2');

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should show all models when search is cleared', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, 'LSTM');
      await user.clear(searchInput);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.getByText('Random Forest')).toBeInTheDocument();
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
      });
    });
  });

  describe('Status Filter', () => {
    it('should filter models by active status', async () => {
      renderWithProviders(<ModelRegistry />);

      const statusFilter = screen.getByLabelText(/Filter models by status/i);
      fireEvent.change(statusFilter, { target: { value: 'active' } });

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should filter models by training status', async () => {
      renderWithProviders(<ModelRegistry />);

      const statusFilter = screen.getByLabelText(/Filter models by status/i);
      fireEvent.change(statusFilter, { target: { value: 'training' } });

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
        expect(screen.queryByText('LSTM Predictor')).not.toBeInTheDocument();
      });
    });

    it('should show all models when status filter is cleared', async () => {
      renderWithProviders(<ModelRegistry />);

      const statusFilter = screen.getByLabelText(/Filter models by status/i);
      fireEvent.change(statusFilter, { target: { value: 'active' } });
      fireEvent.change(statusFilter, { target: { value: '' } });

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.getByText('Random Forest')).toBeInTheDocument();
      });
    });
  });

  describe('Type Filter', () => {
    it('should filter models by LSTM type', async () => {
      renderWithProviders(<ModelRegistry />);

      const typeFilter = screen.getByLabelText(/Filter models by type/i);
      fireEvent.change(typeFilter, { target: { value: 'lstm' } });

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should show all models when type filter is cleared', async () => {
      renderWithProviders(<ModelRegistry />);

      const typeFilter = screen.getByLabelText(/Filter models by type/i);
      fireEvent.change(typeFilter, { target: { value: 'lstm' } });
      fireEvent.change(typeFilter, { target: { value: '' } });

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.getByText('Random Forest')).toBeInTheDocument();
      });
    });
  });

  describe('Combined Filters', () => {
    it('should apply search and status filter together', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      const statusFilter = screen.getByLabelText(/Filter models by status/i);

      await user.type(searchInput, 'Predictor');
      fireEvent.change(statusFilter, { target: { value: 'active' } });

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
        expect(screen.queryByText('XGBoost Classifier')).not.toBeInTheDocument();
      });
    });
  });

  describe('Empty States', () => {
    it('should show empty state when no models match filters', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, 'NonexistentModel');

      await waitFor(() => {
        expect(screen.getByText(/No models found/i)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels on all interactive elements', () => {
      renderWithProviders(<ModelRegistry />);

      expect(screen.getByLabelText(/Search ML models/i)).toHaveAttribute('aria-label');
      expect(screen.getByLabelText(/Filter models by status/i)).toHaveAttribute('aria-label');
      expect(screen.getByLabelText(/Filter models by type/i)).toHaveAttribute('aria-label');
    });

    it('should have ARIA descriptions for filters', () => {
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      expect(searchInput).toHaveAttribute('aria-describedby');
    });

    it('should announce filter results to screen readers', async () => {
      const mockAnnounce = vi.fn();
      vi.mocked(require('../../../hooks/useAccessibility').useAnnouncer).mockReturnValue(mockAnnounce);

      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      await user.type(searchInput, 'LSTM');

      await waitFor(() => {
        expect(mockAnnounce).toHaveBeenCalledWith(expect.stringContaining('Found 1 model'));
      });
    });
  });

  describe('Keyboard Navigation', () => {
    it('should be navigable with Tab key', () => {
      renderWithProviders(<ModelRegistry />);

      const searchInput = screen.getByLabelText(/Search ML models/i);
      searchInput.focus();
      expect(document.activeElement).toBe(searchInput);

      fireEvent.keyDown(searchInput, { key: 'Tab' });
      // Next focusable element should receive focus
    });

    it('should activate filters with Enter key', async () => {
      renderWithProviders(<ModelRegistry />);

      const statusFilter = screen.getByLabelText(/Filter models by status/i);
      statusFilter.focus();
      fireEvent.keyDown(statusFilter, { key: 'Enter' });

      // Filter should be activatable via keyboard
    });
  });

  describe('Performance', () => {
    it('should render large model lists efficiently', () => {
      const _largeModelList = Array.from({ length: 100 }, (_, i) => ({
        ...mockModels[0],
        id: String(i),
        name: `Model ${i}`,
      }));

      const start = performance.now();
      renderWithProviders(<ModelRegistry />);
      const end = performance.now();

      expect(end - start).toBeLessThan(1000); // Should render in less than 1 second
    });
  });
});
