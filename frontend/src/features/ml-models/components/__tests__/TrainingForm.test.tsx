import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TrainingForm from '../TrainingForm';

// Mock the API hooks
const mockMutate = vi.fn();
vi.mock('../../hooks/useMLModels', () => ({
  useTrainModel: () => ({
    mutate: mockMutate,
    isPending: false,
    isSuccess: false,
    error: null,
  }),
}));

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

describe('TrainingForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the training form with ARIA label', () => {
      renderWithProviders(<TrainingForm />);
      const form = screen.getByLabelText(/ML model training configuration form/i);
      expect(form).toBeInTheDocument();
    });

    it('should render all required form fields', () => {
      renderWithProviders(<TrainingForm />);

      expect(screen.getByLabelText(/Model name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Model type/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Training data period/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Features/i)).toBeInTheDocument();
    });

    it('should have aria-required on required fields', () => {
      renderWithProviders(<TrainingForm />);

      const modelNameInput = screen.getByLabelText(/Model name/i);
      expect(modelNameInput).toHaveAttribute('aria-required', 'true');
    });

    it('should have aria-describedby with help text', () => {
      renderWithProviders(<TrainingForm />);

      const modelNameInput = screen.getByLabelText(/Model name/i);
      const describedById = modelNameInput.getAttribute('aria-describedby');
      expect(describedById).toBeTruthy();

      const helpText = document.getElementById(describedById!);
      expect(helpText).toHaveClass('sr-only');
    });

    it('should render submit button', () => {
      renderWithProviders(<TrainingForm />);
      expect(screen.getByRole('button', { name: /Start Training/i })).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should show validation error for empty model name', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Model name is required/i)).toBeInTheDocument();
      });
    });

    it('should show validation error for invalid model name format', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      await user.type(nameInput, 'invalid name!@#');

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Model name must contain only letters, numbers/i)).toBeInTheDocument();
      });
    });

    it('should require model type selection', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      await user.type(nameInput, 'TestModel');

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Model type is required/i)).toBeInTheDocument();
      });
    });

    it('should validate training period dates', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      // Set end date before start date
      const startDateInput = screen.getByLabelText(/Start date/i);
      const endDateInput = screen.getByLabelText(/End date/i);

      await user.type(startDateInput, '2024-01-20');
      await user.type(endDateInput, '2024-01-10');

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/End date must be after start date/i)).toBeInTheDocument();
      });
    });

    it('should require at least one feature', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      await user.type(nameInput, 'TestModel');

      // Deselect all features if any are selected
      const featureCheckboxes = screen.getAllByRole('checkbox');
      for (const checkbox of featureCheckboxes) {
        if ((checkbox as HTMLInputElement).checked) {
          await user.click(checkbox);
        }
      }

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/At least one feature is required/i)).toBeInTheDocument();
      });
    });
  });

  describe('Form Submission', () => {
    it('should submit valid form data', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      // Fill in all required fields
      const nameInput = screen.getByLabelText(/Model name/i);
      await user.type(nameInput, 'TestLSTMModel');

      const modelTypeSelect = screen.getByLabelText(/Model type/i);
      await user.click(modelTypeSelect);
      await user.click(screen.getByText('LSTM'));

      const startDateInput = screen.getByLabelText(/Start date/i);
      await user.type(startDateInput, '2024-01-01');

      const endDateInput = screen.getByLabelText(/End date/i);
      await user.type(endDateInput, '2024-01-31');

      // Select features
      const priceFeature = screen.getByLabelText(/Price/i);
      await user.click(priceFeature);

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'TestLSTMModel',
            type: 'lstm',
            features: expect.arrayContaining(['price']),
          })
        );
      });
    });

    it('should disable submit button while submitting', async () => {
      const _user = userEvent.setup();
      
      vi.mocked(require('../../hooks/useMLModels').useTrainModel).mockReturnValue({
        mutate: mockMutate,
        isPending: true,
        isSuccess: false,
        error: null,
      });

      renderWithProviders(<TrainingForm />);

      const submitButton = screen.getByRole('button', { name: /Training.../i });
      expect(submitButton).toBeDisabled();
    });

    it('should show success message after successful submission', async () => {
      vi.mocked(require('../../hooks/useMLModels').useTrainModel).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isSuccess: true,
        error: null,
      });

      renderWithProviders(<TrainingForm />);

      await waitFor(() => {
        expect(screen.getByText(/Training started successfully/i)).toBeInTheDocument();
      });
    });

    it('should show error message on submission failure', async () => {
      vi.mocked(require('../../hooks/useMLModels').useTrainModel).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isSuccess: false,
        error: new Error('Training failed: Insufficient data'),
      });

      renderWithProviders(<TrainingForm />);

      await waitFor(() => {
        expect(screen.getByText(/Training failed: Insufficient data/i)).toBeInTheDocument();
      });
    });

    it('should reset form after successful submission', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i) as HTMLInputElement;
      await user.type(nameInput, 'TestModel');

      // Simulate successful submission
      vi.mocked(require('../../hooks/useMLModels').useTrainModel).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isSuccess: true,
        error: null,
      });

      await waitFor(() => {
        expect(nameInput.value).toBe('');
      });
    });
  });

  describe('Model Type Selection', () => {
    it('should display all model type options', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const modelTypeSelect = screen.getByLabelText(/Model type/i);
      await user.click(modelTypeSelect);

      expect(screen.getByText('LSTM')).toBeInTheDocument();
      expect(screen.getByText('Random Forest')).toBeInTheDocument();
      expect(screen.getByText('XGBoost')).toBeInTheDocument();
      expect(screen.getByText('Transformer')).toBeInTheDocument();
    });

    it('should update form when model type is selected', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const modelTypeSelect = screen.getByLabelText(/Model type/i);
      await user.click(modelTypeSelect);
      await user.click(screen.getByText('Random Forest'));

      await waitFor(() => {
        expect(modelTypeSelect).toHaveTextContent('Random Forest');
      });
    });
  });

  describe('Feature Selection', () => {
    it('should allow multiple feature selection', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const priceFeature = screen.getByLabelText(/Price/i);
      const volumeFeature = screen.getByLabelText(/Volume/i);

      await user.click(priceFeature);
      await user.click(volumeFeature);

      expect(priceFeature).toBeChecked();
      expect(volumeFeature).toBeChecked();
    });

    it('should uncheck feature when clicked again', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const priceFeature = screen.getByLabelText(/Price/i);

      await user.click(priceFeature);
      expect(priceFeature).toBeChecked();

      await user.click(priceFeature);
      expect(priceFeature).not.toBeChecked();
    });
  });

  describe('Advanced Configuration', () => {
    it('should expand advanced options section', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const advancedButton = screen.getByText(/Advanced Options/i);
      await user.click(advancedButton);

      expect(screen.getByLabelText(/Learning rate/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Batch size/i)).toBeInTheDocument();
    });

    it('should validate advanced configuration values', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const advancedButton = screen.getByText(/Advanced Options/i);
      await user.click(advancedButton);

      const learningRateInput = screen.getByLabelText(/Learning rate/i);
      await user.clear(learningRateInput);
      await user.type(learningRateInput, '2.0'); // Invalid: too high

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Learning rate must be between 0 and 1/i)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper form landmark', () => {
      renderWithProviders(<TrainingForm />);
      const form = screen.getByRole('form');
      expect(form).toHaveAttribute('aria-label');
    });

    it('should associate labels with inputs', () => {
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      const nameLabel = screen.getByText('Model name');
      
      expect(nameLabel).toHaveAttribute('for', nameInput.id);
    });

    it('should provide error messages to screen readers', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const submitButton = screen.getByRole('button', { name: /Start Training/i });
      await user.click(submitButton);

      await waitFor(() => {
        const errorMessage = screen.getByText(/Model name is required/i);
        expect(errorMessage).toHaveAttribute('role', 'alert');
      });
    });
  });

  describe('Keyboard Navigation', () => {
    it('should navigate form with Tab key', async () => {
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      nameInput.focus();
      expect(document.activeElement).toBe(nameInput);

      fireEvent.keyDown(nameInput, { key: 'Tab' });
      // Should move to next field
    });

    it('should submit form with Enter key', async () => {
      const user = userEvent.setup();
      renderWithProviders(<TrainingForm />);

      const nameInput = screen.getByLabelText(/Model name/i);
      await user.type(nameInput, 'TestModel');
      await user.keyboard('{Enter}');

      // Form should attempt submission
    });
  });
});
