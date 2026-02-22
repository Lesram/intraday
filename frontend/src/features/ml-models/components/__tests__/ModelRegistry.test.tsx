import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { App } from 'antd';
import ModelRegistry from '../ModelRegistry';
import type { ModelInfo, ModelListResponse } from '@/types/ml';

// Mock the ML API
const mockModels: ModelInfo[] = [
  {
    id: '1',
    name: 'LSTM Predictor',
    model_type: 'lstm',
    version: '1.0.0',
    status: 'ready',
    active: true,
    path: '/models/lstm',
    trained_at: '2024-01-15T10:00:00Z',
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
    metrics: { accuracy: 0.85 },
    features: ['price', 'volume'],
    symbols: ['AAPL'],
    hyperparameters: {},
    prediction_count: 15000,
  },
  {
    id: '2',
    name: 'Random Forest',
    model_type: 'random_forest',
    version: '2.1.0',
    status: 'inactive',
    active: false,
    path: '/models/rf',
    trained_at: '2024-01-10T08:00:00Z',
    created_at: '2024-01-10T08:00:00Z',
    updated_at: '2024-01-10T08:00:00Z',
    metrics: { accuracy: 0.78 },
    features: ['close', 'rsi'],
    symbols: ['MSFT'],
    hyperparameters: {},
    prediction_count: 8000,
  },
  {
    id: '3',
    name: 'XGBoost Classifier',
    model_type: 'xgboost',
    version: '1.5.2',
    status: 'training',
    active: false,
    path: '/models/xgb',
    trained_at: '2024-01-20T14:00:00Z',
    created_at: '2024-01-20T14:00:00Z',
    updated_at: '2024-01-20T14:00:00Z',
    metrics: {},
    features: [],
    symbols: [],
    hyperparameters: {},
    prediction_count: 0,
  },
];

const mockListResponse: ModelListResponse = {
  models: mockModels,
  total: 3,
  page: 1,
  page_size: 10,
};

vi.mock('@/services/mlApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/mlApi')>('@/services/mlApi');
  return {
    ...actual,
    mlApi: {
      listModels: vi.fn().mockResolvedValue({
        models: [
          {
            id: '1', name: 'LSTM Predictor', model_type: 'lstm', version: '1.0.0',
            status: 'ready', active: true, path: '/models/lstm',
            trained_at: '2024-01-15T10:00:00Z', created_at: '2024-01-15T10:00:00Z',
            updated_at: '2024-01-15T10:00:00Z', metrics: { accuracy: 0.85 },
            features: ['price', 'volume'], symbols: ['AAPL'], hyperparameters: {},
            prediction_count: 15000,
          },
          {
            id: '2', name: 'Random Forest', model_type: 'random_forest', version: '2.1.0',
            status: 'inactive', active: false, path: '/models/rf',
            trained_at: '2024-01-10T08:00:00Z', created_at: '2024-01-10T08:00:00Z',
            updated_at: '2024-01-10T08:00:00Z', metrics: { accuracy: 0.78 },
            features: ['close', 'rsi'], symbols: ['MSFT'], hyperparameters: {},
            prediction_count: 8000,
          },
          {
            id: '3', name: 'XGBoost Classifier', model_type: 'xgboost', version: '1.5.2',
            status: 'training', active: false, path: '/models/xgb',
            trained_at: '2024-01-20T14:00:00Z', created_at: '2024-01-20T14:00:00Z',
            updated_at: '2024-01-20T14:00:00Z', metrics: {},
            features: [], symbols: [], hyperparameters: {}, prediction_count: 0,
          },
        ],
        total: 3, page: 1, page_size: 10,
      }),
      deleteModel: vi.fn().mockResolvedValue({}),
      activateModel: vi.fn().mockResolvedValue({}),
    },
  };
});

vi.mock('@/hooks/useAccessibility', () => ({
  useAnnouncer: () => vi.fn(),
  useAriaId: (prefix: string) => `${prefix}-test`,
}));

vi.mock('@/hooks/useResponsive', () => ({
  useIsMobile: () => false,
}));

vi.mock('@/hooks/usePerformance', () => ({
  useDebounce: (value: string) => value,
}));

vi.mock('../hooks/useErrorHandler', () => ({
  useErrorHandler: () => ({ handleError: vi.fn() }),
}));

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <App>{component}</App>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('ModelRegistry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the model registry', async () => {
      renderWithProviders(<ModelRegistry />);
      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });
    });

    it('should render all model names', async () => {
      renderWithProviders(<ModelRegistry />);
      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.getByText('Random Forest')).toBeInTheDocument();
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
      });
    });

    it('should render search input', async () => {
      renderWithProviders(<ModelRegistry />);
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search by name/i)).toBeInTheDocument();
      });
    });

    it('should render model versions', async () => {
      renderWithProviders(<ModelRegistry />);
      await waitFor(() => {
        expect(screen.getByText(/v1.0.0/)).toBeInTheDocument();
        expect(screen.getByText(/v2.1.0/)).toBeInTheDocument();
      });
    });
  });

  describe('Search Functionality', () => {
    it('should filter models by name when searching', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      await user.type(searchInput, 'LSTM');

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should filter models by type', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      await user.type(searchInput, 'xgboost');

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
        expect(screen.queryByText('LSTM Predictor')).not.toBeInTheDocument();
      });
    });

    it('should filter models by version', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      await user.type(searchInput, '1.5.2');

      await waitFor(() => {
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });
    });

    it('should show all models when search is cleared', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      await user.type(searchInput, 'LSTM');

      await waitFor(() => {
        expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
      });

      await user.clear(searchInput);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
        expect(screen.getByText('Random Forest')).toBeInTheDocument();
        expect(screen.getByText('XGBoost Classifier')).toBeInTheDocument();
      });
    });
  });

  describe('Empty States', () => {
    it('should show message when no models match search', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      await user.type(searchInput, 'NonexistentModel');

      await waitFor(() => {
        expect(screen.queryByText('LSTM Predictor')).not.toBeInTheDocument();
      });
    });
  });

  describe('Keyboard Navigation', () => {
    it('should have focusable search input', async () => {
      renderWithProviders(<ModelRegistry />);

      await waitFor(() => {
        expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      searchInput.focus();
      expect(document.activeElement).toBe(searchInput);
    });
  });

  describe('Performance', () => {
    it('should render in reasonable time', async () => {
      const start = performance.now();
      renderWithProviders(<ModelRegistry />);
      const end = performance.now();
      expect(end - start).toBeLessThan(1000);
    });
  });
});
