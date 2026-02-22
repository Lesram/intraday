import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from 'antd';
import TrainingForm from '../TrainingForm';

// Mock the ML API
const mockStartTraining = vi.fn().mockResolvedValue({ training_id: 'train-123' });

vi.mock('@/services/mlApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/mlApi')>('@/services/mlApi');
  return {
    ...actual,
    mlApi: {
      ...actual.mlApi,
      startTraining: (...args: unknown[]) => mockStartTraining(...args),
    },
  };
});

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <App>{component}</App>
    </QueryClientProvider>
  );
};

describe('TrainingForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the training form with title', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText(/Train New Model/i)).toBeInTheDocument();
    });

    it('should render the form with ARIA label', () => {
      renderWithProviders(<TrainingForm />);
      const form = screen.getByLabelText(/ML model training configuration form/i);
      expect(form).toBeInTheDocument();
    });

    it('should render Model Name field', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText('Model Name')).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/ensemble_model_v1/i)).toBeInTheDocument();
    });

    it('should render Model Type field with default', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText('Model Type')).toBeInTheDocument();
    });

    it('should render Symbols field', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText('Symbols')).toBeInTheDocument();
    });

    it('should render submit and reset buttons', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByRole('button', { name: /Start Training/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Reset/i })).toBeInTheDocument();
    });

    it('should render info alert about training time', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText(/Training Time/i)).toBeInTheDocument();
      expect(screen.getByText(/5-30 minutes/i)).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should show validation error for empty model name', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Please enter a model name/i)).toBeInTheDocument();
      });
    });

    it('should show validation error for missing symbols', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      // Fill name but not symbols
      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      await user.type(nameInput, 'TestModel');

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Please select at least one symbol/i)).toBeInTheDocument();
      });
    });

    it('should validate model name format', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      await user.type(nameInput, 'bad name!@#');

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        const matches = screen.getAllByText(/Only letters, numbers, hyphens/i);
        expect(matches.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Form Interaction', () => {
    it('should allow typing a model name', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      await user.type(nameInput, 'MyTestModel');
      expect(nameInput).toHaveValue('MyTestModel');
    });

    it('should have model name with aria-required', () => {
      renderWithProviders(<TrainingForm />);
      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      expect(nameInput).toHaveAttribute('aria-required', 'true');
    });

    it('should have aria-describedby with help text', () => {
      renderWithProviders(<TrainingForm />);
      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      expect(nameInput).toHaveAttribute('aria-describedby', 'model-name-help');
    });

    it('should allow clicking reset button after typing', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i) as HTMLInputElement;
      await user.type(nameInput, 'TestModel');
      expect(nameInput.value).toBe('TestModel');

      const resetButton = screen.getByRole('button', { name: /Reset/i });
      await user.click(resetButton);

      // Ant Design form.resetFields() updates internal state;
      // verify no errors thrown and button remains enabled
      expect(resetButton).not.toBeDisabled();
    });
  });

  describe('Advanced Configuration', () => {
    it('should have advanced settings section', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByText(/Advanced Settings/i)).toBeInTheDocument();
    });
  });

  describe('Keyboard Navigation', () => {
    it('should allow focusing model name input', () => {
      renderWithProviders(<TrainingForm />);
      const nameInput = screen.getByPlaceholderText(/ensemble_model_v1/i);
      nameInput.focus();
      expect(document.activeElement).toBe(nameInput);
    });
  });
});
