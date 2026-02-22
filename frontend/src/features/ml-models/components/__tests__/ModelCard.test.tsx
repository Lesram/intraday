import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ModelCard from '../ModelCard';
import type { ModelInfo } from '@/types/ml';

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
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>
  );
};

const mockModel: ModelInfo = {
  id: '1',
  name: 'LSTM Predictor',
  model_type: 'lstm',
  version: '1.0.0',
  status: 'ready',
  active: true,
  path: '/models/lstm-predictor',
  trained_at: '2024-01-15T10:00:00Z',
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
  metrics: {
    accuracy: 0.85,
    precision: 0.82,
    recall: 0.88,
    f1_score: 0.85,
    training_time: 3600,
  },
  features: ['price', 'volume', 'rsi', 'macd'],
  symbols: ['AAPL', 'MSFT'],
  hyperparameters: {},
  prediction_count: 15000,
};

describe('ModelCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render model name', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText('LSTM Predictor')).toBeDefined();
    });

    it('should render model version', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/v1.0.0/i)).toBeDefined();
    });

    it('should render model type badge', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      // model_type 'lstm' → toUpperCase() → 'LSTM'
      expect(screen.getByText('LSTM')).toBeDefined();
    });

    it('should render status badge', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      // status 'ready' → toUpperCase() → 'READY'
      expect(screen.getByText('READY')).toBeDefined();
    });

    it('should display accuracy metric title', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText('Accuracy')).toBeDefined();
    });

    it('should display active tag when model is active', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText('ACTIVE')).toBeDefined();
    });
  });

  describe('Status Indicators', () => {
    it('should show ready status', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'ready' }} />);
      expect(screen.getByText('READY')).toBeDefined();
    });

    it('should show training status', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'training' }} />);
      expect(screen.getByText('TRAINING')).toBeDefined();
    });

    it('should show failed status', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'failed' }} />);
      expect(screen.getByText('FAILED')).toBeDefined();
    });

    it('should show inactive status', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'inactive' }} />);
      expect(screen.getByText('INACTIVE')).toBeDefined();
    });
  });

  describe('Performance Metrics', () => {
    it('should display metric labels when available', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText('Accuracy')).toBeDefined();
      expect(screen.getByText('F1 Score')).toBeDefined();
      expect(screen.getByText('Predictions')).toBeDefined();
    });

    it('should display additional metrics when present', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/Precision/i)).toBeDefined();
      expect(screen.getByText(/Recall/i)).toBeDefined();
    });

    it('should handle missing metrics gracefully', () => {
      const modelNoMetrics = {
        ...mockModel,
        metrics: {} as ModelInfo['metrics'],
      };
      renderWithProviders(<ModelCard model={modelNoMetrics} />);
      const naElements = screen.getAllByText('N/A');
      expect(naElements.length).toBeGreaterThan(0);
    });

    it('should format accuracy as percentage', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      // formatAccuracy(0.85) → "85.00%"
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      expect(container.textContent).toContain('85.00%');
    });
  });

  describe('Feature List', () => {
    it('should display number of features', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/4 features/i)).toBeDefined();
    });

    it('should not show feature count for empty features', () => {
      const model = { ...mockModel, features: [] };
      const { container } = renderWithProviders(<ModelCard model={model} />);
      expect(container.textContent).not.toContain('0 features');
    });
  });

  describe('Training Information', () => {
    it('should display trained time', () => {
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      // dayjs('2024-01-15...').fromNow() → "X years ago" or similar
      expect(container.textContent).toContain('Trained');
    });

    it('should display training time in metrics', () => {
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      // Math.round(3600 / 60) = 60m
      expect(container.textContent).toContain('60m');
    });
  });

  describe('Actions', () => {
    it('should render action buttons', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should have clickable card', () => {
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      const card = container.querySelector('.ant-card');
      expect(card).toBeTruthy();
    });
  });

  describe('Model Types', () => {
    it('should render random_forest as RANDOM FOREST', () => {
      const rfModel = { ...mockModel, model_type: 'random_forest' as const };
      renderWithProviders(<ModelCard model={rfModel} />);
      expect(screen.getByText('RANDOM FOREST')).toBeDefined();
    });

    it('should render xgboost as XGBOOST', () => {
      const xgbModel = { ...mockModel, model_type: 'xgboost' as const };
      renderWithProviders(<ModelCard model={xgbModel} />);
      expect(screen.getByText('XGBOOST')).toBeDefined();
    });

    it('should render ensemble as ENSEMBLE', () => {
      const ensModel = { ...mockModel, model_type: 'ensemble' as const };
      renderWithProviders(<ModelCard model={ensModel} />);
      expect(screen.getByText('ENSEMBLE')).toBeDefined();
    });
  });

  describe('Responsive Design', () => {
    it('should render without errors on mobile viewport', () => {
      global.innerWidth = 375;
      global.dispatchEvent(new Event('resize'));
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      expect(container.firstChild).toBeDefined();
    });

    it('should render without errors on desktop viewport', () => {
      global.innerWidth = 1920;
      global.dispatchEvent(new Event('resize'));
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      expect(container.firstChild).toBeDefined();
    });
  });

  describe('Edge Cases', () => {
    it('should handle very long model names', () => {
      const longNameModel = {
        ...mockModel,
        name: 'Very Long Model Name That Might Cause Layout Issues',
      };
      renderWithProviders(<ModelCard model={longNameModel} />);
      expect(screen.getByText(/Very Long Model Name/i)).toBeDefined();
    });

    it('should handle inactive model without active tag', () => {
      const inactiveModel = { ...mockModel, active: false };
      renderWithProviders(<ModelCard model={inactiveModel} />);
      expect(screen.queryByText('ACTIVE')).toBeNull();
    });

    it('should handle zero prediction count', () => {
      const model = { ...mockModel, prediction_count: 0 };
      const { container } = renderWithProviders(<ModelCard model={model} />);
      expect(container.textContent).toContain('0');
    });
  });
});
