import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ModelCard from '../ModelCard';

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

const mockModel = {
  id: '1',
  name: 'LSTM Predictor',
  type: 'lstm',
  version: '1.0.0',
  status: 'active',
  accuracy: 0.85,
  precision: 0.82,
  recall: 0.88,
  f1Score: 0.85,
  createdAt: '2024-01-15T10:00:00Z',
  lastTrainedAt: '2024-01-15T10:00:00Z',
  description: 'Long Short-Term Memory model for price prediction',
  features: ['price', 'volume', 'rsi', 'macd'],
  trainingDuration: 3600,
  totalPredictions: 15000,
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
      expect(screen.getByText('LSTM')).toBeDefined();
    });

    it('should render status badge', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/active/i)).toBeDefined();
    });

    it('should display accuracy metric', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/85%/)).toBeDefined();
    });

    it('should render description', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/Long Short-Term Memory/i)).toBeDefined();
    });
  });

  describe('Status Indicators', () => {
    it('should show active status with green badge', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'active' }} />);
      const statusBadge = screen.getByText(/active/i);
      expect(statusBadge.className).toContain('success');
    });

    it('should show training status with blue badge', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'training' }} />);
      const statusBadge = screen.getByText(/training/i);
      expect(statusBadge.className).toContain('processing');
    });

    it('should show inactive status with gray badge', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'inactive' }} />);
      const statusBadge = screen.getByText(/inactive/i);
      expect(statusBadge.className).toContain('default');
    });

    it('should show failed status with red badge', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, status: 'failed' }} />);
      const statusBadge = screen.getByText(/failed/i);
      expect(statusBadge.className).toContain('error');
    });
  });

  describe('Performance Metrics', () => {
    it('should display all metrics when available', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      
      expect(screen.getByText(/Accuracy/i)).toBeDefined();
      expect(screen.getByText(/Precision/i)).toBeDefined();
      expect(screen.getByText(/Recall/i)).toBeDefined();
      expect(screen.getByText(/F1 Score/i)).toBeDefined();
    });

    it('should handle missing metrics gracefully', () => {
      const modelWithoutMetrics = {
        ...mockModel,
        accuracy: null,
        precision: null,
        recall: null,
        f1Score: null,
      };
      
      renderWithProviders(<ModelCard model={modelWithoutMetrics} />);
      expect(screen.getByText(/N\/A/i)).toBeDefined();
    });

    it('should format accuracy as percentage', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, accuracy: 0.8523 }} />);
      expect(screen.getByText(/85\.23%/)).toBeDefined();
    });
  });

  describe('Feature List', () => {
    it('should display number of features', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/4 features/i)).toBeDefined();
    });

    it('should handle empty feature list', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, features: [] }} />);
      expect(screen.getByText(/0 features/i)).toBeDefined();
    });
  });

  describe('Training Information', () => {
    it('should display creation date', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/Created:/i)).toBeDefined();
    });

    it('should display last trained date', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/Last Trained:/i)).toBeDefined();
    });

    it('should display training duration', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/1h 0m/)).toBeDefined();
    });

    it('should display total predictions', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/15,000/)).toBeDefined();
    });
  });

  describe('Actions', () => {
    it('should render action buttons', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should have View Details button', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      expect(screen.getByText(/View Details/i)).toBeDefined();
    });

    it('should have proper ARIA labels on buttons', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      const viewButton = screen.getByLabelText(/View details for/i);
      expect(viewButton).toBeDefined();
    });
  });

  describe('Accessibility', () => {
    it('should have semantic HTML structure', () => {
      const { container } = renderWithProviders(<ModelCard model={mockModel} />);
      const article = container.querySelector('article');
      expect(article).toBeDefined();
    });

    it('should have proper heading hierarchy', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      const heading = screen.getByRole('heading', { name: /LSTM Predictor/i });
      expect(heading).toBeDefined();
    });

    it('should provide text alternatives for visual indicators', () => {
      renderWithProviders(<ModelCard model={mockModel} />);
      // Status badge should have text, not just color
      const statusText = screen.getByText(/active/i);
      expect(statusText.textContent).toBeTruthy();
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
        name: 'Very Long Model Name That Might Cause Layout Issues In The UI Component',
      };
      
      renderWithProviders(<ModelCard model={longNameModel} />);
      expect(screen.getByText(/Very Long Model Name/i)).toBeDefined();
    });

    it('should handle very long descriptions', () => {
      const longDescModel = {
        ...mockModel,
        description: 'A'.repeat(500),
      };
      
      renderWithProviders(<ModelCard model={longDescModel} />);
      const { container } = renderWithProviders(<ModelCard model={longDescModel} />);
      expect(container.textContent).toContain('A');
    });

    it('should handle missing optional fields', () => {
      const minimalModel = {
        id: '1',
        name: 'Minimal Model',
        type: 'lstm',
        version: '1.0.0',
        status: 'active',
      };
      
      renderWithProviders(<ModelCard model={minimalModel} />);
      expect(screen.getByText('Minimal Model')).toBeDefined();
    });

    it('should handle extreme accuracy values', () => {
      renderWithProviders(<ModelCard model={{ ...mockModel, accuracy: 0.999999 }} />);
      expect(screen.getByText(/99\.9999%/)).toBeDefined();
    });
  });
});
